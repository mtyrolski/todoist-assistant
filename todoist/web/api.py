from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# NOTE: This file is intentionally lightweight (no Streamlit imports).
from datetime import datetime, timedelta
from typing import Any, Literal
import json
import time

import plotly.io as pio

from todoist.database.base import Database
from todoist.database.dataframe import load_activity_data
from todoist.plots import (
    cumsum_completed_tasks_periodically,
    current_tasks_types,
    plot_completed_tasks_periodically,
    plot_events_over_time,
    plot_heatmap_of_events_by_day_and_hour,
    plot_most_popular_labels,
    plot_task_lifespans,
)
from todoist.stats import p1_tasks, p2_tasks, p3_tasks, p4_tasks

# FastAPI application powering the new web dashboard.
app = FastAPI(title="Todoist Dashboard API")

# Allow the local Next.js dev server to talk to the API without CORS issues.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["health"])
async def healthcheck() -> dict[str, str]:
    """Simple readiness endpoint for the dashboard stack."""

    return {"status": "ok"}


Granularity = Literal["W", "ME", "3ME"]


def _extract_metrics(df_activity, granularity: Granularity) -> tuple[list[dict[str, Any]], str, str]:
    granularity_to_timedelta = {
        "W": timedelta(weeks=1),
        "ME": timedelta(weeks=4),
        "3ME": timedelta(weeks=12),
    }
    timespan = granularity_to_timedelta[granularity]

    end_range = df_activity.index.max().to_pydatetime()
    beg_range = end_range - timespan
    previous_beg_range = beg_range - timespan
    previous_end_range = end_range - timespan

    current_period_str = f"{beg_range.strftime('%Y-%m-%d')} to {end_range.strftime('%Y-%m-%d')}"
    previous_period_str = f"{previous_beg_range.strftime('%Y-%m-%d')} to {previous_end_range.strftime('%Y-%m-%d')}"

    def _get_total_events(beg_, end_) -> int:
        filtered_df = df_activity[(df_activity.index >= beg_) & (df_activity.index <= end_)]
        return len(filtered_df)

    def _get_total_tasks_by_type(beg_, end_, task_type: str) -> int:
        filtered_df = df_activity[(df_activity.index >= beg_) & (df_activity.index <= end_)]
        return int((filtered_df["type"] == task_type).sum())

    metric_specs: list[tuple[str, Any, bool]] = [
        ("Events", _get_total_events, False),
        ("Completed Tasks", lambda b, e: _get_total_tasks_by_type(b, e, "completed"), False),
        ("Added Tasks", lambda b, e: _get_total_tasks_by_type(b, e, "added"), False),
        ("Rescheduled Tasks", lambda b, e: _get_total_tasks_by_type(b, e, "rescheduled"), True),
    ]

    metrics: list[dict[str, Any]] = []
    for metric_name, metric_func, inverse in metric_specs:
        current_value = int(metric_func(beg_range, end_range))
        previous_value = int(metric_func(previous_beg_range, previous_end_range))
        if previous_value:
            delta_percent = round((current_value - previous_value) / previous_value * 100, 2)
        else:
            delta_percent = None
        metrics.append(
            {
                "name": metric_name,
                "value": current_value,
                "deltaPercent": delta_percent,
                "inverseDelta": inverse,
            }
        )

    return metrics, current_period_str, previous_period_str


def _fig_to_dict(fig) -> dict[str, Any]:
    return json.loads(pio.to_json(fig, validate=False, pretty=False))


class _DashboardState:
    def __init__(self) -> None:
        self.last_refresh_s: float = 0.0
        self.db: Database | None = None
        self.df_activity = None
        self.active_projects = None
        self.project_colors = None
        self.label_colors = None


_state = _DashboardState()
_STATE_TTL_S = 60.0


def _ensure_state(refresh: bool) -> None:
    now = time.time()
    if not refresh and _state.db is not None and (now - _state.last_refresh_s) < _STATE_TTL_S:
        return

    dbio = Database(".env")
    dbio.pull()
    df_activity = load_activity_data(dbio)
    active_projects = dbio.fetch_projects(include_tasks=True)
    project_colors = dbio.fetch_mapping_project_name_to_color()
    label_colors = dbio.fetch_label_colors()

    _state.db = dbio
    _state.df_activity = df_activity
    _state.active_projects = active_projects
    _state.project_colors = project_colors
    _state.label_colors = label_colors
    _state.last_refresh_s = now


@app.get("/api/dashboard/home", tags=["dashboard"])
async def dashboard_home(
    granularity: Granularity = "W",
    weeks: int = 12,
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Home dashboard payload: metrics, badges, and Plotly figures.

    Notes:
    - `weeks` controls the date range used for time-series plots (Streamlit default ~12 weeks).
    - `granularity` controls periodic aggregation where applicable.
    - `refresh=true` forces a Todoist API pull + activity reload (otherwise cached briefly).
    """
    _ensure_state(refresh=refresh)

    df_activity = _state.df_activity
    active_projects = _state.active_projects
    project_colors = _state.project_colors
    label_colors = _state.label_colors

    if df_activity is None or active_projects is None or project_colors is None or label_colors is None:
        return {"error": "Dashboard data unavailable. Run `make init_local_env` and configure `.env`."}

    end_range = df_activity.index.max().to_pydatetime()
    beg_range = end_range - timedelta(weeks=max(1, weeks))

    metrics, current_period, previous_period = _extract_metrics(df_activity, granularity)

    p1 = sum(map(p1_tasks, active_projects))
    p2 = sum(map(p2_tasks, active_projects))
    p3 = sum(map(p3_tasks, active_projects))
    p4 = sum(map(p4_tasks, active_projects))

    figures = {
        "currentTasksTypes": _fig_to_dict(current_tasks_types(active_projects)),
        "mostPopularLabels": _fig_to_dict(plot_most_popular_labels(active_projects, label_colors)),
        "taskLifespans": _fig_to_dict(plot_task_lifespans(df_activity)),
        "completedTasksPeriodically": _fig_to_dict(
            plot_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors)
        ),
        "cumsumCompletedTasksPeriodically": _fig_to_dict(
            cumsum_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors)
        ),
        "heatmapEventsByDayHour": _fig_to_dict(plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range)),
        "eventsOverTime": _fig_to_dict(plot_events_over_time(df_activity, beg_range, end_range, granularity)),
    }

    return {
        "range": {
            "beg": beg_range.strftime("%Y-%m-%d"),
            "end": end_range.strftime("%Y-%m-%d"),
            "granularity": granularity,
            "weeks": weeks,
        },
        "metrics": {"items": metrics, "currentPeriod": current_period, "previousPeriod": previous_period},
        "badges": {"p1": p1, "p2": p2, "p3": p3, "p4": p4},
        "figures": figures,
        "refreshedAt": datetime.now().isoformat(timespec="seconds"),
    }
