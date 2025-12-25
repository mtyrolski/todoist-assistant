import asyncio
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# NOTE: This file is intentionally lightweight (dashboard API).
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast
from uuid import uuid4
import contextlib
import io
import json
import os
from pathlib import Path
from threading import Lock
import time

import pandas as pd
import plotly.io as pio
import plotly.graph_objects as go
import hydra
from loguru import logger
from omegaconf import DictConfig

from todoist.database.base import Database
from todoist.database.dataframe import load_activity_data
from todoist.database.dataframe import ADJUSTMENTS_VARIABLE_NAME
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
from todoist.automations.base import Automation
from todoist.utils import Cache, load_config
from todoist.version import get_version

# FastAPI application powering the new web dashboard.
app = FastAPI(title="Todoist Dashboard API", version=get_version())

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
        self.demo_mode: bool = False


@dataclass
class _ProgressState:
    active: bool = False
    stage: str | None = None
    step: int = 0
    total_steps: int = 0
    started_at: str | None = None
    updated_at: str | None = None
    detail: str | None = None
    error: str | None = None


_state = _DashboardState()
_progress_state = _ProgressState()
_STATE_TTL_S = 60.0
_STATE_LOCK = asyncio.Lock()
_ADMIN_LOCK = asyncio.Lock()
_JOBS_LOCK = asyncio.Lock()
_PROGRESS_LOCK = Lock()
_PROGRESS_TOTAL_STEPS = 3

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class _AdminJob:
    id: str
    kind: str
    status: str  # queued | running | done | failed
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: Any | None = None
    error: str | None = None


_JOBS: dict[str, _AdminJob] = {}


