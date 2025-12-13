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


def test_deep_token_creates_batch_and_children_and_removes_source_task():
    task = Task(
        id="1",
        task_entry=_task_entry(
            task_id="1",
            content="Do thing @_X3 - part J",
            labels=["work"],
        ),
    )

    db = _FakeDb(tasks=[task])
    Multiply()._tick(db)

    # 1) replacement parent (same level)
    assert db.inserts[0]["content"] == "Do thing"
    assert "parent_id" not in db.inserts[0]

    # 2) batch task under replacement parent
    assert db.inserts[1]["content"] == "Batch of work - part J"
    assert db.inserts[1]["parent_id"] == "new1"

    # 3..5) leaf subtasks under batch
    leaf_contents = [db.inserts[i]["content"] for i in (2, 3, 4)]
    assert leaf_contents == [
        "Do thing - part J - 1/3",
        "Do thing - part J - 2/3",
        "Do thing - part J - 3/3",
    ]
    assert all(db.inserts[i]["parent_id"] == "new2" for i in (2, 3, 4))

    # original source task removed for idempotency
    assert db.removed_ids == ["1"]
