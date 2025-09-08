"""
Tests for database operations that create and modify data structures.
"""
import unittest
from unittest.mock import patch, MagicMock, call
import json
import inspect

from todoist.database.db_tasks import DatabaseTasks
from todoist.database.db_projects import DatabaseProjects
from todoist.database.db_activity import DatabaseActivity
from todoist.types import Task, TaskEntry, Project, ProjectEntry


class TestDatabaseTasksOperations(unittest.TestCase):
    """Test database operations for task creation and modification."""

    def setUp(self):
        """Set up test fixtures."""
        self.db_tasks = DatabaseTasks()

    @patch('todoist.database.db_tasks.run')
    @patch('todoist.database.db_tasks.get_api_key')
    @patch('todoist.database.db_tasks.try_n_times')
    def test_insert_task_basic(self, mock_try_n_times, mock_get_api_key, mock_run):
        """Test basic task insertion."""
        # Mock the API response
        mock_get_api_key.return_value = "test_api_key"
        mock_response = MagicMock()
        mock_response.stdout = json.dumps({
            'id': '3501',
            'content': 'Buy milk',
            'description': '',
            'project_id': '226095',
            'is_completed': False,
            'priority': 1
        }).encode()
        mock_run.return_value = mock_response
        mock_try_n_times.return_value = {
            'id': '3501',
            'content': 'Buy milk',
            'description': '',
            'project_id': '226095',
            'is_completed': False,
            'priority': 1
        }

        # Test task insertion
        result = self.db_tasks.insert_task(content="Buy milk", project_id="226095")

        # Verify the result
        self.assertEqual(result['id'], '3501')
        self.assertEqual(result['content'], 'Buy milk')
        self.assertEqual(result['project_id'], '226095')

        # Verify API call was made correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]  # Get the command arguments
        self.assertIn('curl', call_args)
        self.assertIn('https://api.todoist.com/rest/v2/tasks', call_args)
        self.assertIn('-X', call_args)
        self.assertIn('POST', call_args)

    def test_insert_task_signature_parameters(self):
        """Test that insert_task has all expected parameters."""
        signature = inspect.signature(self.db_tasks.insert_task)
        expected_params = [
            'content', 'description', 'project_id', 'section_id', 'parent_id',
            'order', 'labels', 'priority', 'due_string', 'due_date', 'due_datetime',
            'due_lang', 'assignee_id', 'duration', 'duration_unit', 'deadline_date',
            'deadline_lang'
        ]
        
        actual_params = list(signature.parameters.keys())
        for param in expected_params:
            self.assertIn(param, actual_params, f"Parameter '{param}' should be in insert_task signature")

    @patch('todoist.database.db_tasks.run')
    @patch('todoist.database.db_tasks.get_api_key')
    def test_remove_task(self, mock_get_api_key, mock_run):
        """Test task removal."""
        mock_get_api_key.return_value = "test_api_key"
        mock_response = MagicMock()
        mock_response.returncode = 0
        mock_response.stdout = b''  # Empty response for successful DELETE
        mock_run.return_value = mock_response

        # Test task removal
        result = self.db_tasks.remove_task("task123")

        # Verify the result
        self.assertTrue(result)

        # Verify API call was made correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]  # Get the command arguments
        self.assertIn('curl', call_args)
        self.assertIn('https://api.todoist.com/rest/v2/tasks/task123', call_args)
        self.assertIn('-X', call_args)
        self.assertIn('DELETE', call_args)

    @patch('todoist.database.db_tasks.run')
    @patch('todoist.database.db_tasks.get_api_key')
    @patch('todoist.database.db_tasks.try_n_times')
    def test_fetch_task_by_id(self, mock_try_n_times, mock_get_api_key, mock_run):
        """Test fetching task by ID."""
        mock_get_api_key.return_value = "test_api_key"
        mock_response = MagicMock()
        mock_response.stdout = json.dumps({
            "id": "2995104339",
            "content": "Buy Milk",
            "description": "",
            "project_id": "2203306141",
            "is_completed": False,
            "priority": 1
        }).encode()
        mock_run.return_value = mock_response
        mock_try_n_times.return_value = {
            "id": "2995104339",
            "content": "Buy Milk",
            "description": "",
            "project_id": "2203306141",
            "is_completed": False,
            "priority": 1
        }

        # Test fetching task
        result = self.db_tasks.fetch_task_by_id("2995104339")

        # Verify the result
        self.assertEqual(result['id'], "2995104339")
        self.assertEqual(result['content'], "Buy Milk")

        # Verify API call was made correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn('curl', call_args)
        self.assertIn('https://api.todoist.com/rest/v2/tasks/2995104339', call_args)
        self.assertIn('-X', call_args)
        self.assertIn('GET', call_args)

    @patch('todoist.database.db_tasks.run')
    @patch('todoist.database.db_tasks.get_api_key')
    @patch('todoist.database.db_tasks.try_n_times')
    def test_insert_task_from_template_valid_overrides(self, mock_try_n_times, mock_get_api_key, mock_run):
        """Test insert_task_from_template with valid overrides."""
        # Mock the API call
        mock_get_api_key.return_value = "test_api_key"
        mock_response = MagicMock()
        mock_response.stdout = json.dumps({'id': 'new_task_id'}).encode()
        mock_run.return_value = mock_response
        mock_try_n_times.return_value = {'id': 'new_task_id'}
        
        # Create a mock task template
        task_entry = TaskEntry(
            id="template_task",
            is_deleted=False,
            added_at="2024-01-01T00:00:00Z",
            child_order=1,
            responsible_uid=None,
            content="Template Task",
            description="A template task",
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
            duration=None,
            updated_at="2024-01-01T00:00:00Z",
            v2_id="v2_template",
            v2_parent_id=None,
            v2_project_id="v2_project123",
            v2_section_id="v2_section123",
            day_order=None
        )
        
        template_task = Task(id="template_task", task_entry=task_entry)

        # Test with valid overrides
        result = self.db_tasks.insert_task_from_template(
            template_task, 
            content="New Task Content",
            priority=3
        )

        # Verify result
        self.assertEqual(result['id'], 'new_task_id')
        
        # Verify that the API was called (indicating the method worked)
        mock_run.assert_called_once()

    def test_insert_task_from_template_invalid_overrides(self):
        """Test insert_task_from_template with invalid overrides."""
        # Create a mock task template
        task_entry = TaskEntry(
            id="template_task",
            is_deleted=False,
            added_at="2024-01-01T00:00:00Z",
            child_order=1,
            responsible_uid=None,
            content="Template Task",
            description="A template task",
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
            duration=None,
            updated_at="2024-01-01T00:00:00Z",
            v2_id="v2_template",
            v2_parent_id=None,
            v2_project_id="v2_project123",
            v2_section_id="v2_section123",
            day_order=None
        )
        
        template_task = Task(id="template_task", task_entry=task_entry)

        # Test with invalid overrides
        result = self.db_tasks.insert_task_from_template(
            template_task, 
            invalid_param="should_not_work"
        )

        # Verify error response
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Invalid overrides')