def _env_demo_mode() -> bool:
    value = os.getenv("TODOIST_DASHBOARD_DEMO", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _progress_snapshot() -> dict[str, Any]:
    with _PROGRESS_LOCK:
        return {
            "active": _progress_state.active,
            "stage": _progress_state.stage,
            "step": _progress_state.step,
            "totalSteps": _progress_state.total_steps,
            "startedAt": _progress_state.started_at,
            "updatedAt": _progress_state.updated_at,
            "detail": _progress_state.detail,
            "error": _progress_state.error,
        }


def _set_progress(stage: str, *, step: int, total_steps: int, detail: str | None = None) -> None:
    now = _now_iso()
    with _PROGRESS_LOCK:
        if not _progress_state.active:
            _progress_state.started_at = now
            _progress_state.error = None
        _progress_state.active = True
        _progress_state.stage = stage
        _progress_state.step = step
        _progress_state.total_steps = total_steps
        _progress_state.detail = detail
        _progress_state.updated_at = now


def _finish_progress(error: str | None = None) -> None:
    now = _now_iso()
    with _PROGRESS_LOCK:
        _progress_state.active = False
        _progress_state.stage = None
        _progress_state.step = 0
        _progress_state.total_steps = 0
        _progress_state.detail = None
        _progress_state.started_at = None
        _progress_state.updated_at = now
        _progress_state.error = error


def _refresh_state_sync(*, demo_mode: bool) -> None:
    error: str | None = None
    try:
        _set_progress(
            "Querying project data",
            step=1,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail="Fetching projects and tasks",
        )
        dbio = Database(".env")
        dbio.pull()

        _set_progress(
            "Building project hierarchy",
            step=2,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail="Resolving roots across active and archived projects",
        )
        df_activity = load_activity_data(dbio)

        _set_progress(
            "Preparing dashboard data",
            step=3,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail="Loading metadata and caches",
        )
        active_projects = dbio.fetch_projects(include_tasks=True)

        if demo_mode and not dbio.is_anonymized:
            from todoist.database.demo import anonymize_label_names, anonymize_project_names

            project_ori2anonym = anonymize_project_names(df_activity)
            label_ori2anonym = anonymize_label_names(active_projects)
            dbio.anonymize(project_mapping=project_ori2anonym, label_mapping=label_ori2anonym)

        project_colors = dbio.fetch_mapping_project_name_to_color()
        label_colors = dbio.fetch_label_colors()

        _state.db = dbio
        _state.df_activity = df_activity
        _state.active_projects = active_projects
        _state.project_colors = project_colors
        _state.label_colors = label_colors
        _state.last_refresh_s = time.time()
        _state.home_payload_cache = {}
        _state.demo_mode = demo_mode
    except Exception as exc:  # pragma: no cover - defensive
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _finish_progress(error)


async def _ensure_state(refresh: bool, *, demo_mode: bool | None = None) -> None:
    now = time.time()
    desired_demo = _env_demo_mode() if demo_mode is None else demo_mode
    if (
        not refresh
        and _state.db is not None
        and _state.demo_mode == desired_demo
        and (now - _state.last_refresh_s) < _STATE_TTL_S
    ):
        return

    async with _STATE_LOCK:
        now = time.time()
        desired_demo = _env_demo_mode() if demo_mode is None else demo_mode
        if (
            not refresh
            and _state.db is not None
            and _state.demo_mode == desired_demo
            and (now - _state.last_refresh_s) < _STATE_TTL_S
        ):
            return
        await asyncio.to_thread(_refresh_state_sync, demo_mode=desired_demo)


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


@app.get("/api/dashboard/progress", tags=["dashboard"])
async def dashboard_progress() -> dict[str, Any]:
    """Return current data refresh progress for the dashboard."""

    return _progress_snapshot()


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
    except Exception as exc:
        logger.debug("Skipping busiest day insight: {}", exc)

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
    except Exception as exc:
        logger.debug("Skipping added vs completed insight: {}", exc)

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
    except Exception as exc:
        logger.debug("Skipping peak hour insight: {}", exc)

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
    - `weeks` controls the date range used for time-series plots (default ~12 weeks).
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


def _serialize_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return None


def _load_automations() -> list[Automation]:
    config = load_config("automations", str((_REPO_ROOT / "configs").resolve()))
    automations: list[Automation] = hydra.utils.instantiate(cast(DictConfig, config).automations)
    return automations


def _automation_launch_metadata(automation: Automation) -> dict[str, Any]:
    launches = Cache().automation_launches.load().get(automation.name, [])
    last_launch = launches[-1] if launches else None
    last_launch_iso = _serialize_dt(last_launch)
    return {
        "name": automation.name,
        "frequencyMinutes": automation.frequency,
        "isLong": getattr(automation, "is_long", False),
        "launchCount": len(launches),
        "lastLaunch": last_launch_iso,
    }


@app.get("/api/admin/automations", tags=["admin"])
async def admin_automations() -> dict[str, Any]:
    """List configured automations plus cached launch metadata."""

    automations = _load_automations()
    return {"automations": [_automation_launch_metadata(a) for a in automations]}


def _run_automation_sync(automation: Automation, *, dbio: Database) -> dict[str, Any]:
    output_stream = io.StringIO()
    started_at = datetime.now()
    with contextlib.redirect_stdout(output_stream), contextlib.redirect_stderr(output_stream):
        loguru_handler_id = logger.add(output_stream, format="{message}", level="DEBUG")
        try:
            task_delegations = automation.tick(dbio)
        finally:
            logger.remove(loguru_handler_id)
    finished_at = datetime.now()
    return {
        "name": automation.name,
        "startedAt": started_at.isoformat(timespec="seconds"),
        "finishedAt": finished_at.isoformat(timespec="seconds"),
        "durationSeconds": round((finished_at - started_at).total_seconds(), 3),
        "output": output_stream.getvalue(),
        "taskDelegations": task_delegations,
    }


@app.post("/api/admin/automations/run", tags=["admin"])
async def admin_run_automation(name: str, refresh: bool = False) -> dict[str, Any]:
    """
    Run a single automation by name (from configs/automations.yaml).

    Notes:
    - Uses the same frequency gating as the CLI/observer runner.
    - `refresh=true` forces the dashboard state to reload after the run.
    """
    async with _ADMIN_LOCK:
        automations = {a.name: a for a in _load_automations()}
        if name not in automations:
            raise HTTPException(status_code=404, detail=f"Unknown automation: {name}")

        dbio = Database(".env")
        dbio.pull()
        result = await asyncio.to_thread(_run_automation_sync, automations[name], dbio=dbio)
        dbio.reset()

        if refresh:
            await _ensure_state(refresh=True)
        return result


@app.post("/api/admin/automations/run_all", tags=["admin"])
async def admin_run_all_automations(refresh: bool = False) -> dict[str, Any]:
    """Run all configured automations sequentially."""

    async with _ADMIN_LOCK:
        dbio = Database(".env")
        dbio.pull()
        results: list[dict[str, Any]] = []
        for automation in _load_automations():
            results.append(await asyncio.to_thread(_run_automation_sync, automation, dbio=dbio))
            dbio.reset()

        if refresh:
            await _ensure_state(refresh=True)
        return {"results": results}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


async def _save_job(job: _AdminJob) -> None:
    async with _JOBS_LOCK:
        _JOBS[job.id] = job


async def _get_job(job_id: str) -> _AdminJob:
    async with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job id")
        return job


async def _update_job(job_id: str, **fields: Any) -> None:
    async with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)


