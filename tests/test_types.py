"""
Tests for data structure creation and modification in todoist.types module.
"""
import datetime as dt

from todoist.types import (
    ProjectEntry, TaskEntry, EventEntry,
    Project, Task, Event,
    is_recurring_task, is_non_recurring_task,
    is_event_rescheduled
)


def test_project_entry_creation():
    """Test ProjectEntry dataclass creation and basic properties."""
    project_entry = ProjectEntry(
        id="12345",
        name="Test Project",
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
        v2_id="v2_12345",
        v2_parent_id=None,
        sync_id=None,
        collapsed=False
    )
    
    assert project_entry.id == "12345"
    assert project_entry.name == "Test Project"
    assert project_entry.color == "blue"
    assert project_entry.parent_id is None
    assert project_entry.is_archived is False
    assert project_entry.can_assign_tasks is True
    
    # Test string representation
    assert str(project_entry) == "Project Test Project"
    assert repr(project_entry) == "Project Test Project"


def test_project_entry_with_defaults():
    """Test ProjectEntry creation with default values."""
    project_entry = ProjectEntry(
        id="12345",
        name="Test Project",
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
        v2_id="v2_12345",
        v2_parent_id=None,
        sync_id=None,
        collapsed=False
    )
    
    # Test default values
    assert project_entry.inbox_project is False
    assert project_entry.description == ''
    assert project_entry.default_order is None
    assert project_entry.public_access is False
    assert project_entry.access is None
    assert project_entry.new_api_kwargs is None


