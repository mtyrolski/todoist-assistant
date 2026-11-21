from pathlib import Path

from scripts.check_release_identity import NOT_FOUND_SHA256, identity_errors


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
        '[project]\nname = "todometry"\nversion = "0.4.1"\n'
        '[project.scripts]\ntodometry = "todometry.cli:app"\n',
        encoding="utf-8",
    )
    package = tmp_path / "todometry"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    assert identity_errors(tmp_path) == []


def test_release_guard_rejects_wrong_version_and_entry_point(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "todometry"\nversion = "0.4.0"\n'
        '[project.scripts]\ntodometry = "todoist.cli:app"\n',
        encoding="utf-8",
    )
    package = tmp_path / "todometry"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    errors = identity_errors(tmp_path)
    assert any("version" in error for error in errors)
    assert any("entry point" in error for error in errors)


def test_release_guard_rejects_web_injection_and_type_erasure(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "todometry"\nversion = "0.4.1"\n'
        '[project.scripts]\ntodometry = "todometry.cli:app"\n'
        '[tool.ruff.lint.per-file-ignores]\n"todometry/web/routes/*.py" = ["F821"]\n',
        encoding="utf-8",
    )
    web = tmp_path / "todometry" / "web"
    web.mkdir(parents=True)
    (web.parent / "__init__.py").write_text("", encoding="utf-8")
    (web / "route.py").write_text(
        "# pyright: reportUndefinedVariable=false\nglobals().update({})\n",
        encoding="utf-8",
    )
    (web / "api.pyi").write_text(
        "from typing import Any\ndef __getattr__(name: str) -> Any: ...\n",
        encoding="utf-8",
    )
    errors = identity_errors(tmp_path)
    assert any("injection" in error for error in errors)
    assert any("catch-all" in error for error in errors)
    assert any("undefined-name" in error for error in errors)
    assert any("suppression" in error for error in errors)


def test_release_guard_rejects_404_hash_and_does_not_use_resource_hash(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "todometry"\nversion = "0.4.1"\n'
        '[project.scripts]\ntodometry = "todometry.cli:app"\n',
        encoding="utf-8",
    )
    package = tmp_path / "todometry"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    formula = tmp_path / "Formula" / "todometry.rb"
    formula.parent.mkdir()
    formula.write_text(
        f'  sha256 "{NOT_FOUND_SHA256}"\n'
        '  resource "example" do\n    sha256 "' + "a" * 64 + '"\n  end\n',
        encoding="utf-8",
    )
    assert any("Homebrew" in error for error in identity_errors(tmp_path))
    formula.write_text(
        '  resource "example" do\n    sha256 "' + "a" * 64 + '"\n  end\n',
        encoding="utf-8",
    )
    assert any("Homebrew" in error for error in identity_errors(tmp_path))
    # A plausible digest passes the static guard; its authenticity must still be
    # verified against the actual public release archive before publication.
    formula.write_text('  sha256 "' + "a" * 64 + '"\n', encoding="utf-8")
    assert not any("Homebrew" in error for error in identity_errors(tmp_path))
