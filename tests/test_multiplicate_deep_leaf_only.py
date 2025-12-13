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
        self.updated: list[tuple[str, str]] = []
        self._counter = 0

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

    def update_task_content(self, task_id: str, content: str):
        self.updated.append((task_id, content))
        return {"id": task_id}


class _TestMultiply(Multiply):
    def run_once(self, db):
        self._tick(db)


def test_deep_token_on_non_leaf_is_stripped_and_not_expanded():
    parent = Task(
        id="1",
        task_entry=_task_entry(task_id="1", content="Parent @_X3 - part J", labels=["work"]),
    )
    child = Task(
        id="2",
        task_entry=_task_entry(task_id="2", content="Child", labels=["work"], parent_id="1"),
    )

    db = _FakeDb(tasks=[parent, child])
    _TestMultiply().run_once(db)

    assert db.updated == [("1", "Parent")]
    assert db.inserts == []
    assert db.removed_ids == []


def test_deep_token_prioritized_over_flat_label():
    task = Task(
        id="1",
        task_entry=_task_entry(task_id="1", content="Do thing @_X2 - part J", labels=["X9", "work"]),
    )

    db = _FakeDb(tasks=[task])
    _TestMultiply().run_once(db)

    # Deep expansion: replacement parent + batch + 2 leaves
    assert len(db.inserts) == 4
    assert db.inserts[0]["content"] == "Do thing"
    assert db.inserts[1]["content"] == "Batch of work - part J"
