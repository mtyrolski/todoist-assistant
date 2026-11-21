import os
import errno
import sys
import subprocess
from pathlib import Path
import tempfile
import zipfile
import shutil

import pytest

from todometry.core.env import EnvVar

_ALLOWED_MSIEXEC_CODES = {0, 3010, 1641}


def test_windows_installer_data_directory_matches_launcher():
    import xml.etree.ElementTree as etree

    root = Path(__file__).resolve().parents[2]
    directories = etree.parse(root / "windows/installer/components.wxs").findall(
        ".//{*}Directory[@Id='APPDATADIR']"
    )
    assert len(directories) == 1
    assert directories[0].get("Name") == "Todometry"


@pytest.mark.parametrize("existing", [None, "urgency:\n  enabled: false\n"])
def test_windows_staged_defaults_preserve_migrated_and_existing_settings(
    tmp_path, monkeypatch, existing
):
    from scripts.build_windows import _stage_assets
    from todometry.core.utils import migrate_legacy_files
    from todometry.launcher import _ensure_env_and_files

    repo_root = Path(__file__).resolve().parents[2]
    app_root = tmp_path / "installed-app"
    installer_config = tmp_path / "installer-config"
    _stage_assets(
        repo_root, app_root, installer_config, include_dashboard=False, node_version=""
    )
    bundled = app_root / "configs" / "dashboard.yaml"
    assert (
        bundled.read_bytes() == (repo_root / "configs" / "dashboard.yaml").read_bytes()
    )
    assert not (installer_config / "dashboard.yaml").exists()

    legacy, target = tmp_path / "TodoistAssistant", tmp_path / "Todometry"
    (legacy / "config").mkdir(parents=True)
    legacy_dashboard = legacy / "config" / "dashboard.yaml"
    legacy_dashboard.write_text("urgency:\n  enabled: true\n", encoding="utf-8")
    shutil.copytree(installer_config, target / "config")
    if existing is not None:
        (target / "config" / "dashboard.yaml").write_text(existing, encoding="utf-8")

    # The launcher migrates old state before adding any missing defaults.
    migrate_legacy_files(legacy, target, ("config",))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    for name in (
        EnvVar.CONFIG_DIR,
        EnvVar.CACHE_DIR,
        EnvVar.DATA_DIR,
        EnvVar.LOGS_DIR,
        EnvVar.PERSONAL_DIR,
    ):
        monkeypatch.delenv(str(name), raising=False)
    _ensure_env_and_files(target, target / "config", app_root)
    dashboard = target / "config" / "dashboard.yaml"
    assert dashboard.read_text(encoding="utf-8") == (
        existing or legacy_dashboard.read_text(encoding="utf-8")
    )
    assert legacy_dashboard.read_text(encoding="utf-8") == "urgency:\n  enabled: true\n"
    assert (target / ".v040-migration-complete").exists()
    _ensure_env_and_files(target, target / "config", app_root)
    assert dashboard.read_text(encoding="utf-8") == (
        existing or legacy_dashboard.read_text(encoding="utf-8")
    )


