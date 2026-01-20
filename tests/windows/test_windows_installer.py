import os
import sys
import subprocess
from pathlib import Path
import tempfile
import zipfile

import pytest

_ALLOWED_MSIEXEC_CODES = {0, 3010, 1641}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only installer test")
def test_windows_msi_contents() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    msi_path = _resolve_msi_path(repo_root)

    expected_dashboard = os.getenv("TODOIST_EXPECT_DASHBOARD", "").strip().lower() in {"1", "true", "yes"}

    with tempfile.TemporaryDirectory() as temp_dir:
        _run_msiexec([
            "msiexec",
            "/a",
            str(msi_path),
            "/qn",
            "/norestart",
            f"TARGETDIR={temp_dir}",
        ])

        extracted_root = Path(temp_dir)
        exe_path = _find_required(extracted_root, "todoist-assistant.exe")
        app_root = exe_path.parent

        _find_required(extracted_root, ".env.template")
        _find_required(extracted_root, "automations.yaml")

        has_python = _has_python_runtime(app_root)
        assert has_python, "Expected bundled Python runtime artifacts in installer payload"

        if expected_dashboard:
            frontend_zip = app_root / "frontend.zip"
            if frontend_zip.exists():
                with zipfile.ZipFile(frontend_zip, "r") as archive:
                    names = set(archive.namelist())
                has_server = "server.js" in names
                has_assets = any(
                    name.startswith(".next/static/") or name.startswith("public/")
                    for name in names
                )
                assert has_server, "Dashboard server.js missing from frontend.zip"
                assert has_assets, "Dashboard assets missing from frontend.zip (.next/static or public)"
            else:
                server_candidates = [
                    app_root / "server.js",
                    app_root / "frontend" / "server.js",
                ]
                server_js = next((path for path in server_candidates if path.exists()), None)
                assert server_js is not None, "Dashboard server.js missing from packaged frontend"
                static_candidates = [
                    app_root / ".next" / "static",
                    app_root / "frontend" / ".next" / "static",
                ]
                public_candidates = [
                    app_root / "public",
                    app_root / "frontend" / "public",
                ]
                has_assets = any(path.exists() for path in static_candidates + public_candidates)
                assert has_assets, "Dashboard assets missing (.next/static or public)"


def _resolve_msi_path(repo_root: Path) -> Path:
    env_path = os.getenv("TODOIST_MSI_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
        raise AssertionError(f"MSI not found at TODOIST_MSI_PATH={env_path}")

    candidates = sorted((repo_root / "dist" / "windows").glob("todoist-assistant-*.msi"))
    if not candidates:
        raise AssertionError("MSI not found. Build with: uv run python3 -m scripts.build_windows")
    return candidates[-1]


def _run_msiexec(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in _ALLOWED_MSIEXEC_CODES:
        details = result.stdout.strip() or result.stderr.strip()
        raise AssertionError(f"msiexec failed ({result.returncode}): {details}")


def _find_required(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if not matches:
        raise AssertionError(f"Required file missing from MSI payload: {filename}")
    return matches[0]


def _has_python_runtime(app_root: Path) -> bool:
    candidates = [app_root, app_root / "_internal"]
    for root in candidates:
        if (root / "base_library.zip").exists():
            return True
        if any(root.glob("*.pyd")):
            return True
        if any(root.glob("python*.dll")):
            return True
    return False
