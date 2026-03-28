"""Tests for LLM breakdown runner batching behavior."""


from threading import Lock
import time
from typing import cast

from tests.factories import make_project, make_task
from todoist.automations.llm_breakdown.automation import LLMBreakdown
from todoist.automations.llm_breakdown.models import TaskBreakdown
from todoist.automations.llm_breakdown.runner import run_breakdown
from todoist.database.base import Database
from todoist.env import EnvVar


class _FakeDb:
    def __init__(self, tasks):
        self.project = make_project(project_id="project-1", tasks=list(tasks))
        self.updated: list[tuple[str, list[str] | None]] = []

    def fetch_projects(self, *, include_tasks: bool = False):
        assert include_tasks is True
        return [self.project]

    def update_task(self, task_id: str, **kwargs):
        self.updated.append((task_id, kwargs.get("labels")))
        return {"id": task_id}


def test_run_breakdown_uses_concurrent_triton_requests(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "triton_local")

    tasks = [
        make_task(f"task-{index}", content=f"Task {index}", labels=["llm-breakdown"])
        for index in range(5)
    ]
    db = _FakeDb(tasks)
    automation = LLMBreakdown()

    state = {"active": 0, "max_active": 0, "calls": 0}
    lock = Lock()

    class _FakeTriton:
        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            with lock:
                state["calls"] += 1
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            time.sleep(0.05)
            with lock:
                state["active"] -= 1
            return TaskBreakdown(children=[])

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeTriton())

    run_breakdown(automation, cast(Database, db))

    assert automation.max_tasks_per_tick == 4
    assert state["calls"] == 4
    assert state["max_active"] >= 2
    assert len(db.updated) == 4