class TestDatabaseProjectsOperations(unittest.TestCase):
    """Test database operations for project creation and modification."""

    def setUp(self):
        """Set up test fixtures."""
        self.db_projects = DatabaseProjects()

    def test_initialization(self):
        """Test DatabaseProjects initialization."""
        self.assertIsNone(self.db_projects.archived_projects_cache)
        self.assertIsNone(self.db_projects.projects_cache)
        self.assertIsNone(self.db_projects.mapping_project_name_to_color)

    @patch('todoist.database.db_projects.run')
    @patch('todoist.database.db_projects.get_api_key')
    def test_fetch_archived_projects_caching(self, mock_get_api_key, mock_run):
        """Test fetch_archived_projects with caching behavior."""
        mock_get_api_key.return_value = "test_api_key"
        mock_response = MagicMock()
        mock_response.stdout = json.dumps([{
            "id": "12345",
            "name": "Archived Project",
            "color": "blue",
            "parent_id": None,
            "child_order": 1,
            "view_style": "list",
            "is_favorite": False,
            "is_archived": True,
            "is_deleted": False,
            "is_frozen": False,
            "can_assign_tasks": True,
            "shared": False,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "v2_id": "v2_12345",
            "v2_parent_id": None,
            "sync_id": None,
            "collapsed": False
        }]).encode()
        mock_run.return_value = mock_response

        # First call should make API request
        result1 = self.db_projects.fetch_archived_projects()
        self.assertEqual(len(result1), 1)
        self.assertEqual(result1[0].id, "12345")
        self.assertTrue(result1[0].is_archived)
        mock_run.assert_called_once()

        # Second call should use cache
        result2 = self.db_projects.fetch_archived_projects()
        self.assertEqual(len(result2), 1)
        self.assertEqual(result1, result2)
        # Still only one call (cached)
        mock_run.assert_called_once()

    def test_reset_clears_caches(self):
        """Test that reset clears all caches."""
        # Set some cache values
        self.db_projects.archived_projects_cache = {"test": "value"}
        self.db_projects.projects_cache = ["test"]
        
        # Mock the pull method to avoid actual API calls
        with patch.object(self.db_projects, 'pull'):
            self.db_projects.reset()
        
        # Verify caches are cleared
        self.assertIsNone(self.db_projects.archived_projects_cache)
        self.assertIsNone(self.db_projects.projects_cache)

    @patch('todoist.database.db_projects.safe_instantiate_entry')
    @patch('todoist.database.db_projects.run')
    @patch('todoist.database.db_projects.get_api_key')
    def test_fetch_project_by_id(self, mock_get_api_key, mock_run, mock_safe_instantiate):
        """Test fetching a single project by ID."""
        mock_get_api_key.return_value = "test_api_key"
        mock_response = MagicMock()
        mock_response.stdout = json.dumps({
            "project": {
                "id": "12345",
                "name": "Test Project",
                "color": "blue",
                "parent_id": None,
                "child_order": 1,
                "view_style": "list",
                "is_favorite": False,
                "is_archived": False,
                "is_deleted": False,
                "is_frozen": False,
                "can_assign_tasks": True,
                "shared": False,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "v2_id": "v2_12345",
                "v2_parent_id": None,
                "sync_id": None,
                "collapsed": False
            }
        }).encode()
        mock_run.return_value = mock_response
        
        # Create a mock ProjectEntry
        mock_project_entry = MagicMock()
        mock_project_entry.id = "12345"
        mock_safe_instantiate.return_value = mock_project_entry

        # Test fetching project
        result = self.db_projects.fetch_project_by_id("12345")

        # Verify result
        self.assertIsInstance(result, Project)
        self.assertEqual(result.id, "12345")
        self.assertFalse(result.is_archived)
        self.assertEqual(len(result.tasks), 0)


