"""
Tests for data transformation and dataframe operations.
"""
import pandas as pd
import datetime as dt
import pytest
from unittest.mock import patch

from todoist.types import Event, EventEntry, Project, ProjectEntry, events_to_dataframe


@pytest.fixture
def event_entry1():
    """Create first sample EventEntry for testing."""
    return EventEntry(
        id="event1",
        object_type="item",
        object_id="task1",
        event_type="completed",
        event_date="2024-01-01T12:00:00Z",
        parent_project_id="project1",
        parent_item_id=None,
        initiator_id="user1",
        extra_data={"content": "Task 1 Content"},
        extra_data_id="extra1",
        v2_object_id="v2_task1",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project1"
    )


@pytest.fixture
def event_entry2():
    """Create second sample EventEntry for testing."""
    return EventEntry(
        id="event2",
        object_type="item",
        object_id="task2",
        event_type="added",
        event_date="2024-01-02T14:30:00Z",
        parent_project_id="project2",
        parent_item_id=None,
        initiator_id="user1",
        extra_data={"content": "Task 2 Content"},
        extra_data_id="extra2",
        v2_object_id="v2_task2",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project2"
    )


@pytest.fixture
def event1(event_entry1):
    """Create first Event for testing."""
    return Event(
        event_entry=event_entry1,
        id="event1",
        date=dt.datetime(2024, 1, 1, 12, 0, 0)
    )


@pytest.fixture
def event2(event_entry2):
    """Create second Event for testing."""
    return Event(
        event_entry=event_entry2,
        id="event2",
        date=dt.datetime(2024, 1, 2, 14, 30, 0)
    )


@pytest.fixture
def project_entry1():
    """Create first sample ProjectEntry for testing."""
    return ProjectEntry(
        id="project1",
        name="Project One",
        color="blue",
        parent_id=None,
        child_order=1,
        view_style="list",
        is_favorite=False,
        is_archived=False,
        is_deleted=False,
        is_frozen=False,
        can_assign_tasks=True,
        shared=False,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_project1",
        v2_parent_id=None,
        sync_id=None,
        collapsed=False
    )


@pytest.fixture
def project_entry2():
    """Create second sample ProjectEntry for testing."""
    return ProjectEntry(
        id="project2",
        name="Project Two",
        color="red",
        parent_id=None,
        child_order=2,
        view_style="list",
        is_favorite=False,
        is_archived=False,
        is_deleted=False,
        is_frozen=False,
        can_assign_tasks=True,
        shared=False,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_project2",
        v2_parent_id=None,
        sync_id=None,
        collapsed=False
    )


@pytest.fixture
def project1(project_entry1):
    """Create first Project for testing."""
    return Project(
        id="project1",
        project_entry=project_entry1,
        tasks=[],
        is_archived=False
    )


@pytest.fixture
def project2(project_entry2):
    """Create second Project for testing."""
    return Project(
        id="project2",
        project_entry=project_entry2,
        tasks=[],
        is_archived=False
    )


def test_events_to_dataframe_basic(event1, event2, project1, project2):
    """Test basic events_to_dataframe functionality."""
    activity = {event1, event2}
    project_id_to_name = {
        "project1": "Project One",
        "project2": "Project Two"
    }
    project_id_to_root = {
        "project1": project1,
        "project2": project2
    }

    df = events_to_dataframe(activity, project_id_to_name, project_id_to_root)

    # Verify dataframe structure
    assert isinstance(df, pd.DataFrame)
    expected_columns = [
        'id', 'title', 'date', 'type', 'parent_project_id',
        'parent_project_name', 'root_project_id', 'root_project_name', 'parent_item_id'
    ]
    for col in expected_columns:
        assert col in df.columns

    # Verify data content
    assert len(df) == 2

    # Check event 1 data
    event1_row = df[df['id'] == 'event1'].iloc[0]
    assert event1_row['title'] == 'Task 1 Content'
    assert event1_row['type'] == 'completed'
    assert event1_row['parent_project_id'] == 'project1'
    assert event1_row['parent_project_name'] == 'Project One'
    assert event1_row['root_project_id'] == 'project1'
    assert event1_row['root_project_name'] == 'Project One'

    # Check event 2 data
    event2_row = df[df['id'] == 'event2'].iloc[0]
    assert event2_row['title'] == 'Task 2 Content'
    assert event2_row['type'] == 'added'
    assert event2_row['parent_project_id'] == 'project2'
    assert event2_row['parent_project_name'] == 'Project Two'


def test_events_to_dataframe_chronological_order(event1, event2, project1, project2):
    """Test that events are sorted chronologically."""
    # Create events in reverse chronological order
    future_event_entry = EventEntry(
        id="event_future",
        object_type="item",
        object_id="task_future",
        event_type="updated",
        event_date="2024-01-05T10:00:00Z",
        parent_project_id="project1",
        parent_item_id=None,
        initiator_id="user1",
        extra_data={"content": "Future Task"},
        extra_data_id="extra_future",
        v2_object_id="v2_task_future",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project1"
    )

    future_event = Event(
        event_entry=future_event_entry,
        id="event_future",
        date=dt.datetime(2024, 1, 5, 10, 0, 0)
    )

    # Set with events in different order
    activity = {future_event, event1, event2}
    project_id_to_name = {"project1": "Project One", "project2": "Project Two"}
    project_id_to_root = {"project1": project1, "project2": project2}

    df = events_to_dataframe(activity, project_id_to_name, project_id_to_root)

    # Verify chronological order (oldest first)
    dates = df['date'].tolist()
    sorted_dates = sorted(dates)
    assert dates == sorted_dates

    # Verify the first row is the oldest event
    first_row = df.iloc[0]
    assert first_row['id'] == 'event1'  # 2024-01-01

    # Verify the last row is the newest event
    last_row = df.iloc[-1]
    assert last_row['id'] == 'event_future'  # 2024-01-05


