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
        self._tasks: dict[str, Task] = {t.id: t for t in tasks}
        self._projects = [SimpleNamespace(tasks=list(self._tasks.values()))]
        self.inserts: list[dict] = []
        self.removed_ids: list[str] = []
        self.updated: list[tuple[str, dict]] = []
        self._counter = 0

    def fetch_projects(self, include_tasks: bool = True):
        _ = include_tasks
        self._projects[0].tasks = list(self._tasks.values())
        return self._projects

    def insert_task_from_template(self, _task: Task, **overrides):
        self._counter += 1
        self.inserts.append(overrides)
        new_id = f"new{self._counter}"
        content = overrides.get("content", _task.task_entry.content)
        labels = overrides.get("labels", list(_task.task_entry.labels))
        parent_id = overrides.get("parent_id", _task.task_entry.parent_id)
        created_task = Task(
            id=new_id,
            task_entry=_task_entry(task_id=new_id, content=content, labels=labels, parent_id=parent_id),
        )
        self._tasks[new_id] = created_task
        return {"id": new_id}

    def remove_task(self, task_id: str) -> bool:
        self.removed_ids.append(task_id)
        self._tasks.pop(task_id, None)
        return True

    def update_task(self, task_id: str, **kwargs):
        self.updated.append((task_id, kwargs))
        task = self._tasks.get(task_id)
        if task is not None and "labels" in kwargs:
            task.task_entry.labels = kwargs["labels"]
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
    m = _TestMultiply()
    m.run_once(db)
    m.run_once(db)

    # After the second tick, child multiplication happens under the newly created parent copies.
    child_inserts = [i for i in db.inserts if i.get("content", "").startswith("Child story-point")]
    assert len(child_inserts) == 4
    child_parent_ids = {i.get("parent_id") for i in child_inserts}
    assert None not in child_parent_ids
    assert "1" not in child_parent_ids
    assert child_parent_ids.issubset({"new1", "new2"})
    assert "1" in db.removed_ids
    assert "2" in db.removed_ids


def test_deep_child_under_expanded_parent_is_cloned_then_expanded_next_tick():
    parent = Task(id="1", task_entry=_task_entry(task_id="1", content="Parent", labels=["X2"]))
    deep_child = Task(
        id="2",
        task_entry=_task_entry(
            task_id="2",
            content="Do thing",
            labels=["_X2", "work"],
            parent_id="1",
        ),
    )

    db = _FakeDb(tasks=[parent, deep_child])
    m = _TestMultiply()
    m.run_once(db)
    m.run_once(db)

    # Two cloned deep-child tasks should each expand into 2 subtasks on the next tick.
    leaf_inserts = [i for i in db.inserts if i.get("content", "").startswith("Do thing - ")]
    assert len(leaf_inserts) == 4
    assert {i.get("parent_id") for i in leaf_inserts}.issubset({"new3", "new4"})
    assert {task_id: kwargs for task_id, kwargs in db.updated} == {
        "new3": {"labels": ["work"]},
        "new4": {"labels": ["work"]},
    }

    assert "1" in db.removed_ids
    assert "2" in db.removed_ids