def test_windows_clean_install_seeds_missing_defaults_without_overwriting(
    tmp_path, monkeypatch
):
    from scripts.build_windows import _stage_assets
    from todometry.launcher import _ensure_env_and_files

    repo_root = Path(__file__).resolve().parents[2]
    app_root, target = tmp_path / "app", tmp_path / "Todometry"
    _stage_assets(
        repo_root, app_root, target / "config", include_dashboard=False, node_version=""
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    for name in (
        EnvVar.CONFIG_DIR,
        EnvVar.CACHE_DIR,
        EnvVar.DATA_DIR,
        EnvVar.LOGS_DIR,
        EnvVar.PERSONAL_DIR,
    ):
        monkeypatch.delenv(str(name), raising=False)
    _ensure_env_and_files(target, target / "config", app_root)
    assert (target / "config" / "dashboard.yaml").read_bytes() == (
        app_root / "configs" / "dashboard.yaml"
    ).read_bytes()


@pytest.mark.parametrize("race", [False, True])
def test_seed_defaults_without_hardlinks_preserves_concurrent_file(
    tmp_path, monkeypatch, race
):
    from todometry.launcher import _seed_config_dir

    app_root, config = tmp_path / "app", tmp_path / "config"
    (app_root / "configs").mkdir(parents=True)
    (app_root / "configs" / "dashboard.yaml").write_text("default", encoding="utf-8")
    config.mkdir()
    destination = config / "dashboard.yaml"

    def unsupported(_source, _target):
        if race:
            destination.write_text("user settings", encoding="utf-8")
        raise OSError(errno.EOPNOTSUPP, "hard links unavailable")

    monkeypatch.setattr(os, "link", unsupported)
    _seed_config_dir(config, app_root)
    assert destination.read_text(encoding="utf-8") == (
        "user settings" if race else "default"
    )
    assert not list(config.glob(".config-*"))


def test_seed_defaults_reports_fallback_write_failure_and_cleans_partial_file(
    tmp_path, monkeypatch
):
    from todometry.launcher import _seed_config_dir

    app_root, config = tmp_path / "app", tmp_path / "config"
    (app_root / "configs").mkdir(parents=True)
    (app_root / "configs" / "dashboard.yaml").write_text("default", encoding="utf-8")
    config.mkdir()

    def unsupported(_source, _target):
        def fail_copy(_source, output):
            output.write(b"partial")
            raise OSError(errno.ENOSPC, "disk full")

        monkeypatch.setattr(shutil, "copyfileobj", fail_copy)
        raise OSError(errno.EOPNOTSUPP, "hard links unavailable")

    monkeypatch.setattr(os, "link", unsupported)
    with pytest.raises(OSError, match="disk full"):
        _seed_config_dir(config, app_root)
    assert not (config / "dashboard.yaml").exists()
    assert not list(config.glob(".config-*"))


def test_completed_migration_keeps_ambiguous_existing_dashboard(tmp_path, monkeypatch):
    from scripts.build_windows import _stage_assets
    from todometry.core.utils import migrate_legacy_files
    from todometry.launcher import _ensure_env_and_files

    repo_root = Path(__file__).resolve().parents[2]
    app_root, target = tmp_path / "app", tmp_path / "Todometry"
    legacy = tmp_path / "TodoistAssistant"
    _stage_assets(
        repo_root, app_root, target / "config", include_dashboard=False, node_version=""
    )
    (legacy / "config").mkdir(parents=True)
    old_dashboard = legacy / "config" / "dashboard.yaml"
    old_dashboard.write_text("urgency:\n  enabled: true\n", encoding="utf-8")
    dashboard = target / "config" / "dashboard.yaml"
    shutil.copyfile(app_root / "configs" / "dashboard.yaml", dashboard)
    (target / ".v040-migration-complete").touch()
    original = dashboard.read_bytes()

    migrate_legacy_files(legacy, target, ("config",))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    for name in (
        EnvVar.CONFIG_DIR,
        EnvVar.CACHE_DIR,
        EnvVar.DATA_DIR,
        EnvVar.LOGS_DIR,
        EnvVar.PERSONAL_DIR,
    ):
        monkeypatch.delenv(str(name), raising=False)
    _ensure_env_and_files(target, target / "config", app_root)
    assert dashboard.read_bytes() == original
    assert old_dashboard.read_text(encoding="utf-8") == "urgency:\n  enabled: true\n"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only installer test")
def test_windows_msi_contents() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    msi_path = _resolve_msi_path(repo_root)

    expected_dashboard = os.getenv(
        str(EnvVar.EXPECT_DASHBOARD), ""
    ).strip().lower() in {"1", "true", "yes"}

    with tempfile.TemporaryDirectory() as temp_dir:
        _run_msiexec(
            [
                "msiexec",
                "/a",
                str(msi_path),
                "/qn",
                "/norestart",
                f"TARGETDIR={temp_dir}",
            ]
        )

        extracted_root = Path(temp_dir)
        exe_path = _find_required(extracted_root, "todometry.exe")
        app_root = exe_path.parent

        _find_required(extracted_root, ".env.template")
        assert (app_root / "configs" / "dashboard.yaml").is_file()
        assert list(extracted_root.rglob("dashboard.yaml")) == [
            app_root / "configs" / "dashboard.yaml"
        ]

        has_python = _has_python_runtime(app_root)
        assert has_python, (
            "Expected bundled Python runtime artifacts in installer payload"
        )

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
                assert has_assets, (
                    "Dashboard assets missing from frontend.zip (.next/static or public)"
                )
            else:
                server_candidates = [
                    app_root / "server.js",
                    app_root / "frontend" / "server.js",
                ]
                server_js = next(
                    (path for path in server_candidates if path.exists()), None
                )
                assert server_js is not None, (
                    "Dashboard server.js missing from packaged frontend"
                )
                static_candidates = [
                    app_root / ".next" / "static",
                    app_root / "frontend" / ".next" / "static",
                ]
                public_candidates = [
                    app_root / "public",
                    app_root / "frontend" / "public",
                ]
                has_assets = any(
                    path.exists() for path in static_candidates + public_candidates
                )
                assert has_assets, "Dashboard assets missing (.next/static or public)"


def _resolve_msi_path(repo_root: Path) -> Path:
    env_path = os.getenv(str(EnvVar.MSI_PATH))
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
        raise AssertionError(f"MSI not found at {EnvVar.MSI_PATH}={env_path}")

    candidates = sorted((repo_root / "dist" / "windows").glob("todometry-*.msi"))
    if not candidates:
        pytest.skip(
            "MSI not found. Build with: uv run python3 -m scripts.build_windows"
        )
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
