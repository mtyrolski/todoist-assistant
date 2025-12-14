from types import SimpleNamespace

from todoist.automations.multiplicate import Multiply
from todoist.types import Task, TaskEntry


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

    def fetch_projects(self, include_tasks: bool = True):
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
    Multiply()._tick(db)

    assert [i["content"] for i in db.inserts] == [
        "Do thing - 1/3",
        "Do thing - 2/3",
        "Do thing - 3/3",
    ]
    assert all(i.get("parent_id") == "1" for i in db.inserts)
    assert all(i.get("labels") == ["work"] for i in db.inserts)

    # multiplier label removed from the parent for idempotency
    assert db.updated == {"labels": ["work"]}
    assert db.removed_ids == []
