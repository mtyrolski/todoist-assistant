import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# NOTE: This file is intentionally lightweight (no Streamlit imports).
from datetime import datetime, timedelta
from typing import Any, Literal, cast
import json
import os
import time

import pandas as pd
import plotly.io as pio
import plotly.graph_objects as go

from todoist.database.base import Database
from todoist.database.dataframe import load_activity_data
from todoist.types import Project
from todoist.plots import (
    cumsum_completed_tasks_periodically,
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


def _extract_metrics_dict(df_activity, periods: dict[str, Any]) -> list[dict[str, Any]]:
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
    payload = pio.to_json(fig, validate=False, pretty=False)
    return json.loads(payload or "{}")


class _DashboardState:
    def __init__(self) -> None:
        self.last_refresh_s: float = 0.0
        self.db: Database | None = None
        self.df_activity: pd.DataFrame | None = None
        self.active_projects: list[Project] | None = None
        self.project_colors: dict[str, str] | None = None
        self.label_colors: dict[str, str] | None = None
        self.home_payload_cache: dict[tuple[str, ...], dict[str, Any]] = {}


_state = _DashboardState()
_STATE_TTL_S = 60.0
_STATE_LOCK = asyncio.Lock()


def _refresh_state_sync() -> None:
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
    _state.last_refresh_s = time.time()
    _state.home_payload_cache = {}


async def _ensure_state(refresh: bool) -> None:
    now = time.time()
    if not refresh and _state.db is not None and (now - _state.last_refresh_s) < _STATE_TTL_S:
        return

    async with _STATE_LOCK:
        now = time.time()
        if not refresh and _state.db is not None and (now - _state.last_refresh_s) < _STATE_TTL_S:
            return
        await asyncio.to_thread(_refresh_state_sync)


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
    # Intentionally ignore refresh: this endpoint must stay non-blocking and avoid Todoist API calls.
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


def _parse_yyyy_mm_dd(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Dates must use YYYY-MM-DD format") from exc


def _compute_plot_range(
    df_activity,
    *,
    weeks: int,
    beg: str | None,
    end: str | None,
) -> tuple[datetime, datetime]:
    if (beg is None) ^ (end is None):
        raise HTTPException(status_code=400, detail="Provide both beg and end, or neither")

    if beg is not None and end is not None:
        beg_dt = _parse_yyyy_mm_dd(beg)
        # Make `end` inclusive at the day level for dataframe slicing / plotting.
        end_dt = _parse_yyyy_mm_dd(end) + timedelta(days=1)
        if end_dt <= beg_dt:
            raise HTTPException(status_code=400, detail="end must be after beg")
        if (end_dt - beg_dt) > timedelta(weeks=260):
            raise HTTPException(status_code=400, detail="Date range must be <= 260 weeks")
        return beg_dt, end_dt

    if weeks < 1 or weeks > 260:
        raise HTTPException(status_code=400, detail="weeks must be between 1 and 260")

    end_range = df_activity.index.max().to_pydatetime()
    beg_range = end_range - timedelta(weeks=weeks)
    return beg_range, end_range


def _last_completed_week_bounds(anchor: datetime) -> tuple[datetime, datetime, str]:
    week_start = datetime.combine(anchor.date() - timedelta(days=anchor.weekday()), datetime.min.time())
    last_week_end = week_start
    last_week_start = last_week_end - timedelta(days=7)
    label = f"{last_week_start.strftime('%Y-%m-%d')} to {(last_week_end - timedelta(days=1)).strftime('%Y-%m-%d')}"
    return last_week_start, last_week_end, label


def _completed_share_leaderboard(
    df_activity,
    *,
    beg: datetime,
    end: datetime,
    column: str,
    project_colors: dict[str, str],
    limit: int = 10,
) -> dict[str, Any]:
    df_period = df_activity[(df_activity.index >= beg) & (df_activity.index < end)]
    df_completed = df_period[df_period["type"] == "completed"]
    total_completed = int(len(df_completed))

    counts = df_completed[column].fillna("").replace("", "(unknown)").value_counts().head(limit)

    items: list[dict[str, Any]] = []
    for name, completed in counts.items():
        completed_i = int(completed)
        pct = round((completed_i / total_completed) * 100, 2) if total_completed else 0.0
        items.append(
            {
                "name": name,
                "completed": completed_i,
                "percentOfCompleted": pct,
                "color": project_colors.get(name, "#808080"),
            }
        )

    fig = go.Figure(
        data=[
            go.Bar(
                x=[it["percentOfCompleted"] for it in items][::-1],
                y=[it["name"] for it in items][::-1],
                orientation="h",
                marker=dict(color=[it["color"] for it in items][::-1]),
                hovertemplate="%{y}<br>%{x:.2f}% of completed tasks<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        xaxis_title="% of completed tasks",
        yaxis_title="Project",
        height=360,
        margin=dict(l=140, r=18, t=10, b=46),
        plot_bgcolor="#111318",
        paper_bgcolor="#111318",
    )

    return {"items": items, "totalCompleted": total_completed, "figure": _fig_to_dict(fig)}


def _compute_insights(
    df_activity,
    *,
    beg: datetime,
    end: datetime,
    project_colors: dict[str, str],
) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []

    df_period = df_activity[(df_activity.index >= beg) & (df_activity.index < end)]

    # 1) Most active sub-project (completed tasks) in the completed week.
    project_col = "parent_project_name" if "parent_project_name" in df_period.columns else "root_project_name"
    df_completed = df_period[df_period["type"] == "completed"]
    if not df_completed.empty and project_col in df_completed.columns:
        counts = df_completed[project_col].fillna("").replace("", "(unknown)").value_counts()
        if not counts.empty:
            name = str(counts.index[0])
            completed_i = int(counts.iloc[0])
            insights.append(
                {
                    "title": "Most active project",
                    "value": name,
                    "detail": f"{completed_i} completed tasks (last week)",
                    "color": project_colors.get(name),
                }
            )

    # 2) Most rescheduled sub-project (proxy for churn).
    df_rescheduled = df_period[df_period["type"] == "rescheduled"]
    if not df_rescheduled.empty and project_col in df_rescheduled.columns:
        counts = df_rescheduled[project_col].fillna("").replace("", "(unknown)").value_counts()
        if not counts.empty:
            name = str(counts.index[0])
            rescheduled_i = int(counts.iloc[0])
            insights.append(
                {
                    "title": "Most rescheduled project",
                    "value": name,
                    "detail": f"{rescheduled_i} reschedules (last week)",
                    "color": project_colors.get(name),
                }
            )

    # 3) Busiest day (all events).
    try:
        if not df_period.empty:
            day_counts = pd.Series(pd.to_datetime(df_period.index).day_name()).value_counts()
            if not day_counts.empty:
                day = str(day_counts.index[0])
                cnt = int(day_counts.iloc[0])
                insights.append({"title": "Busiest day", "value": day, "detail": f"{cnt} events (last week)"})
    except Exception:
        pass

    # 4) Added vs completed (throughput).
    try:
        added_i = int((df_period["type"] == "added").sum())
        completed_i = int((df_period["type"] == "completed").sum())
        ratio = round((completed_i / added_i), 2) if added_i else None
        insights.append(
            {
                "title": "Added vs completed",
                "value": f"{added_i} / {completed_i}",
                "detail": f"Completion/added ratio: {ratio}" if ratio is not None else "No added tasks (last week)",
            }
        )
    except Exception:
        pass

    # 5) Peak hour (all events) in the completed week.
    try:
        if not df_period.empty:
            hours = pd.to_datetime(df_period.index).to_series(index=df_period.index).dt.hour
            hour_counts = hours.value_counts()
            if not hour_counts.empty:
                peak_hour_raw = hour_counts.index.to_list()[0]
                peak_hour = int(peak_hour_raw)
                insights.append(
                    {
                        "title": "Peak hour",
                        "value": f"{peak_hour:02d}:00",
                        "detail": "Most events (selected range)",
                    }
                )
    except Exception:
        pass

    return insights[:4]


@app.get("/api/dashboard/home", tags=["dashboard"])
async def dashboard_home(
    granularity: Granularity = "W",
    weeks: int = 12,
    beg: str | None = None,
    end: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Home dashboard payload: metrics, badges, and Plotly figures.

    Notes:
    - `weeks` controls the date range used for time-series plots (Streamlit default ~12 weeks).
    - `beg`/`end` (YYYY-MM-DD) override `weeks` when provided.
    - `granularity` controls periodic aggregation where applicable.
    - `refresh=true` forces a Todoist API pull + activity reload (otherwise cached briefly).
    """
    await _ensure_state(refresh=refresh)

    df_activity = _state.df_activity
    active_projects = _state.active_projects
    project_colors = _state.project_colors
    label_colors = _state.label_colors

    if df_activity is None or active_projects is None or project_colors is None or label_colors is None:
        return {"error": "Dashboard data unavailable. Please ensure the database is configured and accessible."}

    beg_range, end_range = _compute_plot_range(df_activity, weeks=weeks, beg=beg, end=end)
    beg_label = beg if beg is not None else beg_range.strftime("%Y-%m-%d")
    end_label = end if end is not None else end_range.strftime("%Y-%m-%d")

    periods = _period_bounds(df_activity, granularity)
    metrics = _extract_metrics_dict(df_activity, periods)

    p1 = sum(map(p1_tasks, active_projects))
    p2 = sum(map(p2_tasks, active_projects))
    p3 = sum(map(p3_tasks, active_projects))
    p4 = sum(map(p4_tasks, active_projects))

    cache_key = (
        "home",
        f"g={granularity}",
        f"beg={beg_label}",
        f"end={end_label}",
    )
    cached = _state.home_payload_cache.get(cache_key)
    if cached and not refresh:
        return cached

    figures = {
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

    anchor_dt = cast(datetime, pd.Timestamp(cast(Any, df_activity.index.max())).to_pydatetime())
    last_week_beg, last_week_end, last_week_label = _last_completed_week_bounds(anchor_dt)
    parent_completed_share = _completed_share_leaderboard(
        df_activity,
        beg=last_week_beg,
        end=last_week_end,
        column="parent_project_name",
        project_colors=project_colors,
    )
    root_completed_share = _completed_share_leaderboard(
        df_activity,
        beg=last_week_beg,
        end=last_week_end,
        column="root_project_name",
        project_colors=project_colors,
    )

    payload = {
        "range": {
            "beg": beg_label,
            "end": end_label,
            "granularity": granularity,
            "weeks": weeks,
        },
        "metrics": {
            "items": metrics,
            "currentPeriod": periods["currentLabel"],
            "previousPeriod": periods["previousLabel"],
        },
        "badges": {"p1": p1, "p2": p2, "p3": p3, "p4": p4},
        "insights": {
            "label": last_week_label,
            "items": _compute_insights(df_activity, beg=last_week_beg, end=last_week_end, project_colors=project_colors),
        },
        "leaderboards": {
            "lastCompletedWeek": {
                "label": last_week_label,
                "beg": last_week_beg.strftime("%Y-%m-%d"),
                "end": (last_week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
                "parentProjects": parent_completed_share,
                "rootProjects": root_completed_share,
            }
        },
        "figures": figures,
        "refreshedAt": datetime.now().isoformat(timespec="seconds"),
    }
    _state.home_payload_cache[cache_key] = payload
    return payload
