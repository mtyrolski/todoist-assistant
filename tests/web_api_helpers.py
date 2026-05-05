"""Shared helpers for web API endpoint tests."""

import pandas as pd
import plotly.graph_objects as go

import todoist.web.api as web_api

# pylint: disable=protected-access


# pylint: disable=protected-access


def _stub_all_figures(monkeypatch) -> None:
    monkeypatch.setattr(
        web_api, "plot_weekly_completion_trend", lambda *args, **kwargs: go.Figure()
    )
    monkeypatch.setattr(
        web_api, "plot_task_lifespans", lambda *args, **kwargs: go.Figure()
    )
    monkeypatch.setattr(
        web_api,
        "plot_completed_tasks_periodically",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api,
        "cumsum_completed_tasks_periodically",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api,
        "plot_active_project_hierarchy",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api,
        "plot_heatmap_of_events_by_day_and_hour",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api, "plot_events_over_time", lambda *args, **kwargs: go.Figure()
    )

def _set_state_with_df(df: pd.DataFrame) -> None:
    web_api._state.df_activity = df
    web_api._state.active_projects = []
    web_api._state.project_colors = {}
    web_api._state.db = None
    web_api._state.home_payload_cache = {}

def _clear_dashboard_state() -> None:
    web_api._state.df_activity = None
    web_api._state.active_projects = None
    web_api._state.project_colors = None
    web_api._state.db = None
    web_api._state.demo_mode = False
    web_api._state.home_payload_cache = {}

def _single_event_df() -> pd.DataFrame:
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
    return df.set_index("date")
