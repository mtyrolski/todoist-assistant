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
    # Minimal constructor for the TaskEntry dataclass.
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
        self.removed_ids: list[str] = []

    def fetch_projects(self, include_tasks: bool = True):
        return self._projects

    def insert_task_from_template(self, *args, **kwargs):
        return None

    def remove_task(self, task_id: str) -> bool:
        self.removed_ids.append(task_id)
        return True


def test_tasks_sorted_by_depth_child_before_parent():
    parent = Task(id="1", task_entry=_task_entry(task_id="1", content="P", labels=["X2"]))
    child = Task(id="2", task_entry=_task_entry(task_id="2", content="C", labels=["X2"], parent_id="1"))

    # Deliberately provide child first; Multiply should process child before parent (DFS post-order).
    db = _FakeDb(tasks=[child, parent])
    Multiply()._tick(db)

    assert db.removed_ids == ["2", "1"]

