import datetime as dt
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from tests.factories import make_project, make_project_entry
from todoist.core.types import Event, EventEntry, events_to_dataframe

EXPECTED_EVENT_COLUMNS = [
    "id",
    "title",
    "date",
    "type",
    "parent_project_id",
    "parent_project_name",
    "root_project_id",
    "root_project_name",
    "parent_item_id",
]


def _event_entry(event_id: str, **overrides: Any) -> EventEntry:
    payload: dict[str, Any] = {
        "id": event_id,
        "object_type": "item",
        "object_id": event_id.replace("event", "task"),
        "event_type": "completed",
        "event_date": "2024-01-01T12:00:00Z",
        "parent_project_id": "project1",
        "parent_item_id": None,
        "initiator_id": "user1",
        "extra_data": {"content": event_id},
        "extra_data_id": event_id.replace("event", "extra"),
        "v2_object_id": event_id.replace("event", "v2_task"),
        "v2_parent_item_id": None,
        "v2_parent_project_id": "v2_project1",
    }
    payload.update(overrides)
    return EventEntry(**payload)


def _event(
    event_id: str,
    *,
    date: dt.datetime = dt.datetime(2024, 1, 1, 12, 0, 0),
    **entry_overrides: Any,
) -> Event:
    return Event(event_entry=_event_entry(event_id, **entry_overrides), id=event_id, date=date)


def _project(project_id: str, name: str):
    return make_project(
        project_id=project_id,
        project_entry=make_project_entry(project_id=project_id, name=name),
    )


@pytest.fixture
def event_entry1():
    return _event_entry("event1", extra_data={"content": "Task 1 Content"})


@pytest.fixture
def event_entry2():
    return _event_entry(
        "event2",
        object_id="task2",
        event_type="added",
        event_date="2024-01-02T14:30:00Z",
        parent_project_id="project2",
        extra_data={"content": "Task 2 Content"},
        extra_data_id="extra2",
        v2_object_id="v2_task2",
        v2_parent_project_id="v2_project2",
    )


@pytest.fixture
def event1(event_entry1):
    return Event(
        event_entry=event_entry1, id="event1", date=dt.datetime(2024, 1, 1, 12, 0, 0)
    )


@pytest.fixture
def event2(event_entry2):
    return Event(
        event_entry=event_entry2, id="event2", date=dt.datetime(2024, 1, 2, 14, 30, 0)
    )


@pytest.fixture
def project_entry1():
    return make_project_entry(project_id="project1", name="Project One")


@pytest.fixture
def project_entry2():
    return make_project_entry(project_id="project2", name="Project Two", color="red", child_order=2)


@pytest.fixture
def project1(project_entry1):
    return make_project(project_id="project1", project_entry=project_entry1)


@pytest.fixture
def project2(project_entry2):
    return make_project(project_id="project2", project_entry=project_entry2)


def test_events_to_dataframe_basic(event1, event2, project1, project2):
    df = events_to_dataframe(
        {event1, event2},
        {"project1": "Project One", "project2": "Project Two"},
        {"project1": project1, "project2": project2},
    )

    assert isinstance(df, pd.DataFrame)
    for col in EXPECTED_EVENT_COLUMNS:
        assert col in df.columns
    assert len(df) == 2

    event1_row = df[df["id"] == "event1"].iloc[0]
    assert event1_row[
        ["title", "type", "parent_project_id", "parent_project_name", "root_project_id", "root_project_name"]
    ].to_dict() == {
        "title": "Task 1 Content",
        "type": "completed",
        "parent_project_id": "project1",
        "parent_project_name": "Project One",
        "root_project_id": "project1",
        "root_project_name": "Project One",
    }

    event2_row = df[df["id"] == "event2"].iloc[0]
    assert event2_row["title"] == "Task 2 Content"
    assert event2_row["type"] == "added"
    assert event2_row["parent_project_id"] == "project2"
    assert event2_row["parent_project_name"] == "Project Two"


def test_events_to_dataframe_chronological_order(event1, event2, project1, project2):
    future_event = _event(
        "event_future",
        date=dt.datetime(2024, 1, 5, 10, 0, 0),
        object_id="task_future",
        event_type="updated",
        event_date="2024-01-05T10:00:00Z",
        extra_data={"content": "Future Task"},
        extra_data_id="extra_future",
        v2_object_id="v2_task_future",
    )

    df = events_to_dataframe(
        {future_event, event1, event2},
        {"project1": "Project One", "project2": "Project Two"},
        {"project1": project1, "project2": project2},
    )

    dates = df["date"].tolist()
    assert dates == sorted(dates)
    assert df.iloc[0]["id"] == "event1"
    assert df.iloc[-1]["id"] == "event_future"


def test_events_to_dataframe_unsupported_event_types(event1, project1):
    unsupported_event = _event(
        "event_unsupported",
        date=dt.datetime(2024, 1, 3, 12, 0, 0),
        object_id="task_unsupported",
        event_type="unsupported_type",
        event_date="2024-01-03T12:00:00Z",
        extra_data={"content": "Unsupported Event"},
        extra_data_id="extra_unsupported",
        v2_object_id="v2_task_unsupported",
    )

    with patch("todoist.core.types.logger") as mock_logger:
        df = events_to_dataframe(
            {event1, unsupported_event}, {"project1": "Project One"}, {"project1": project1}
        )

        assert len(df) == 1
        assert df.iloc[0]["id"] == "event1"
        mock_logger.info.assert_called()


def test_events_to_dataframe_missing_project_mapping(event1, project1):
    missing_project_event = _event(
        "event_missing",
        date=dt.datetime(2024, 1, 3, 12, 0, 0),
        object_id="task_missing",
        event_date="2024-01-03T12:00:00Z",
        parent_project_id="missing_project",
        extra_data={"content": "Missing Project Event"},
        extra_data_id="extra_missing",
        v2_object_id="v2_task_missing",
        v2_parent_project_id="v2_missing_project",
    )

    with patch("todoist.core.types.logger") as mock_logger:
        df = events_to_dataframe(
            {event1, missing_project_event}, {"project1": "Project One"}, {"project1": project1}
        )

        assert len(df) == 1
        assert df.iloc[0]["id"] == "event1"
        mock_logger.warning.assert_called()


def test_events_to_dataframe_empty_activity():
    df = events_to_dataframe(set(), {}, {})

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    for col in EXPECTED_EVENT_COLUMNS:
        assert col in df.columns


@pytest.mark.parametrize(
    ("extra_data", "expected"),
    [
        ({"content": "Task 1 Content"}, "Task 1 Content"),
        ({"name": "Project Name"}, "Project Name"),
        ({"other_field": "value"}, None),
    ],
)
def test_event_name_extraction(extra_data: dict[str, str], expected: str | None):
    assert _event("event_name", extra_data=extra_data).name == expected


def test_dataframe_column_types(event1, event2, project1, project2):
    df = events_to_dataframe(
        {event1, event2},
        {"project1": "Project One", "project2": "Project Two"},
        {"project1": project1, "project2": project2},
    )

    for column in [
        "id",
        "parent_project_id",
        "root_project_id",
        "title",
        "type",
        "parent_project_name",
        "root_project_name",
    ]:
        assert pd.api.types.is_string_dtype(df[column])
    assert all(isinstance(d, dt.datetime) for d in df["date"])
