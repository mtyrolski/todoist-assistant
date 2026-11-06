import os
import plistlib
import socket
import subprocess
import sys
import shutil
import time
from pathlib import Path

import pytest
import requests

from todoist.core.env import EnvVar
from todoist.core.version import get_version


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, capture_output=True)
    if check and result.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(
            f"Command failed ({result.returncode}): {joined}\n{result.stdout}\n{result.stderr}"
        )
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
    pkg_path = os.environ.get(EnvVar.PKG_PATH)
    if not pkg_path:
        pytest.skip(f"{EnvVar.PKG_PATH} not set")

    pkg = Path(pkg_path)
    if not pkg.exists():
        raise AssertionError(f"pkg not found at {pkg}")

    binary = Path("/usr/local/todoist-assistant/todoist-assistant")
    shim = Path("/usr/local/bin/todoist-assistant")
    config_dir = Path("/usr/local/etc/todoist-assistant")
    for existing in (binary.parent, shim, config_dir):
        if existing.exists():
            pytest.fail(
                f"Package smoke test requires a clean runner; already exists: {existing}"
            )
    config_template = config_dir / ".env.template"
    _run(["sudo", "-n", "installer", "-pkg", str(pkg), "-target", "/"])

    assert binary.exists(), f"Missing CLI binary at {binary}"
    assert shim.exists(), f"Missing shim at {shim}"
    assert config_template.exists(), f"Missing config template at {config_template}"

    _run([str(shim), "--help"])
    assert _run([str(shim), "--version"]).stdout.strip() == get_version()

    _run(["sudo", "-n", "rm", "-rf", "/usr/local/todoist-assistant"])
    _run(["sudo", "-n", "rm", "-f", "/usr/local/bin/todoist-assistant"])
    _run(["sudo", "-n", "rm", "-rf", "/usr/local/etc/todoist-assistant"])

    assert not binary.exists(), "CLI bundle still present after removal"
    assert not shim.exists(), "Shim still present after removal"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only test")
def test_app_frontend_host(tmp_path: Path) -> None:
    app_value = os.environ.get("TODOIST_APP_PATH")
    if not app_value:
        pytest.skip("TODOIST_APP_PATH not set")
    app = Path(app_value)
    executable = app / "Contents" / "MacOS" / "TodoistAssistant"
    assert executable.is_file(), f"Missing app executable: {executable}"
    with (app / "Contents" / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert info["CFBundleDisplayName"] == "Telemetry for Todoist"
    assert info["CFBundleIdentifier"] == "com.todoist.assistant"
    assert info["CFBundleShortVersionString"] == get_version()
    assert info["CFBundleVersion"] == get_version()

    data_dir = tmp_path / "todoist-data"
    config_dir = tmp_path / "todoist-config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    frontend_port = _reserve_port()
    api_port = _reserve_port()
    cmd = [
        str(executable),
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
    env[EnvVar.DATA_DIR] = str(data_dir)
    env[EnvVar.CONFIG_DIR] = str(config_dir)

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
            health_url = f"http://127.0.0.1:{api_port}/api/health"
            _wait_for_frontend(health_url, timeout=60.0)
            assert (
                requests.get(health_url, timeout=5).json()["version"] == get_version()
            )
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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only test")
def test_brew_install_smoke() -> None:
    if shutil.which("brew") is None:
        pytest.skip("Homebrew not available on this runner")

    formula = os.environ.get(EnvVar.BREW_FORMULA)
    if not formula:
        pytest.skip(f"{EnvVar.BREW_FORMULA} not set")
    if _run(
        ["brew", "list", "--versions", "todoist-assistant"], check=False
    ).stdout.strip():
        pytest.fail(
            "Homebrew smoke test requires a runner without the existing formula"
        )
    if not Path(formula).exists():
        pytest.skip("Homebrew formula not available in this checkout")

    tarball = os.environ.get(EnvVar.BREW_TARBALL)
    if tarball and not Path(tarball).exists():
        raise AssertionError(f"{EnvVar.BREW_TARBALL} not found at {tarball}")

    os.environ.setdefault("HOMEBREW_NO_AUTO_UPDATE", "1")

    _run(["brew", "install", "--build-from-source", formula])
    _run(["todoist-assistant", "--help"])
    assert _run(["todoist-assistant", "--version"]).stdout.strip() == get_version()
    _run(["brew", "uninstall", "--force", "todoist-assistant"])