class TestDatabaseActivityOperations(unittest.TestCase):
    """Test database operations for activity data fetching and processing."""

    def setUp(self):
        """Set up test fixtures."""
        self.db_activity = DatabaseActivity()

    @patch('todoist.database.db_activity.logger')
    def test_fetch_activity_adaptively_empty_windows(self, mock_logger):
        """Test adaptive fetching stops after empty windows."""
        with patch.object(self.db_activity, 'fetch_activity') as mock_fetch:
            # Simulate empty responses
            mock_fetch.return_value = []
            
            # Test with early stop after 2 empty windows
            result = self.db_activity.fetch_activity_adaptively(
                nweeks_window_size=1, 
                early_stop_after_n_windows=2
            )

            # Should stop after 2 empty windows
            self.assertEqual(len(result), 0)
            self.assertEqual(mock_fetch.call_count, 2)

    @patch('todoist.database.db_activity.logger')
    def test_fetch_activity_adaptively_with_events(self, mock_logger):
        """Test adaptive fetching with events."""
        from todoist.types import Event, EventEntry
        import datetime as dt

        # Create mock events
        event_entry1 = EventEntry(
            id="event1", object_type="item", object_id="task1",
            event_type="completed", event_date="2024-01-01T12:00:00Z",
            parent_project_id="proj1", parent_item_id=None,
            initiator_id="user1", extra_data={"content": "Task 1"},
            extra_data_id="extra1", v2_object_id="v2_task1",
            v2_parent_item_id=None, v2_parent_project_id="v2_proj1"
        )
        event1 = Event(
            event_entry=event_entry1,
            id="event1",
            date=dt.datetime(2024, 1, 1, 12, 0, 0)
        )

        with patch.object(self.db_activity, 'fetch_activity') as mock_fetch:
            # First call returns events, second returns empty
            mock_fetch.side_effect = [[event1], []]
            
            result = self.db_activity.fetch_activity_adaptively(
                nweeks_window_size=1,
                early_stop_after_n_windows=1
            )

            # Should get the event from first call, then stop after 1 empty window
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].id, "event1")
            self.assertEqual(mock_fetch.call_count, 2)

    def test_fetch_activity_signature(self):
        """Test fetch_activity method signature."""
        signature = inspect.signature(self.db_activity.fetch_activity)
        params = list(signature.parameters.keys())
        
        # Should have parameters for pagination
        self.assertIn('max_pages', params)
        self.assertIn('starting_page', params)
        
        # Check default values
        self.assertEqual(signature.parameters['max_pages'].default, 4)
        self.assertEqual(signature.parameters['starting_page'].default, 0)


