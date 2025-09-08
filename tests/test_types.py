"""
Tests for data structure creation and modification in todoist.types module.
"""
import unittest
import datetime as dt
from unittest.mock import patch, MagicMock

from todoist.types import (
    ProjectEntry, TaskEntry, EventEntry,
    Project, Task, Event,
    is_recurring_task, is_non_recurring_task,
    is_event_rescheduled, events_to_dataframe
)


class TestDataStructureCreation(unittest.TestCase):
    """Test creation and basic properties of data structures."""

    def test_project_entry_creation(self):
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
        
        self.assertEqual(project_entry.id, "12345")
        self.assertEqual(project_entry.name, "Test Project")
        self.assertEqual(project_entry.color, "blue")
        self.assertIsNone(project_entry.parent_id)
        self.assertFalse(project_entry.is_archived)
        self.assertTrue(project_entry.can_assign_tasks)
        
        # Test string representation
        self.assertEqual(str(project_entry), "Project Test Project")
        self.assertEqual(repr(project_entry), "Project Test Project")

    def test_project_entry_with_defaults(self):
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
        self.assertFalse(project_entry.inbox_project)
        self.assertEqual(project_entry.description, '')
        self.assertIsNone(project_entry.default_order)
        self.assertFalse(project_entry.public_access)
        self.assertIsNone(project_entry.access)
        self.assertIsNone(project_entry.new_api_kwargs)

    def test_task_entry_creation(self):
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
        
        self.assertEqual(task_entry.id, "task123")
        self.assertEqual(task_entry.content, "Test Task")
        self.assertEqual(task_entry.description, "A test task")
        self.assertEqual(task_entry.labels, ["label1", "label2"])
        self.assertFalse(task_entry.checked)
        self.assertEqual(task_entry.priority, 1)
        
        # Test string representation
        self.assertEqual(str(task_entry), "Task Test Task")
        self.assertEqual(repr(task_entry), "Task Test Task")

    def test_task_entry_kwargs_property(self):
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
        self.assertIn('content', kwargs)
        self.assertIn('duration_unit', kwargs)
        self.assertIn('duration', kwargs)
        self.assertEqual(kwargs['content'], "Test Task")
        self.assertIsNone(kwargs['duration_unit'])
        self.assertIsNone(kwargs['duration'])

    def test_task_entry_with_duration(self):
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
        self.assertEqual(kwargs['duration_unit'], "minute")
        self.assertEqual(kwargs['duration'], 30)
        
        duration_kwargs = task_entry.duration_kwargs
        self.assertIsNotNone(duration_kwargs)
        self.assertEqual(duration_kwargs['duration'], 30)
        self.assertEqual(duration_kwargs['unit'], "minute")

    def test_task_entry_due_datetime_property(self):
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
        self.assertIsInstance(due_dt, dt.datetime)
        self.assertEqual(due_dt.year, 2024)
        self.assertEqual(due_dt.month, 1)
        self.assertEqual(due_dt.day, 15)
        self.assertEqual(due_dt.hour, 14)
        self.assertEqual(due_dt.minute, 30)

    def test_event_entry_creation(self):
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
        
        self.assertEqual(event_entry.id, "event123")
        self.assertEqual(event_entry.object_type, "item")
        self.assertEqual(event_entry.event_type, "completed")
        self.assertEqual(event_entry.extra_data["content"], "Test Task")
        
        # Test string representation
        self.assertEqual(str(event_entry), "Event item completed")
        self.assertEqual(repr(event_entry), "Event item completed")


class TestDataStructureComposition(unittest.TestCase):
    """Test higher-level data structure composition and relationships."""

    def test_project_creation(self):
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
        
        self.assertEqual(project.id, "12345")
        self.assertEqual(len(project.tasks), 1)
        self.assertEqual(project.tasks[0].id, "task123")
        self.assertFalse(project.is_archived)
        
        # Test equality
        project2 = Project(id="12345", project_entry=project_entry, tasks=[], is_archived=False)
        self.assertEqual(project, project2)

    def test_task_creation_and_properties(self):
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
        self.assertFalse(task.is_recurring)
        self.assertTrue(task.is_non_recurring)
        
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
        self.assertTrue(recurring_task.is_recurring)
        self.assertFalse(recurring_task.is_non_recurring)


class TestDataStructureUtilities(unittest.TestCase):
    """Test utility functions for data structure operations."""

    def test_is_recurring_task_function(self):
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
        self.assertTrue(is_recurring_task(recurring_task))
        self.assertFalse(is_non_recurring_task(recurring_task))

    def test_is_event_rescheduled_function(self):
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
        
        self.assertTrue(is_event_rescheduled(event))
        self.assertEqual(event.event_type, "rescheduled")

    def test_event_properties(self):
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
        
        self.assertEqual(event.name, "Test Task Content")
        self.assertEqual(event.event_type, "completed")
        self.assertEqual(str(event), "Event event123 (2024-01-01 12:00:00) Test Task Content")


if __name__ == '__main__':
    unittest.main()