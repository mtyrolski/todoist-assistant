"""
Tests for database operations that create and modify data structures.
"""
import inspect
import pytest
from unittest.mock import patch, MagicMock

from todoist.api import EndpointCallResult, TodoistEndpoints
from todoist.api.client import RequestSpec
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


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_insert_task_basic(mock_request_json, db_tasks):
    """Test basic task insertion using the API client abstraction."""
    mock_request_json.return_value = {
        'id': '3501',
        'content': 'Buy milk',
        'description': '',
        'project_id': '226095',
        'is_completed': False,
        'priority': 1
    }

    result = db_tasks.insert_task(content="Buy milk", project_id="226095")

    assert result['id'] == '3501'
    assert result['content'] == 'Buy milk'
    assert result['project_id'] == '226095'

    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint == TodoistEndpoints.CREATE_TASK
    assert spec_arg.json_body['content'] == 'Buy milk'
    assert spec_arg.json_body['project_id'] == '226095'
    assert mock_request_json.call_args.kwargs['operation_name'] == 'create task'


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


@patch('todoist.database.db_tasks.TodoistAPIClient.request')
def test_remove_task(mock_request, db_tasks):
    """Test task removal via the API client abstraction."""
    mock_request.return_value = EndpointCallResult(
        endpoint=TodoistEndpoints.DELETE_TASK.format(task_id="task123"),
        request_headers={},
        request_params={},
        status_code=204,
        elapsed=0.1,
        text="",
        json=None,
    )

    result = db_tasks.remove_task("task123")

    assert result is True
    mock_request.assert_called_once()
    spec_arg = mock_request.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint.url.endswith("/task123")
    assert mock_request.call_args.kwargs['operation_name'] == 'delete task task123'


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_fetch_task_by_id(mock_request_json, db_tasks):
    """Test fetching task by ID via the API client abstraction."""
    mock_request_json.return_value = {
        "id": "2995104339",
        "content": "Buy Milk",
        "description": "",
        "project_id": "2203306141",
        "is_completed": False,
        "priority": 1
    }

    result = db_tasks.fetch_task_by_id("2995104339")

    assert result['id'] == "2995104339"
    assert result['content'] == "Buy Milk"

    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint.url.endswith("/2995104339")
    assert mock_request_json.call_args.kwargs['operation_name'] == 'fetch task 2995104339'


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_insert_task_from_template_valid_overrides(mock_request_json, db_tasks, sample_task_entry):
    """Test insert_task_from_template with valid overrides via API client."""
    mock_request_json.return_value = {'id': 'new_task_id'}

    template_task = Task(id="template_task", task_entry=sample_task_entry)

    result = db_tasks.insert_task_from_template(
        template_task,
        content="New Task Content",
        priority=3
    )

    assert result['id'] == 'new_task_id'
    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.json_body['content'] == 'New Task Content'
    assert spec_arg.json_body['priority'] == 3


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


