"""
Tests for database operations that create and modify data structures.
"""
import json
import inspect
import pytest
from unittest.mock import patch, MagicMock, call

from todoist.database.db_tasks import DatabaseTasks
from todoist.database.db_projects import DatabaseProjects
from todoist.database.db_activity import DatabaseActivity
from todoist.types import Task, TaskEntry, Project, ProjectEntry


@pytest.fixture
def db_tasks():
    """Create DatabaseTasks instance for testing."""
    return DatabaseTasks()


@pytest.fixture
def db_projects():
    """Create DatabaseProjects instance for testing."""
    return DatabaseProjects()


@pytest.fixture
def db_activity():
    """Create DatabaseActivity instance for testing."""
    return DatabaseActivity()


@pytest.fixture
def sample_task_entry():
    """Create a sample TaskEntry for testing."""
    return TaskEntry(
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


@pytest.fixture
def sample_project_entry():
    """Create a sample ProjectEntry for testing."""
    return ProjectEntry(
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


@patch('todoist.database.db_tasks.run')
@patch('todoist.database.db_tasks.get_api_key')
@patch('todoist.database.db_tasks.try_n_times')
def test_insert_task_basic(mock_try_n_times, mock_get_api_key, mock_run, db_tasks):
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
    result = db_tasks.insert_task(content="Buy milk", project_id="226095")

    # Verify the result
    assert result['id'] == '3501'
    assert result['content'] == 'Buy milk'
    assert result['project_id'] == '226095'

    # Verify API call was made correctly
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]  # Get the command arguments
    assert 'curl' in call_args
    assert 'https://api.todoist.com/rest/v2/tasks' in call_args
    assert '-X' in call_args
    assert 'POST' in call_args


def test_insert_task_signature_parameters(db_tasks):
    """Test that insert_task has all expected parameters."""
    signature = inspect.signature(db_tasks.insert_task)
    expected_params = [
        'content', 'description', 'project_id', 'section_id', 'parent_id',
        'order', 'labels', 'priority', 'due_string', 'due_date', 'due_datetime',
        'due_lang', 'assignee_id', 'duration', 'duration_unit', 'deadline_date',
        'deadline_lang'
    ]
    
    actual_params = list(signature.parameters.keys())
    for param in expected_params:
        assert param in actual_params, f"Parameter '{param}' should be in insert_task signature"


@patch('todoist.database.db_tasks.run')
@patch('todoist.database.db_tasks.get_api_key')
def test_remove_task(mock_get_api_key, mock_run, db_tasks):
    """Test task removal."""
    mock_get_api_key.return_value = "test_api_key"
    mock_response = MagicMock()
    mock_response.returncode = 0
    mock_response.stdout = b''  # Empty response for successful DELETE
    mock_run.return_value = mock_response

    # Test task removal
    result = db_tasks.remove_task("task123")

    # Verify the result
    assert result is True

    # Verify API call was made correctly
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]  # Get the command arguments
    assert 'curl' in call_args
    assert 'https://api.todoist.com/rest/v2/tasks/task123' in call_args
    assert '-X' in call_args
    assert 'DELETE' in call_args


@patch('todoist.database.db_tasks.run')
@patch('todoist.database.db_tasks.get_api_key')
@patch('todoist.database.db_tasks.try_n_times')
def test_fetch_task_by_id(mock_try_n_times, mock_get_api_key, mock_run, db_tasks):
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
    result = db_tasks.fetch_task_by_id("2995104339")

    # Verify the result
    assert result['id'] == "2995104339"
    assert result['content'] == "Buy Milk"

    # Verify API call was made correctly
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert 'curl' in call_args
    assert 'https://api.todoist.com/rest/v2/tasks/2995104339' in call_args
    assert '-X' in call_args
    assert 'GET' in call_args


@patch('todoist.database.db_tasks.run')
@patch('todoist.database.db_tasks.get_api_key')
@patch('todoist.database.db_tasks.try_n_times')
def test_insert_task_from_template_valid_overrides(mock_try_n_times, mock_get_api_key, mock_run, db_tasks, sample_task_entry):
    """Test insert_task_from_template with valid overrides."""
    # Mock the API call
    mock_get_api_key.return_value = "test_api_key"
    mock_response = MagicMock()
    mock_response.stdout = json.dumps({'id': 'new_task_id'}).encode()
    mock_run.return_value = mock_response
    mock_try_n_times.return_value = {'id': 'new_task_id'}
    
    template_task = Task(id="template_task", task_entry=sample_task_entry)

    # Test with valid overrides
    result = db_tasks.insert_task_from_template(
        template_task, 
        content="New Task Content",
        priority=3
    )

    # Verify result
    assert result['id'] == 'new_task_id'
    
    # Verify that the API was called (indicating the method worked)
    mock_run.assert_called_once()


