"""Executive review API job lifecycle tests."""

import threading
import time

import pandas as pd
import pytest

from tests.web_api_helpers import _set_state_with_df
import todoist.web.api as web_api
import todoist.web.routes.dashboard as dashboard_routes


@pytest.fixture(autouse=True)
def _reset_review_run():
    dashboard_routes._EXECUTIVE_REVIEW_RUN = None
    dashboard_routes._EXECUTIVE_REVIEW_TASKS.clear()
    yield
    dashboard_routes._EXECUTIVE_REVIEW_RUN = None


def _configure_review(monkeypatch, chat):
    _set_state_with_df(pd.DataFrame())

    async def ensure_state(*, refresh: bool) -> None:
        assert refresh is False
        run = dashboard_routes._EXECUTIVE_REVIEW_RUN
        assert run is not None and run.status == "running"

    class Model:
        def chat(self, _messages):
            return chat()

    monkeypatch.setattr(web_api, "_ensure_state", ensure_state)
    monkeypatch.setattr(dashboard_routes, "resolve_llm_backend", lambda **_: "codex")
    monkeypatch.setattr(dashboard_routes, "review_context", lambda *_: {"week": 1})
    monkeypatch.setattr(dashboard_routes, "load_runtime_env_values", lambda _path: {})
    monkeypatch.setattr(
        dashboard_routes, "build_codex_chat_model", lambda *_args, **_kwargs: Model()
    )


def _wait_for_status(api_client, expected: str) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        payload = api_client.get("/api/dashboard/executive_review").json()
        if payload["status"] == expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Executive review did not reach {expected}")


def test_review_run_is_deduplicated_and_restored(monkeypatch, api_client) -> None:
    release = threading.Event()
    calls = 0

    def chat() -> str:
        nonlocal calls
        calls += 1
        assert release.wait(timeout=2)
        return "Weekly result"

    _configure_review(monkeypatch, chat)

    started = api_client.post("/api/dashboard/executive_review").json()
    duplicate = api_client.post("/api/dashboard/executive_review?refresh=true").json()
    restored = api_client.get("/api/dashboard/executive_review").json()

    assert started["status"] == "running"
    assert duplicate["runId"] == started["runId"]
    assert restored["runId"] == started["runId"]
    assert restored["loading"] is True

    release.set()
    completed = _wait_for_status(api_client, "completed")
    restored_again = api_client.get("/api/dashboard/executive_review").json()

    assert calls == 1
    assert completed["summary"] == "Weekly result"
    assert restored_again["runId"] == started["runId"]
    assert restored_again["summary"] == "Weekly result"
    assert restored_again["cached"] is True

    refreshed = api_client.post("/api/dashboard/executive_review?refresh=true").json()
    assert refreshed["runId"] != started["runId"]
    _wait_for_status(api_client, "completed")
    assert calls == 2


def test_review_failure_is_retained(monkeypatch, api_client) -> None:
    def fail() -> str:
        raise ValueError("model unavailable")

    _configure_review(monkeypatch, fail)

    run_id = api_client.post("/api/dashboard/executive_review").json()["runId"]
    failed = _wait_for_status(api_client, "failed")
    restored = api_client.get("/api/dashboard/executive_review").json()

    assert failed["runId"] == run_id
    assert failed["summary"] is None
    assert "model unavailable" in failed["detail"]
    assert restored == failed


def test_review_stays_disabled_without_codex(monkeypatch, api_client) -> None:
    monkeypatch.setattr(dashboard_routes, "resolve_llm_backend", lambda **_: "openai")

    payload = api_client.post("/api/dashboard/executive_review").json()

    assert payload == {
        "enabled": False,
        "summary": None,
        "detail": "Start with make dashboard_codex to generate the executive review.",
    }
    assert dashboard_routes._EXECUTIVE_REVIEW_RUN is None
