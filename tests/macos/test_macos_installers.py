import os
from pathlib import Path
import subprocess
import shutil
import sys

import pytest


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, capture_output=True)
    if check and result.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(f"Command failed ({result.returncode}): {joined}\n{result.stdout}\n{result.stderr}")
    return result


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