@patch('todoist.database.db_projects.TodoistAPIClient.request_json')
def test_fetch_archived_projects_caching(mock_request_json, db_projects):
    """Test fetch_archived_projects with caching behavior."""
    mock_request_json.return_value = [{
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
    }]

    result1 = db_projects.fetch_archived_projects()
    assert len(result1) == 1
    assert result1[0].id == "12345"
    assert result1[0].is_archived is True
    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint == TodoistEndpoints.LIST_ARCHIVED_PROJECTS

    mock_request_json.reset_mock()

    result2 = db_projects.fetch_archived_projects()
    assert len(result2) == 1
    assert result1 == result2
    mock_request_json.assert_not_called()


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
@patch('todoist.database.db_projects.TodoistAPIClient.request_json')
def test_fetch_project_by_id(mock_request_json, mock_safe_instantiate, db_projects):
    """Test fetching a single project by ID."""
    mock_request_json.return_value = {
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
    }

    mock_project_entry = MagicMock()
    mock_project_entry.id = "12345"
    mock_safe_instantiate.return_value = mock_project_entry

    result = db_projects.fetch_project_by_id("12345")

    assert isinstance(result, Project)
    assert result.id == "12345"
    assert result.is_archived is False
    assert len(result.tasks) == 0

    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint == TodoistEndpoints.GET_PROJECT_DATA
    assert spec_arg.data == {"project_id": "12345"}


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


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_insert_tasks_empty_list(mock_request_json, db_tasks):
    """Test insert_tasks with empty list."""
    result = db_tasks.insert_tasks([])
    assert result == []
    mock_request_json.assert_not_called()


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_insert_tasks_single_task(mock_request_json, db_tasks):
    """Test insert_tasks with a single task."""
    mock_request_json.return_value = {
        'id': 'task1',
        'content': 'Test Task 1',
        'project_id': 'project123',
        'priority': 1
    }

    tasks_data = [
        {"content": "Test Task 1", "project_id": "project123"}
    ]
    
    results = db_tasks.insert_tasks(tasks_data)
    
    assert len(results) == 1
    assert results[0]['id'] == 'task1'
    assert results[0]['content'] == 'Test Task 1'
    mock_request_json.assert_called_once()


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_insert_tasks_multiple_tasks(mock_request_json, db_tasks):
    """Test insert_tasks with multiple tasks in parallel."""
    # Mock different responses for different tasks
    def mock_response_side_effect(spec, **kwargs):
        content = spec.json_body.get('content', '')
        if 'Task 1' in content:
            return {'id': 'task1', 'content': content, 'priority': 1}
        elif 'Task 2' in content:
            return {'id': 'task2', 'content': content, 'priority': 2}
        elif 'Task 3' in content:
            return {'id': 'task3', 'content': content, 'priority': 3}
        return {'id': 'unknown', 'content': content}
    
    mock_request_json.side_effect = mock_response_side_effect

    tasks_data = [
        {"content": "Test Task 1", "priority": 1},
        {"content": "Test Task 2", "priority": 2},
        {"content": "Test Task 3", "priority": 3},
    ]
    
    results = db_tasks.insert_tasks(tasks_data)
    
    assert len(results) == 3
    assert results[0]['id'] == 'task1'
    assert results[1]['id'] == 'task2'
    assert results[2]['id'] == 'task3'
    assert mock_request_json.call_count == 3


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_insert_tasks_with_failure(mock_request_json, db_tasks):
    """Test insert_tasks when one task fails."""
    call_count = {'count': 0}
    
    def mock_response_with_failure(spec, **kwargs):
        call_count['count'] += 1
        content = spec.json_body.get('content', '')
        if 'Task 2' in content:
            # Simulate failure for Task 2
            raise Exception("API Error")
        return {'id': f'task{call_count["count"]}', 'content': content}
    
    mock_request_json.side_effect = mock_response_with_failure

    tasks_data = [
        {"content": "Test Task 1"},
        {"content": "Test Task 2"},
        {"content": "Test Task 3"},
    ]
    
    results = db_tasks.insert_tasks(tasks_data)
    
    assert len(results) == 3
    # Task 1 and 3 should succeed
    assert 'id' in results[0]
    assert 'id' in results[2]
    # Task 2 should fail and return empty dict (after retries)
    assert results[1] == {}


@patch('todoist.database.db_tasks.TodoistAPIClient.request_json')
def test_insert_tasks_preserves_order(mock_request_json, db_tasks):
    """Test that insert_tasks preserves the order of results despite parallel execution."""
    import time
    
    def mock_response_with_delay(spec, **kwargs):
        content = spec.json_body.get('content', '')
        # Add variable delays to simulate real network conditions
        if 'Task 1' in content:
            time.sleep(0.03)
            return {'id': 'task1', 'content': content}
        elif 'Task 2' in content:
            time.sleep(0.01)
            return {'id': 'task2', 'content': content}
        elif 'Task 3' in content:
            time.sleep(0.02)
            return {'id': 'task3', 'content': content}
        return {'id': 'unknown', 'content': content}
    
    mock_request_json.side_effect = mock_response_with_delay

    tasks_data = [
        {"content": "Test Task 1"},
        {"content": "Test Task 2"},
        {"content": "Test Task 3"},
    ]
    
    results = db_tasks.insert_tasks(tasks_data)
    
    # Despite Task 2 completing first, results should be in original order
    assert len(results) == 3
    assert results[0]['id'] == 'task1'
    assert results[1]['id'] == 'task2'
    assert results[2]['id'] == 'task3'