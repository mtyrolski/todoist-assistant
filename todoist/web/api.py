# pylint: disable=global-statement,too-many-lines

import asyncio
from collections.abc import Mapping
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4
import contextlib
import io
import json
import os
import re
from pathlib import Path

import time

import pandas as pd
import numpy as np
import plotly.io as pio
import plotly.graph_objects as go
import hydra
from loguru import logger
from omegaconf import DictConfig, OmegaConf

from todoist.api.client import RequestSpec, TodoistAPIClient, TimeoutSettings
from todoist.api.endpoints import TodoistEndpoints
from todoist.database.base import Database
from todoist.database.dataframe import load_activity_data
from todoist.database.dataframe import ADJUSTMENTS_VARIABLE_NAME
from todoist.types import Event, Project
from todoist.dashboard.plots import (
    cumsum_completed_tasks_periodically,
    plot_completed_tasks_periodically,
    plot_events_over_time,
    plot_heatmap_of_events_by_day_and_hour,
    plot_most_popular_labels,
    plot_task_lifespans,
)
from todoist.stats import p1_tasks, p2_tasks, p3_tasks, p4_tasks
from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.observer import AutomationObserver
from todoist.automations.llm_breakdown.config import BASE_SYSTEM_PROMPT, coerce_model_config
from todoist.automations.llm_breakdown.models import ProgressKey
from todoist.automations.multiplicate.automation import MultiplyConfig
from todoist.llm import MessageRole, TransformersMistral3ChatModel
from todoist.llm.llm_utils import _sanitize_text
from todoist.utils import Cache, LocalStorageError, load_config, set_tqdm_progress_callback, get_tqdm_progress_callback
from dotenv import dotenv_values, set_key, unset_key
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

    return {"status": "ok", "version": get_version()}


Granularity = Literal["W", "ME", "3ME"]


