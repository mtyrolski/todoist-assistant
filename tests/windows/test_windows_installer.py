import os
import sys
import subprocess
from pathlib import Path
import tempfile

import pytest


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
            f"TARGETDIR={temp_dir}",
        ])

        extracted_root = Path(temp_dir)
        exe_path = _find_required(extracted_root, "todoist-assistant.exe")
        app_root = exe_path.parent

        _find_required(extracted_root, ".env.template")
        _find_required(extracted_root, "automations.yaml")

        has_python = (app_root / "base_library.zip").exists() or any(app_root.glob("*.pyd")) or any(app_root.glob("python*.dll"))
        assert has_python, "Expected bundled Python runtime artifacts in installer payload"

        if expected_dashboard:
            server_js = app_root / "frontend" / "server.js"
            assert server_js.exists(), "Dashboard server.js missing from packaged frontend"
            static_dir = app_root / "frontend" / ".next" / "static"
            public_dir = app_root / "frontend" / "public"
            assert static_dir.exists() or public_dir.exists(), "Dashboard assets missing (.next/static or public)"


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
    if result.returncode != 0:
        details = result.stdout.strip() or result.stderr.strip()
        raise AssertionError(f"msiexec failed ({result.returncode}): {details}")


def _find_required(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if not matches:
        raise AssertionError(f"Required file missing from MSI payload: {filename}")
    return matches[0]
