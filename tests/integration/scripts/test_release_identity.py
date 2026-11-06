from pathlib import Path

from scripts.check_release_identity import identity_errors


def test_release_guard_rejects_old_identity(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "todoist-assistant"\nversion = "0.4.1"\n',
        encoding="utf-8",
    )
    errors = identity_errors(tmp_path)
    assert len(errors) == 3
    assert any("distribution" in error for error in errors)
    assert any("package" in error for error in errors)
    assert any("entry point" in error for error in errors)


def test_release_guard_accepts_matching_identity(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "telemetry-for-todoist"\nversion = "0.4.1"\n'
        '[project.scripts]\ntodoist-telemetry = "todometry.cli:app"\n',
        encoding="utf-8",
    )
    package = tmp_path / "todometry"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    assert identity_errors(tmp_path) == []


def test_release_guard_rejects_wrong_version_and_entry_point(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "telemetry-for-todoist"\nversion = "0.4.0"\n'
        '[project.scripts]\ntodoist-telemetry = "todoist.cli:app"\n',
        encoding="utf-8",
    )
    package = tmp_path / "todometry"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    errors = identity_errors(tmp_path)
    assert any("version" in error for error in errors)
    assert any("entry point" in error for error in errors)