def test_insert_task_from_template_invalid_overrides(db_tasks, sample_task_entry):
    """Test insert_task_from_template with invalid overrides."""
    template_task = Task(id="template_task", task_entry=sample_task_entry)

    # Test with invalid overrides
    result = db_tasks.insert_task_from_template(
        template_task, 
        invalid_param="should_not_work"
    )

    # Verify error response
    assert 'error' in result
    assert result['error'] == 'Invalid overrides'


def test_database_projects_initialization(db_projects):
    """Test DatabaseProjects initialization."""
    assert db_projects.archived_projects_cache is None
    assert db_projects.projects_cache is None
    assert db_projects.mapping_project_name_to_color is None


@patch('todoist.database.db_projects.run')
@patch('todoist.database.db_projects.get_api_key')
def test_fetch_archived_projects_caching(mock_get_api_key, mock_run, db_projects):
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
    result1 = db_projects.fetch_archived_projects()
    assert len(result1) == 1
    assert result1[0].id == "12345"
    assert result1[0].is_archived is True
    mock_run.assert_called_once()

    # Second call should use cache
    result2 = db_projects.fetch_archived_projects()
    assert len(result2) == 1
    assert result1 == result2
    # Still only one call (cached)
    mock_run.assert_called_once()


def test_reset_clears_caches(db_projects):
    """Test that reset clears all caches."""
    # Set some cache values
    db_projects.archived_projects_cache = {"test": "value"}
    db_projects.projects_cache = ["test"]
    
    # Mock the pull method to avoid actual API calls
    with patch.object(db_projects, 'pull'):
        db_projects.reset()
    
    # Verify caches are cleared
    assert db_projects.archived_projects_cache is None
    assert db_projects.projects_cache is None


@patch('todoist.database.db_projects.safe_instantiate_entry')
@patch('todoist.database.db_projects.run')
@patch('todoist.database.db_projects.get_api_key')
def test_fetch_project_by_id(mock_get_api_key, mock_run, mock_safe_instantiate, db_projects):
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
    result = db_projects.fetch_project_by_id("12345")

    # Verify result
    assert isinstance(result, Project)
    assert result.id == "12345"
    assert result.is_archived is False
    assert len(result.tasks) == 0


@patch('todoist.database.db_activity.logger')
def test_fetch_activity_adaptively_empty_windows(mock_logger, db_activity):
    """Test adaptive fetching stops after empty windows."""
    with patch.object(db_activity, 'fetch_activity') as mock_fetch:
        # Simulate empty responses
        mock_fetch.return_value = []
        
        # Test with early stop after 2 empty windows
        result = db_activity.fetch_activity_adaptively(
            nweeks_window_size=1, 
            early_stop_after_n_windows=2
        )

        # Should stop after 2 empty windows
        assert len(result) == 0
        assert mock_fetch.call_count == 2


@patch('todoist.database.db_activity.logger')
def test_fetch_activity_adaptively_with_events(mock_logger, db_activity):
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

    with patch.object(db_activity, 'fetch_activity') as mock_fetch:
        # First call returns events, second returns empty
        mock_fetch.side_effect = [[event1], []]
        
        result = db_activity.fetch_activity_adaptively(
            nweeks_window_size=1,
            early_stop_after_n_windows=1
        )

        # Should get the event from first call, then stop after 1 empty window
        assert len(result) == 1
        assert result[0].id == "event1"
        assert mock_fetch.call_count == 2


def test_fetch_activity_signature(db_activity):
    """Test fetch_activity method signature."""
    signature = inspect.signature(db_activity.fetch_activity)
    params = list(signature.parameters.keys())
    
    # Should have parameters for pagination
    assert 'max_pages' in params
    assert 'starting_page' in params
    
    # Check default values
    assert signature.parameters['max_pages'].default == 4
    assert signature.parameters['starting_page'].default == 0


def test_task_equality(sample_task_entry):
    """Test Task equality comparison."""
    task1 = Task(id="task123", task_entry=sample_task_entry)
    task2 = Task(id="task123", task_entry=sample_task_entry)
    task3 = Task(id="task456", task_entry=sample_task_entry)
    
    assert task1 == task2
    assert task1 != task3


def test_project_equality(sample_project_entry):
    """Test Project equality comparison."""
    project1 = Project(id="12345", project_entry=sample_project_entry, tasks=[], is_archived=False)
    project2 = Project(id="12345", project_entry=sample_project_entry, tasks=[], is_archived=False)
    project3 = Project(id="67890", project_entry=sample_project_entry, tasks=[], is_archived=False)
    
    assert project1 == project2
    assert project1 != project3


def test_event_equality_and_hashing():
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
    assert event1a == event1b
    assert event1a != event2

    # Test hashing (for use in sets)
    event_set = {event1a, event1b, event2}
    assert len(event_set) == 2  # event1a and event1b should be same


def test_task_entry_duration_edge_cases():
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
    
    assert task_entry.duration_kwargs is None

    # Test with invalid duration structure
    task_entry.duration = {"invalid": "structure"}
    assert task_entry.duration_kwargs is None

    # Test with non-dict duration
    task_entry.duration = "not_a_dict"
    assert task_entry.duration_kwargs is None