from types import SimpleNamespace
from typing import cast
from datetime import datetime
from unittest.mock import patch

# pylint: disable=protected-access

from todoist.automations.multiplicate import Multiply
from todoist.database.base import Database
from todoist.core.types import Task, TaskEntry
from todoist.core.utils import Cache


def _task_entry(
    *,
    task_id: str,
    content: str,
    labels: list[str],
    parent_id: str | None = None,
) -> TaskEntry:
    return TaskEntry(
        id=task_id,
        is_deleted=False,
        added_at="",
        child_order=0,
        responsible_uid=None,
        content=content,
        description="",
        user_id="",
        assigned_by_uid="",
        project_id="p1",
        section_id="s1",
        sync_id=None,
        collapsed=False,
        due=None,
        parent_id=parent_id,
        labels=labels,
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="",
        v2_id=None,
        v2_parent_id=None,
        v2_project_id=None,
        v2_section_id=None,
        day_order=None,
        new_api_kwargs=None,
    )


class _FakeDb:
    def __init__(self, tasks: list[Task]):
        self._projects = [SimpleNamespace(tasks=tasks)]
        self.inserts: list[dict] = []
        self.removed_ids: list[str] = []
        self.updated: dict = {}
        self._counter = 0
        self.labels: list[dict[str, str]] = []
        self.deleted_labels: list[str] = []

    def fetch_projects(self, include_tasks: bool = True):
        _ = include_tasks
        return self._projects

    def insert_task_from_template(self, _task: Task, **overrides):
        self._counter += 1
        self.inserts.append(overrides)
        return {"id": f"new{self._counter}"}

    def remove_task(self, task_id: str) -> bool:
        self.removed_ids.append(task_id)
        return True

    def update_task(self, task_id: str, **kwargs):
        _ = task_id
        self.updated = kwargs
        return {"id": task_id}

    def list_labels(self):
        return list(self.labels)

    def delete_label_by_name(self, label_name: str) -> bool:
        self.deleted_labels.append(label_name)
        return True


def test_deep_label_creates_children_under_task_and_removes_multiplier_label():
    task = Task(
        id="1",
        task_entry=_task_entry(
            task_id="1",
            content="Do thing",
            labels=["_X3", "work"],
        ),
    )

    db = _FakeDb(tasks=[task])
    Multiply()._tick(cast(Database, db))

    assert [i["content"] for i in db.inserts] == [
        "Do thing - 1/3",
        "Do thing - 2/3",
        "Do thing - 3/3",
    ]
    assert all(i.get("parent_id") == "1" for i in db.inserts)
    assert all(i.get("labels") == ["work", "effort-point"] for i in db.inserts)

    # multiplier label removed from the parent for idempotency
    assert db.updated == {"labels": ["work"]}
    assert not db.removed_ids


def test_multiply_runs_as_polling_automation_without_new_activity():
    assert Multiply().should_run_without_new_activity() is True


def test_multiplier_cleanup_deletes_unused_label_after_retention(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    Cache().multiplication_label_usage.save(
        {"_X3": {"lastSeenAt": "2025-03-10T12:00:00"}}
    )
    db = _FakeDb(tasks=[])
    db.labels = [{"id": "label-1", "name": "_X3", "color": "blue"}]
    automation = Multiply(config={"cleanup_unused_labels_after_days": 7})

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            _ = tz
            return datetime(2025, 3, 20, 12, 0, 0)

    with patch(
        "todoist.automations.multiplicate.automation.datetime",
        _FixedDateTime,
    ):
        automation._tick(cast(Database, db))

    assert db.deleted_labels == ["_X3"]
    assert Cache().multiplication_label_usage.load() == {}


def test_multiplier_cleanup_deletes_untracked_unused_label_immediately(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    db = _FakeDb(tasks=[])
    db.labels = [{"id": "label-1", "name": "_X90", "color": "blue"}]

    Multiply(config={"cleanup_unused_labels_after_days": 7})._tick(cast(Database, db))

    assert db.deleted_labels == ["_X90"]
    assert Cache().multiplication_label_usage.load() == {}
