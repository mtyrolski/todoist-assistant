"""Tests for LLM breakdown runner batching behavior."""


from threading import Lock
import time
from typing import cast

from tests.factories import make_project, make_task
from todoist.automations.llm_breakdown.automation import LLMBreakdown
from todoist.automations.llm_breakdown.models import BreakdownNode, ProgressKey, TaskBreakdown
from todoist.automations.llm_breakdown.runner import run_breakdown
from todoist.database.base import Database
from todoist.env import EnvVar


class _FakeDb:
    def __init__(self, tasks):
        self.project = make_project(project_id="project-1", tasks=list(tasks))
        self.updated: list[tuple[str, list[str] | None]] = []
        self.insert_calls: list[dict[str, object]] = []
        self.fail_next_insert = False

    def fetch_projects(self, *, include_tasks: bool = False):
        assert include_tasks is True
        return [self.project]

    def update_task(self, task_id: str, **kwargs):
        self.updated.append((task_id, kwargs.get("labels")))
        return {"id": task_id}

    def insert_task(self, **kwargs):
        self.insert_calls.append(dict(kwargs))
        if self.fail_next_insert:
            self.fail_next_insert = False
            raise RuntimeError("Item not found")
        return {"id": f"child-{len(self.insert_calls)}"}


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


def test_llm_request_parallelism_treats_zero_max_tasks_per_tick_as_unlimited(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "triton_local")

    automation = LLMBreakdown(max_tasks_per_tick=0)

    assert automation.llm_request_parallelism(4) == 4


def test_run_breakdown_omits_project_id_for_subtasks(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    task = make_task("task-1", content="Task 1", labels=["llm-breakdown"], project_id="project-1")
    db = _FakeDb([task])
    automation = LLMBreakdown()

    class _FakeLlm:
        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    assert len(db.insert_calls) == 1
    assert db.insert_calls[0]["parent_id"] == "task-1"
    assert db.insert_calls[0]["project_id"] is None


def test_run_breakdown_continues_after_insert_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    tasks = [
        make_task(f"task-{index}", content=f"Task {index}", labels=["llm-breakdown"], project_id="project-1")
        for index in range(2)
    ]
    db = _FakeDb(tasks)
    db.fail_next_insert = True
    automation = LLMBreakdown()

    class _FakeLlm:
        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    progress = automation.progress_load()
    results = progress.get(ProgressKey.RESULTS.value)
    assert isinstance(results, list)
    assert len(db.insert_calls) == 2
    assert any(item.get("task_id") == "task-0" and item.get("status") == "failed" for item in results)
    assert any(item.get("task_id") == "task-1" and item.get("status") == "completed" for item in results)


def test_run_breakdown_clears_rollout_label_when_children_already_exist(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    parent = make_task("task-1", content="Task 1", labels=["llm-breakdown"], project_id="project-1")
    child = make_task(
        "child-1",
        content="Existing child",
        labels=[],
        project_id="project-1",
        parent_id="task-1",
    )
    db = _FakeDb([parent, child])
    automation = LLMBreakdown()

    class _FakeLlm:
        def structured_chat(self, messages, schema):
            raise AssertionError("LLM should not run for tasks that already have children")

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    assert db.updated == [("task-1", [])]
