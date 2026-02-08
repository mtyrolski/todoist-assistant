"""Behavior tests for threaded database helpers."""

from concurrent.futures import Future

from todoist.database.db_activity import DatabaseActivity
from todoist.database.db_projects import DatabaseProjects
from todoist.database.db_tasks import DatabaseTasks


def test_fetch_activity_short_circuits_for_zero_pages():
    db_activity = DatabaseActivity()
    result = db_activity.fetch_activity(max_pages=0)
    assert result == []


def test_fetch_projects_short_circuits_for_empty_project_list(monkeypatch):
    db_projects = DatabaseProjects()
    monkeypatch.setattr(db_projects, "_fetch_projects_data", lambda: [])

    result = db_projects.fetch_projects(include_tasks=True)
    assert result == []
    assert db_projects.projects_cache == []


def test_insert_tasks_returns_empty_dict_for_insert_errors(monkeypatch):
    db_tasks = DatabaseTasks()
    monkeypatch.setattr(db_tasks, "insert_task", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr("todoist.utils.time.sleep", lambda _seconds: None)

    result = db_tasks.insert_tasks([{"content": "Task 1"}])
    assert result == [{}]


def test_insert_tasks_limits_max_workers_to_task_count(monkeypatch):
    db_tasks = DatabaseTasks()
    captured: dict[str, int] = {}

    class InlineExecutor:
        def __init__(self, max_workers: int):
            captured["max_workers"] = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            fut: Future[dict[str, str]] = Future()
            fut.set_result(fn(*args, **kwargs))
            return fut

    monkeypatch.setattr("todoist.database.db_tasks.ThreadPoolExecutor", InlineExecutor)
    monkeypatch.setattr("todoist.database.db_tasks.tqdm", lambda iterable, **_kwargs: iterable)
    monkeypatch.setattr("todoist.database.db_tasks.get_max_concurrent_requests", lambda: 99)
    monkeypatch.setattr(db_tasks, "insert_task", lambda **task: {"id": task["content"]})

    result = db_tasks.insert_tasks([{"content": "Task 1"}, {"content": "Task 2"}])
    assert captured["max_workers"] == 2
    assert result == [{"id": "Task 1"}, {"id": "Task 2"}]


def test_insert_tasks_replaces_timed_out_futures_with_empty_dict(monkeypatch):
    db_tasks = DatabaseTasks()

    class InlineExecutor:
        def __init__(self, max_workers: int):
            self._max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            fut: Future[dict[str, str]] = Future()
            task_payload = args[0]
            if task_payload.get("content") == "Task 2":
                fut.set_exception(TimeoutError("simulated timeout"))
            else:
                fut.set_result(fn(*args, **kwargs))
            return fut

    monkeypatch.setattr("todoist.database.db_tasks.ThreadPoolExecutor", InlineExecutor)
    monkeypatch.setattr("todoist.database.db_tasks.tqdm", lambda iterable, **_kwargs: iterable)
    monkeypatch.setattr(db_tasks, "insert_task", lambda **task: {"id": task["content"]})

    result = db_tasks.insert_tasks([{"content": "Task 1"}, {"content": "Task 2"}])
    assert result == [{"id": "Task 1"}, {}]
