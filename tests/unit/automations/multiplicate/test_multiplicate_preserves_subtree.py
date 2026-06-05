from types import SimpleNamespace

from todoist.automations.multiplicate import Multiply
from todoist.core.types import Task, TaskEntry


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
        self.updated: list[tuple[str, dict]] = []
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

    def update_task(self, task_id: str, **kwargs):
        self.updated.append((task_id, kwargs))
        return {"id": task_id}


class _TestMultiply(Multiply):
    def run_once(self, db):
        self._tick(db)


def test_flat_label_is_removed_without_inline_rollout():
    # Flat Xn rollout is no longer supported; the automation only removes the label.
    parent = Task(
        id="1", task_entry=_task_entry(task_id="1", content="Parent", labels=["X2"])
    )
    child = Task(
        id="2",
        task_entry=_task_entry(
            task_id="2", content="Child", labels=["work"], parent_id="1"
        ),
    )

    db = _FakeDb(tasks=[parent, child])
    _TestMultiply().run_once(db)

    assert db.inserts == []
    assert db.removed_ids == []
    assert db.updated == [("1", {"labels": []})]


def test_deep_label_creates_subtasks():
    task = Task(
        id="1",
        task_entry=_task_entry(
            task_id="1",
            content="Testowo inner",
            labels=["_X5", "work"],
        ),
    )

    db = _FakeDb(tasks=[task])
    _TestMultiply().run_once(db)

    leaves = [i for i in db.inserts if i.get("parent_id") == "1"]
    assert len(leaves) == 5
    assert leaves[0]["content"] == "Testowo inner - 1/5"
    assert leaves[-1]["content"] == "Testowo inner - 5/5"
    assert all(item.get("labels") == ["work", "effort-point"] for item in leaves)

    assert db.updated == [("1", {"labels": ["work"]})]
    assert not db.removed_ids
