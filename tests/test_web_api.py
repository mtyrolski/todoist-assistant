"""Tests for FastAPI web dashboard endpoints."""


import pandas as pd
import plotly.graph_objects as go
from fastapi.testclient import TestClient

import todoist.web.api as web_api

# pylint: disable=protected-access


def _stub_all_figures(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "plot_most_popular_labels", lambda *args, **kwargs: go.Figure())
    monkeypatch.setattr(web_api, "plot_task_lifespans", lambda *args, **kwargs: go.Figure())
    monkeypatch.setattr(web_api, "plot_completed_tasks_periodically", lambda *args, **kwargs: go.Figure())
    monkeypatch.setattr(web_api, "cumsum_completed_tasks_periodically", lambda *args, **kwargs: go.Figure())
    monkeypatch.setattr(web_api, "plot_heatmap_of_events_by_day_and_hour", lambda *args, **kwargs: go.Figure())
    monkeypatch.setattr(web_api, "plot_events_over_time", lambda *args, **kwargs: go.Figure())


def _set_state_with_df(df: pd.DataFrame) -> None:
    web_api._state.df_activity = df
    web_api._state.active_projects = []
    web_api._state.project_colors = {}
    web_api._state.label_colors = {}
    web_api._state.db = None


def test_dashboard_home_validates_weeks(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    df = pd.DataFrame(
        [
            {
                "date": "2025-01-15",
                "id": "e1",
                "title": "t1",
                "type": "completed",
                "parent_project_name": "A",
                "root_project_name": "A",
                "task_id": "1",
            }
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    _set_state_with_df(df)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=10000")
    assert res.status_code == 400


def test_dashboard_home_requires_beg_and_end(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    df = pd.DataFrame(
        [
            {
                "date": "2025-01-15",
                "id": "e1",
                "title": "t1",
                "type": "completed",
                "parent_project_name": "A",
                "root_project_name": "A",
                "task_id": "1",
            }
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    _set_state_with_df(df)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?beg=2025-01-01")
    assert res.status_code == 400


def test_dashboard_home_last_completed_week_parent_share(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    # Anchor date is 2025-01-15 (Wed). Last completed ISO week is 2025-01-06..2025-01-12.
    df = pd.DataFrame(
        [
            # In last completed week:
            {
                "date": "2025-01-06",
                "id": "c1",
                "title": "x",
                "type": "completed",
                "parent_project_name": "Parent A",
                "root_project_name": "Root 1",
                "task_id": "t1",
            },
            {
                "date": "2025-01-07",
                "id": "c2",
                "title": "y",
                "type": "completed",
                "parent_project_name": "Parent A",
                "root_project_name": "Root 1",
                "task_id": "t2",
            },
            {
                "date": "2025-01-08",
                "id": "c3",
                "title": "z",
                "type": "completed",
                "parent_project_name": "Parent B",
                "root_project_name": "Root 2",
                "task_id": "t3",
            },
            # Not completed:
            {
                "date": "2025-01-09",
                "id": "a1",
                "title": "n",
                "type": "added",
                "parent_project_name": "Parent A",
                "root_project_name": "Root 1",
                "task_id": "t4",
            },
            # Anchor (partial week, should be excluded from last completed week):
            {
                "date": "2025-01-15",
                "id": "c4",
                "title": "w",
                "type": "completed",
                "parent_project_name": "Parent C",
                "root_project_name": "Root 3",
                "task_id": "t5",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    _set_state_with_df(df)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=12&granularity=W")
    assert res.status_code == 200
    payload = res.json()

    last_week = payload["leaderboards"]["lastCompletedWeek"]
    assert last_week["label"] == "2025-01-06 to 2025-01-12"
    parent_items = last_week["parentProjects"]["items"]
    assert last_week["parentProjects"]["totalCompleted"] == 3

    by_name = {it["name"]: it for it in parent_items}
    assert by_name["Parent A"]["completed"] == 2
    assert by_name["Parent B"]["completed"] == 1
    assert abs(by_name["Parent A"]["percentOfCompleted"] - 66.67) < 0.02
    assert abs(by_name["Parent B"]["percentOfCompleted"] - 33.33) < 0.02


def test_dashboard_status_returns_services() -> None:
    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/status")
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload.get("services"), list)
    assert any(svc.get("name") == "Todoist token" for svc in payload["services"])


def test_openapi_includes_app_version() -> None:
    client = TestClient(web_api.app)
    res = client.get("/openapi.json")
    assert res.status_code == 200
    payload = res.json()
    assert payload["info"]["version"] == web_api.app.version
    assert payload["info"]["version"] != "0.0.0"


def test_dashboard_progress_inactive_state() -> None:
    """Test progress endpoint returns correct structure when inactive."""
    # Reset progress state to inactive
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = "2025-01-01T00:00:00"
    web_api._progress_state.detail = None
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify structure
    assert "active" in payload
    assert "stage" in payload
    assert "step" in payload
    assert "totalSteps" in payload
    assert "startedAt" in payload
    assert "updatedAt" in payload
    assert "detail" in payload
    assert "error" in payload

    # Verify inactive state
    assert payload["active"] is False
    assert payload["stage"] is None
    assert payload["step"] == 0
    assert payload["totalSteps"] == 0
    assert payload["startedAt"] is None
    assert payload["error"] is None


def test_dashboard_progress_active_state() -> None:
    """Test progress endpoint returns correct structure when active."""
    # Set progress state to active
    web_api._progress_state.active = True
    web_api._progress_state.stage = "Loading data"
    web_api._progress_state.step = 2
    web_api._progress_state.total_steps = 5
    web_api._progress_state.started_at = "2025-01-01T10:00:00"
    web_api._progress_state.updated_at = "2025-01-01T10:00:30"
    web_api._progress_state.detail = "Fetching projects"
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify active state with all fields populated
    assert payload["active"] is True
    assert payload["stage"] == "Loading data"
    assert payload["step"] == 2
    assert payload["totalSteps"] == 5
    assert payload["startedAt"] == "2025-01-01T10:00:00"
    assert payload["updatedAt"] == "2025-01-01T10:00:30"
    assert payload["detail"] == "Fetching projects"
    assert payload["error"] is None


def test_dashboard_progress_with_error() -> None:
    """Test progress endpoint returns error state correctly."""
    # Set progress state with error
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = "2025-01-01T10:05:00"
    web_api._progress_state.detail = None
    web_api._progress_state.error = "Failed to connect to API"

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify error is captured
    assert payload["active"] is False
    assert payload["error"] == "Failed to connect to API"
    assert payload["updatedAt"] == "2025-01-01T10:05:00"


def test_dashboard_progress_without_error() -> None:
    """Test progress endpoint handles state without error correctly."""
    # Set progress state without error
    web_api._progress_state.active = True
    web_api._progress_state.stage = "Processing"
    web_api._progress_state.step = 1
    web_api._progress_state.total_steps = 3
    web_api._progress_state.started_at = "2025-01-01T12:00:00"
    web_api._progress_state.updated_at = "2025-01-01T12:00:15"
    web_api._progress_state.detail = None
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify no error
    assert payload["active"] is True
    assert payload["error"] is None
    assert payload["stage"] == "Processing"
