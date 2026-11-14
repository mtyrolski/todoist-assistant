import inspect
from unittest.mock import patch

from todometry.api import TodoistEndpoints
from todometry.api.client import RequestSpec


@patch("todometry.database.db_tasks.TodoistAPIClient.request_json")
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