@app.get("/api/admin/jobs/{job_id}", tags=["admin"])
async def admin_job(job_id: str) -> dict[str, Any]:
    job = await _get_job(job_id)
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "createdAt": job.created_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "result": job.result,
        "error": job.error,
    }


async def _run_automation_job(*, job_id: str, name: str) -> None:
    await _update_job(job_id, status="running", started_at=_now_iso())
    try:
        async with _ADMIN_LOCK:
            automations = {a.name: a for a in _load_automations()}
            if name not in automations:
                raise HTTPException(status_code=404, detail=f"Unknown automation: {name}")

            dbio = Database(".env")
            dbio.pull()
            result = await asyncio.to_thread(_run_automation_sync, automations[name], dbio=dbio)
            dbio.reset()

        await _update_job(job_id, status="done", finished_at=_now_iso(), result=result)
    except Exception as exc:  # pragma: no cover - defensive
        await _update_job(job_id, status="failed", finished_at=_now_iso(), error=f"{type(exc).__name__}: {exc}")


async def _run_all_automations_job(*, job_id: str) -> None:
    await _update_job(job_id, status="running", started_at=_now_iso())
    try:
        async with _ADMIN_LOCK:
            dbio = Database(".env")
            dbio.pull()
            results: list[dict[str, Any]] = []
            for automation in _load_automations():
                results.append(await asyncio.to_thread(_run_automation_sync, automation, dbio=dbio))
                dbio.reset()

        await _update_job(job_id, status="done", finished_at=_now_iso(), result={"results": results})
    except Exception as exc:  # pragma: no cover - defensive
        await _update_job(job_id, status="failed", finished_at=_now_iso(), error=f"{type(exc).__name__}: {exc}")


@app.post("/api/admin/automations/run_async", tags=["admin"])
async def admin_run_automation_async(name: str) -> dict[str, Any]:
    """Start an automation run in the background and return a job id."""

    job = _AdminJob(
        id=str(uuid4()),
        kind="automation",
        status="queued",
        created_at=_now_iso(),
    )
    await _save_job(job)
    asyncio.create_task(_run_automation_job(job_id=job.id, name=name))
    return {"jobId": job.id, "status": job.status}


@app.post("/api/admin/automations/run_all_async", tags=["admin"])
async def admin_run_all_automations_async() -> dict[str, Any]:
    """Start a run of all configured automations in the background and return a job id."""

    job = _AdminJob(
        id=str(uuid4()),
        kind="automations",
        status="queued",
        created_at=_now_iso(),
    )
    await _save_job(job)
    asyncio.create_task(_run_all_automations_job(job_id=job.id))
    return {"jobId": job.id, "status": job.status}


