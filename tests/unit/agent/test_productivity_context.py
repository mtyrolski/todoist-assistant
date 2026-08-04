from pathlib import Path

import pandas as pd
import pytest

from tests.factories import make_project, make_task
from todoist.agent.productivity_context import build_productivity_context
from todoist.core.env import EnvVar
from todoist.core.utils import Cache


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


def test_ai_context_helpers_fetch_and_upsert_only_project_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context_task = make_task(
        "context-1",
        content="* Stable constraint",
        labels=["ai_context"],
        project_id="project-1",
    )
    project = make_project(
        project_id="project-1", name="Platform", tasks=[context_task]
    )

    class _FakeDatabase:
        def __init__(self, _env_path: str) -> None:
            self.updated = []
            self.comments = []

        def fetch_projects(self, *, include_tasks: bool):
            assert include_tasks is True
            return [project]

        def update_task(self, task_id: str, **kwargs):
            self.updated.append((task_id, kwargs))
            return {"id": task_id}

        def create_comment(self, *, task_id: str, content: str):
            self.comments.append({"task_id": task_id, "content": content})
            return {"id": "comment-1"}

    fake_db = _FakeDatabase(str(tmp_path / ".env"))
    monkeypatch.setattr(
        "todoist.agent.productivity_context.Database", lambda _path: fake_db
    )
    ctx = build_productivity_context(
        cache_path=tmp_path, repo_root=tmp_path, env_path=tmp_path / ".env"
    )

    assert ctx.ai_context(project_id="project-1")[0]["taskId"] == "context-1"
    assert "Project: Platform (1 context task(s))" in ctx.rendered_ai_context()
    aggregate = ctx.project_ai_context(project_id="project-1")[0]
    assert aggregate["contextCount"] == 1
    assert aggregate["entries"][0]["taskId"] == "context-1"
    result = ctx.upsert_ai_context(
        "project-1",
        "Updated stable constraint",
        description="The stable constraint applies to every release.",
        task_id="context-1",
    )

    assert result["action"] == "updated"
    assert fake_db.updated[0][1] == {
        "content": "* Updated stable constraint",
        "description": "The stable constraint applies to every release.",
    }
    assert fake_db.comments[0]["task_id"] == "context-1"


def _save_dashboard_activity(cache_path: Path) -> None:
    activity = pd.DataFrame(
        [
            {
                "date": "2026-06-09T10:00:00Z",
                "type": "completed",
                "title": "Previous Academy task",
                "parent_project_name": "Magisterka",
                "root_project_name": "Academy",
            },
            {
                "date": "2026-06-14T20:00:00Z",
                "type": "completed",
                "title": "Late previous-week task",
                "parent_project_name": "Magisterka",
                "root_project_name": "Academy",
            },
            {
                "date": "2026-06-15T08:00:00Z",
                "type": "completed",
                "title": "Mapped thesis task",
                "parent_project_name": "Magisterka",
                "root_project_name": "Academy",
            },
            {
                "date": "2026-06-16T09:00:00Z",
                "type": "completed",
                "title": "Academy task",
                "parent_project_name": "Academy",
                "root_project_name": "Academy",
            },
            {
                "date": "2026-06-17T11:00:00Z",
                "type": "added",
                "title": "Health follow-up",
                "parent_project_name": "Health",
                "root_project_name": "Health",
            },
        ]
    )
    Cache(str(cache_path)).dashboard_state.save({"df_activity": activity})


def test_project_comparison_uses_mapped_root_project_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    _save_dashboard_activity(tmp_path)
    ctx = build_productivity_context(cache_path=tmp_path, repo_root=tmp_path)

    result = ctx.project_comparison(period="week", as_of="2026-06-18T12:00:00+02:00")

    academy = next(item for item in result["projects"] if item["project"] == "Academy")
    assert academy["current"]["completed"] == 2
    # Active periods compare the same elapsed duration, not a partial week to a full week.
    assert academy["previous"]["completed"] == 1
    assert academy["change"]["completed"] == 1
    assert result["comparisonMode"] == "elapsed_to_elapsed"
    assert result["periodComplete"] is False
    assert all("projectId" not in item for item in result["projects"])


def test_executive_summary_returns_daily_decision_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    _save_dashboard_activity(tmp_path)
    ctx = build_productivity_context(cache_path=tmp_path, repo_root=tmp_path)

    result = ctx.executive_summary(period="day", as_of="2026-06-17T18:00:00+02:00")

    assert result["period"]["start"] == "2026-06-17"
    assert result["totals"]["added"] == 1
    assert result["leadingProjects"][0]["project"] == "Health"
    assert result["busiestDay"] == {"date": "2026-06-17", "events": 1}
    assert isinstance(result["signals"], list)
