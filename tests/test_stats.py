"""Tests for statistics and date helper functions in ``todoist.stats``."""

from datetime import datetime
from functools import partial

import pytest

from todoist.stats import (
    all_tasks,
    any_labels,
    extract_task_due_date,
    p1_tasks,
    p2_tasks,
    p3_tasks,
    p4_tasks,
    priority_tasks,
    try_parse_date,
)

# pylint: disable=redefined-outer-name


@pytest.fixture
def project_with_tasks(project_factory, task_factory):
    """Project fixture with representative priorities and labels."""
    tasks = [
        task_factory("task1", priority=4, labels=["urgent", "work"]),
        task_factory("task2", priority=4, labels=["urgent"]),
        task_factory("task3", priority=3, labels=["important"]),
        task_factory("task4", priority=2, labels=[]),
        task_factory("task5", priority=1, labels=["someday"]),
    ]
    return project_factory(tasks=tasks)


@pytest.mark.parametrize("task_count", [0, 1, 5])
def test_all_tasks_counts(project_factory, task_factory, task_count: int):
    tasks = [task_factory(f"task{i}") for i in range(task_count)]
    project = project_factory(project_id=f"project_{task_count}", tasks=tasks)
    assert all_tasks(project) == task_count


@pytest.mark.parametrize(
    ("priority", "expected_count"),
    [(4, 2), (3, 1), (2, 1), (1, 1)],
)
def test_priority_tasks_counts(project_with_tasks, priority: int, expected_count: int):
    assert priority_tasks(project_with_tasks, prio=priority) == expected_count


def test_priority_tasks_no_match(project_factory, task_factory):
    project = project_factory(
        project_id="project_no_match",
        tasks=[
            task_factory("task1", priority=2),
            task_factory("task2", priority=2),
        ],
    )
    assert priority_tasks(project, prio=4) == 0


@pytest.mark.parametrize(
    ("counter", "expected_count"),
    [(p1_tasks, 2), (p2_tasks, 1), (p3_tasks, 1), (p4_tasks, 1)],
)
def test_priority_partial_helpers(project_with_tasks, counter: partial, expected_count: int):
    assert counter(project_with_tasks) == expected_count


def test_priority_partials_on_empty_project(project_factory):
    empty = project_factory(project_id="empty", tasks=[])
    assert p1_tasks(empty) == 0
    assert p2_tasks(empty) == 0
    assert p3_tasks(empty) == 0
    assert p4_tasks(empty) == 0


@pytest.mark.parametrize(
    ("task_labels", "expected_count"),
    [
        ([["a"], ["b", "c"], []], 2),
        ([[], [], []], 0),
        ([["x"], ["y"], ["z"]], 3),
        ([["a", "b", "c"], [], ["d"]], 2),
    ],
)
def test_any_labels_counts(project_factory, task_factory, task_labels: list[list[str]], expected_count: int):
    tasks = [task_factory(f"task{i}", labels=labels) for i, labels in enumerate(task_labels, start=1)]
    project = project_factory(project_id="labels", tasks=tasks)
    assert any_labels(project) == expected_count


@pytest.mark.parametrize(
    ("raw_date", "expected"),
    [
        ("2024-01-15", datetime(2024, 1, 15)),
        ("2024-01-15T14:30:00Z", datetime(2024, 1, 15, 14, 30, 0)),
        ("2024-01-15T14:30:00", datetime(2024, 1, 15, 14, 30, 0)),
        ("2024-01-15T14:30:00.123456Z", datetime(2024, 1, 15, 14, 30, 0, 123456)),
        ("invalid-date-format", None),
        ("15-01-2024", None),
        ("2024-01", None),
        ("", None),
    ],
)
def test_try_parse_date_supported_formats(raw_date: str, expected: datetime | None):
    assert try_parse_date(raw_date) == expected


@pytest.mark.parametrize(
    ("due", "expected"),
    [
        (None, None),
        ("2024-01-15", datetime(2024, 1, 15)),
        ("2024-01-15T14:30:00Z", datetime(2024, 1, 15, 14, 30, 0)),
        ("2024-01-15T14:30:45.123456Z", datetime(2024, 1, 15, 14, 30, 45, 123456)),
        ({"date": "2024-01-15"}, datetime(2024, 1, 15)),
        ({"date": "2024-01-15T14:30:00Z", "is_recurring": False}, datetime(2024, 1, 15, 14, 30, 0)),
        (
            {"date": "2024-01-15T10:00:00Z", "is_recurring": True, "timezone": "UTC"},
            datetime(2024, 1, 15, 10, 0, 0),
        ),
        ("invalid-date", None),
        ({"date": "invalid-date"}, None),
        ("2024-12-31", datetime(2024, 12, 31)),
        ("2025-01-01", datetime(2025, 1, 1)),
        ("2024-02-29", datetime(2024, 2, 29)),
    ],
)
def test_extract_task_due_date_cases(due, expected: datetime | None):
    assert extract_task_due_date(due) == expected


def test_extract_task_due_date_missing_date_key_raises():
    with pytest.raises(KeyError):
        extract_task_due_date({"is_recurring": False, "timezone": "UTC"})
