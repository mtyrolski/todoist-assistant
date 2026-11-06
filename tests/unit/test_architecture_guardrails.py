"""Regression coverage for the web architecture checks."""

from pathlib import Path

import pytest

from scripts.check_architecture import check_ruff, check_tree


@pytest.mark.parametrize(
    "source",
    [
        "def _sync_api_globals(): pass\n",
        "globals().update({'injected': 1})\n",
        "globals()['injected'] = 1\n",
        "from todometry.web import api as source\nnamespace = vars(source)\n",
        "import todometry.web.api as source\nnamespace = source.__dict__\n",
    ],
)
def test_rejects_new_namespace_injection(tmp_path: Path, source: str) -> None:
    web = tmp_path / "todometry" / "web"
    web.mkdir(parents=True)
    (web / "new.py").write_text(source, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert any("new.py" in error for error in check_tree(tmp_path))


def test_legacy_ceiling_does_not_allow_more_injection(tmp_path: Path) -> None:
    web = tmp_path / "todometry" / "web"
    web.mkdir(parents=True)
    (web / "api.py").write_text(
        "_sync_api_globals()\n_sync_api_globals()\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert any("sync: 2 occurrences, allowed 1" in e for e in check_tree(tmp_path))


def test_new_namespace_does_not_escape_injection_check(tmp_path: Path) -> None:
    web = tmp_path / "todometry" / "web"
    web.mkdir(parents=True)
    (web / "route.py").write_text(
        "from todometry.web import api as source\nnamespace = vars(source)\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert any("route.py" in error for error in check_tree(tmp_path))


def test_ruff_allows_only_existing_narrow_baseline() -> None:
    def config(lint):
        return {"tool": {"ruff": {"lint": lint}}}

    assert not check_ruff(
        config({"per-file-ignores": {"todometry/web/routes/*.py": ["F821"]}})
    )
    assert check_ruff({"tool": {"ruff": {"ignore": ["F821"]}}})
    assert check_ruff(config({"ignore": ["F821"]}))
    assert check_ruff(config({"extend-ignore": ["F"]}))
    assert check_ruff(config({"per-file-ignores": {"*.py": ["F821"]}}))
    assert check_ruff(
        config({"per-file-ignores": {"todometry/web/routes/*.py": ["ALL"]}})
    )
    assert check_ruff(
        config({"extend-per-file-ignores": {"todometry/web/routes/*.py": ["F821"]}})
    )