class TestDataStructureModification(unittest.TestCase):
    """Test data structure modification operations and edge cases."""

    def test_task_equality(self):
        """Test Task equality comparison."""
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
        
        task1 = Task(id="task123", task_entry=task_entry)
        task2 = Task(id="task123", task_entry=task_entry)
        task3 = Task(id="task456", task_entry=task_entry)
        
        self.assertEqual(task1, task2)
        self.assertNotEqual(task1, task3)

    def test_project_equality(self):
        """Test Project equality comparison."""
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
        
        project1 = Project(id="12345", project_entry=project_entry, tasks=[], is_archived=False)
        project2 = Project(id="12345", project_entry=project_entry, tasks=[], is_archived=False)
        project3 = Project(id="67890", project_entry=project_entry, tasks=[], is_archived=False)
        
        self.assertEqual(project1, project2)
        self.assertNotEqual(project1, project3)

    def test_event_equality_and_hashing(self):
        """Test Event equality and hashing for set operations."""
        from todoist.types import Event, EventEntry
        import datetime as dt

        event_entry1 = EventEntry(
            id="event1", object_type="item", object_id="task1",
            event_type="completed", event_date="2024-01-01T12:00:00Z",
            parent_project_id="proj1", parent_item_id=None,
            initiator_id="user1", extra_data={"content": "Task 1"},
            extra_data_id="extra1", v2_object_id="v2_task1",
            v2_parent_item_id=None, v2_parent_project_id="v2_proj1"
        )

        event1a = Event(
            event_entry=event_entry1,
            id="event1",
            date=dt.datetime(2024, 1, 1, 12, 0, 0)
        )
        
        event1b = Event(
            event_entry=event_entry1,
            id="event1",
            date=dt.datetime(2024, 1, 1, 12, 0, 0)
        )
        
        event2 = Event(
            event_entry=event_entry1,
            id="event2",
            date=dt.datetime(2024, 1, 1, 12, 0, 0)
        )

        # Test equality
        self.assertEqual(event1a, event1b)
        self.assertNotEqual(event1a, event2)

        # Test hashing (for use in sets)
        event_set = {event1a, event1b, event2}
        self.assertEqual(len(event_set), 2)  # event1a and event1b should be same

    def test_task_entry_duration_edge_cases(self):
        """Test TaskEntry duration property with edge cases."""
        # Test with None duration
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
        
        self.assertIsNone(task_entry.duration_kwargs)

        # Test with invalid duration structure
        task_entry.duration = {"invalid": "structure"}
        self.assertIsNone(task_entry.duration_kwargs)

        # Test with non-dict duration
        task_entry.duration = "not_a_dict"
        self.assertIsNone(task_entry.duration_kwargs)


if __name__ == '__main__':
    unittest.main()