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


def test_flat_child_attaches_to_new_parent_copies_not_top_level():
    parent = Task(id="1", task_entry=_task_entry(task_id="1", content="Parent", labels=["X2"]))
    child = Task(
        id="2",
        task_entry=_task_entry(task_id="2", content="Child", labels=["X2"], parent_id="1"),
    )

    db = _FakeDb(tasks=[parent, child])
    _TestMultiply().run_once(db)

    # Parent copies created first
    parent_inserts = [i for i in db.inserts if i.get("content", "").startswith("Parent")]
    assert len(parent_inserts) == 2

    # Child copies must point at *new* parent ids, not missing parent_id (top-level)
    # and not the deleted original parent "1".
    child_inserts = [i for i in db.inserts if i.get("content", "").startswith("Child")]
    assert len(child_inserts) >= 2
    child_parent_ids = {i.get("parent_id") for i in child_inserts}
    assert None not in child_parent_ids
    assert "1" not in child_parent_ids
    assert child_parent_ids.issubset({"new1", "new2"})

    # Both source tasks removed for idempotency
    assert db.removed_ids == ["1", "2"]


def test_deep_child_under_expanded_parent_is_reparented_via_replacement_parent():
    parent = Task(id="1", task_entry=_task_entry(task_id="1", content="Parent", labels=["X2"]))
    deep_child = Task(
        id="2",
        task_entry=_task_entry(
            task_id="2",
            content="Do thing @_X2 - part J",
            labels=["work"],
            parent_id="1",
        ),
    )

    db = _FakeDb(tasks=[parent, deep_child])
    _TestMultiply().run_once(db)

    # Replacement parents for deep child should be created under each new parent copy.
    replacement_parents = [i for i in db.inserts if i.get("content") == "Do thing"]
    assert len(replacement_parents) == 2
    assert {i.get("parent_id") for i in replacement_parents} == {"new1", "new2"}

    # Deep child source removed
    assert db.removed_ids == ["1", "2"]
