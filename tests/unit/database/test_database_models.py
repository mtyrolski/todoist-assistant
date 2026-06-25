from typing import Any, cast

from tests.unit.database.helpers import make_event
from todoist.core.types import Project, Task


def test_task_equality(sample_task_entry):
    task1 = Task(id="task123", task_entry=sample_task_entry)
    task2 = Task(id="task123", task_entry=sample_task_entry)
    task3 = Task(id="task456", task_entry=sample_task_entry)

    assert task1 == task2
    assert task1 != task3


def test_project_equality(sample_project_entry):
    project1 = Project(
        id="12345", project_entry=sample_project_entry, tasks=[], is_archived=False
    )
    project2 = Project(
        id="12345", project_entry=sample_project_entry, tasks=[], is_archived=False
    )
    project3 = Project(
        id="67890", project_entry=sample_project_entry, tasks=[], is_archived=False
    )

    assert project1 == project2
    assert project1 != project3


def test_event_equality_and_hashing():
    event1a = make_event("event1")
    event1b = make_event("event1")
    event2 = make_event("event2")

    assert event1a == event1b
    assert event1a != event2
    assert len({event1a, event1b, event2}) == 2


def test_task_entry_duration_edge_cases(sample_task_entry):
    task_entry = sample_task_entry
    task_entry.duration = None
    assert task_entry.duration_kwargs is None

    task_entry.duration = {"invalid": "structure"}
    assert task_entry.duration_kwargs is None

    task_entry.duration = cast(Any, "not_a_dict")
    assert task_entry.duration_kwargs is None