def _period_bounds(df_activity, granularity: Granularity) -> dict[str, Any]:
    granularity_to_timedelta = {
        "W": timedelta(weeks=1),
        "ME": timedelta(weeks=4),
        "3ME": timedelta(weeks=12),
    }
    timespan = granularity_to_timedelta[granularity]

    end_range = _safe_activity_anchor(df_activity)
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
_activity_backfill_attempted = False
_STATE_TTL_S = 60.0
_STATE_LOCK = asyncio.Lock()
_ADMIN_LOCK = asyncio.Lock()
_JOBS_LOCK = asyncio.Lock()
_PROGRESS_LOCK = asyncio.Lock()
_PROGRESS_TOTAL_STEPS = 3
_main_loop: asyncio.AbstractEventLoop | None = None
_TQDM_STEP_MAP = {
    "Querying project data": 1,
    "Building project hierarchy": 2,
    "Querying activity data": 1,
}

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_dir() -> Path:
    override = os.getenv("TODOIST_DATA_DIR") or os.getenv("TODOIST_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT


def _resolve_config_dir() -> Path:
    override = os.getenv("TODOIST_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / "configs"

_DATA_DIR = _resolve_data_dir()
_CONFIG_DIR = _resolve_config_dir()
_AUTOMATIONS_PATH = _CONFIG_DIR / "automations.yaml"
_TEMPLATES_REGISTRY_PATH = _CONFIG_DIR / "templates.yaml"
_TEMPLATES_DIR = _CONFIG_DIR / "templates"
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_API_KEY_PLACEHOLDERS = {
    "put your api here",
    "put your api key here",
    "your todoist api key",
}
_API_KEY_MIN_LENGTH = 20
_API_KEY_HEX_RE = re.compile(r"^[a-fA-F0-9]{32,64}$")
_API_KEY_FALLBACK_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


def _resolve_env_path() -> Path:
    cache_dir = os.getenv("TODOIST_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir).expanduser().resolve() / ".env"
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
    return _REPO_ROOT / ".env"


def _normalize_api_key(raw: str | None) -> str:
    if not raw:
        return ""
    value = str(raw).strip().strip("'\"")
    if not value:
        return ""
    if value.strip().lower() in _API_KEY_PLACEHOLDERS:
        return ""
    return value


def _looks_like_api_key(value: str) -> bool:
    if len(value) < _API_KEY_MIN_LENGTH:
        return False
    if any(char.isspace() for char in value):
        return False
    if _API_KEY_HEX_RE.fullmatch(value):
        return True
    return _API_KEY_FALLBACK_RE.fullmatch(value) is not None


def _resolve_api_key() -> str:
    env_value = _normalize_api_key(os.getenv("API_KEY"))
    if env_value:
        return env_value
    env_path = _resolve_env_path()
    if env_path.exists():
        data = dotenv_values(env_path)
        file_value = _normalize_api_key(data.get("API_KEY"))
        if file_value:
            os.environ["API_KEY"] = file_value
            return file_value
    return ""


def _mask_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


def _validate_api_token(token: str) -> tuple[bool, str | None, int | None]:
    client = TodoistAPIClient(max_attempts=1)
    spec = RequestSpec(
        endpoint=TodoistEndpoints.LIST_LABELS,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TimeoutSettings(connect=5.0, read=10.0),
        max_attempts=1,
    )
    try:
        payload = client.request_json(spec, operation_name="validate_api_token")
    except Exception as exc:  # pragma: no cover - network dependent
        return False, f"{type(exc).__name__}: {exc}", None
    label_count = len(payload) if isinstance(payload, list) else None
    return True, None, label_count


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

# === LLM CHAT QUEUE =========================================================
_CHAT_QUEUE_STATUSES = {"queued", "running", "done", "failed"}
_CHAT_ROLES = {MessageRole.SYSTEM.value, MessageRole.USER.value, MessageRole.ASSISTANT.value}
_CHAT_QUEUE_LIMIT = 200
_LLM_CHAT_TIMEOUT_S = 60 * 60
_CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant for planning and summarizing Todoist work. "
    "Be concise and ask clarifying questions when needed."
)

_LLM_CHAT_MODEL: TransformersMistral3ChatModel | None = None
_LLM_CHAT_MODEL_LOADING = False
_LLM_CHAT_MODEL_LOCK = asyncio.Lock()
_LLM_CHAT_STORAGE_LOCK = asyncio.Lock()
_LLM_CHAT_WORKER_LOCK = asyncio.Lock()
_LLM_CHAT_WORKER_RUNNING = False
_LLM_CHAT_AGENT = None
_LLM_CHAT_AGENT_LOCK = asyncio.Lock()


def _env_demo_mode() -> bool:
    value = os.getenv("TODOIST_DASHBOARD_DEMO", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _run_async_in_main_loop(coro: Any) -> Any:
    """Run an async coroutine in the main event loop from a worker thread."""
    if _main_loop is not None:
        future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
        return future.result()
    else:
        # Fallback to creating a new event loop if main loop is not set
        return asyncio.run(coro)


async def _progress_snapshot() -> dict[str, Any]:
    async with _PROGRESS_LOCK:
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


async def _set_progress(stage: str, *, step: int, total_steps: int, detail: str | None = None) -> None:
    now = _now_iso()
    async with _PROGRESS_LOCK:
        if not _progress_state.active:
            _progress_state.started_at = now
            _progress_state.error = None
        _progress_state.active = True
        _progress_state.stage = stage
        _progress_state.step = step
        _progress_state.total_steps = total_steps
        _progress_state.detail = detail
        _progress_state.updated_at = now


async def _finish_progress(error: str | None = None) -> None:
    now = _now_iso()
    async with _PROGRESS_LOCK:
        _progress_state.active = False
        _progress_state.stage = None
        _progress_state.step = 0
        _progress_state.total_steps = 0
        _progress_state.detail = None
        _progress_state.started_at = None
        _progress_state.updated_at = now
        _progress_state.error = error


def _build_tqdm_progress_callback():
    last_update = 0.0
    last_value = -1

    def _callback(desc: str, current: int, total: int, unit: str | None) -> None:
        nonlocal last_update, last_value
        now = time.time()
        if current == last_value and (now - last_update) < 0.4:
            return
        if current != total and (now - last_update) < 0.35:
            return
        last_value = current
        last_update = now
        step = _TQDM_STEP_MAP.get(desc, _progress_state.step or 1)
        unit_suffix = f" {unit}" if unit else ""
        detail = f"{desc}: {current}/{total}{unit_suffix}"
        _run_async_in_main_loop(_set_progress(
            desc or "Working",
            step=step,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail=detail,
        ))

    return _callback


def _refresh_state_sync(*, demo_mode: bool) -> None:
    global _activity_backfill_attempted
    # Reset progress state to clear any stale information from previous failed refreshes
    _run_async_in_main_loop(_finish_progress(error=None))

    previous_callback = get_tqdm_progress_callback()
    set_tqdm_progress_callback(_build_tqdm_progress_callback())

    error: str | None = None
    try:
        _run_async_in_main_loop(_set_progress(
            "Querying project data",
            step=1,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail="Fetching projects and tasks",
        ))
        dbio = Database(".env")
        dbio.pull()

        try:
            cached_events = Cache().activity.load()
        except LocalStorageError:
            cached_events = set()

        def _should_backfill(events: set[Event]) -> bool:
            if not events:
                return True
            dates = [e.date for e in events if isinstance(e.date, datetime)]
            if not dates:
                return True
            span = max(dates) - min(dates)
            return span < timedelta(weeks=12)

        if cached_events and _resolve_api_key() and not _activity_backfill_attempted:
            if _should_backfill(cached_events):
                try:
                    cfg = _read_yaml_config(_AUTOMATIONS_PATH, required=False)
                    activity_cfg = cfg.get("activity") if isinstance(cfg, DictConfig) else None
                    nweeks = 10
                    early_stop = 2
                    if isinstance(activity_cfg, Mapping):
                        nweeks = int(activity_cfg.get("nweeks_window_size", nweeks))
                        early_stop = int(activity_cfg.get("early_stop_after_n_windows", early_stop))
                    logger.info(
                        "Activity cache looks short; backfilling history (window={}w, stop={}).",
                        nweeks,
                        early_stop,
                    )
                    events = dbio.fetch_activity_adaptively(
                        nweeks_window_size=nweeks,
                        early_stop_after_n_windows=early_stop,
                        events_already_fetched=set(cached_events),
                    )
                    Cache().activity.save(set(events))
                except Exception as exc:  # pragma: no cover - network-dependent
                    logger.warning("Failed to backfill activity cache: {}", exc)
                finally:
                    _activity_backfill_attempted = True

        if not cached_events and _resolve_api_key():
            try:
                cfg = _read_yaml_config(_AUTOMATIONS_PATH, required=False)
                activity_cfg = cfg.get("activity") if isinstance(cfg, DictConfig) else None
                nweeks = 10
                early_stop = 2
                if isinstance(activity_cfg, Mapping):
                    nweeks = int(activity_cfg.get("nweeks_window_size", nweeks))
                    early_stop = int(activity_cfg.get("early_stop_after_n_windows", early_stop))
                logger.info(
                    "Activity cache empty; fetching full history (window={}w, stop={}).",
                    nweeks,
                    early_stop,
                )
                events = dbio.fetch_activity_adaptively(
                    nweeks_window_size=nweeks,
                    early_stop_after_n_windows=early_stop,
                    events_already_fetched=set(),
                )
                if not events:
                    logger.info("Adaptive fetch returned no events; attempting recent activity pages.")
                    events = dbio.fetch_activity(max_pages=2)
                Cache().activity.save(set(events))
            except Exception as exc:  # pragma: no cover - network-dependent
                logger.warning("Failed to seed activity cache: {}", exc)
            finally:
                _activity_backfill_attempted = True

        _run_async_in_main_loop(_set_progress(
            "Building project hierarchy",
            step=2,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail="Resolving roots across active and archived projects",
        ))
        try:
            df_activity = load_activity_data(dbio)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load activity data; using empty dataset: {}", exc)
            df_activity = _empty_activity_df()

        _run_async_in_main_loop(_set_progress(
            "Preparing dashboard data",
            step=3,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail="Loading metadata and caches",
        ))
        active_projects = dbio.fetch_projects(include_tasks=True)

        if demo_mode and not dbio.is_anonymized:
            from todoist.database.demo import anonymize_label_names, anonymize_project_names

            project_ori2anonym = anonymize_project_names(df_activity)
            label_ori2anonym = anonymize_label_names(active_projects)
            dbio.anonymize(project_mapping=project_ori2anonym, label_mapping=label_ori2anonym)

        if demo_mode:
            from todoist.database.demo import anonymize_activity_dates

            df_activity = anonymize_activity_dates(df_activity)

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
        set_tqdm_progress_callback(previous_callback)
        _run_async_in_main_loop(_finish_progress(error))


async def _ensure_state(refresh: bool, *, demo_mode: bool | None = None) -> None:
    global _main_loop
    desired_demo = _env_demo_mode() if demo_mode is None else demo_mode
    if not refresh and _state.db is not None and _state.demo_mode == desired_demo:
        return

    async with _STATE_LOCK:
        desired_demo = _env_demo_mode() if demo_mode is None else demo_mode
        if not refresh and _state.db is not None and _state.demo_mode == desired_demo:
            return
        # Store the main event loop for worker threads to use
        _main_loop = asyncio.get_running_loop()
        await asyncio.to_thread(_refresh_state_sync, demo_mode=desired_demo)


def _stat_file(path: str) -> dict[str, Any] | None:
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
        return {"path": path, "mtime": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"), "size": size}
    except OSError:
        return {"path": path, "mtime": None, "size": None}


def _service_statuses() -> list[dict[str, Any]]:

    api_key_set = bool(_resolve_api_key())
    cache_activity = _stat_file("activity.joblib")
    automation_log = _stat_file("automation.log")
    observer_state = _load_observer_state()
    observer_enabled = bool(observer_state.get("enabled", True))

    observer_recent = False
    if automation_log and automation_log.get("mtime"):
        try:
            log_dt = datetime.fromisoformat(automation_log["mtime"])
            observer_recent = (datetime.now() - log_dt) < timedelta(minutes=2)
        except ValueError:
            observer_recent = False

    if not observer_enabled:
        observer_status = "warn"
        observer_detail = "disabled"
    elif observer_recent:
        observer_status = "ok"
        observer_detail = "recent activity"
    else:
        observer_status = "neutral"
        observer_detail = "not detected"

    return [
        {"name": "Todoist token", "status": "ok" if api_key_set else "warn", "detail": "API_KEY set" if api_key_set else "API_KEY missing"},
        {"name": "Activity cache", "status": "ok" if cache_activity else "warn", "detail": cache_activity or "activity.joblib missing"},
        {"name": "Automation log", "status": "ok" if automation_log else "warn", "detail": automation_log or "automation.log missing"},
        {"name": "Observer", "status": observer_status, "detail": observer_detail},
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
        "activityCache": _stat_file("activity.joblib"),
        "now": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/dashboard/progress", tags=["dashboard"])
async def dashboard_progress() -> dict[str, Any]:
    """Return current data refresh progress for the dashboard."""

    return await _progress_snapshot()


def _llm_breakdown_snapshot() -> dict[str, Any]:
    payload = Cache().llm_breakdown_progress.load()
    if not isinstance(payload, dict):
        payload = {}

    results = payload.get(ProgressKey.RESULTS.value)
    results = results if isinstance(results, list) else []
    recent = results[-3:] if results else []

    return {
        "active": bool(payload.get("active")),
        "status": payload.get("status") or "idle",
        "runId": payload.get("run_id"),
        "startedAt": payload.get("started_at"),
        "updatedAt": payload.get("updated_at"),
        "tasksTotal": int(payload.get("tasks_total") or 0),
        "tasksCompleted": int(payload.get("tasks_completed") or 0),
        "tasksFailed": int(payload.get("tasks_failed") or 0),
        "tasksPending": int(payload.get("tasks_pending") or 0),
        "current": payload.get("current"),
        "error": payload.get("error"),
        "recent": recent,
    }


@app.get("/api/dashboard/llm_breakdown", tags=["dashboard"])
async def dashboard_llm_breakdown() -> dict[str, Any]:
    """Return LLM breakdown queue progress."""

    return _llm_breakdown_snapshot()


def _normalize_chat_message(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    role = str(raw.get("role") or "").strip().lower()
    if role not in _CHAT_ROLES:
        return None
    content = _sanitize_text(raw.get("content"))
    if not content:
        return None
    created_at = str(raw.get("created_at") or raw.get("createdAt") or "")
    return {"role": role, "content": content, "created_at": created_at}


def _normalize_chat_conversation(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    conv_id = str(raw.get("id") or "").strip()
    if not conv_id:
        return None
    title = _sanitize_text(raw.get("title")) or "Untitled chat"
    created_at = str(raw.get("created_at") or raw.get("createdAt") or "")
    updated_at = str(raw.get("updated_at") or raw.get("updatedAt") or created_at or "")
    messages_raw = raw.get("messages")
    messages: list[dict[str, Any]] = []
    if isinstance(messages_raw, list):
        for msg in messages_raw:
            normalized = _normalize_chat_message(msg)
            if normalized:
                messages.append(normalized)
    return {
        "id": conv_id,
        "title": title,
        "created_at": created_at,
        "updated_at": updated_at,
        "messages": messages,
    }


def _normalize_chat_queue_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("id") or "").strip()
    conversation_id = str(raw.get("conversation_id") or raw.get("conversationId") or "").strip()
    content = _sanitize_text(raw.get("content"))
    if not item_id or not conversation_id or not content:
        return None
    status = str(raw.get("status") or "queued").strip().lower()
    if status not in _CHAT_QUEUE_STATUSES:
        status = "queued"
    created_at = str(raw.get("created_at") or raw.get("createdAt") or "")
    return {
        "id": item_id,
        "conversation_id": conversation_id,
        "content": content,
        "status": status,
        "created_at": created_at,
        "started_at": raw.get("started_at") or raw.get("startedAt"),
        "finished_at": raw.get("finished_at") or raw.get("finishedAt"),
        "error": raw.get("error"),
    }


def _load_llm_chat_conversations() -> list[dict[str, Any]]:
    try:
        payload = Cache().llm_chat_conversations.load()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load LLM chat conversations: {}", exc)
        return []
    if not isinstance(payload, list):
        return []
    conversations: list[dict[str, Any]] = []
    for raw in payload:
        normalized = _normalize_chat_conversation(raw)
        if normalized:
            conversations.append(normalized)
    return conversations


def _save_llm_chat_conversations(conversations: list[dict[str, Any]]) -> None:
    try:
        Cache().llm_chat_conversations.save(conversations)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to save LLM chat conversations: {}", exc)


def _load_llm_chat_queue() -> list[dict[str, Any]]:
    try:
        payload = Cache().llm_chat_queue.load()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load LLM chat queue: {}", exc)
        return []
    if not isinstance(payload, list):
        return []
    queue_items: list[dict[str, Any]] = []
    for raw in payload:
        normalized = _normalize_chat_queue_item(raw)
        if normalized:
            queue_items.append(normalized)
    return queue_items


def _save_llm_chat_queue(items: list[dict[str, Any]]) -> None:
    try:
        Cache().llm_chat_queue.save(items)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to save LLM chat queue: {}", exc)


def _truncate_text(value: str, limit: int = 120) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _conversation_summary(conv: dict[str, Any]) -> dict[str, Any]:
    messages = conv.get("messages") or []
    last_message = None
    if messages:
        last_message = messages[-1].get("content")
        if isinstance(last_message, str):
            last_message = _truncate_text(last_message, 140)
        else:
            last_message = None
    return {
        "id": conv.get("id"),
        "title": conv.get("title"),
        "createdAt": conv.get("created_at"),
        "updatedAt": conv.get("updated_at"),
        "messageCount": len(messages),
        "lastMessage": last_message,
    }


def _queue_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "conversationId": item.get("conversation_id"),
        "content": _truncate_text(item.get("content") or "", 160),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
        "startedAt": item.get("started_at"),
        "finishedAt": item.get("finished_at"),
        "error": item.get("error"),
    }


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _expire_llm_chat_queue(queue: list[dict[str, Any]], now_dt: datetime) -> bool:
    changed = False
    cutoff = now_dt - timedelta(seconds=_LLM_CHAT_TIMEOUT_S)
    now_iso = now_dt.isoformat(timespec="seconds")
    for item in queue:
        if item.get("status") != "running":
            continue
        started_at = item.get("started_at") or item.get("created_at")
        started_dt = _parse_iso_timestamp(started_at)
        if started_dt is None:
            continue
        if started_dt <= cutoff:
            item["status"] = "failed"
            item["finished_at"] = now_iso
            item["error"] = "Timed out after 1h"
            changed = True
    return changed


def _prune_queue(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(queue) <= _CHAT_QUEUE_LIMIT:
        return queue
    to_drop = len(queue) - _CHAT_QUEUE_LIMIT
    if to_drop <= 0:
        return queue
    trimmed: list[dict[str, Any]] = []
    for item in queue:
        if to_drop and item.get("status") in {"done", "failed"}:
            to_drop -= 1
            continue
        trimmed.append(item)
    return trimmed


async def _llm_chat_model_status() -> tuple[bool, bool]:
    async with _LLM_CHAT_MODEL_LOCK:
        return _LLM_CHAT_MODEL is not None, _LLM_CHAT_MODEL_LOADING


async def _start_llm_chat_model_load() -> None:
    global _LLM_CHAT_MODEL_LOADING
    async with _LLM_CHAT_MODEL_LOCK:
        if _LLM_CHAT_MODEL is not None or _LLM_CHAT_MODEL_LOADING:
            return
        _LLM_CHAT_MODEL_LOADING = True
    asyncio.create_task(_load_llm_chat_model_task())


async def _load_llm_chat_model_task() -> None:
    global _LLM_CHAT_MODEL, _LLM_CHAT_MODEL_LOADING
    try:
        config = coerce_model_config(None)
        model = await asyncio.to_thread(TransformersMistral3ChatModel, config)
        async with _LLM_CHAT_MODEL_LOCK:
            _LLM_CHAT_MODEL = model
        await asyncio.to_thread(_build_llm_chat_agent_sync, model)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to load LLM chat model: {}", exc)
    finally:
        async with _LLM_CHAT_MODEL_LOCK:
            _LLM_CHAT_MODEL_LOADING = False
    await _maybe_start_llm_chat_worker()


def _build_chat_messages(conversation: dict[str, Any], user_content: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if _CHAT_SYSTEM_PROMPT:
        messages.append({"role": MessageRole.SYSTEM.value, "content": _CHAT_SYSTEM_PROMPT})
    for msg in conversation.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        # Skip system messages from history to avoid conflicts with the prepended system prompt
        if role in _CHAT_ROLES and content and role != MessageRole.SYSTEM.value:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": MessageRole.USER.value, "content": user_content})
    return messages


def _build_llm_chat_agent_sync(model: TransformersMistral3ChatModel) -> None:
    global _LLM_CHAT_AGENT
    try:
        from todoist.agent.context import load_local_agent_context
        from todoist.agent.graph import build_agent_graph
        from todoist.agent.repl_tool import SafePythonReplTool
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LLM chat agent unavailable: {}", exc)
        return

    cache_path = os.getenv("TODOIST_AGENT_CACHE_PATH", str(_REPO_ROOT))
    prefabs_dir = os.getenv("TODOIST_AGENT_INSTRUCTIONS_DIR", str(_REPO_ROOT / "configs/agent_instructions"))
    max_tool_loops_env = os.getenv("TODOIST_AGENT_MAX_TOOL_LOOPS", "8").strip()
    try:
        max_tool_loops = max(1, int(max_tool_loops_env))
    except ValueError:
        max_tool_loops = 8

    local_ctx = load_local_agent_context(cache_path)
    tool_ctx = {
        "events": local_ctx.events,
        "events_df": local_ctx.events_df.copy(),
        "pd": pd,
        "np": np,
    }
    python_tool = SafePythonReplTool(tool_ctx)
    agent = build_agent_graph(
        llm=model,
        python_repl=python_tool,
        prefabs_dir=prefabs_dir,
        max_tool_loops=max_tool_loops,
    )
    _LLM_CHAT_AGENT = agent


async def _maybe_start_llm_chat_worker() -> None:
    global _LLM_CHAT_WORKER_RUNNING
    async with _LLM_CHAT_WORKER_LOCK:
        if _LLM_CHAT_WORKER_RUNNING:
            return
        if _LLM_CHAT_MODEL is None:
            return
        _LLM_CHAT_WORKER_RUNNING = True
    asyncio.create_task(_run_llm_chat_queue())


async def _run_llm_chat_queue() -> None:
    global _LLM_CHAT_WORKER_RUNNING
    try:
        while True:
            async with _LLM_CHAT_MODEL_LOCK:
                model = _LLM_CHAT_MODEL
            if model is None:
                return

            async with _LLM_CHAT_STORAGE_LOCK:
                queue = _load_llm_chat_queue()
                if _expire_llm_chat_queue(queue, datetime.now()):
                    _save_llm_chat_queue(queue)
                next_item = next((item for item in queue if item.get("status") == "queued"), None)
                if next_item is None:
                    return
                next_item["status"] = "running"
                next_item["started_at"] = _now_iso()
                _save_llm_chat_queue(queue)
                conversations = _load_llm_chat_conversations()
                conversation = next(
                    (item for item in conversations if item.get("id") == next_item["conversation_id"]),
                    None,
                )

            if conversation is None:
                async with _LLM_CHAT_STORAGE_LOCK:
                    queue = _load_llm_chat_queue()
                    for item in queue:
                        if item.get("id") == next_item["id"]:
                            item["status"] = "failed"
                            item["finished_at"] = _now_iso()
                            item["error"] = "Conversation not found"
                            break
                    _save_llm_chat_queue(queue)
                continue

            async with _LLM_CHAT_AGENT_LOCK:
                agent = _LLM_CHAT_AGENT

            try:
                if agent is not None:
                    base_messages = [
                        {"role": msg.get("role"), "content": msg.get("content")}
                        for msg in (conversation.get("messages") or [])
                        if msg.get("role") and msg.get("content")
                    ]
                    state: Any = {
                        "messages": [*base_messages, {"role": MessageRole.USER.value, "content": next_item["content"]}]
                    }
                    result = await asyncio.to_thread(agent.invoke, state)
                    messages = result.get("messages") if isinstance(result, dict) else None
                    if not isinstance(messages, list):
                        raise ValueError("Agent returned invalid messages")
                    new_messages = messages[len(base_messages):] if len(messages) >= len(base_messages) else messages
                    now = _now_iso()
                    async with _LLM_CHAT_STORAGE_LOCK:
                        queue = _load_llm_chat_queue()
                        queue_item = next((item for item in queue if item.get("id") == next_item["id"]), None)
                        if queue_item is None or queue_item.get("status") != "running":
                            continue
                        queue_item["status"] = "done"
                        queue_item["finished_at"] = now
                        queue_item["error"] = None
                        _save_llm_chat_queue(queue)

                        conversations = _load_llm_chat_conversations()
                        for item in conversations:
                            if item.get("id") == next_item["conversation_id"]:
                                item.setdefault("messages", [])
                                for msg in new_messages:
                                    role = str(msg.get("role") or "")
                                    content = _sanitize_text(msg.get("content"))
                                    if not role or not content:
                                        continue
                                    item["messages"].append(
                                        {
                                            "role": role,
                                            "content": content,
                                            "created_at": now,
                                        }
                                    )
                                item["updated_at"] = now
                                break
                        _save_llm_chat_conversations(conversations)
                else:
                    messages = _build_chat_messages(conversation, next_item["content"])
                    response = await asyncio.to_thread(model.chat, messages)
                    response_text = _sanitize_text(response) or ""

                    # Only save messages if we got a non-empty response
                    if not response_text:
                        # Mark as failed if response is empty
                        async with _LLM_CHAT_STORAGE_LOCK:
                            queue = _load_llm_chat_queue()
                            queue_item = next((item for item in queue if item.get("id") == next_item["id"]), None)
                            if queue_item is not None and queue_item.get("status") == "running":
                                queue_item["status"] = "failed"
                                queue_item["finished_at"] = _now_iso()
                                queue_item["error"] = "Empty response from model"
                                _save_llm_chat_queue(queue)
                        continue

                    now = _now_iso()
                    async with _LLM_CHAT_STORAGE_LOCK:
                        queue = _load_llm_chat_queue()
                        queue_item = next((item for item in queue if item.get("id") == next_item["id"]), None)
                        if queue_item is None or queue_item.get("status") != "running":
                            continue
                        queue_item["status"] = "done"
                        queue_item["finished_at"] = now
                        queue_item["error"] = None
                        _save_llm_chat_queue(queue)

                        conversations = _load_llm_chat_conversations()
                        for item in conversations:
                            if item.get("id") == next_item["conversation_id"]:
                                item.setdefault("messages", [])
                                item["messages"].append(
                                    {
                                        "role": MessageRole.USER.value,
                                        "content": next_item["content"],
                                        "created_at": now,
                                    }
                                )
                                item["messages"].append(
                                    {
                                        "role": MessageRole.ASSISTANT.value,
                                        "content": response_text,
                                        "created_at": now,
                                    }
                                )
                                item["updated_at"] = now
                                break
                        _save_llm_chat_conversations(conversations)
            except Exception as exc:  # pragma: no cover - defensive
                async with _LLM_CHAT_STORAGE_LOCK:
                    queue = _load_llm_chat_queue()
                    for item in queue:
                        if item.get("id") == next_item["id"]:
                            if item.get("status") != "running":
                                break
                            item["status"] = "failed"
                            item["finished_at"] = _now_iso()
                            item["error"] = f"{type(exc).__name__}: {exc}"
                            break
                    _save_llm_chat_queue(queue)
                continue
    finally:
        async with _LLM_CHAT_WORKER_LOCK:
            _LLM_CHAT_WORKER_RUNNING = False


async def _llm_chat_snapshot() -> dict[str, Any]:
    enabled, loading = await _llm_chat_model_status()
    async with _LLM_CHAT_STORAGE_LOCK:
        queue = _load_llm_chat_queue()
        if _expire_llm_chat_queue(queue, datetime.now()):
            _save_llm_chat_queue(queue)
        conversations = _load_llm_chat_conversations()

    counts = {status: 0 for status in _CHAT_QUEUE_STATUSES}
    for item in queue:
        status = item.get("status")
        if status in counts:
            counts[status] += 1

    items = list(reversed(queue))[:12]
    summaries = [_conversation_summary(conv) for conv in conversations]
    summaries.sort(key=lambda item: item.get("updatedAt") or "", reverse=True)
    current = next((item for item in queue if item.get("status") == "running"), None)
    return {
        "enabled": enabled,
        "loading": loading,
        "queue": {
            "total": len(queue),
            "queued": counts["queued"],
            "running": counts["running"],
            "done": counts["done"],
            "failed": counts["failed"],
            "items": [_queue_item_payload(item) for item in items],
            "current": _queue_item_payload(current) if current else None,
        },
        "conversations": summaries,
    }


@app.get("/api/dashboard/llm_chat", tags=["dashboard"])
async def dashboard_llm_chat() -> dict[str, Any]:
    """Return LLM chat queue status and conversation summaries."""

    return await _llm_chat_snapshot()


@app.post("/api/llm_chat/enable", tags=["llm"])
async def llm_chat_enable() -> dict[str, Any]:
    """Start loading the local LLM model used for chat."""

    await _start_llm_chat_model_load()
    enabled, loading = await _llm_chat_model_status()
    return {"enabled": enabled, "loading": loading}


@app.post("/api/llm_chat/send", tags=["llm"])
async def llm_chat_send(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Queue a chat prompt for the local LLM."""

    message = _sanitize_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    enabled, loading = await _llm_chat_model_status()
    if not (enabled or loading):
        raise HTTPException(status_code=409, detail="Model not loaded. Click Enable in the dashboard first.")

    conversation_id = _sanitize_text(payload.get("conversationId") or payload.get("conversation_id"))
    now = _now_iso()

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
        conversation = None
        if conversation_id:
            conversation = next((item for item in conversations if item.get("id") == conversation_id), None)
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            conversation_id = str(uuid4())
            title = _truncate_text(message, 80)
            conversation = {
                "id": conversation_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }
            conversations.append(conversation)

        conversation["updated_at"] = now

        queue = _load_llm_chat_queue()
        item = {
            "id": str(uuid4()),
            "conversation_id": conversation_id,
            "content": message,
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
        queue.append(item)
        queue = _prune_queue(queue)
        _save_llm_chat_queue(queue)
        _save_llm_chat_conversations(conversations)

    if enabled or loading:
        await _maybe_start_llm_chat_worker()
    return {
        "queued": True,
        "item": _queue_item_payload(item),
        "conversationId": conversation_id,
    }


@app.get("/api/llm_chat/conversations/{conversation_id}", tags=["llm"])
async def llm_chat_conversation(conversation_id: str) -> dict[str, Any]:
    """Fetch a conversation transcript."""

    # Validate conversation_id format (should be a valid UUID)
    try:
        UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid conversation ID format") from exc

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
    conversation = next((item for item in conversations if item.get("id") == conversation_id), None)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": conversation.get("id"),
        "title": conversation.get("title"),
        "createdAt": conversation.get("created_at"),
        "updatedAt": conversation.get("updated_at"),
        "messages": [
            {
                "role": msg.get("role"),
                "content": msg.get("content"),
                "createdAt": msg.get("created_at"),
            }
            for msg in conversation.get("messages") or []
        ],
    }


def _parse_yyyy_mm_dd(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Dates must use YYYY-MM-DD format") from exc


def _safe_activity_anchor(df_activity) -> datetime:
    if df_activity is None or df_activity.empty:
        return datetime.now()
    try:
        max_value = pd.to_datetime(df_activity.index).max()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Failed to resolve activity anchor; defaulting to now: {}", exc)
        return datetime.now()
    if pd.isna(max_value):
        return datetime.now()
    if isinstance(max_value, pd.Timestamp):
        return max_value.to_pydatetime()
    if isinstance(max_value, datetime):
        return max_value
    try:
        return datetime.fromisoformat(str(max_value))
    except ValueError:
        return datetime.now()


def _empty_activity_df() -> pd.DataFrame:
    df = pd.DataFrame(
        columns=[
            "id",
            "title",
            "type",
            "parent_project_id",
            "parent_project_name",
            "root_project_id",
            "root_project_name",
            "parent_item_id",
            "task_id",
            "date",
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


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

    end_range = _safe_activity_anchor(df_activity)
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
    - `refresh=true` forces a Todoist API pull + activity reload (otherwise cached state is reused).
    """
    await _ensure_state(refresh=refresh)

    df_activity = _state.df_activity
    active_projects = _state.active_projects
    project_colors = _state.project_colors
    label_colors = _state.label_colors

    if df_activity is None or active_projects is None or project_colors is None or label_colors is None:
        return {"error": "Dashboard data unavailable. Please ensure the database is configured and accessible."}

    no_data = df_activity.empty
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
        f"no_data={int(no_data)}",
    )
    cached = _state.home_payload_cache.get(cache_key)
    if cached and not refresh:
        return cached

    anchor_dt = _safe_activity_anchor(df_activity)
    last_week_beg, last_week_end, last_week_label = _last_completed_week_bounds(anchor_dt)

    if no_data:
        figures = {}
        parent_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
        root_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
    else:
        figures = {
            "mostPopularLabels": _fig_to_dict(plot_most_popular_labels(active_projects, label_colors)),
            "taskLifespans": _fig_to_dict(plot_task_lifespans(df_activity)),
            "completedTasksPeriodically": _fig_to_dict(
                plot_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors)
            ),
            "cumsumCompletedTasksPeriodically": _fig_to_dict(
                cumsum_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors)
            ),
            "heatmapEventsByDayHour": _fig_to_dict(
                plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range)
            ),
            "eventsOverTime": _fig_to_dict(plot_events_over_time(df_activity, beg_range, end_range, granularity)),
        }
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
        "noData": no_data,
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
            "items": []
            if no_data
            else _compute_insights(df_activity, beg=last_week_beg, end=last_week_end, project_colors=project_colors),
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
    config = load_config("automations", str(_CONFIG_DIR.resolve()))
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

    try:
        automations = _load_automations()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load automations: {}", exc)
        return {"automations": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"automations": [_automation_launch_metadata(a) for a in automations]}


@app.get("/api/admin/api_token", tags=["admin"])
async def admin_api_token_status() -> dict[str, Any]:
    token = _resolve_api_key()
    env_path = _resolve_env_path()
    return {
        "configured": bool(token),
        "masked": _mask_api_key(token),
        "envPath": str(env_path),
    }


@app.post("/api/admin/api_token", tags=["admin"])
async def admin_set_api_token(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    token = _normalize_api_key(payload.get("token"))
    if not token:
        raise HTTPException(status_code=400, detail="API token is required.")
    if not _looks_like_api_key(token):
        raise HTTPException(
            status_code=400,
            detail="API token looks invalid. Use the Todoist API token (no spaces, at least 20 characters).",
        )
    validate = payload.get("validate", True)
    labels_count = None
    if validate:
        ok, detail, labels_count = _validate_api_token(token)
        if not ok:
            status = 400 if detail and ("403" in detail or "401" in detail) else 502
            raise HTTPException(status_code=status, detail=f"API token validation failed: {detail}")
    env_path = _resolve_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(env_path), "API_KEY", token)
    os.environ["API_KEY"] = token
    return {
        "configured": True,
        "masked": _mask_api_key(token),
        "envPath": str(env_path),
        "validated": bool(validate),
        "labelsCount": labels_count,
    }


@app.post("/api/admin/api_token/validate", tags=["admin"])
async def admin_validate_api_token(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    token = _normalize_api_key(payload.get("token")) or _resolve_api_key()
    if not token:
        return {"configured": False, "valid": False, "detail": "API token missing."}
    ok, detail, labels_count = _validate_api_token(token)
    return {
        "configured": True,
        "valid": ok,
        "detail": detail or "",
        "masked": _mask_api_key(token),
        "labelsCount": labels_count,
    }


@app.delete("/api/admin/api_token", tags=["admin"])
async def admin_clear_api_token() -> dict[str, Any]:
    env_path = _resolve_env_path()
    if env_path.exists():
        unset_key(str(env_path), "API_KEY")
    os.environ.pop("API_KEY", None)
    return {"configured": False, "masked": "", "envPath": str(env_path)}


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


def _load_observer_state() -> dict[str, Any]:
    try:
        payload = Cache().observer_state.load()
    except LocalStorageError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return payload


def _serialize_observer_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", True))
    return {
        "enabled": enabled,
        "updatedAt": payload.get("updatedAt"),
        "lastRunAt": payload.get("lastRunAt"),
        "lastDurationSeconds": payload.get("lastDurationSeconds"),
        "lastEvents": payload.get("lastEvents"),
        "lastStatus": payload.get("lastStatus"),
        "lastError": payload.get("lastError"),
    }


def _build_observer(db: Database) -> AutomationObserver:
    config = load_config("automations", str(_CONFIG_DIR.resolve()))
    activity_automation: Activity = hydra.utils.instantiate(cast(DictConfig, config).activity)
    automations: list[Automation] = hydra.utils.instantiate(cast(DictConfig, config).automations)
    short_automations = [auto for auto in automations if not isinstance(auto, Activity)]
    return AutomationObserver(db=db, automations=short_automations, activity=activity_automation)


@app.get("/api/admin/observer", tags=["admin"])
async def admin_observer_state() -> dict[str, Any]:
    return _serialize_observer_state(_load_observer_state())


@app.post("/api/admin/observer", tags=["admin"])
async def admin_set_observer(enabled: bool = Body(..., embed=True)) -> dict[str, Any]:
    async with _ADMIN_LOCK:
        state = _load_observer_state()
        state["enabled"] = bool(enabled)
        state["updatedAt"] = _now_iso()
        Cache().observer_state.save(state)
    return _serialize_observer_state(state)


@app.post("/api/admin/observer/run", tags=["admin"])
async def admin_run_observer(force: bool = False) -> dict[str, Any]:
    async with _ADMIN_LOCK:
        state = _load_observer_state()
        enabled = bool(state.get("enabled", True))
        if not enabled and not force:
            raise HTTPException(status_code=409, detail="Observer is disabled")

        started_at = datetime.now()
        dbio = Database(".env")
        try:
            dbio.pull()
            observer = _build_observer(dbio)
            new_events = await asyncio.to_thread(observer.run_once)
            status = "ran" if new_events > 0 else "idle"
            state.update(
                {
                    "lastStatus": status,
                    "lastEvents": int(new_events),
                    "lastError": None,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            state.update(
                {
                    "lastStatus": "failed",
                    "lastEvents": None,
                    "lastError": f"{type(exc).__name__}: {exc}",
                }
            )
            raise HTTPException(status_code=500, detail=state["lastError"]) from exc
        finally:
            dbio.reset()
            finished_at = datetime.now()
            state["lastRunAt"] = finished_at.isoformat(timespec="seconds")
            state["lastDurationSeconds"] = round((finished_at - started_at).total_seconds(), 3)
            state["updatedAt"] = _now_iso()
            Cache().observer_state.save(state)

    return {"state": _serialize_observer_state(state)}


def _log_files() -> list[dict[str, Any]]:
    log_files: list[dict[str, Any]] = []
    for log_path in _DATA_DIR.rglob("*.log"):
        if not log_path.is_file():
            continue
        try:
            stat = log_path.stat()
        except OSError:
            continue
        if stat.st_size <= 0:
            continue
        try:
            rel_path = log_path.relative_to(_DATA_DIR)
        except ValueError:
            rel_path = log_path.name
        log_files.append(
            {
                "path": str(rel_path),
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return sorted(log_files, key=lambda x: x["path"])

def _safe_data_path(rel_path: str, *, suffix: str | None = None) -> Path:
    candidate = (_DATA_DIR / rel_path).resolve()
    if _DATA_DIR not in candidate.parents and candidate != _DATA_DIR:
        raise HTTPException(status_code=400, detail="Path must be within data directory")
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
    abs_path = _safe_data_path(path, suffix=".log")
    stat = abs_path.stat()
    payload = _read_log_file(abs_path, tail_lines=tail_lines, page=page)
    return {
        "path": str(abs_path.relative_to(_DATA_DIR)),
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        **payload,
    }


def _available_mapping_files() -> list[str]:
    personal_dir = _DATA_DIR / "personal"
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
    personal_dir = _DATA_DIR / "personal"
    personal_dir.mkdir(parents=True, exist_ok=True)
    target = _safe_data_path(str(Path("personal") / filename), suffix=".py")
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
    target = _safe_data_path(str(Path("personal") / filename), suffix=".py")
    target.write_text(_generate_adjustment_file_content(mappings), encoding="utf-8")


def _read_yaml_config(path: Path, *, required: bool = True) -> DictConfig:
    if not path.exists():
        if required:
            raise HTTPException(status_code=404, detail=f"Missing config file: {path.name}")
        return OmegaConf.create({})
    try:
        loaded = OmegaConf.load(path)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to read {path.name}: {exc}") from exc
    if loaded is None:
        return OmegaConf.create({})
    return cast(DictConfig, loaded)


def _save_yaml_config(path: Path, config: DictConfig) -> None:
    try:
        OmegaConf.save(config, path, resolve=False)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to write {path.name}: {exc}") from exc


def _ensure_identifier(value: str, *, label: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned or not _IDENTIFIER_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must match /^[a-z][a-z0-9_-]*$/",
        )
    return cleaned


def _template_path(category: str, name: str) -> Path:
    safe_category = _ensure_identifier(category, label="category")
    safe_name = _ensure_identifier(name, label="template name")
    return _TEMPLATES_DIR / safe_category / f"{safe_name}.yaml"


def _template_defaults_key(category: str, name: str) -> str:
    return f"templates/{category}@{category}.{name}"


def _load_defaults_list(config: DictConfig) -> list[Any]:
    defaults = config.get("defaults")
    if defaults is None:
        return []
    data = OmegaConf.to_container(defaults, resolve=False)
    return data if isinstance(data, list) else []


def _normalize_template_node(raw: Mapping[str, Any]) -> dict[str, Any]:
    content = str(raw.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Template content is required")
    payload: dict[str, Any] = {"content": content}
    description = raw.get("description")
    if description not in (None, ""):
        payload["description"] = str(description)
    due_delta = raw.get("due_date_days_difference")
    if due_delta is None:
        due_delta = raw.get("dueDateDaysDifference")
    if due_delta not in (None, ""):
        try:
            payload["due_date_days_difference"] = int(due_delta)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="due_date_days_difference must be an integer") from exc
    children = raw.get("children") or []
    if children:
        if not isinstance(children, list):
            raise HTTPException(status_code=400, detail="children must be a list")
        payload["children"] = [_normalize_template_node(child) for child in children]
    return payload


def _template_to_camel(raw: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": raw.get("content", ""),
    }
    if raw.get("description") not in (None, ""):
        payload["description"] = raw.get("description")
    if raw.get("due_date_days_difference") not in (None, ""):
        payload["dueDateDaysDifference"] = raw.get("due_date_days_difference")
    children = raw.get("children") or []
    if isinstance(children, list) and children:
        payload["children"] = [_template_to_camel(child) for child in children if isinstance(child, Mapping)]
    return payload


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


def _llm_breakdown_settings_payload(config: DictConfig) -> dict[str, Any]:
    raw = config.get("llm_breakdown") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}

    variants_raw = data.get("variants") or {}
    variants: dict[str, Any] = {}
    if isinstance(variants_raw, Mapping):
        for key, value in variants_raw.items():
            if not isinstance(value, Mapping):
                continue
            variants[str(key)] = {
                "instruction": value.get("instruction", ""),
                "maxDepth": value.get("max_depth"),
                "maxChildren": value.get("max_children"),
                "queueDepth": value.get("queue_depth"),
            }

    return {
        "labelPrefix": data.get("label_prefix", "llm-"),
        "defaultVariant": data.get("default_variant", "breakdown"),
        "maxDepth": data.get("max_depth", 3),
        "maxChildren": data.get("max_children", 6),
        "maxTotalTasks": data.get("max_total_tasks", 60),
        "maxQueueDepth": data.get("max_queue_depth", 1),
        "autoQueueChildren": data.get("auto_queue_children", True),
        "variants": variants,
    }


@app.get("/api/admin/llm_breakdown/settings", tags=["admin"])
async def admin_llm_breakdown_settings() -> dict[str, Any]:
    config = _read_yaml_config(_AUTOMATIONS_PATH)
    return {
        "settings": _llm_breakdown_settings_payload(config),
        "basePrompt": BASE_SYSTEM_PROMPT,
    }


@app.put("/api/admin/llm_breakdown/settings", tags=["admin"])
async def admin_update_llm_breakdown_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    config = _read_yaml_config(_AUTOMATIONS_PATH)
    lb_config = config.get("llm_breakdown") or {}

    def _coerce_int(value: Any, field: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{field} must be an integer") from exc

    updates: dict[str, Any] = {}
    if "labelPrefix" in payload:
        updates["label_prefix"] = str(payload["labelPrefix"]).strip()
    if "defaultVariant" in payload:
        updates["default_variant"] = str(payload["defaultVariant"]).strip()
    if "maxDepth" in payload:
        updates["max_depth"] = _coerce_int(payload["maxDepth"], "maxDepth")
    if "maxChildren" in payload:
        updates["max_children"] = _coerce_int(payload["maxChildren"], "maxChildren")
    if "maxTotalTasks" in payload:
        updates["max_total_tasks"] = _coerce_int(payload["maxTotalTasks"], "maxTotalTasks")
    if "maxQueueDepth" in payload:
        updates["max_queue_depth"] = _coerce_int(payload["maxQueueDepth"], "maxQueueDepth")
    if "autoQueueChildren" in payload:
        updates["auto_queue_children"] = bool(payload["autoQueueChildren"])

    if "variants" in payload:
        variants_raw = payload.get("variants")
        if not isinstance(variants_raw, Mapping):
            raise HTTPException(status_code=400, detail="variants must be an object")
        variants: dict[str, Any] = {}
        for key, value in variants_raw.items():
            if not isinstance(value, Mapping):
                raise HTTPException(status_code=400, detail=f"Variant {key} must be an object")
            instruction = str(value.get("instruction", "")).strip()
            variant_payload: dict[str, Any] = {"instruction": instruction}
            if "maxDepth" in value and value.get("maxDepth") not in (None, ""):
                variant_payload["max_depth"] = _coerce_int(value.get("maxDepth"), "maxDepth")
            if "maxChildren" in value and value.get("maxChildren") not in (None, ""):
                variant_payload["max_children"] = _coerce_int(value.get("maxChildren"), "maxChildren")
            if "queueDepth" in value and value.get("queueDepth") not in (None, ""):
                variant_payload["queue_depth"] = _coerce_int(value.get("queueDepth"), "queueDepth")
            variants[str(key).strip()] = variant_payload
        updates["variants"] = variants

    if isinstance(lb_config, DictConfig):
        for key, value in updates.items():
            lb_config[key] = value
    elif isinstance(lb_config, dict):
        lb_config.update(updates)
    else:
        lb_config = updates

    if "variants" in updates or "default_variant" in updates:
        snapshot = OmegaConf.to_container(lb_config, resolve=False) if isinstance(lb_config, DictConfig) else lb_config
        default_variant = updates.get("default_variant") or (
            snapshot.get("default_variant") if isinstance(snapshot, Mapping) else None
        )
        variants_value = updates.get("variants") or (snapshot.get("variants") if isinstance(snapshot, Mapping) else None)
        if default_variant and isinstance(variants_value, Mapping) and default_variant not in variants_value:
            raise HTTPException(status_code=400, detail="defaultVariant must exist in variants")

    config["llm_breakdown"] = lb_config
    async with _ADMIN_LOCK:
        _save_yaml_config(_AUTOMATIONS_PATH, config)

    return {
        "saved": True,
        "settings": _llm_breakdown_settings_payload(config),
        "basePrompt": BASE_SYSTEM_PROMPT,
    }


def _multiplication_settings_payload(config: DictConfig) -> dict[str, Any]:
    raw = config.get("multiply") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}

    defaults = MultiplyConfig()
    config_data = data.get("config") if isinstance(data.get("config"), Mapping) else {}
    if not isinstance(config_data, Mapping):
        config_data = {}

    return {
        "flatLeafTemplate": config_data.get("flat_leaf_template", defaults.flat_leaf_template),
        "deepLeafTemplate": config_data.get("deep_leaf_template", defaults.deep_leaf_template),
        "flatLabelRegex": config_data.get("flat_label_regex", defaults.flat_label_regex),
        "deepLabelRegex": config_data.get("deep_label_regex", defaults.deep_label_regex),
    }


@app.get("/api/admin/multiplication", tags=["admin"])
async def admin_multiplication_settings() -> dict[str, Any]:
    config = _read_yaml_config(_AUTOMATIONS_PATH)
    return {"settings": _multiplication_settings_payload(config)}


@app.put("/api/admin/multiplication", tags=["admin"])
async def admin_update_multiplication_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    flat_template = str(payload.get("flatLeafTemplate", "")).strip()
    deep_template = str(payload.get("deepLeafTemplate", "")).strip()
    if not flat_template or not deep_template:
        raise HTTPException(status_code=400, detail="flatLeafTemplate and deepLeafTemplate are required")

    config = _read_yaml_config(_AUTOMATIONS_PATH)
    multiply_cfg = config.get("multiply") or {}
    existing = OmegaConf.to_container(multiply_cfg, resolve=False) if multiply_cfg else {}
    if not isinstance(existing, dict):
        existing = {}
    config_data = existing.get("config") if isinstance(existing.get("config"), Mapping) else {}
    if not isinstance(config_data, Mapping):
        config_data = {}
    config_data = dict(config_data)
    config_data["flat_leaf_template"] = flat_template
    config_data["deep_leaf_template"] = deep_template

    existing["config"] = config_data
    config["multiply"] = existing

    async with _ADMIN_LOCK:
        _save_yaml_config(_AUTOMATIONS_PATH, config)

    return {"saved": True, "settings": _multiplication_settings_payload(config)}


def _template_summary(path: Path) -> dict[str, Any]:
    cfg = _read_yaml_config(path)
    data = OmegaConf.to_container(cfg, resolve=False)
    if not isinstance(data, dict):
        data = {}
    category = path.parent.name
    name = path.stem
    raw_children = data.get("children")
    children: list[Any] = raw_children if isinstance(raw_children, list) else []
    return {
        "category": category,
        "name": name,
        "title": data.get("content", name),
        "description": data.get("description"),
        "path": str(path.relative_to(_CONFIG_DIR)),
        "label": f"template-{name}",
        "childrenCount": len(children),
    }


@app.get("/api/admin/templates", tags=["admin"])
async def admin_templates() -> dict[str, Any]:
    if not _TEMPLATES_DIR.exists():
        return {"templates": [], "categories": []}
    templates: list[dict[str, Any]] = []
    categories: set[str] = set()
    for category_dir in sorted(_TEMPLATES_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        categories.add(category_dir.name)
        for file in sorted(category_dir.glob("*.yaml")):
            templates.append(_template_summary(file))
    return {"templates": templates, "categories": sorted(categories)}


@app.get("/api/admin/templates/{category}/{name}", tags=["admin"])
async def admin_template_detail(category: str, name: str) -> dict[str, Any]:
    safe_category = _ensure_identifier(category, label="category")
    safe_name = _ensure_identifier(name, label="template name")
    path = _template_path(safe_category, safe_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    cfg = _read_yaml_config(path)
    data = OmegaConf.to_container(cfg, resolve=False)
    if not isinstance(data, dict):
        data = {}
    template_payload = cast(Mapping[str, Any], data)
    return {
        "category": safe_category,
        "name": safe_name,
        "label": f"template-{safe_name}",
        "template": _template_to_camel(template_payload),
    }


@app.post("/api/admin/templates", tags=["admin"])
async def admin_create_template(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    category = _ensure_identifier(str(payload.get("category", "")), label="category")
    name = _ensure_identifier(str(payload.get("name", "")), label="template name")
    template = payload.get("template")
    if not isinstance(template, Mapping):
        raise HTTPException(status_code=400, detail="template must be an object")

    path = _template_path(category, name)
    if path.exists():
        raise HTTPException(status_code=409, detail="Template already exists")

    normalized = _normalize_template_node(template)
    path.parent.mkdir(parents=True, exist_ok=True)
    _save_yaml_config(path, OmegaConf.create(normalized))

    templates_cfg = _read_yaml_config(_TEMPLATES_REGISTRY_PATH)
    defaults = _load_defaults_list(templates_cfg)
    entry_key = _template_defaults_key(category, name)
    if not any(isinstance(item, Mapping) and entry_key in item for item in defaults):
        defaults.append({entry_key: name})
        templates_cfg["defaults"] = defaults

    automations_cfg = _read_yaml_config(_AUTOMATIONS_PATH)
    template_cfg = automations_cfg.get("template") or {}
    task_templates = OmegaConf.to_container(template_cfg.get("task_templates"), resolve=False) if template_cfg else {}
    if not isinstance(task_templates, dict):
        task_templates = {}
    task_templates[name] = f"${{{category}.{name}}}"
    template_cfg["task_templates"] = task_templates
    automations_cfg["template"] = template_cfg
    async with _ADMIN_LOCK:
        _save_yaml_config(_TEMPLATES_REGISTRY_PATH, templates_cfg)
        _save_yaml_config(_AUTOMATIONS_PATH, automations_cfg)

    return {"created": True, "category": category, "name": name}


@app.put("/api/admin/templates/{category}/{name}", tags=["admin"])
async def admin_update_template(
    category: str,
    name: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    safe_category = _ensure_identifier(category, label="category")
    safe_name = _ensure_identifier(name, label="template name")
    template = payload.get("template")
    if not isinstance(template, Mapping):
        raise HTTPException(status_code=400, detail="template must be an object")

    path = _template_path(safe_category, safe_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    normalized = _normalize_template_node(template)
    async with _ADMIN_LOCK:
        _save_yaml_config(path, OmegaConf.create(normalized))
    return {"saved": True, "category": safe_category, "name": safe_name}


@app.delete("/api/admin/templates/{category}/{name}", tags=["admin"])
async def admin_delete_template(category: str, name: str) -> dict[str, Any]:
    safe_category = _ensure_identifier(category, label="category")
    safe_name = _ensure_identifier(name, label="template name")
    path = _template_path(safe_category, safe_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    path.unlink()

    templates_cfg = _read_yaml_config(_TEMPLATES_REGISTRY_PATH)
    defaults = _load_defaults_list(templates_cfg)
    entry_key = _template_defaults_key(safe_category, safe_name)
    defaults = [
        item for item in defaults
        if not (isinstance(item, Mapping) and entry_key in item)
    ]
    templates_cfg["defaults"] = defaults

    automations_cfg = _read_yaml_config(_AUTOMATIONS_PATH)
    template_cfg = automations_cfg.get("template") or {}
    task_templates = OmegaConf.to_container(template_cfg.get("task_templates"), resolve=False) if template_cfg else {}
    if isinstance(task_templates, dict) and safe_name in task_templates:
        del task_templates[safe_name]
    template_cfg["task_templates"] = task_templates
    automations_cfg["template"] = template_cfg
    async with _ADMIN_LOCK:
        _save_yaml_config(_TEMPLATES_REGISTRY_PATH, templates_cfg)
        _save_yaml_config(_AUTOMATIONS_PATH, automations_cfg)

    return {"deleted": True, "category": safe_category, "name": safe_name}
