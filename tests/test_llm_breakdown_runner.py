"""Tests for AI breakdown runner batching behavior."""


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
        self.comments: list[dict[str, str]] = []
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

    def create_comment(self, *, task_id: str | None = None, project_id: str | None = None, content: str):
        assert task_id is not None
        assert project_id is None
        self.comments.append({"task_id": task_id, "content": content})
        return {"id": f"comment-{len(self.comments)}"}

    def fetch_task_comments(self, task_id: str):
        return [comment for comment in self.comments if comment["task_id"] == task_id]


class _RefreshableFakeDb(_FakeDb):
    def __init__(self, initial_tasks, refreshed_tasks):
        super().__init__(initial_tasks)
        self.refreshed_project = make_project(project_id="project-1", tasks=list(refreshed_tasks))
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1
        self.project = self.refreshed_project


def test_run_breakdown_uses_concurrent_triton_requests(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "triton_local")

    tasks = [
        make_task(f"task-{index}", content=f"Task {index}", labels=["ai-breakdown"])
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
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

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

    task = make_task("task-1", content="Task 1", labels=["ai-breakdown"], project_id="project-1")
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


def test_run_breakdown_recovers_with_fallback_after_insert_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    tasks = [
        make_task(f"task-{index}", content=f"Task {index}", labels=["ai-breakdown"], project_id="project-1")
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
    assert len(db.insert_calls) == 3
    assert db.insert_calls[1]["content"] == "Define first concrete step"
    assert any(item.get("task_id") == "task-0" and item.get("status") == "completed" for item in results)
    assert any(item.get("task_id") == "task-1" and item.get("status") == "completed" for item in results)


def test_run_breakdown_uses_fallback_child_when_llm_returns_empty_breakdown(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    task = make_task("task-1", content="Task 1", labels=["ai-breakdown"], project_id="project-1")
    db = _FakeDb([task])
    automation = LLMBreakdown()

    class _FakeLlm:
        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            return TaskBreakdown(children=[])

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    assert len(db.insert_calls) == 1
    assert db.insert_calls[0]["parent_id"] == "task-1"
    assert db.insert_calls[0]["content"] == "Define first concrete step"
    assert db.updated == [("task-1", [])]


def test_run_breakdown_retries_empty_llm_breakdown_before_fallback(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    task = make_task("task-1", content="Task 1", labels=["ai-breakdown"], project_id="project-1")
    db = _FakeDb([task])
    automation = LLMBreakdown()
    calls = {"count": 0}

    class _FakeLlm:
        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            calls["count"] += 1
            if calls["count"] == 1:
                return TaskBreakdown(children=[])
            assert "Do not return an empty list" in messages[0]["content"]
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    assert calls["count"] == 2
    assert len(db.insert_calls) == 1
    assert db.insert_calls[0]["content"] == "Draft metrics"
    assert db.updated == [("task-1", [])]


def test_run_breakdown_writes_todoist_comments_for_llm_interactions(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    task = make_task("task-1", content="Task 1", labels=["ai-breakdown"], project_id="project-1")
    db = _FakeDb([task])
    automation = LLMBreakdown()

    class _FakeLlm:
        class config:
            model_id = "test-model"

        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    assert [comment["task_id"] for comment in db.comments] == ["task-1", "task-1"]
    assert "Status: started" in db.comments[0]["content"]
    assert "Model: unknown / test-model" in db.comments[0]["content"]
    assert "Status: completed" in db.comments[1]["content"]
    assert "Created subtasks: 1" in db.comments[1]["content"]
    assert "- Draft metrics" in db.comments[1]["content"]


def test_run_breakdown_keeps_task_labeled_when_llm_generation_fails(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    task = make_task("task-1", content="Task 1", labels=["ai-breakdown"], project_id="project-1")
    db = _FakeDb([task])
    automation = LLMBreakdown()

    class _FakeLlm:
        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            raise RuntimeError("timed out")

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    progress = automation.progress_load()
    results = progress.get(ProgressKey.RESULTS.value)
    assert isinstance(results, list)
    assert db.insert_calls == []
    assert db.updated == []
    assert len(db.comments) == 2
    assert "Status: failed" in db.comments[1]["content"]
    assert "Label kept for retry (1/3)." in db.comments[1]["content"]
    assert any(
        item.get("task_id") == "task-1"
        and item.get("status") == "failed"
        and item.get("created_count") == 0
        for item in results
    )


def test_run_breakdown_marks_task_failed_after_three_generation_failures(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    task = make_task("task-1", content="Task 1", labels=["ai-breakdown"], project_id="project-1")
    db = _FakeDb([task])
    db.comments.extend(
        [
            {
                "task_id": "task-1",
                "content": "Todoist Assistant AI Breakdown\nStatus: failed\nRun: first",
            },
            {
                "task_id": "task-1",
                "content": "Todoist Assistant AI Breakdown\nStatus: failed\nRun: second",
            },
        ]
    )
    automation = LLMBreakdown()

    class _FakeLlm:
        def structured_chat(self, messages, schema):
            assert schema is TaskBreakdown
            assert messages
            raise RuntimeError("timed out")

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    assert db.insert_calls == []
    assert db.updated == [("task-1", ["ai-breakdown-failed"])]
    assert "Status: failed" in db.comments[-1]["content"]
    assert "Failure limit reached (3/3); replaced label with ai-breakdown-failed." in db.comments[-1]["content"]


def test_run_breakdown_ignores_failed_breakdown_label(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    task = make_task("task-1", content="Task 1", labels=["ai-breakdown-failed"], project_id="project-1")
    db = _FakeDb([task])
    automation = LLMBreakdown()

    class _FakeLlm:
        def structured_chat(self, messages, schema):  # pragma: no cover - should not be called
            raise AssertionError("failed label should not be processed")

    monkeypatch.setattr(automation, "get_llm", lambda: _FakeLlm())

    run_breakdown(automation, cast(Database, db))

    assert db.insert_calls == []
    assert db.updated == []
    assert db.comments == []


def test_run_breakdown_processes_tasks_even_when_children_already_exist(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    parent = make_task("task-1", content="Task 1", labels=["ai-breakdown"], project_id="project-1")
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
        def __init__(self) -> None:
            self.calls = 0

        def structured_chat(self, messages, schema):
            self.calls += 1
            assert schema is TaskBreakdown
            assert messages
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

    fake_llm = _FakeLlm()
    monkeypatch.setattr(automation, "get_llm", lambda: fake_llm)

    run_breakdown(automation, cast(Database, db))

    assert fake_llm.calls == 1
    assert len(db.insert_calls) == 1
    assert db.insert_calls[0]["parent_id"] == "task-1"
    assert db.insert_calls[0]["project_id"] is None
    assert db.updated == [("task-1", [])]


def test_run_breakdown_expands_labeled_subtask_in_place(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    root = make_task("task-root", content="Root task", labels=[], project_id="project-1")
    child = make_task(
        "task-child",
        content="Child task",
        labels=["ai-breakdown"],
        project_id="project-1",
        parent_id="task-root",
    )
    db = _FakeDb([root, child])
    automation = LLMBreakdown()

    class _FakeLlm:
        def __init__(self) -> None:
            self.calls = 0

        def structured_chat(self, messages, schema):
            self.calls += 1
            assert schema is TaskBreakdown
            assert messages
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

    fake_llm = _FakeLlm()
    monkeypatch.setattr(automation, "get_llm", lambda: fake_llm)

    run_breakdown(automation, cast(Database, db))

    assert fake_llm.calls == 1
    assert len(db.insert_calls) == 1
    assert db.insert_calls[0]["parent_id"] == "task-child"
    assert db.updated == [("task-child", [])]


def test_llm_breakdown_tick_refreshes_active_tasks_before_selecting_labels(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    stale_task = make_task("task-1", content="Task 1", labels=[], project_id="project-1")
    refreshed_task = make_task(
        "task-1",
        content="Task 1",
        labels=["ai-breakdown"],
        project_id="project-1",
    )
    db = _RefreshableFakeDb([stale_task], [refreshed_task])
    automation = LLMBreakdown(frequency_in_minutes=0)

    class _FakeLlm:
        def __init__(self) -> None:
            self.calls = 0

        def structured_chat(self, messages, schema):
            self.calls += 1
            assert schema is TaskBreakdown
            assert messages
            return TaskBreakdown(children=[BreakdownNode(content="Draft metrics")])

    fake_llm = _FakeLlm()
    monkeypatch.setattr(automation, "get_llm", lambda: fake_llm)

    automation.tick(cast(Database, db))

    assert db.reset_calls == 1
    assert fake_llm.calls == 1
    assert len(db.insert_calls) == 1
    assert db.insert_calls[0]["parent_id"] == "task-1"
    assert db.updated == [("task-1", [])]
