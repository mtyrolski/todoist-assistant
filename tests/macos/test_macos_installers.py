import os
import socket
import subprocess
import sys
import shutil
import time
from pathlib import Path

import pytest
import requests


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, capture_output=True)
    if check and result.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(f"Command failed ({result.returncode}): {joined}\n{result.stdout}\n{result.stderr}")
    return result


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_frontend(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, timeout=2)
        except requests.RequestException:
            resp = None
        if resp is not None and resp.status_code == 200:
            return
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url} to respond")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only test")
def test_pkg_install_smoke() -> None:
    pkg_path = os.environ.get("TODOIST_PKG_PATH")
    if not pkg_path:
        pytest.skip("TODOIST_PKG_PATH not set")

    pkg = Path(pkg_path)
    if not pkg.exists():
        raise AssertionError(f"pkg not found at {pkg}")

    _run(["sudo", "-n", "installer", "-pkg", str(pkg), "-target", "/"])

    binary = Path("/usr/local/todoist-assistant/todoist-assistant")
    shim = Path("/usr/local/bin/todoist-assistant")
    config_template = Path("/usr/local/etc/todoist-assistant/.env.template")

    assert binary.exists(), f"Missing CLI binary at {binary}"
    assert shim.exists(), f"Missing shim at {shim}"
    assert config_template.exists(), f"Missing config template at {config_template}"

    _run([str(shim), "--help"])

    _run(["sudo", "-n", "rm", "-rf", "/usr/local/todoist-assistant"])
    _run(["sudo", "-n", "rm", "-f", "/usr/local/bin/todoist-assistant"])
    _run(["sudo", "-n", "rm", "-rf", "/usr/local/etc/todoist-assistant"])

    assert not binary.exists(), "CLI bundle still present after removal"
    assert not shim.exists(), "Shim still present after removal"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only test")
def test_pkg_frontend_host(tmp_path: Path) -> None:
    pkg_path = os.environ.get("TODOIST_PKG_PATH")
    if not pkg_path:
        pytest.skip("TODOIST_PKG_PATH not set")

    pkg = Path(pkg_path)
    if not pkg.exists():
        raise AssertionError(f"pkg not found at {pkg}")

    _run(["sudo", "-n", "installer", "-pkg", str(pkg), "-target", "/"])

    shim = Path("/usr/local/bin/todoist-assistant")
    if not shim.exists():
        raise AssertionError(f"shim not found at {shim}")

    data_dir = tmp_path / "todoist-data"
    config_dir = tmp_path / "todoist-config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    frontend_port = _reserve_port()
    api_port = _reserve_port()
    cmd = [
        str(shim),
        "--no-browser",
        "--frontend-port",
        str(frontend_port),
        "--api-port",
        str(api_port),
        "--data-dir",
        str(data_dir),
        "--config-dir",
        str(config_dir),
    ]
    env = os.environ.copy()
    env["TODOIST_DATA_DIR"] = str(data_dir)
    env["TODOIST_CONFIG_DIR"] = str(config_dir)

    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"

    with open(stdout_path, "w") as out_f, open(stderr_path, "w") as err_f:
        proc = subprocess.Popen(cmd, env=env, stdout=out_f, stderr=err_f)
    
        try:
            frontend_url = f"http://127.0.0.1:{frontend_port}"
            # Increased timeout for CI runners which can be slow
            _wait_for_frontend(frontend_url, timeout=60.0)
            resp = requests.get(frontend_url, timeout=5)
            assert resp.status_code == 200, f"Unexpected HTTP {resp.status_code}"
        except Exception:
            # Dump logs on failure
            if stdout_path.exists():
                print(f"\n=== STDOUT ===\n{stdout_path.read_text()}\n==============")
            if stderr_path.exists():
                print(f"\n=== STDERR ===\n{stderr_path.read_text()}\n==============")
            raise
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    _run(["sudo", "-n", "rm", "-rf", "/usr/local/todoist-assistant"])
    _run(["sudo", "-n", "rm", "-f", "/usr/local/bin/todoist-assistant"])
    _run(["sudo", "-n", "rm", "-rf", "/usr/local/etc/todoist-assistant"])

    assert not Path("/usr/local/bin/todoist-assistant").exists()

@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only test")
def test_brew_install_smoke() -> None:
    if shutil.which("brew") is None:
        pytest.skip("Homebrew not available on this runner")

    formula = os.environ.get("TODOIST_BREW_FORMULA", "Formula/todoist-assistant.rb")
    if not Path(formula).exists():
        pytest.skip("Homebrew formula not available in this checkout")

    tarball = os.environ.get("TODOIST_BREW_TARBALL")
    if tarball and not Path(tarball).exists():
        raise AssertionError(f"TODOIST_BREW_TARBALL not found at {tarball}")

    os.environ.setdefault("HOMEBREW_NO_AUTO_UPDATE", "1")

    _run(["brew", "install", "--build-from-source", formula])
    _run(["todoist-assistant", "--help"])
    _run(["brew", "uninstall", "--force", "todoist-assistant"])
