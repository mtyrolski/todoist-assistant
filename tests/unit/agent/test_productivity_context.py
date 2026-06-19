from pathlib import Path

import pytest

from todoist.agent.productivity_context import build_productivity_context
from todoist.core.env import EnvVar


def test_productivity_context_exposes_codex_assistant_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setenv(str(EnvVar.CONFIG_DIR), str(tmp_path / "config"))
    monkeypatch.setenv(str(EnvVar.DATA_DIR), str(tmp_path / "data"))
    ctx = build_productivity_context(cache_path=tmp_path, repo_root=tmp_path)

    tool_names = {item["name"] for item in ctx.cache_summary()}

    assert "activity" in tool_names
    assert ctx.llm_usage()["totals"]["totalTokens"] == 0
    assert ctx.telemetry_status()["enabled"] is False


def test_create_tasks_requires_explicit_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    ctx = build_productivity_context(cache_path=tmp_path, repo_root=tmp_path)

    with pytest.raises(PermissionError):
        ctx.create_tasks("project-id", [{"content": "Draft proposal"}])
