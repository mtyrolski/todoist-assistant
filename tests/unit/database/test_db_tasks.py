import inspect
import time
from unittest.mock import patch

from todoist.api import EndpointCallResult, TodoistEndpoints
from todoist.api.client import RequestSpec
from todoist.core.types import Task


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_insert_task_basic(mock_request_json, db_tasks):
    mock_request_json.return_value = {
        "id": "3501",
        "content": "Buy milk",
        "description": "",
        "project_id": "226095",
        "is_completed": False,
        "priority": 1,
    }

    result = db_tasks.insert_task(content="Buy milk", project_id="226095")

    assert result["id"] == "3501"
    assert result["content"] == "Buy milk"
    assert result["project_id"] == "226095"
    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint == TodoistEndpoints.CREATE_TASK
    assert spec_arg.json_body is not None
    assert spec_arg.json_body["content"] == "Buy milk"
    assert spec_arg.json_body["project_id"] == "226095"
    assert mock_request_json.call_args.kwargs["operation_name"] == "create task"


def test_insert_task_signature_parameters(db_tasks):
    signature = inspect.signature(db_tasks.insert_task)
    expected_params = [
        "content",
        "description",
        "project_id",
        "section_id",
        "parent_id",
        "order",
        "labels",
        "priority",
        "due_string",
        "due_date",
        "due_datetime",
        "due_lang",
        "assignee_id",
        "duration",
        "duration_unit",
        "deadline_date",
        "deadline_lang",
    ]

    actual_params = list(signature.parameters)
    for param in expected_params:
        assert param in actual_params, (
            f"Parameter '{param}' should be in insert_task signature"
        )


@patch("todoist.database.db_tasks.TodoistAPIClient.request")
def test_remove_task(mock_request, db_tasks):
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
    assert mock_request.call_count == 2
    spec_arg = mock_request.call_args_list[-1].args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint.url.endswith("/task123")
    assert (
        mock_request.call_args_list[-1].kwargs["operation_name"]
        == "delete task task123"
    )


@patch("todoist.database.db_tasks.TodoistAPIClient.request")
def test_remove_task_refuses_literal_star_space_title(mock_request, db_tasks):
    mock_request.return_value = EndpointCallResult(
        endpoint=TodoistEndpoints.GET_TASK.format(task_id="context-1"),
        request_headers={},
        request_params={},
        status_code=200,
        elapsed=0.1,
        text='{"id":"context-1","content":"* Durable context"}',
        json={"id": "context-1", "content": "* Durable context"},
    )

    assert db_tasks.remove_task("context-1") is False
    assert mock_request.call_count == 1
    assert mock_request.call_args.kwargs["operation_name"] == "fetch task context-1"


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_fetch_task_by_id(mock_request_json, db_tasks):
    mock_request_json.return_value = {
        "id": "2995104339",
        "content": "Buy Milk",
        "description": "",
        "project_id": "2203306141",
        "is_completed": False,
        "priority": 1,
    }

    result = db_tasks.fetch_task_by_id("2995104339")

    assert result["id"] == "2995104339"
    assert result["content"] == "Buy Milk"
    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint.url.endswith("/2995104339")
    assert (
        mock_request_json.call_args.kwargs["operation_name"] == "fetch task 2995104339"
    )


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_insert_task_from_template_valid_overrides(
    mock_request_json, db_tasks, sample_task_entry
):
    mock_request_json.return_value = {"id": "new_task_id"}
    template_task = Task(id="template_task", task_entry=sample_task_entry)

    result = db_tasks.insert_task_from_template(
        template_task, content="New Task Content", priority=3
    )

    assert result["id"] == "new_task_id"
    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.json_body is not None
    assert spec_arg.json_body["content"] == "New Task Content"
    assert spec_arg.json_body["priority"] == 3


def test_insert_task_from_template_invalid_overrides(db_tasks, sample_task_entry):
    template_task = Task(id="template_task", task_entry=sample_task_entry)

    result = db_tasks.insert_task_from_template(
        template_task, invalid_param="should_not_work"
    )

    assert result["error"] == "Invalid overrides"


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_insert_tasks_empty_list(mock_request_json, db_tasks):
    result = db_tasks.insert_tasks([])

    assert result == []
    mock_request_json.assert_not_called()


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_insert_tasks_single_task(mock_request_json, db_tasks):
    mock_request_json.return_value = {
        "id": "task1",
        "content": "Test Task 1",
        "project_id": "project123",
        "priority": 1,
    }

    results = db_tasks.insert_tasks(
        [{"content": "Test Task 1", "project_id": "project123"}]
    )

    assert len(results) == 1
    assert results[0]["id"] == "task1"
    assert results[0]["content"] == "Test Task 1"
    mock_request_json.assert_called_once()


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_insert_tasks_multiple_tasks(mock_request_json, db_tasks):
    def mock_response_side_effect(spec, **_kwargs):
        content = spec.json_body.get("content", "")
        priority = spec.json_body.get("priority")
        return {"id": f"task{priority}", "content": content, "priority": priority}

    mock_request_json.side_effect = mock_response_side_effect

    results = db_tasks.insert_tasks(
        [
            {"content": "Test Task 1", "priority": 1},
            {"content": "Test Task 2", "priority": 2},
            {"content": "Test Task 3", "priority": 3},
        ]
    )

    assert [result["id"] for result in results] == ["task1", "task2", "task3"]
    assert mock_request_json.call_count == 3


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_insert_tasks_with_failure(mock_request_json, db_tasks):
    call_count = {"count": 0}

    def mock_response_with_failure(spec, **_kwargs):
        call_count["count"] += 1
        content = spec.json_body.get("content", "")
        if "Task 2" in content:
            raise Exception("API Error")
        return {"id": f"task{call_count['count']}", "content": content}

    mock_request_json.side_effect = mock_response_with_failure

    results = db_tasks.insert_tasks(
        [
            {"content": "Test Task 1"},
            {"content": "Test Task 2"},
            {"content": "Test Task 3"},
        ]
    )

    assert len(results) == 3
    assert "id" in results[0]
    assert "id" in results[2]
    assert results[1] == {}


@patch("todoist.database.db_tasks.TodoistAPIClient.request_json")
def test_insert_tasks_preserves_order(mock_request_json, db_tasks):
    delays = {"Task 1": 0.03, "Task 2": 0.01, "Task 3": 0.02}

    def mock_response_with_delay(spec, **_kwargs):
        content = spec.json_body.get("content", "")
        for task_name, delay in delays.items():
            if task_name in content:
                time.sleep(delay)
                return {"id": task_name.lower().replace(" ", ""), "content": content}
        return {"id": "unknown", "content": content}

    mock_request_json.side_effect = mock_response_with_delay

    results = db_tasks.insert_tasks(
        [
            {"content": "Test Task 1"},
            {"content": "Test Task 2"},
            {"content": "Test Task 3"},
        ]
    )

    assert [result["id"] for result in results] == ["task1", "task2", "task3"]
