from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# NOTE: This file is intentionally lightweight (no Streamlit imports).
from datetime import datetime, timedelta
from typing import Any, Literal
import json
import os
import time

import plotly.io as pio
import plotly.graph_objects as go

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


def _period_bounds(df_activity, granularity: Granularity) -> dict[str, Any]:
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

    return {
        "beg": beg_range,
        "end": end_range,
        "prevBeg": previous_beg_range,
        "prevEnd": previous_end_range,
        "currentLabel": current_period_str,
        "previousLabel": previous_period_str,
    }


def _extract_metrics(df_activity, periods: dict[str, Any]) -> list[dict[str, Any]]:
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
        current_value = int(metric_func(periods["beg"], periods["end"]))
        previous_value = int(metric_func(periods["prevBeg"], periods["prevEnd"]))
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

    return metrics


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


def _service_statuses() -> list[dict[str, Any]]:
    def stat_file(path: str) -> dict[str, Any] | None:
        if not os.path.exists(path):
            return None
        try:
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
            return {"path": path, "mtime": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"), "size": size}
        except OSError:
            return {"path": path, "mtime": None, "size": None}

    api_key_set = bool(os.getenv("API_KEY"))
    cache_activity = stat_file("activity.joblib")
    automation_log = stat_file("automation.log")

    observer_recent = False
    if automation_log and automation_log.get("mtime"):
        try:
            log_dt = datetime.fromisoformat(automation_log["mtime"])
            observer_recent = (datetime.now() - log_dt) < timedelta(minutes=2)
        except ValueError:
            observer_recent = False

    return [
        {"name": "Todoist token", "status": "ok" if api_key_set else "warn", "detail": "API_KEY set" if api_key_set else "API_KEY missing"},
        {"name": "Activity cache", "status": "ok" if cache_activity else "warn", "detail": cache_activity or "activity.joblib missing"},
        {"name": "Automation log", "status": "ok" if automation_log else "warn", "detail": automation_log or "automation.log missing"},
        {"name": "Observer", "status": "ok" if observer_recent else "neutral", "detail": "recent activity" if observer_recent else "not detected"},
    ]


@app.get("/api/dashboard/status", tags=["dashboard"])
async def dashboard_status(refresh: bool = False) -> dict[str, Any]:
    """
    Lightweight status endpoint for UI badges (does not generate plots).
    """
    _ = refresh
    return {
        "services": _service_statuses(),
        "apiCache": {
            "lastRefresh": datetime.fromtimestamp(_state.last_refresh_s).isoformat(timespec="seconds")
            if _state.last_refresh_s
            else None
        },
        "now": datetime.now().isoformat(timespec="seconds"),
    }


def _leaderboard(df_activity, *, periods: dict[str, Any], column: str, project_colors: dict[str, str]) -> dict[str, Any]:
    df_cur = df_activity[(df_activity.index >= periods["beg"]) & (df_activity.index <= periods["end"])]
    df_prev = df_activity[(df_activity.index >= periods["prevBeg"]) & (df_activity.index <= periods["prevEnd"])]

    cur_counts = df_cur[column].fillna("").replace("", "(unknown)").value_counts()
    prev_counts = df_prev[column].fillna("").replace("", "(unknown)").value_counts()
    top_names = list(cur_counts.head(10).index)

    items: list[dict[str, Any]] = []
    for name in top_names:
        cur = int(cur_counts.get(name, 0))
        prev = int(prev_counts.get(name, 0))
        delta_pct = round((cur - prev) / prev * 100, 2) if prev else None
        items.append(
            {
                "name": name,
                "events": cur,
                "prevEvents": prev,
                "deltaPercent": delta_pct,
                "color": project_colors.get(name, "#808080"),
            }
        )

    fig = go.Figure(
        data=[
            go.Bar(
                x=[it["events"] for it in items][::-1],
                y=[it["name"] for it in items][::-1],
                orientation="h",
                marker=dict(color=[it["color"] for it in items][::-1]),
                hovertemplate="%{y}<br>%{x} events<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        xaxis_title="Events",
        yaxis_title="Project",
        height=360,
        margin=dict(l=140, r=18, t=10, b=46),
        plot_bgcolor="#111318",
        paper_bgcolor="#111318",
    )

    return {"items": items, "figure": _fig_to_dict(fig)}


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

    periods = _period_bounds(df_activity, granularity)
    metrics = _extract_metrics(df_activity, periods)

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
        "metrics": {
            "items": metrics,
            "currentPeriod": periods["currentLabel"],
            "previousPeriod": periods["previousLabel"],
        },
        "badges": {"p1": p1, "p2": p2, "p3": p3, "p4": p4},
        "leaderboards": {
            "parentProjects": _leaderboard(
                df_activity,
                periods=periods,
                column="parent_project_name",
                project_colors=project_colors,
            ),
            "rootProjects": _leaderboard(
                df_activity,
                periods=periods,
                column="root_project_name",
                project_colors=project_colors,
            ),
            "period": {"current": periods["currentLabel"], "previous": periods["previousLabel"]},
        },
        "figures": figures,
        "refreshedAt": datetime.now().isoformat(timespec="seconds"),
    }
