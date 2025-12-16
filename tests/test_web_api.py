"""Tests for FastAPI web dashboard endpoints."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from fastapi.testclient import TestClient

import todoist.web.api as web_api


def _stub_all_figures(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "current_tasks_types", lambda *args, **kwargs: go.Figure())
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
    web_api._state.db = object()


def test_dashboard_home_validates_weeks(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
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