def _log_files() -> list[dict[str, Any]]:
    log_files: list[dict[str, Any]] = []
    for log_path in _REPO_ROOT.rglob("*.log"):
        if not log_path.is_file():
            continue
        try:
            stat = log_path.stat()
        except OSError:
            continue
        if stat.st_size <= 0:
            continue
        log_files.append(
            {
                "path": str(log_path.relative_to(_REPO_ROOT)),
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return sorted(log_files, key=lambda x: x["path"])


def _safe_repo_path(rel_path: str, *, suffix: str | None = None) -> Path:
    candidate = (_REPO_ROOT / rel_path).resolve()
    if _REPO_ROOT not in candidate.parents and candidate != _REPO_ROOT:
        raise HTTPException(status_code=400, detail="Path must be within repository")
    if suffix and candidate.suffix != suffix:
        raise HTTPException(status_code=400, detail=f"Path must end with {suffix}")
    return candidate


@app.get("/api/admin/logs", tags=["admin"])
async def admin_logs() -> dict[str, Any]:
    return {"logs": _log_files()}


def _read_log_file(path: Path, *, tail_lines: int, page: int) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError as exc:
        raise HTTPException(status_code=404, detail=f"Unable to read log file: {exc}") from exc

    total_lines = len(lines)
    per_page = max(1, min(2000, int(tail_lines)))
    total_pages = max(1, (total_lines + per_page - 1) // per_page)
    page_i = max(1, min(int(page), total_pages))

    end_line = total_lines - (page_i - 1) * per_page
    start_line = max(0, end_line - per_page)
    content = "".join(lines[start_line:end_line])
    return {
        "content": content,
        "page": page_i,
        "perPage": per_page,
        "totalPages": total_pages,
        "totalLines": total_lines,
    }


@app.get("/api/admin/logs/read", tags=["admin"])
async def admin_read_log(path: str, tail_lines: int = 40, page: int = 1) -> dict[str, Any]:
    abs_path = _safe_repo_path(path, suffix=".log")
    stat = abs_path.stat()
    payload = _read_log_file(abs_path, tail_lines=tail_lines, page=page)
    return {
        "path": str(abs_path.relative_to(_REPO_ROOT)),
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        **payload,
    }


def _available_mapping_files() -> list[str]:
    personal_dir = _REPO_ROOT / "personal"
    if not personal_dir.exists():
        return ["archived_root_projects.py"]

    mapping_files: list[str] = []
    for file in personal_dir.glob("*.py"):
        if file.name.startswith("__"):
            continue
        try:
            content = file.read_text(encoding="utf-8")
        except OSError:
            continue
        if ADJUSTMENTS_VARIABLE_NAME in content:
            mapping_files.append(file.name)

    return sorted(mapping_files) if mapping_files else ["archived_root_projects.py"]


def _generate_adjustment_file_content(mappings: dict[str, str]) -> str:
    content = [
        "# Adjustments for archived root projects",
        "# This file was generated by the web dashboard admin UI",
        "",
        f"{ADJUSTMENTS_VARIABLE_NAME} = {{",
    ]
    for archived_name, active_name in sorted(mappings.items()):
        content.append(f'    "{archived_name}": "{active_name}",')
    content.append("}")
    content.append("")
    return "\n".join(content)


def _load_mapping_file(filename: str) -> dict[str, str]:
    personal_dir = _REPO_ROOT / "personal"
    personal_dir.mkdir(exist_ok=True)
    target = _safe_repo_path(str(Path("personal") / filename), suffix=".py")
    if not target.exists():
        target.write_text(_generate_adjustment_file_content({}), encoding="utf-8")
        return {}

    # Match dataframe.py behavior (exec python file) so the UI shows the effective mapping.
    import importlib.util
    import sys

    module_name = "dashboard_adjustments"
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    mapping = getattr(module, ADJUSTMENTS_VARIABLE_NAME, {})
    return mapping if isinstance(mapping, dict) else {}


def _save_mapping_file(filename: str, mappings: dict[str, str]) -> None:
    target = _safe_repo_path(str(Path("personal") / filename), suffix=".py")
    target.write_text(_generate_adjustment_file_content(mappings), encoding="utf-8")


@app.get("/api/admin/project_adjustments", tags=["admin"])
async def admin_project_adjustments(file: str | None = None, refresh: bool = False) -> dict[str, Any]:
    """Return mapping files, current mapping content, and project lists for building adjustments."""

    selected = file or _available_mapping_files()[0]
    mappings = _load_mapping_file(selected)

    await _ensure_state(refresh=refresh)
    dbio = _state.db
    if dbio is None:
        raise HTTPException(status_code=500, detail="Database unavailable")

    active_projects = dbio.fetch_projects(include_tasks=False)
    archived_projects = dbio.fetch_archived_projects()

    active_root = sorted({p.project_entry.name for p in active_projects if p.project_entry.parent_id is None})
    archived_names = sorted({p.project_entry.name for p in archived_projects})
    unmapped_archived = [name for name in archived_names if name not in mappings]

    return {
        "files": _available_mapping_files(),
        "selectedFile": selected,
        "mappings": mappings,
        "activeRootProjects": active_root,
        "archivedProjects": archived_names,
        "unmappedArchivedProjects": unmapped_archived,
    }


@app.put("/api/admin/project_adjustments", tags=["admin"])
async def admin_save_project_adjustments(
    file: str,
    refresh: bool = True,
    mappings: dict[str, str] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Save mapping dict to the selected mapping file."""

    if not isinstance(mappings, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mappings.items()):
        raise HTTPException(status_code=400, detail="Body must be a JSON object of string->string mappings")

    async with _ADMIN_LOCK:
        _save_mapping_file(file, mappings)
        if refresh:
            await _ensure_state(refresh=True)
    return {"saved": True, "file": file, "count": len(mappings)}
