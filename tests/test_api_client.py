"""Tests for the Todoist API client retry behavior."""

import json
from unittest.mock import MagicMock, patch

import requests

from todoist.api.client import RequestSpec, TodoistAPIClient
from todoist.api.endpoints import TodoistEndpoints


def _response(
    status_code: int,
    *,
    payload: dict | None = None,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.headers.update(headers or {})
    response.url = TodoistEndpoints.LIST_LABELS.url
    response.request = requests.Request("GET", response.url).prepare()
    if payload is not None:
        response._content = json.dumps(payload).encode("utf-8")
    else:
        response._content = text.encode("utf-8")
    return response


def test_request_json_retries_using_retry_after_header():
    client = TodoistAPIClient(max_attempts=2)
    session = MagicMock()
    session.request.side_effect = [
        _response(429, payload={"error": "rate_limited"}, headers={"Retry-After": "7"}),
        _response(200, payload={"results": []}),
    ]
    client._session_local.session = session
    spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS)

    with patch("todoist.utils.time.sleep") as mock_sleep:
        payload = client.request_json(spec, operation_name="list labels")

    assert payload == {"results": []}
    mock_sleep.assert_called_once_with(7.0)
    assert session.request.call_count == 2


def test_request_json_retries_using_payload_retry_after():
    client = TodoistAPIClient(max_attempts=2)
    session = MagicMock()
    session.request.side_effect = [
        _response(429, payload={"retry_after": 3}),
        _response(200, payload={"results": [{"id": "label1"}]}),
    ]
    client._session_local.session = session
    spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS)

    with patch("todoist.utils.time.sleep") as mock_sleep:
        payload = client.request_json(spec, operation_name="list labels")

    assert payload == {"results": [{"id": "label1"}]}
    mock_sleep.assert_called_once_with(3.0)
    assert session.request.call_count == 2


def test_request_json_uses_rpm_hint_when_retry_after_is_missing():
    client = TodoistAPIClient(max_attempts=2, max_requests_per_minute=30)
    session = MagicMock()
    session.request.side_effect = [
        _response(429, text="Too Many Requests"),
        _response(200, payload={"results": []}),
    ]
    client._session_local.session = session
    spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS)

    with patch("todoist.utils.time.sleep") as mock_sleep:
        payload = client.request_json(spec, operation_name="list labels")

    assert payload == {"results": []}
    mock_sleep.assert_called_once_with(2.0)
    assert session.request.call_count == 2
