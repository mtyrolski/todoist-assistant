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
    """Child with X2 and parent with X2 should result in proper DFS expansion.

    With children-first processing:
    1. Child (X2) is expanded first → creates 2 copies under original parent (id=1)
    2. Parent (X2) is expanded next → creates 2 parent copies, and clones the 2 child copies under each
    
    Result: 2 initial child copies + 2×2 cloned children = 6 total child inserts in one tick.
    """
    parent = Task(id="1", task_entry=_task_entry(task_id="1", content="Parent", labels=["X2"]))
    child = Task(
        id="2",
        task_entry=_task_entry(task_id="2", content="Child", labels=["X2"], parent_id="1"),
    )

    db = _FakeDb(tasks=[parent, child])
    m = _TestMultiply()
    m.run_once(db)  # Single tick handles both expansions with DFS order

    # Child expansion creates 2 copies under original parent (new1, new2),
    # then parent expansion clones them under each new parent copy (new3, new4).
    child_inserts = [i for i in db.inserts if i.get("content", "").startswith("Child story-point")]
    assert len(child_inserts) == 6  # 2 from child expansion + 4 from parent cloning

    # Check parent_ids: 2 under original parent "1", and 2 each under new parents
    child_parent_ids = [i.get("parent_id") for i in child_inserts]
    assert child_parent_ids.count("1") == 2  # initial child expansion
    assert child_parent_ids.count("new3") == 2  # cloned under first new parent
    assert child_parent_ids.count("new4") == 2  # cloned under second new parent
    
    assert "1" in db.removed_ids
    assert "2" in db.removed_ids
def test_deep_child_under_expanded_parent_is_cloned_then_expanded_next_tick():
    """Deep child (_X2) under parent (X2) with DFS children-first expansion.
    
    With children-first processing:
    1. Deep child (_X2) expands first → creates 2 subtasks under itself (new1, new2)
    2. Parent (X2) expands next → creates 2 parent copies, each cloning deep_child and its subtree
    
    Result: 2 initial subtasks + 2×2 cloned subtasks = 6 total leaf inserts in one tick.
    """
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
    m.run_once(db)  # Single tick handles both expansions with DFS order

    # Deep child expands first (2 subtasks), then parent expands and clones
    # deep_child with its subtree under each new parent copy.
    leaf_inserts = [i for i in db.inserts if i.get("content", "").startswith("Do thing - ")]
    assert len(leaf_inserts) == 6  # 2 from deep expansion + 4 from cloning (2 under each of 2 new parents)

    # Check parent_ids distribution
    leaf_parent_ids = [i.get("parent_id") for i in leaf_inserts]
    assert leaf_parent_ids.count("2") == 2  # initial deep expansion

    # The _X2 label should be removed from the original deep_child
    assert ("2", {"labels": ["work"]}) in db.updated

    assert "1" in db.removed_ids
    assert "2" in db.removed_ids