def test_events_to_dataframe_unsupported_event_types(event1, project1):
    """Test filtering of unsupported event types."""
    # Create an unsupported event type
    unsupported_event_entry = EventEntry(
        id="event_unsupported",
        object_type="item",
        object_id="task_unsupported",
        event_type="unsupported_type",  # Not in SUPPORTED_EVENT_TYPES
        event_date="2024-01-03T12:00:00Z",
        parent_project_id="project1",
        parent_item_id=None,
        initiator_id="user1",
        extra_data={"content": "Unsupported Event"},
        extra_data_id="extra_unsupported",
        v2_object_id="v2_task_unsupported",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project1"
    )

    unsupported_event = Event(
        event_entry=unsupported_event_entry,
        id="event_unsupported",
        date=dt.datetime(2024, 1, 3, 12, 0, 0)
    )

    activity = {event1, unsupported_event}
    project_id_to_name = {"project1": "Project One"}
    project_id_to_root = {"project1": project1}

    with patch('todoist.types.logger') as mock_logger:
        df = events_to_dataframe(activity, project_id_to_name, project_id_to_root)

        # Should only contain supported events
        assert len(df) == 1
        assert df.iloc[0]['id'] == 'event1'

        # Should log filtering information
        mock_logger.info.assert_called()


def test_events_to_dataframe_missing_project_mapping(event1, project1):
    """Test handling of events with missing project mappings."""
    # Create event with project not in mapping
    missing_project_event_entry = EventEntry(
        id="event_missing",
        object_type="item",
        object_id="task_missing",
        event_type="completed",
        event_date="2024-01-03T12:00:00Z",
        parent_project_id="missing_project",  # Not in project mappings
        parent_item_id=None,
        initiator_id="user1",
        extra_data={"content": "Missing Project Event"},
        extra_data_id="extra_missing",
        v2_object_id="v2_task_missing",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_missing_project"
    )

    missing_project_event = Event(
        event_entry=missing_project_event_entry,
        id="event_missing",
        date=dt.datetime(2024, 1, 3, 12, 0, 0)
    )

    activity = {event1, missing_project_event}
    project_id_to_name = {"project1": "Project One"}  # Missing project not included
    project_id_to_root = {"project1": project1}   # Missing project not included

    with patch('todoist.types.logger') as mock_logger:
        df = events_to_dataframe(activity, project_id_to_name, project_id_to_root)

        # Should only contain events with valid project mappings
        assert len(df) == 1
        assert df.iloc[0]['id'] == 'event1'

        # Should log warning about missing projects
        mock_logger.warning.assert_called()


def test_events_to_dataframe_empty_activity():
    """Test events_to_dataframe with empty activity set."""
    activity = set()
    project_id_to_name = {}
    project_id_to_root = {}

    df = events_to_dataframe(activity, project_id_to_name, project_id_to_root)

    # Should return empty dataframe with correct structure
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    expected_columns = [
        'id', 'title', 'date', 'type', 'parent_project_id',
        'parent_project_name', 'root_project_id', 'root_project_name', 'parent_item_id'
    ]
    for col in expected_columns:
        assert col in df.columns


def test_event_name_extraction(event_entry1):
    """Test event name extraction from extra_data."""
    # Test event with 'content' in extra_data
    content_event = Event(
        event_entry=event_entry1,
        id="content_event",
        date=dt.datetime(2024, 1, 1, 12, 0, 0)
    )
    assert content_event.name == "Task 1 Content"

    # Test event with 'name' in extra_data
    name_event_entry = EventEntry(
        id="name_event",
        object_type="project",
        object_id="project123",
        event_type="added",
        event_date="2024-01-01T12:00:00Z",
        parent_project_id="project1",
        parent_item_id=None,
        initiator_id="user1",
        extra_data={"name": "Project Name"},
        extra_data_id="extra_name",
        v2_object_id="v2_project123",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project1"
    )

    name_event = Event(
        event_entry=name_event_entry,
        id="name_event",
        date=dt.datetime(2024, 1, 1, 12, 0, 0)
    )
    assert name_event.name == "Project Name"

    # Test event with neither content nor name
    no_name_event_entry = EventEntry(
        id="no_name_event",
        object_type="item",
        object_id="task123",
        event_type="completed",
        event_date="2024-01-01T12:00:00Z",
        parent_project_id="project1",
        parent_item_id=None,
        initiator_id="user1",
        extra_data={"other_field": "value"},
        extra_data_id="extra_other",
        v2_object_id="v2_task123",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project1"
    )

    no_name_event = Event(
        event_entry=no_name_event_entry,
        id="no_name_event",
        date=dt.datetime(2024, 1, 1, 12, 0, 0)
    )
    assert no_name_event.name is None


def test_dataframe_column_types(event1, event2, project1, project2):
    """Test that dataframe columns have appropriate data types."""
    activity = {event1, event2}
    project_id_to_name = {
        "project1": "Project One",
        "project2": "Project Two"
    }
    project_id_to_root = {
        "project1": project1,
        "project2": project2
    }

    df = events_to_dataframe(activity, project_id_to_name, project_id_to_root)

    # Check that id columns are strings
    assert df['id'].dtype == 'object'
    assert df['parent_project_id'].dtype == 'object'
    assert df['root_project_id'].dtype == 'object'

    # Check that date column contains datetime objects
    assert all(isinstance(d, dt.datetime) for d in df['date'])

    # Check that string columns are strings
    assert df['title'].dtype == 'object'
    assert df['type'].dtype == 'object'
    assert df['parent_project_name'].dtype == 'object'
    assert df['root_project_name'].dtype == 'object'