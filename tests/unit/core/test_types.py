"""Tests for Todoist domain data structures."""

import datetime as dt
from typing import Any

import pytest

from tests.factories import make_project, make_project_entry, make_task, make_task_entry
from todoist.core.types import (
    Event,
    EventEntry,
    ProjectEntry,
    TaskEntry,
    is_event_rescheduled,
    is_non_recurring_task,
    is_recurring_task,
)


def _event_entry(**overrides: Any) -> EventEntry:
    payload: dict[str, Any] = {
        "id": "event123",
        "object_type": "item",
        "object_id": "task123",
        "event_type": "completed",
        "event_date": "2024-01-01T12:00:00Z",
        "parent_project_id": "project123",
        "parent_item_id": None,
        "initiator_id": "user123",
        "extra_data": {"content": "Test Task Content"},
        "extra_data_id": "extra123",
        "v2_object_id": "v2_task123",
        "v2_parent_item_id": None,
        "v2_parent_project_id": "v2_project123",
    }
    payload.update(overrides)
    return EventEntry(**payload)


@pytest.mark.parametrize(
    ("entry", "expected_text"),
    [
        (make_project_entry(project_id="12345"), "Project Test Project"),
        (make_task_entry(content="Test Task"), "Task Test Task"),
        (_event_entry(extra_data={"content": "Test Task"}), "Event item completed"),
    ],
)
def test_entries_keep_identity_fields_and_display_text(entry: Any, expected_text: str) -> None:
    assert str(entry) == expected_text
    assert repr(entry) == expected_text

    if isinstance(entry, ProjectEntry):
        assert entry.id == "12345"
        assert entry.name == "Test Project"
        assert entry.color == "blue"
        assert entry.parent_id is None
        assert entry.is_archived is False
        assert entry.can_assign_tasks is True
    elif isinstance(entry, TaskEntry):
        assert entry.id == "task123"
        assert entry.content == "Test Task"
        assert entry.labels == []
        assert entry.checked is False
        assert entry.priority == 1
    else:
        assert entry.id == "event123"
        assert entry.object_type == "item"
        assert entry.event_type == "completed"
        assert entry.extra_data["content"] == "Test Task"


def test_project_entry_defaults() -> None:
    project_entry = make_project_entry(project_id="12345")

    assert project_entry.inbox_project is False
    assert project_entry.description == ""
    assert project_entry.default_order is None
    assert project_entry.public_access is False
    assert project_entry.access is None
    assert project_entry.new_api_kwargs is None


@pytest.mark.parametrize(
    ("duration", "expected_kwargs", "expected_duration_kwargs"),
    [
        (None, {"duration_unit": None, "duration": None}, None),
        (
            {"amount": 30, "unit": "minute", "duration": 30},
            {"duration_unit": "minute", "duration": 30},
            {"duration": 30, "unit": "minute"},
        ),
    ],
)
def test_task_entry_kwargs(duration, expected_kwargs, expected_duration_kwargs) -> None:
    task_entry = make_task_entry(
        content="Test Task",
        description="A test task",
        labels=["label1", "label2"] if duration is None else [],
        duration=duration,
    )

    kwargs = task_entry.kwargs
    assert kwargs["content"] == "Test Task"
    for key, value in expected_kwargs.items():
        assert kwargs[key] == value
    assert task_entry.duration_kwargs == expected_duration_kwargs


def test_task_entry_due_datetime_property() -> None:
    due_dt = make_task_entry(due={"date": "2024-01-15T14:30:00"}).due_datetime

    assert isinstance(due_dt, dt.datetime)
    assert due_dt == dt.datetime(2024, 1, 15, 14, 30)


def test_project_creation_and_equality() -> None:
    task = make_task("task123", content="Test Task", project_id="12345")
    project_entry = make_project_entry(project_id="12345")
    project = make_project(project_id="12345", project_entry=project_entry, tasks=[task])

    assert project.id == "12345"
    assert len(project.tasks) == 1
    assert project.tasks[0].id == "task123"
    assert project.is_archived is False
    assert project == make_project(project_id="12345", project_entry=project_entry)


@pytest.mark.parametrize(
    ("is_recurring", "expected_recurring", "expected_non_recurring"),
    [(False, False, True), (True, True, False)],
)
def test_task_recurring_properties(
    is_recurring: bool, expected_recurring: bool, expected_non_recurring: bool
) -> None:
    task = make_task(
        "task123",
        due={"date": "2024-01-15", "is_recurring": is_recurring},
    )

    assert task.is_recurring is expected_recurring
    assert task.is_non_recurring is expected_non_recurring
    assert is_recurring_task(task) is expected_recurring
    assert is_non_recurring_task(task) is expected_non_recurring


def test_is_event_rescheduled_function() -> None:
    event = Event(
        event_entry=_event_entry(
            event_type="updated",
            initiator_id=None,
            extra_data={
                "content": "Test Task",
                "due_date": "2025-04-06T21:59:59.000000Z",
                "last_due_date": "2025-04-05T21:59:59.000000Z",
                "note_count": 0,
            },
        ),
        id="event123",
        date=dt.datetime(2024, 1, 1, 12, 0, 0),
    )

    assert is_event_rescheduled(event) is True
    assert event.event_type == "rescheduled"


def test_event_properties() -> None:
    event = Event(
        event_entry=_event_entry(),
        id="event123",
        date=dt.datetime(2024, 1, 1, 12, 0, 0),
    )

    assert event.name == "Test Task Content"
    assert event.event_type == "completed"
    assert str(event) == "Event event123 (2024-01-01 12:00:00) Test Task Content"
