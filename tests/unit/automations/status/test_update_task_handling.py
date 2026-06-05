"""
Tests for update_task behavior with different API responses.
"""

# pylint: disable=protected-access

from dataclasses import dataclass
from typing import Any

from todoist.api.client import EndpointCallResult, RequestSpec
from todoist.api.endpoints import Endpoint
from todoist.database.db_tasks import DatabaseTasks


@dataclass
class _FakeClient:
    result: EndpointCallResult

    def request(
        self,
        spec: RequestSpec,
        *,
        expect_json: bool = False,
        operation_name: str | None = None,
    ) -> EndpointCallResult:
        _ = (spec, expect_json, operation_name)
        return self.result


def _result(*, status_code: int, json_body: Any | None) -> EndpointCallResult:
    return EndpointCallResult(
        endpoint=Endpoint("update_task", "POST", "https://example.test"),
        request_headers={},
        request_params={},
        status_code=status_code,
        elapsed=0.0,
        text="" if json_body is None else "{}",
        json=json_body,
    )


def test_update_task_accepts_no_content_response() -> None:
    db = DatabaseTasks()
    db._api_client = _FakeClient(_result(status_code=204, json_body=None))  # type: ignore[attr-defined]

    assert db.update_task("123", content="new") == {}


def test_update_task_returns_json_when_present() -> None:
    payload = {"id": "123", "content": "new"}
    db = DatabaseTasks()
    db._api_client = _FakeClient(_result(status_code=200, json_body=payload))  # type: ignore[attr-defined]

    assert db.update_task("123", content="new") == payload