def test_task_entry_creation():
    """Test TaskEntry dataclass creation and properties."""
    task_entry = TaskEntry(
        id="task123",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Test Task",
        description="A test task",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="project123",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due=None,
        parent_id=None,
        labels=["label1", "label2"],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task123",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    assert task_entry.id == "task123"
    assert task_entry.content == "Test Task"
    assert task_entry.description == "A test task"
    assert task_entry.labels == ["label1", "label2"]
    assert task_entry.checked is False
    assert task_entry.priority == 1
    
    # Test string representation
    assert str(task_entry) == "Task Test Task"
    assert repr(task_entry) == "Task Test Task"


def test_task_entry_kwargs_property():
    """Test TaskEntry kwargs property."""
    task_entry = TaskEntry(
        id="task123",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Test Task",
        description="A test task",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="project123",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due=None,
        parent_id=None,
        labels=["label1", "label2"],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task123",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    kwargs = task_entry.kwargs
    assert 'content' in kwargs
    assert 'duration_unit' in kwargs
    assert 'duration' in kwargs
    assert kwargs['content'] == "Test Task"
    assert kwargs['duration_unit'] is None
    assert kwargs['duration'] is None


def test_task_entry_with_duration():
    """Test TaskEntry with duration property."""
    task_entry = TaskEntry(
        id="task123",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Test Task",
        description="A test task",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="project123",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due=None,
        parent_id=None,
        labels=[],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration={"amount": 30, "unit": "minute", "duration": 30},
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task123",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    kwargs = task_entry.kwargs
    assert kwargs['duration_unit'] == "minute"
    assert kwargs['duration'] == 30
    
    duration_kwargs = task_entry.duration_kwargs
    assert duration_kwargs is not None
    assert duration_kwargs['duration'] == 30
    assert duration_kwargs['unit'] == "minute"


def test_task_entry_due_datetime_property():
    """Test TaskEntry due_datetime property with various formats."""
    # Test with datetime string
    task_entry = TaskEntry(
        id="task123",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Test Task",
        description="",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="project123",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due={"date": "2024-01-15T14:30:00"},
        parent_id=None,
        labels=[],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task123",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    due_dt = task_entry.due_datetime
    assert isinstance(due_dt, dt.datetime)
    assert due_dt.year == 2024
    assert due_dt.month == 1
    assert due_dt.day == 15
    assert due_dt.hour == 14
    assert due_dt.minute == 30


def test_event_entry_creation():
    """Test EventEntry dataclass creation."""
    event_entry = EventEntry(
        id="event123",
        object_type="item",
        object_id="task123",
        event_type="completed",
        event_date="2024-01-01T12:00:00Z",
        parent_project_id="project123",
        parent_item_id=None,
        initiator_id="user123",
        extra_data={"content": "Test Task"},
        extra_data_id="extra123",
        v2_object_id="v2_task123",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project123"
    )
    
    assert event_entry.id == "event123"
    assert event_entry.object_type == "item"
    assert event_entry.event_type == "completed"
    assert event_entry.extra_data["content"] == "Test Task"
    
    # Test string representation
    assert str(event_entry) == "Event item completed"
    assert repr(event_entry) == "Event item completed"


def test_project_creation():
    """Test Project class creation with ProjectEntry and tasks."""
    project_entry = ProjectEntry(
        id="12345",
        name="Test Project",
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
        v2_id="v2_12345",
        v2_parent_id=None,
        sync_id=None,
        collapsed=False
    )
    
    task_entry = TaskEntry(
        id="task123",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Test Task",
        description="",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="12345",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due=None,
        parent_id=None,
        labels=[],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task123",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    task = Task(id="task123", task_entry=task_entry)
    project = Project(id="12345", project_entry=project_entry, tasks=[task], is_archived=False)
    
    assert project.id == "12345"
    assert len(project.tasks) == 1
    assert project.tasks[0].id == "task123"
    assert project.is_archived is False
    
    # Test equality
    project2 = Project(id="12345", project_entry=project_entry, tasks=[], is_archived=False)
    assert project == project2


def test_task_creation_and_properties():
    """Test Task class and recurring task properties."""
    # Test non-recurring task
    task_entry = TaskEntry(
        id="task123",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Non-recurring Task",
        description="",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="project123",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due={"date": "2024-01-15", "is_recurring": False},
        parent_id=None,
        labels=[],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task123",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    task = Task(id="task123", task_entry=task_entry)
    assert task.is_recurring is False
    assert task.is_non_recurring is True
    
    # Test recurring task
    recurring_task_entry = TaskEntry(
        id="task456",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Recurring Task",
        description="",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="project123",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due={"date": "2024-01-15", "is_recurring": True},
        parent_id=None,
        labels=[],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task456",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    recurring_task = Task(id="task456", task_entry=recurring_task_entry)
    assert recurring_task.is_recurring is True
    assert recurring_task.is_non_recurring is False


def test_is_recurring_task_function():
    """Test is_recurring_task utility function."""
    # Create a recurring task
    recurring_task_entry = TaskEntry(
        id="task456",
        is_deleted=False,
        added_at="2024-01-01T00:00:00Z",
        child_order=1,
        responsible_uid=None,
        content="Recurring Task",
        description="",
        user_id="user123",
        assigned_by_uid="user123",
        project_id="project123",
        section_id="section123",
        sync_id=None,
        collapsed=False,
        due={"date": "2024-01-15", "is_recurring": True},
        parent_id=None,
        labels=[],
        checked=False,
        priority=1,
        note_count=0,
        added_by_uid="user123",
        completed_at=None,
        deadline=None,
        duration=None,
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_task456",
        v2_parent_id=None,
        v2_project_id="v2_project123",
        v2_section_id="v2_section123",
        day_order=None
    )
    
    recurring_task = Task(id="task456", task_entry=recurring_task_entry)
    assert is_recurring_task(recurring_task) is True
    assert is_non_recurring_task(recurring_task) is False


def test_is_event_rescheduled_function():
    """Test is_event_rescheduled utility function."""
    # Create a rescheduled event
    rescheduled_event_entry = EventEntry(
        id="event123",
        object_type="item",
        object_id="task123",
        event_type="updated",
        event_date="2024-01-01T12:00:00Z",
        parent_project_id="project123",
        parent_item_id=None,
        initiator_id=None,
        extra_data={
            "content": "Test Task",
            "due_date": "2025-04-06T21:59:59.000000Z",
            "last_due_date": "2025-04-05T21:59:59.000000Z",
            "note_count": 0
        },
        extra_data_id="extra123",
        v2_object_id="v2_task123",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project123"
    )
    
    event = Event(
        event_entry=rescheduled_event_entry,
        id="event123",
        date=dt.datetime(2024, 1, 1, 12, 0, 0)
    )
    
    assert is_event_rescheduled(event) is True
    assert event.event_type == "rescheduled"


def test_event_properties():
    """Test Event class properties."""
    event_entry = EventEntry(
        id="event123",
        object_type="item",
        object_id="task123",
        event_type="completed",
        event_date="2024-01-01T12:00:00Z",
        parent_project_id="project123",
        parent_item_id=None,
        initiator_id="user123",
        extra_data={"content": "Test Task Content"},
        extra_data_id="extra123",
        v2_object_id="v2_task123",
        v2_parent_item_id=None,
        v2_parent_project_id="v2_project123"
    )
    
    event = Event(
        event_entry=event_entry,
        id="event123",
        date=dt.datetime(2024, 1, 1, 12, 0, 0)
    )
    
    assert event.name == "Test Task Content"
    assert event.event_type == "completed"
    assert str(event) == "Event event123 (2024-01-01 12:00:00) Test Task Content"