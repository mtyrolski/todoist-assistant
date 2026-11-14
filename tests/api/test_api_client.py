"""Tests for the Todoist API client retry behavior."""

import json
import traceback
from unittest.mock import MagicMock, patch

import pytest
import requests

from todometry.api.client import RequestSpec, TodoistAPIClient
from todometry.api.endpoints import TodoistEndpoints
from todometry.core.utils import MaxRetriesExceeded


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
        setattr(response, "_content", json.dumps(payload).encode("utf-8"))
    else:
        setattr(response, "_content", text.encode("utf-8"))
    return response


def test_request_json_retries_using_retry_after_header():
    client = TodoistAPIClient(max_attempts=2)
    session = MagicMock()
    session.request.side_effect = [
        _response(429, payload={"error": "rate_limited"}, headers={"Retry-After": "7"}),
        _response(200, payload={"results": []}),
    ]
    setattr(client.__dict__["_session_local"], "session", session)
    spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS)

    with patch("todometry.core.utils.time.sleep") as mock_sleep:
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
    setattr(client.__dict__["_session_local"], "session", session)
    spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS)

    with patch("todometry.core.utils.time.sleep") as mock_sleep:
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
    setattr(client.__dict__["_session_local"], "session", session)
    spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS)

    with patch("todometry.core.utils.time.sleep") as mock_sleep:
        payload = client.request_json(spec, operation_name="list labels")

    assert payload == {"results": []}
    mock_sleep.assert_called_once_with(2.0)
    assert session.request.call_count == 2


@pytest.mark.parametrize("failure", ["http", "json", "connection", "timeout"])
def test_failure_diagnostics_do_not_expose_tokens_or_response_bodies(failure: str) -> None:
    secret = "unique-test-token-do-not-log"
    session = MagicMock()
    if failure == "http":
        session.request.return_value = _response(401, text=f"server echoed {secret}")
    elif failure == "json":
        session.request.return_value = _response(200, text=f"invalid JSON {secret}")
    elif failure == "connection":
        session.request.side_effect = requests.ConnectionError(f"sensitive error {secret}")
    else:
        session.request.side_effect = requests.Timeout(f"sensitive timeout {secret}")
    client = TodoistAPIClient(max_attempts=1)
    setattr(client.__dict__["_session_local"], "session", session)
    spec = RequestSpec(
        endpoint=TodoistEndpoints.LIST_LABELS,
        headers={"Authorization": f"Bearer {secret}"},
    )
    with (
        patch("todometry.api.client.get_api_key", return_value=""),
        patch("todometry.api.client.logger") as client_logger,
        patch("todometry.core.utils.logger") as retry_logger,
        pytest.raises(MaxRetriesExceeded) as error,
    ):
        client.request_json(spec, operation_name="list labels")

    rendered = repr(client_logger.mock_calls) + repr(retry_logger.mock_calls)
    rendered += "".join(traceback.format_exception(error.value))
    assert secret not in rendered
    assert "list_labels" in rendered


def test_request_metadata_redacts_auth_and_debug_representations() -> None:
    secret = "unique-test-token-do-not-log"
    client = TodoistAPIClient(max_attempts=1)
    session = MagicMock()
    session.request.return_value = _response(200, payload={"echo": secret})
    setattr(client.__dict__["_session_local"], "session", session)
    spec = RequestSpec(
        endpoint=TodoistEndpoints.LIST_LABELS,
        headers={"authorization": f"Bearer {secret}", "X-Trace": "visible"},
    )

    with patch("todometry.api.client.get_api_key", return_value="stored-test-token"):
        result = client.request(spec, expect_json=True)
    assert session.request.call_args.kwargs["headers"]["authorization"] == f"Bearer {secret}"
    assert sum(key.lower() == "authorization" for key in result.request_headers) == 1
    assert result.request_headers["authorization"] != f"Bearer {secret}"
    assert result.request_headers["X-Trace"] == "visible"
    assert result.json == {"echo": secret}
    assert secret not in repr(spec)
    assert secret not in repr(result)


@pytest.mark.parametrize("failure", ["http", "json", "connection", "timeout"])
def test_sanitized_errors_do_not_retain_sensitive_exception_context(failure: str) -> None:
    secret = "unique-test-token-do-not-log"
    session = MagicMock()
    if failure == "http":
        response = _response(401, text="denied")
        response.raise_for_status = MagicMock(side_effect=requests.HTTPError(secret))
        session.request.return_value = response
    elif failure == "json":
        response = _response(200, text="invalid")
        response.json = MagicMock(side_effect=ValueError(secret))
        session.request.return_value = response
    elif failure == "connection":
        session.request.side_effect = requests.ConnectionError(secret)
    else:
        session.request.side_effect = requests.Timeout(secret)
    client = TodoistAPIClient(max_attempts=1)
    setattr(client.__dict__["_session_local"], "session", session)
    spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS)
    with (
        patch("todometry.api.client.get_api_key", return_value=""),
        patch("todometry.api.client.with_retry", side_effect=lambda fn, **_kwargs: fn()),
        patch("todometry.api.client.logger"),
        pytest.raises(RuntimeError) as error,
    ):
        client.request_json(spec)
    assert secret not in str(error.value)
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
