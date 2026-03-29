# pylint: disable=global-statement,too-many-lines

import asyncio
from collections.abc import Mapping, Sequence
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4
import contextlib
import io
import os
import re
import os.path
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import time

import pandas as pd
import numpy as np
import hydra
import httpx
from google.oauth2.credentials import Credentials
from loguru import logger
from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, Field

from todoist.api.client import RequestSpec, TodoistAPIClient, TimeoutSettings
from todoist.api.endpoints import TodoistEndpoints
from todoist.database.base import Database
from todoist.database.dataframe import load_activity_data
from todoist.database.dataframe import ADJUSTMENTS_VARIABLE_NAME
from todoist.types import Event, Project
from todoist.dashboard.plots import (
    cumsum_completed_tasks_periodically,
    plot_active_project_hierarchy,
    plot_completed_tasks_periodically,
    plot_events_over_time,
    plot_heatmap_of_events_by_day_and_hour,
    plot_task_lifespans,
    plot_weekly_completion_trend,
)
from todoist.stats import p1_tasks, p2_tasks, p3_tasks, p4_tasks
from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.gmail_tasks import GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE, GmailTasksAutomation
from todoist.automations.observer import AutomationObserver
from todoist.automations.llm_breakdown.config import (
    BASE_SYSTEM_PROMPT,
    coerce_model_config,
)
from todoist.automations.llm_breakdown.models import ProgressKey
from todoist.automations.llm_breakdown.models import TaskBreakdown, BreakdownNode
from todoist.automations.multiplicate.automation import MultiplyConfig
from todoist.llm import (
    DEFAULT_MODEL_ID,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_TRITON_MODEL_ID,
    DEFAULT_TRITON_MODEL_NAME,
    DEFAULT_TRITON_URL,
    MessageRole,
    OpenAIChatConfig,
    OpenAIResponsesChatModel,
    TritonChatConfig,
    TritonGenerateChatModel,
    TransformersMistral3ChatModel,
)
from todoist.llm.llm_utils import _sanitize_text
from todoist.dashboard_settings import (
    load_dashboard_config,
    observer_settings_payload,
    resolve_dashboard_config_path,
    update_observer_settings,
)
from todoist.web.dashboard_payload import (
    DEFAULT_URGENCY_SETTINGS,
    build_habit_tracker_payload as _build_habit_tracker_payload,
    completed_share_leaderboard as _completed_share_leaderboard,
    compute_insights as _compute_insights,
    compute_plot_range as _compute_plot_range,
    empty_activity_df as _empty_activity_df,
    evaluate_urgency_status as _evaluate_urgency_status,
    extract_metrics_dict as _extract_metrics_dict,
    fig_to_dict as _fig_to_dict,
    last_completed_week_bounds as _last_completed_week_bounds,
    normalize_activity_df as _normalize_activity_df,
    period_bounds as _period_bounds,
    safe_activity_anchor as _safe_activity_anchor,
)
from todoist.habit_tracker import extract_tracked_habit_tasks
from todoist.utils import (
    Cache,
    LocalStorageError,
    automation_log_path,
    configure_runtime_logging,
    get_log_level,
    load_config,
    set_tqdm_progress_callback,
    get_tqdm_progress_callback,
)
from todoist.env import EnvVar
from dotenv import dotenv_values, set_key, unset_key
from todoist.version import get_version

if TYPE_CHECKING:
    from todoist.agent.graph import AgentState

configure_runtime_logging(log_path=automation_log_path())

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


class _DashboardState:
    def __init__(self) -> None:
        self.last_refresh_s: float = 0.0
        self.db: Database | None = None
        self.df_activity: pd.DataFrame | None = None
        self.active_projects: list[Project] | None = None
        self.project_colors: dict[str, str] | None = None
        self.home_payload_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self.demo_mode: bool = False

    def is_ready_for(self, *, demo_mode: bool) -> bool:
        return (
            self.df_activity is not None
            and self.active_projects is not None
            and self.project_colors is not None
            and self.demo_mode == demo_mode
        )


@dataclass
class _ProgressState:
    active: bool = False
    stage: str | None = None
    step: int = 0
    total_steps: int = 0
    started_at: str | None = None
    updated_at: str | None = None
    detail: str | None = None
    sub_current: int | None = None
    sub_total: int | None = None
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
_DASHBOARD_STATE_SCHEMA_VERSION = 1
_DEMO_DASHBOARD_STATE_SCHEMA_VERSION = 2
_main_loop: asyncio.AbstractEventLoop | None = None
_TQDM_STEP_MAP = {
    "Querying project data": 1,
    "Building project hierarchy": 2,
    "Querying activity data": 1,
}

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_dir() -> Path:
    override = os.getenv(str(EnvVar.DATA_DIR)) or os.getenv(str(EnvVar.CACHE_DIR))
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT


def _resolve_config_dir() -> Path:
    override = os.getenv(str(EnvVar.CONFIG_DIR))
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / "configs"


_DATA_DIR = _resolve_data_dir()
_CONFIG_DIR = _resolve_config_dir()
_AUTOMATIONS_PATH = _CONFIG_DIR / "automations.yaml"
_DASHBOARD_CONFIG_PATH = resolve_dashboard_config_path()
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
_LOCAL_MODEL_OPTIONS = [
    {"id": DEFAULT_MODEL_ID, "label": "Ministral 3 3B Instruct"},
    {"id": "Qwen/Qwen2.5-1.5B-Instruct", "label": "Qwen 2.5 1.5B Instruct"},
    {"id": "Qwen/Qwen2.5-0.5B-Instruct", "label": "Qwen 2.5 0.5B Instruct"},
]
_OPENAI_MODEL_OPTIONS = [
    {"id": "gpt-5-mini", "label": "GPT-5 mini"},
    {"id": "gpt-5", "label": "GPT-5"},
    {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
]
_TRITON_MODEL_OPTIONS = [
    {"id": DEFAULT_TRITON_MODEL_ID, "label": "Qwen 2.5 0.5B Instruct"},
    {"id": "Qwen/Qwen2.5-1.5B-Instruct", "label": "Qwen 2.5 1.5B Instruct"},
    {"id": "Qwen/Qwen2.5-3B-Instruct", "label": "Qwen 2.5 3B Instruct"},
]


def _resolve_env_path() -> Path:
    cache_dir = os.getenv(str(EnvVar.CACHE_DIR))
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


def _normalize_timezone(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip().strip("'\"")


def _is_valid_timezone_name(value: str) -> bool:
    if not value:
        return False
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return False
    except Exception:
        return False
    return True


def _detect_system_timezone() -> str:
    local_timezone = datetime.now().astimezone().tzinfo
    if local_timezone is None:
        return "UTC"

    key = getattr(local_timezone, "key", None)
    if isinstance(key, str) and key.strip():
        return key

    timezone_name = local_timezone.tzname(None)
    if isinstance(timezone_name, str) and timezone_name.strip():
        return timezone_name

    return "UTC"


def _resolve_timezone_status() -> dict[str, Any]:
    env_path = _resolve_env_path()
    timezone_key = str(EnvVar.TIMEZONE)
    system_timezone = _detect_system_timezone()

    override = _normalize_timezone(os.getenv(timezone_key))
    if not override and env_path.exists():
        data = dotenv_values(env_path)
        override = _normalize_timezone(data.get(timezone_key))
        if override:
            os.environ[timezone_key] = override

    payload: dict[str, Any] = {
        "configured": False,
        "timezone": system_timezone,
        "source": "system",
        "override": None,
        "overrideValid": True,
        "system": system_timezone,
        "envPath": str(env_path),
    }
    if not override:
        return payload

    payload["override"] = override
    if _is_valid_timezone_name(override):
        payload["configured"] = True
        payload["timezone"] = override
        payload["source"] = "env"
        return payload

    payload["overrideValid"] = False
    payload["invalidOverride"] = override
    return payload


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

    if not isinstance(payload, dict):
        return False, f"Unexpected payload type: {type(payload).__name__}", None
    results = payload.get("results")
    if not isinstance(results, list):
        return False, "Unexpected labels response payload", None
    return True, None, len(results)


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
_CHAT_ROLES = {
    MessageRole.SYSTEM.value,
    MessageRole.USER.value,
    MessageRole.ASSISTANT.value,
}
_CHAT_QUEUE_LIMIT = 200
_LLM_CHAT_TIMEOUT_S = 60 * 60
_LLM_CHAT_BACKEND_DEFAULT = "transformers_local"
_LLM_CHAT_BACKEND_LABELS = {
    "transformers_local": "Transformers local",
    "triton_local": "Triton local",
    "openai": "OpenAI",
}
_LLM_CHAT_DEVICE_DEFAULT = "cpu"
_LLM_CHAT_DEVICE_LABELS = {
    "cpu": "CPU",
    "cuda": "GPU",
}
_CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant for planning and summarizing Todoist work. "
    "Be concise and ask clarifying questions when needed."
)
_REMAPPABLE_ACTIVE_ROOT_PROJECTS = frozenset({"Inbox"})

_LlmChatModel = TransformersMistral3ChatModel | OpenAIResponsesChatModel | TritonGenerateChatModel

_LLM_CHAT_MODEL: _LlmChatModel | None = None
_LLM_CHAT_MODEL_LOADING = False
_LLM_CHAT_MODEL_LOCK = asyncio.Lock()
_LLM_CHAT_STORAGE_LOCK = asyncio.Lock()
_LLM_CHAT_WORKER_LOCK = asyncio.Lock()
_LLM_CHAT_WORKER_RUNNING = False
_LLM_CHAT_AGENT = None
_LLM_CHAT_AGENT_LOCK = asyncio.Lock()


def _env_demo_mode() -> bool:
    value = os.getenv(str(EnvVar.DASHBOARD_DEMO), "").strip().lower()
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
            "subCurrent": _progress_state.sub_current,
            "subTotal": _progress_state.sub_total,
            "error": _progress_state.error,
        }


async def _set_progress(
    stage: str,
    *,
    step: int,
    total_steps: int,
    detail: str | None = None,
    sub_current: int | None = None,
    sub_total: int | None = None,
) -> None:
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
        _progress_state.sub_current = sub_current
        _progress_state.sub_total = sub_total
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
        _progress_state.sub_current = None
        _progress_state.sub_total = None
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
        _run_async_in_main_loop(
            _set_progress(
                desc or "Working",
                step=step,
                total_steps=_PROGRESS_TOTAL_STEPS,
                detail=detail,
                sub_current=current,
                sub_total=total,
            )
        )

    return _callback


def _activity_cache_signature() -> dict[str, int] | None:
    activity_path = Path(Cache().activity.path)
    if not activity_path.exists():
        return None
    try:
        stat = activity_path.stat()
    except OSError:
        return None
    return {"mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size)}


def _persist_state_to_disk_cache(*, demo_mode: bool) -> None:
    df_activity = _state.df_activity
    active_projects = _state.active_projects
    project_colors = _state.project_colors
    if (
        df_activity is None
        or active_projects is None
        or project_colors is None
    ):
        return

    payload: dict[str, Any] = {
        "version": _DASHBOARD_STATE_SCHEMA_VERSION,
        "created_at": _now_iso(),
        "last_refresh_s": float(_state.last_refresh_s),
        "demo_mode": bool(demo_mode),
        "demo_state_version": (
            _DEMO_DASHBOARD_STATE_SCHEMA_VERSION if demo_mode else None
        ),
        "activity_cache_signature": _activity_cache_signature(),
        "df_activity": df_activity,
        "active_projects": active_projects,
        "project_colors": project_colors,
    }
    try:
        Cache().dashboard_state.save(payload)
    except (LocalStorageError, OSError, TypeError) as exc:
        logger.warning(f"Failed to persist dashboard state cache: {exc}")


def _load_state_from_disk_cache(*, demo_mode: bool) -> bool:
    loaded = False
    try:
        payload = Cache().dashboard_state.load()
    except LocalStorageError:
        payload = None

    if isinstance(payload, dict):
        if payload.get("version") == _DASHBOARD_STATE_SCHEMA_VERSION:
            if bool(payload.get("demo_mode", False)) == demo_mode:
                if demo_mode and payload.get("demo_state_version") != _DEMO_DASHBOARD_STATE_SCHEMA_VERSION:
                    return False
                payload_signature = payload.get("activity_cache_signature")
                current_signature = _activity_cache_signature()
                if payload_signature == current_signature:
                    df_activity = payload.get("df_activity")
                    active_projects = payload.get("active_projects")
                    project_colors = payload.get("project_colors")
                    if isinstance(df_activity, pd.DataFrame):
                        if isinstance(active_projects, list):
                            if isinstance(project_colors, dict):
                                _state.db = None
                                _state.df_activity = _normalize_activity_df(
                                    df_activity
                                )
                                _state.active_projects = active_projects
                                _state.project_colors = {
                                    str(k): str(v) for k, v in project_colors.items()
                                }
                                _state.last_refresh_s = float(
                                    payload.get("last_refresh_s") or time.time()
                                )
                                _state.home_payload_cache = {}
                                _state.demo_mode = demo_mode
                                logger.info(
                                    "Loaded dashboard state cache from disk "
                                    f"(events={len(df_activity)}, "
                                    f"projects={len(active_projects)})"
                                )
                                loaded = True

    return loaded


def _refresh_state_sync(*, demo_mode: bool) -> None:
    global _activity_backfill_attempted
    # Reset progress state to clear any stale information from previous failed refreshes
    _run_async_in_main_loop(_finish_progress(error=None))

    previous_callback = get_tqdm_progress_callback()
    set_tqdm_progress_callback(_build_tqdm_progress_callback())

    error: str | None = None
    try:
        _run_async_in_main_loop(
            _set_progress(
                "Querying project data",
                step=1,
                total_steps=_PROGRESS_TOTAL_STEPS,
                detail="Fetching projects and tasks",
            )
        )
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
                    activity_cfg = (
                        cfg.get("activity") if isinstance(cfg, DictConfig) else None
                    )
                    nweeks = 10
                    early_stop = 2
                    if isinstance(activity_cfg, Mapping):
                        nweeks = int(activity_cfg.get("nweeks_window_size", nweeks))
                        early_stop = int(
                            activity_cfg.get("early_stop_after_n_windows", early_stop)
                        )
                    logger.info(
                        f"Activity cache looks short; backfilling history "
                        f"(window={nweeks}w, stop={early_stop})."
                    )
                    events = dbio.fetch_activity_adaptively(
                        nweeks_window_size=nweeks,
                        early_stop_after_n_windows=early_stop,
                        events_already_fetched=set(cached_events),
                    )
                    Cache().activity.save(set(events))
                except Exception as exc:  # pragma: no cover - network-dependent
                    logger.warning(f"Failed to backfill activity cache: {exc}")
                finally:
                    _activity_backfill_attempted = True

        if not cached_events and _resolve_api_key():
            try:
                cfg = _read_yaml_config(_AUTOMATIONS_PATH, required=False)
                activity_cfg = (
                    cfg.get("activity") if isinstance(cfg, DictConfig) else None
                )
                nweeks = 10
                early_stop = 2
                if isinstance(activity_cfg, Mapping):
                    nweeks = int(activity_cfg.get("nweeks_window_size", nweeks))
                    early_stop = int(
                        activity_cfg.get("early_stop_after_n_windows", early_stop)
                    )
                logger.info(
                    f"Activity cache empty; fetching full history (window={nweeks}w, stop={early_stop})."
                )
                events = dbio.fetch_activity_adaptively(
                    nweeks_window_size=nweeks,
                    early_stop_after_n_windows=early_stop,
                    events_already_fetched=set(),
                )
                if not events:
                    logger.info(
                        "Adaptive fetch returned no events; attempting recent activity pages."
                    )
                    events = dbio.fetch_activity(max_pages=2)
                Cache().activity.save(set(events))
            except Exception as exc:  # pragma: no cover - network-dependent
                logger.warning(f"Failed to seed activity cache: {exc}")
            finally:
                _activity_backfill_attempted = True

        _run_async_in_main_loop(
            _set_progress(
                "Building project hierarchy",
                step=2,
                total_steps=_PROGRESS_TOTAL_STEPS,
                detail="Resolving roots across active and archived projects",
            )
        )
        try:
            df_activity = _normalize_activity_df(load_activity_data(dbio))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Failed to load activity data; using empty dataset: {exc}")
            df_activity = _empty_activity_df()

        _run_async_in_main_loop(
            _set_progress(
                "Preparing dashboard data",
                step=3,
                total_steps=_PROGRESS_TOTAL_STEPS,
                detail="Loading metadata and caches",
            )
        )
        active_projects = dbio.fetch_projects(include_tasks=True)

        if demo_mode and not dbio.is_anonymized:
            from todoist.database.demo import (
                anonymize_label_names,
                anonymize_project_names,
            )

            project_ori2anonym = anonymize_project_names(df_activity, active_projects)
            label_ori2anonym = anonymize_label_names(active_projects)
            dbio.anonymize(
                project_mapping=project_ori2anonym, label_mapping=label_ori2anonym
            )

        if demo_mode:
            from todoist.database.demo import anonymize_activity_dates

            df_activity = anonymize_activity_dates(df_activity)

        project_colors = dbio.fetch_mapping_project_name_to_color()

        _state.db = dbio
        _state.df_activity = df_activity
        _state.active_projects = active_projects
        _state.project_colors = project_colors
        _state.last_refresh_s = time.time()
        _state.home_payload_cache = {}
        _state.demo_mode = demo_mode
        _persist_state_to_disk_cache(demo_mode=demo_mode)
    except Exception as exc:  # pragma: no cover - defensive
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        set_tqdm_progress_callback(previous_callback)
        _run_async_in_main_loop(_finish_progress(error))


async def _ensure_state(refresh: bool, *, demo_mode: bool | None = None) -> None:
    global _main_loop
    desired_demo = _env_demo_mode() if demo_mode is None else demo_mode
    if not refresh and _state.is_ready_for(demo_mode=desired_demo):
        return

    async with _STATE_LOCK:
        desired_demo = _env_demo_mode() if demo_mode is None else demo_mode
        if not refresh and _state.is_ready_for(demo_mode=desired_demo):
            return
        if not refresh and _load_state_from_disk_cache(demo_mode=desired_demo):
            return
        # Store the main event loop for worker threads to use
        _main_loop = asyncio.get_running_loop()
        await asyncio.to_thread(_refresh_state_sync, demo_mode=desired_demo)


def _cache_runtime_path(filename: str) -> Path:
    return Path(Cache().path) / filename


def _stat_file(path: str | Path) -> dict[str, Any] | None:
    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists():
        return None
    try:
        stat = path_obj.stat()
        return {
            "path": str(path_obj),
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "size": stat.st_size,
        }
    except OSError:
        return {"path": str(path_obj), "mtime": None, "size": None}


def _service_statuses() -> list[dict[str, Any]]:
    api_key_set = bool(_resolve_api_key())
    cache_activity = _stat_file(_cache_runtime_path("activity.joblib"))
    automation_log = _stat_file(automation_log_path())
    env_path = _resolve_env_path()
    file_values = dotenv_values(env_path) if env_path.exists() else {}
    triton_settings = _resolve_triton_settings(file_values)
    triton_ready = _triton_ready(triton_settings)
    observer_settings = observer_settings_payload(
        load_dashboard_config(_DASHBOARD_CONFIG_PATH),
        path=_DASHBOARD_CONFIG_PATH,
    )
    observer_enabled = bool(observer_settings["enabled"])

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
        observer_detail = "enabled, waiting for first tick"

    return [
        {
            "name": "Todoist token",
            "status": "ok" if api_key_set else "warn",
            "detail": "API_KEY set" if api_key_set else "API_KEY missing",
        },
        {
            "name": "Activity cache",
            "status": "ok" if cache_activity else "warn",
            "detail": cache_activity or "activity.joblib missing",
        },
        {
            "name": "Automation log",
            "status": "ok" if automation_log else "warn",
            "detail": automation_log or "automation.log missing",
        },
        {
            "name": "Triton",
            "status": "ok" if triton_ready else "warn",
            "detail": (
                f"{triton_settings['modelName']} ready at {triton_settings['baseUrl']}"
                if triton_ready
                else f"not ready at {triton_settings['baseUrl']}"
            ),
        },
        {"name": "Observer", "status": observer_status, "detail": observer_detail},
    ]


@app.get("/api/dashboard/status", tags=["dashboard"])
async def dashboard_status(refresh: bool = False) -> dict[str, Any]:
    """
    Lightweight status endpoint for UI badges (does not generate plots).
    """
    # Intentionally ignore refresh: this endpoint must stay non-blocking and avoid Todoist API calls.
    _ = refresh
    dashboard_config = load_dashboard_config(_DASHBOARD_CONFIG_PATH)
    observer_settings = observer_settings_payload(dashboard_config, path=_DASHBOARD_CONFIG_PATH)
    return {
        "services": _service_statuses(),
        "configurableItems": [
            {
                "key": "observer",
                "label": "Dashboard observer",
                "icon": "wrench",
                "configPath": observer_settings["configPath"],
                "anchor": "observer-control",
            }
        ],
        "apiCache": {
            "lastRefresh": datetime.fromtimestamp(_state.last_refresh_s).isoformat(
                timespec="seconds"
            )
            if _state.last_refresh_s
            else None
        },
        "activityCache": _stat_file(_cache_runtime_path("activity.joblib")),
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
    conversation_id = str(
        raw.get("conversation_id") or raw.get("conversationId") or ""
    ).strip()
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
        logger.warning(f"Failed to load LLM chat conversations: {exc}")
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
        logger.warning(f"Failed to save LLM chat conversations: {exc}")


def _load_llm_chat_queue() -> list[dict[str, Any]]:
    try:
        payload = Cache().llm_chat_queue.load()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to load LLM chat queue: {exc}")
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
        logger.warning(f"Failed to save LLM chat queue: {exc}")


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


def _available_llm_chat_devices() -> list[str]:
    devices = ["cpu"]
    try:
        import torch

        if torch.cuda.is_available():
            devices.append("cuda")
    except Exception:  # pragma: no cover - defensive
        pass
    return devices


def _llm_model_options_payload(
    options: Sequence[Mapping[str, str]], selected: str
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for option in options:
        option_id = _sanitize_text(option.get("id"))
        if not option_id or option_id in seen:
            continue
        seen.add(option_id)
        payload.append(
            {
                "id": option_id,
                "label": _sanitize_text(option.get("label")) or option_id,
                "selected": option_id == selected,
            }
        )
    if selected and selected not in seen:
        payload.insert(0, {"id": selected, "label": selected, "selected": True})
    return payload


def _normalize_llm_chat_backend(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in _LLM_CHAT_BACKEND_LABELS:
        return value
    return _LLM_CHAT_BACKEND_DEFAULT


def _normalize_llm_chat_device(raw: Any, *, available_devices: Sequence[str]) -> str:
    value = str(raw or "").strip().lower()
    if value == "gpu":
        value = "cuda"
    if value in available_devices:
        return value
    return _LLM_CHAT_DEVICE_DEFAULT


def _resolve_openai_settings(file_values: Mapping[str, Any]) -> dict[str, Any]:
    secret_key = _sanitize_text(
        os.getenv("OPEN_AI_SECRET_KEY") or file_values.get("OPEN_AI_SECRET_KEY")
    )
    key_name = _sanitize_text(
        os.getenv("OPEN_AI_KEY_NAME") or file_values.get("OPEN_AI_KEY_NAME")
    )
    model = _sanitize_text(
        os.getenv("OPEN_AI_MODEL") or file_values.get("OPEN_AI_MODEL")
    ) or DEFAULT_OPENAI_MODEL
    if secret_key:
        os.environ["OPEN_AI_SECRET_KEY"] = secret_key
    if key_name:
        os.environ["OPEN_AI_KEY_NAME"] = key_name
    os.environ["OPEN_AI_MODEL"] = model
    return {
        "configured": bool(secret_key),
        "keyName": key_name,
        "model": model,
        "secretKey": secret_key,
        "modelOptions": _llm_model_options_payload(_OPENAI_MODEL_OPTIONS, model),
    }


def _resolve_triton_settings(file_values: Mapping[str, Any]) -> dict[str, Any]:
    base_url = _sanitize_text(
        os.getenv(str(EnvVar.AGENT_TRITON_URL)) or file_values.get(str(EnvVar.AGENT_TRITON_URL))
    ) or DEFAULT_TRITON_URL
    model_name = _sanitize_text(
        os.getenv(str(EnvVar.AGENT_TRITON_MODEL_NAME))
        or file_values.get(str(EnvVar.AGENT_TRITON_MODEL_NAME))
    ) or DEFAULT_TRITON_MODEL_NAME
    model_id = _sanitize_text(
        os.getenv(str(EnvVar.AGENT_TRITON_MODEL_ID))
        or file_values.get(str(EnvVar.AGENT_TRITON_MODEL_ID))
    ) or DEFAULT_TRITON_MODEL_ID
    os.environ[str(EnvVar.AGENT_TRITON_URL)] = base_url
    os.environ[str(EnvVar.AGENT_TRITON_MODEL_NAME)] = model_name
    os.environ[str(EnvVar.AGENT_TRITON_MODEL_ID)] = model_id
    return {
        "baseUrl": base_url,
        "modelName": model_name,
        "modelId": model_id,
        "modelOptions": _llm_model_options_payload(_TRITON_MODEL_OPTIONS, model_id),
    }


def _triton_ready(triton_settings: Mapping[str, Any]) -> bool:
    base_url = _sanitize_text(triton_settings.get("baseUrl"))
    if not base_url:
        return False
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/v2/health/ready",
            timeout=0.5,
        )
        response.raise_for_status()
    except (httpx.HTTPError, ValueError):
        return False
    return True


def _resolve_llm_chat_settings() -> dict[str, Any]:
    env_path = _resolve_env_path()
    backend_key = str(EnvVar.AGENT_BACKEND)
    device_key = str(EnvVar.AGENT_DEVICE)
    local_model_key = str(EnvVar.AGENT_MODEL_ID)
    file_values = dotenv_values(env_path) if env_path.exists() else {}
    available_devices = _available_llm_chat_devices()
    openai_settings = _resolve_openai_settings(file_values)
    triton_settings = _resolve_triton_settings(file_values)
    local_model_id = _sanitize_text(
        os.getenv(local_model_key) or file_values.get(local_model_key)
    ) or DEFAULT_MODEL_ID

    backend = _normalize_llm_chat_backend(
        os.getenv(backend_key) or file_values.get(backend_key)
    )
    device = _normalize_llm_chat_device(
        os.getenv(device_key) or file_values.get(device_key),
        available_devices=available_devices,
    )
    if backend == "openai" and not openai_settings["configured"]:
        backend = _LLM_CHAT_BACKEND_DEFAULT
    os.environ[backend_key] = backend
    os.environ[device_key] = device
    os.environ[local_model_key] = local_model_id

    return {
        "backend": backend,
        "backendLabel": _LLM_CHAT_BACKEND_LABELS[backend],
        "device": device,
        "deviceLabel": _LLM_CHAT_DEVICE_LABELS[device],
        "localModelId": local_model_id,
        "localModelOptions": _llm_model_options_payload(_LOCAL_MODEL_OPTIONS, local_model_id),
        "availableBackends": [
            {
                "id": backend_id,
                "label": label,
                "available": (
                    backend_id == "transformers_local"
                    or backend_id == "triton_local"
                    or (backend_id == "openai" and openai_settings["configured"])
                ),
            }
            for backend_id, label in _LLM_CHAT_BACKEND_LABELS.items()
        ],
        "availableDevices": [
            {
                "id": device_id,
                "label": label,
                "available": device_id in available_devices,
            }
            for device_id, label in _LLM_CHAT_DEVICE_LABELS.items()
        ],
        "openai": {
            "configured": openai_settings["configured"],
            "keyName": openai_settings["keyName"],
            "model": openai_settings["model"],
            "secretKey": openai_settings["secretKey"],
            "modelOptions": openai_settings["modelOptions"],
        },
        "triton": {
            "configured": True,
            "healthy": _triton_ready(triton_settings),
            "baseUrl": triton_settings["baseUrl"],
            "modelName": triton_settings["modelName"],
            "modelId": triton_settings["modelId"],
            "modelOptions": triton_settings["modelOptions"],
        },
        "envPath": str(env_path),
    }


async def _reset_llm_chat_runtime() -> None:
    global _LLM_CHAT_MODEL, _LLM_CHAT_MODEL_LOADING, _LLM_CHAT_AGENT
    async with _LLM_CHAT_MODEL_LOCK:
        _LLM_CHAT_MODEL = None
        _LLM_CHAT_MODEL_LOADING = False
    async with _LLM_CHAT_AGENT_LOCK:
        _LLM_CHAT_AGENT = None


def _public_llm_chat_settings(settings: dict[str, Any]) -> dict[str, Any]:
    public = dict(settings)
    openai_settings = dict(public.get("openai") or {})
    openai_settings.pop("secretKey", None)
    public["openai"] = openai_settings
    return public


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
        settings = _resolve_llm_chat_settings()
        backend = settings["backend"]
        if backend == "transformers_local":
            config = coerce_model_config(
                {"device": settings["device"], "model_id": settings["localModelId"]}
            )
            model = await asyncio.to_thread(TransformersMistral3ChatModel, config)
        elif backend == "triton_local":
            triton_settings = settings["triton"]
            model = await asyncio.to_thread(
                TritonGenerateChatModel,
                TritonChatConfig(
                    base_url=str(triton_settings["baseUrl"]),
                    model_name=str(triton_settings["modelName"]),
                    model_id=str(triton_settings["modelId"]),
                    max_output_tokens=256,
                ),
            )
        elif backend == "openai":
            openai_settings = settings["openai"]
            secret_key = _sanitize_text(openai_settings.get("secretKey"))
            if not secret_key:
                raise ValueError("OpenAI backend is not configured.")
            model = await asyncio.to_thread(
                OpenAIResponsesChatModel,
                OpenAIChatConfig(
                    api_key=secret_key,
                    key_name=_sanitize_text(openai_settings.get("keyName")),
                    model=str(openai_settings.get("model") or DEFAULT_OPENAI_MODEL),
                    max_output_tokens=256,
                ),
            )
        else:
            raise ValueError(f"Unsupported LLM backend: {backend}")
        async with _LLM_CHAT_MODEL_LOCK:
            _LLM_CHAT_MODEL = model
        await asyncio.to_thread(_build_llm_chat_agent_sync, model)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Failed to load LLM chat model: {exc}")
    finally:
        async with _LLM_CHAT_MODEL_LOCK:
            _LLM_CHAT_MODEL_LOADING = False
    await _maybe_start_llm_chat_worker()


def _build_chat_messages(
    conversation: dict[str, Any], user_content: str
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if _CHAT_SYSTEM_PROMPT:
        messages.append(
            {"role": MessageRole.SYSTEM.value, "content": _CHAT_SYSTEM_PROMPT}
        )
    for msg in conversation.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        # Skip system messages from history to avoid conflicts with the prepended system prompt
        if role in _CHAT_ROLES and content and role != MessageRole.SYSTEM.value:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": MessageRole.USER.value, "content": user_content})
    return messages


def _build_llm_chat_agent_sync(model: _LlmChatModel) -> None:
    global _LLM_CHAT_AGENT
    try:
        from todoist.agent.context import load_local_agent_context
        from todoist.agent.graph import build_agent_graph
        from todoist.agent.repl_tool import SafePythonReplTool
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"LLM chat agent unavailable: {exc}")
        return

    cache_path = os.getenv(str(EnvVar.AGENT_CACHE_PATH), str(_REPO_ROOT))
    prefabs_dir = os.getenv(
        str(EnvVar.AGENT_INSTRUCTIONS_DIR), str(_REPO_ROOT / "configs/agent_instructions")
    )
    max_tool_loops_env = os.getenv(str(EnvVar.AGENT_MAX_TOOL_LOOPS), "8").strip()
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
                next_item = next(
                    (item for item in queue if item.get("status") == "queued"), None
                )
                if next_item is None:
                    return
                next_item["status"] = "running"
                next_item["started_at"] = _now_iso()
                _save_llm_chat_queue(queue)
                conversations = _load_llm_chat_conversations()
                conversation = next(
                    (
                        item
                        for item in conversations
                        if item.get("id") == next_item["conversation_id"]
                    ),
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
                    state = cast(
                        "AgentState",
                        {
                        "messages": [
                            *base_messages,
                            {
                                "role": MessageRole.USER.value,
                                "content": next_item["content"],
                            },
                        ]
                        },
                    )
                    result = await asyncio.to_thread(agent.invoke, state)
                    messages = (
                        result.get("messages") if isinstance(result, dict) else None
                    )
                    if not isinstance(messages, list):
                        raise ValueError("Agent returned invalid messages")
                    new_messages = (
                        messages[len(base_messages) :]
                        if len(messages) >= len(base_messages)
                        else messages
                    )
                    now = _now_iso()
                    async with _LLM_CHAT_STORAGE_LOCK:
                        queue = _load_llm_chat_queue()
                        queue_item = next(
                            (
                                item
                                for item in queue
                                if item.get("id") == next_item["id"]
                            ),
                            None,
                        )
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
                            queue_item = next(
                                (
                                    item
                                    for item in queue
                                    if item.get("id") == next_item["id"]
                                ),
                                None,
                            )
                            if (
                                queue_item is not None
                                and queue_item.get("status") == "running"
                            ):
                                queue_item["status"] = "failed"
                                queue_item["finished_at"] = _now_iso()
                                queue_item["error"] = "Empty response from model"
                                _save_llm_chat_queue(queue)
                        continue

                    now = _now_iso()
                    async with _LLM_CHAT_STORAGE_LOCK:
                        queue = _load_llm_chat_queue()
                        queue_item = next(
                            (
                                item
                                for item in queue
                                if item.get("id") == next_item["id"]
                            ),
                            None,
                        )
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
    settings = _resolve_llm_chat_settings()
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
        "backend": {
            "selected": settings["backend"],
            "label": settings["backendLabel"],
            "active": settings["backend"] if enabled or loading else None,
            "options": settings["availableBackends"],
            "openai": {
                "configured": settings["openai"]["configured"],
                "keyName": settings["openai"]["keyName"],
                "model": settings["openai"]["model"],
                "modelOptions": settings["openai"]["modelOptions"],
            },
            "triton": {
                "configured": settings["triton"]["configured"],
                "healthy": settings["triton"]["healthy"],
                "baseUrl": settings["triton"]["baseUrl"],
                "modelName": settings["triton"]["modelName"],
                "modelId": settings["triton"]["modelId"],
                "modelOptions": settings["triton"]["modelOptions"],
            },
            "envPath": settings["envPath"],
        },
        "model": {
            "selected": (
                settings["openai"]["model"]
                if settings["backend"] == "openai"
                else settings["triton"]["modelId"]
                if settings["backend"] == "triton_local"
                else settings["localModelId"]
            ),
            "label": (
                settings["openai"]["model"]
                if settings["backend"] == "openai"
                else settings["triton"]["modelId"]
                if settings["backend"] == "triton_local"
                else settings["localModelId"]
            ),
            "active": (
                settings["openai"]["model"]
                if (enabled or loading) and settings["backend"] == "openai"
                else settings["triton"]["modelId"]
                if (enabled or loading) and settings["backend"] == "triton_local"
                else settings["localModelId"]
                if (enabled or loading) and settings["backend"] == "transformers_local"
                else None
            ),
            "local": {
                "selected": settings["localModelId"],
                "options": settings["localModelOptions"],
            },
            "openai": {
                "selected": settings["openai"]["model"],
                "options": settings["openai"]["modelOptions"],
            },
            "triton": {
                "selected": settings["triton"]["modelId"],
                "options": settings["triton"]["modelOptions"],
            },
            "envPath": settings["envPath"],
        },
        "device": {
            "selected": settings["device"],
            "label": settings["deviceLabel"],
            "active": (
                settings["device"]
                if (enabled or loading) and settings["backend"] == "transformers_local"
                else None
            ),
            "options": settings["availableDevices"],
            "envPath": settings["envPath"],
        },
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


@app.get("/api/llm_chat/settings", tags=["llm"])
async def llm_chat_settings() -> dict[str, Any]:
    return _public_llm_chat_settings(_resolve_llm_chat_settings())


@app.put("/api/llm_chat/settings", tags=["llm"])
async def llm_chat_update_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    settings = _resolve_llm_chat_settings()
    requested_backend = str(payload.get("backend") or "").strip().lower()
    if requested_backend not in {item["id"] for item in settings["availableBackends"]}:
        raise HTTPException(status_code=400, detail="Unsupported LLM backend.")
    backend = _normalize_llm_chat_backend(requested_backend)
    if backend == "openai" and not settings["openai"]["configured"]:
        raise HTTPException(
            status_code=400,
            detail="OpenAI backend is not configured.",
        )

    available_devices = [
        str(item["id"])
        for item in settings["availableDevices"]
        if bool(item["available"])
    ]
    requested_device = str(payload.get("device") or "").strip().lower()
    if requested_device == "gpu":
        requested_device = "cuda"
    if requested_device not in _LLM_CHAT_DEVICE_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported LLM device.")
    if requested_device not in available_devices:
        raise HTTPException(
            status_code=400,
            detail="Requested device is not available on this machine.",
        )
    device = _normalize_llm_chat_device(requested_device, available_devices=available_devices)
    local_model_id = _sanitize_text(payload.get("localModelId")) or settings["localModelId"]
    openai_model = _sanitize_text(payload.get("openaiModel")) or settings["openai"]["model"]
    triton_model_id = _sanitize_text(payload.get("tritonModelId")) or settings["triton"]["modelId"]

    enabled, loading = await _llm_chat_model_status()
    if loading:
        raise HTTPException(
            status_code=409,
            detail="Cannot change LLM settings while the model is loading.",
        )

    env_path = _resolve_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(env_path), str(EnvVar.AGENT_BACKEND), backend)
    set_key(str(env_path), str(EnvVar.AGENT_DEVICE), device)
    set_key(str(env_path), str(EnvVar.AGENT_MODEL_ID), local_model_id)
    set_key(str(env_path), "OPEN_AI_MODEL", openai_model)
    set_key(str(env_path), str(EnvVar.AGENT_TRITON_MODEL_ID), triton_model_id)
    os.environ[str(EnvVar.AGENT_BACKEND)] = backend
    os.environ[str(EnvVar.AGENT_DEVICE)] = device
    os.environ[str(EnvVar.AGENT_MODEL_ID)] = local_model_id
    os.environ["OPEN_AI_MODEL"] = openai_model
    os.environ[str(EnvVar.AGENT_TRITON_MODEL_ID)] = triton_model_id

    if enabled:
        await _reset_llm_chat_runtime()

    updated = _resolve_llm_chat_settings()
    updated["enabled"] = False if enabled else enabled
    updated["loading"] = False
    updated["reloadedRequired"] = enabled
    return _public_llm_chat_settings(updated)


@app.post("/api/llm_chat/enable", tags=["llm"])
async def llm_chat_enable() -> dict[str, Any]:
    """Start loading the local LLM model used for chat."""

    await _start_llm_chat_model_load()
    enabled, loading = await _llm_chat_model_status()
    settings = _resolve_llm_chat_settings()
    return {
        "enabled": enabled,
        "loading": loading,
        "backend": settings["backend"],
        "device": settings["device"],
    }


@app.post("/api/llm_chat/send", tags=["llm"])
async def llm_chat_send(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Queue a chat prompt for the local LLM."""

    message = _sanitize_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    enabled, loading = await _llm_chat_model_status()
    if not (enabled or loading):
        raise HTTPException(
            status_code=409,
            detail="Model not loaded. Click Enable in the dashboard first.",
        )

    conversation_id = _sanitize_text(
        payload.get("conversationId") or payload.get("conversation_id")
    )
    now = _now_iso()

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
        conversation = None
        if conversation_id:
            conversation = next(
                (item for item in conversations if item.get("id") == conversation_id),
                None,
            )
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
        raise HTTPException(
            status_code=400, detail="Invalid conversation ID format"
        ) from exc

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
    conversation = next(
        (item for item in conversations if item.get("id") == conversation_id), None
    )
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

    if df_activity is None or active_projects is None or project_colors is None:
        return {
            "error": "Dashboard data unavailable. Please ensure the database is configured and accessible."
        }

    df_activity = _normalize_activity_df(df_activity)
    dashboard_settings_cfg = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
    dashboard_settings = _dashboard_settings_payload(dashboard_settings_cfg)

    no_data = df_activity.empty
    beg_range, end_range = _compute_plot_range(
        df_activity, weeks=weeks, beg=beg, end=end
    )
    beg_label = beg if beg is not None else beg_range.strftime("%Y-%m-%d")
    end_label = end if end is not None else end_range.strftime("%Y-%m-%d")

    periods = _period_bounds(df_activity, granularity)
    metrics = _extract_metrics_dict(df_activity, periods)
    today = datetime.now().date()
    urgency_status = _evaluate_urgency_status(
        active_projects,
        today=today,
        settings=dashboard_settings_cfg.get("urgency") if hasattr(dashboard_settings_cfg, "get") else None,
    )

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
        f"today={today.isoformat()}",
    )
    cached = _state.home_payload_cache.get(cache_key)
    if cached and not refresh:
        return cached

    anchor_dt = _safe_activity_anchor(df_activity)
    last_week_beg, last_week_end, last_week_label = _last_completed_week_bounds(
        anchor_dt
    )
    tracked_habit_tasks = extract_tracked_habit_tasks(active_projects)
    habit_tracker = _build_habit_tracker_payload(
        df_activity,
        tracked_habit_tasks,
        anchor=anchor_dt,
        project_colors=project_colors,
    )

    if no_data:
        figures = {}
        parent_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
        root_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
    else:
        figures = {
            "weeklyCompletionTrend": _fig_to_dict(
                plot_weekly_completion_trend(df_activity, end_range)
            ),
            "taskLifespans": _fig_to_dict(plot_task_lifespans(df_activity)),
            "completedTasksPeriodically": _fig_to_dict(
                plot_completed_tasks_periodically(
                    df_activity, beg_range, end_range, granularity, project_colors
                )
            ),
            "cumsumCompletedTasksPeriodically": _fig_to_dict(
                cumsum_completed_tasks_periodically(
                    df_activity, beg_range, end_range, granularity, project_colors
                )
            ),
            "heatmapEventsByDayHour": _fig_to_dict(
                plot_heatmap_of_events_by_day_and_hour(
                    df_activity, beg_range, end_range
                )
            ),
            "eventsOverTime": _fig_to_dict(
                plot_events_over_time(df_activity, beg_range, end_range, granularity)
            ),
            "activeProjectHierarchy": _fig_to_dict(
                plot_active_project_hierarchy(
                    df_activity,
                    beg_range,
                    end_range,
                    active_projects,
                    project_colors,
                )
            ),
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
        "urgencyStatus": urgency_status,
        "configurableItems": [
            {
                "key": "urgency",
                "label": "Urgency watch badge",
                "icon": "wrench",
                "configPath": dashboard_settings["configPath"],
                "anchor": "dashboard-settings",
                "summary": (
                    f"Priority thresholds {dashboard_settings['warnPriorityThresholds']}; "
                    f"due within {dashboard_settings['warnDueWithinDays']} days; "
                    f"deadline within {dashboard_settings['warnDeadlineWithinDays']} days."
                ),
            }
        ],
        "badges": {"p1": p1, "p2": p2, "p3": p3, "p4": p4},
        "habitTracker": habit_tracker,
        "insights": {
            "label": last_week_label,
            "items": []
            if no_data
            else _compute_insights(
                df_activity,
                beg=last_week_beg,
                end=last_week_end,
                project_colors=project_colors,
            ),
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
    automations: list[Automation] = hydra.utils.instantiate(
        cast(DictConfig, config).automations
    )
    return automations


def _available_automation_keys(config: Mapping[str, Any]) -> list[str]:
    reserved = {"defaults", "automations", "hydra"}
    keys: list[str] = []
    for key, value in config.items():
        if key in reserved or not isinstance(key, str):
            continue
        if isinstance(value, Mapping) and value.get("_target_"):
            keys.append(key)
    return keys


def _automation_ref(key: str) -> str:
    return f"${{{key}}}"


def _enabled_automation_keys(config: Mapping[str, Any]) -> list[str]:
    raw = config.get("automations")
    if not isinstance(raw, Sequence):
        return []
    keys: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        match = re.fullmatch(r"\$\{([a-zA-Z0-9_-]+)\}", item.strip())
        if match:
            keys.append(match.group(1))
    return keys


def _gmail_automation_status() -> dict[str, Any]:
    credentials_path = _REPO_ROOT / GMAIL_CREDENTIALS_FILE
    token_path = _REPO_ROOT / GMAIL_TOKEN_FILE
    credentials_present = credentials_path.exists()
    token_present = token_path.exists()
    connected = False
    token_detail = "Missing token"
    if token_present:
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), GmailTasksAutomation.SCOPES)
            connected = bool(getattr(creds, "valid", False))
            if connected:
                token_detail = "Authorized"
            elif getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
                token_detail = "Token expired but refreshable"
            else:
                token_detail = "Token present but invalid"
        except Exception as exc:  # pragma: no cover - defensive
            token_detail = f"Token unreadable ({type(exc).__name__})"
    return {
        "credentialsPresent": credentials_present,
        "tokenPresent": token_present,
        "connected": connected,
        "credentialsPath": str(credentials_path),
        "tokenPath": str(token_path),
        "detail": token_detail if credentials_present else "Missing Gmail credentials file",
        "setupDocPath": str(_REPO_ROOT / "docs" / "gmail_setup.md"),
    }


def _automation_metadata_for_key(config: DictConfig, key: str, *, enabled: bool) -> dict[str, Any]:
    section = config.get(key)
    if not isinstance(section, Mapping):
        raise ValueError(f"Automation section missing or invalid: {key}")
    automation = cast(Automation, hydra.utils.instantiate(section))
    payload = {
        **_automation_launch_metadata(automation),
        "key": key,
        "enabled": enabled,
        "target": str(section.get("_target_") or ""),
    }
    if key == "gmail_tasks":
        payload["connection"] = _gmail_automation_status()
    return payload


def _load_automation_inventory() -> list[dict[str, Any]]:
    config = cast(DictConfig, load_config("automations", str(_CONFIG_DIR.resolve())))
    available_keys = _available_automation_keys(config)
    enabled_keys = set(_enabled_automation_keys(config))
    inventory: list[dict[str, Any]] = []
    for key in available_keys:
        inventory.append(_automation_metadata_for_key(config, key, enabled=key in enabled_keys))
    return inventory


def _save_enabled_automations(keys: Sequence[str]) -> None:
    config = _read_yaml_config(_AUTOMATIONS_PATH)
    available_keys = _available_automation_keys(config)
    normalized = [key for key in available_keys if key in set(keys)]
    config["automations"] = [_automation_ref(key) for key in normalized]
    _save_yaml_config(_AUTOMATIONS_PATH, config)


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
        automations = _load_automation_inventory()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to load automations: {exc}")
        return {"automations": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"automations": automations, "configPath": str(_AUTOMATIONS_PATH)}


@app.post("/api/admin/automations/{key}/enabled", tags=["admin"])
async def admin_set_automation_enabled(
    key: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    async with _ADMIN_LOCK:
        config = _read_yaml_config(_AUTOMATIONS_PATH)
        available_keys = _available_automation_keys(config)
        if key not in available_keys:
            raise HTTPException(status_code=404, detail=f"Unknown automation key: {key}")
        enabled_keys = _enabled_automation_keys(config)
        next_keys = [item for item in enabled_keys if item != key]
        if enabled:
            insert_at = max(0, available_keys.index(key))
            ordered = [item for item in available_keys if item in next_keys]
            if key not in ordered:
                ordered.insert(insert_at, key)
            next_keys = ordered
        _save_enabled_automations(next_keys)
    return await admin_automations()


@app.get("/api/admin/automations/gmail/status", tags=["admin"])
async def admin_gmail_automation_status() -> dict[str, Any]:
    return _gmail_automation_status()


@app.post("/api/admin/automations/gmail/connect", tags=["admin"])
async def admin_gmail_automation_connect() -> dict[str, Any]:
    status = _gmail_automation_status()
    if not status["credentialsPresent"]:
        raise HTTPException(
            status_code=400,
            detail="gmail_credentials.json is required before connecting Gmail.",
        )
    automation = GmailTasksAutomation(allow_interactive_auth=True)
    service = await asyncio.to_thread(automation._authenticate_gmail)  # pylint: disable=protected-access
    if service is None:
        raise HTTPException(status_code=500, detail="Gmail authorization did not complete.")
    return _gmail_automation_status()


@app.delete("/api/admin/automations/gmail/connect", tags=["admin"])
async def admin_gmail_automation_disconnect() -> dict[str, Any]:
    token_path = _REPO_ROOT / GMAIL_TOKEN_FILE
    if token_path.exists():
        token_path.unlink()
    return _gmail_automation_status()


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
            raise HTTPException(
                status_code=status, detail=f"API token validation failed: {detail}"
            )
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
async def admin_validate_api_token(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
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


@app.get("/api/admin/timezone", tags=["admin"])
async def admin_timezone_status() -> dict[str, Any]:
    return _resolve_timezone_status()


@app.post("/api/admin/timezone", tags=["admin"])
async def admin_set_timezone(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    timezone_name = _normalize_timezone(payload.get("timezone"))
    if not timezone_name:
        raise HTTPException(status_code=400, detail="Timezone is required.")
    if not _is_valid_timezone_name(timezone_name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid timezone. Use a valid IANA timezone name "
                "(example: Europe/Warsaw)."
            ),
        )
    env_path = _resolve_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(env_path), str(EnvVar.TIMEZONE), timezone_name)
    os.environ[str(EnvVar.TIMEZONE)] = timezone_name
    return _resolve_timezone_status()


@app.delete("/api/admin/timezone", tags=["admin"])
async def admin_clear_timezone() -> dict[str, Any]:
    env_path = _resolve_env_path()
    if env_path.exists():
        unset_key(str(env_path), str(EnvVar.TIMEZONE))
    os.environ.pop(str(EnvVar.TIMEZONE), None)
    return _resolve_timezone_status()


def _run_automation_sync(automation: Automation, *, dbio: Database) -> dict[str, Any]:
    output_stream = io.StringIO()
    started_at = datetime.now()
    with (
        contextlib.redirect_stdout(output_stream),
        contextlib.redirect_stderr(output_stream),
    ):
        loguru_handler_id = logger.add(output_stream, format="{message}", level=get_log_level())
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
        result = await asyncio.to_thread(
            _run_automation_sync, automations[name], dbio=dbio
        )
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
            results.append(
                await asyncio.to_thread(_run_automation_sync, automation, dbio=dbio)
            )
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
                raise HTTPException(
                    status_code=404, detail=f"Unknown automation: {name}"
                )

            dbio = Database(".env")
            dbio.pull()
            result = await asyncio.to_thread(
                _run_automation_sync, automations[name], dbio=dbio
            )
            dbio.reset()

        await _update_job(job_id, status="done", finished_at=_now_iso(), result=result)
    except Exception as exc:  # pragma: no cover - defensive
        await _update_job(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error=f"{type(exc).__name__}: {exc}",
        )


async def _run_all_automations_job(*, job_id: str) -> None:
    await _update_job(job_id, status="running", started_at=_now_iso())
    try:
        async with _ADMIN_LOCK:
            dbio = Database(".env")
            dbio.pull()
            results: list[dict[str, Any]] = []
            for automation in _load_automations():
                results.append(
                    await asyncio.to_thread(_run_automation_sync, automation, dbio=dbio)
                )
                dbio.reset()

        await _update_job(
            job_id, status="done", finished_at=_now_iso(), result={"results": results}
        )
    except Exception as exc:  # pragma: no cover - defensive
        await _update_job(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error=f"{type(exc).__name__}: {exc}",
        )


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
        "refreshIntervalMinutes": payload.get("refreshIntervalMinutes"),
        "refreshIntervalSeconds": payload.get("refreshIntervalSeconds"),
        "updatedAt": payload.get("updatedAt"),
        "lastRunAt": payload.get("lastRunAt"),
        "lastDurationSeconds": payload.get("lastDurationSeconds"),
        "lastEvents": payload.get("lastEvents"),
        "lastAutomationsRan": payload.get("lastAutomationsRan"),
        "lastStatus": payload.get("lastStatus"),
        "lastError": payload.get("lastError"),
    }


def _build_observer(db: Database) -> AutomationObserver:
    config = load_config("automations", str(_CONFIG_DIR.resolve()))
    activity_automation: Activity = hydra.utils.instantiate(
        cast(DictConfig, config).activity
    )
    automations: list[Automation] = hydra.utils.instantiate(
        cast(DictConfig, config).automations
    )
    short_automations = [auto for auto in automations if not isinstance(auto, Activity)]
    return AutomationObserver(
        db=db, automations=short_automations, activity=activity_automation
    )


@app.get("/api/admin/observer", tags=["admin"])
async def admin_observer_state() -> dict[str, Any]:
    config = load_dashboard_config(_DASHBOARD_CONFIG_PATH)
    state = _load_observer_state()
    observer_settings = observer_settings_payload(config, path=_DASHBOARD_CONFIG_PATH)
    state["enabled"] = bool(observer_settings["enabled"])
    state["refreshIntervalMinutes"] = float(observer_settings["refreshIntervalMinutes"])
    state["refreshIntervalSeconds"] = float(observer_settings["refreshIntervalMinutes"]) * 60.0
    return {
        "state": _serialize_observer_state(state),
        "settings": observer_settings,
        "editTargets": [
            {
                "key": "observer",
                "label": "Dashboard observer",
                "icon": "wrench",
                "configPath": observer_settings["configPath"],
                "anchor": "observer-control",
            }
        ],
    }


@app.post("/api/admin/observer", tags=["admin"])
async def admin_set_observer(payload: Any = Body(...)) -> dict[str, Any]:
    if isinstance(payload, bool):
        update_payload: dict[str, Any] = {"enabled": payload}
    elif isinstance(payload, dict):
        update_payload = payload
    else:
        raise HTTPException(status_code=400, detail="Body must be a JSON object or boolean")

    async with _ADMIN_LOCK:
        config = load_dashboard_config(_DASHBOARD_CONFIG_PATH)
        try:
            observer_settings = update_observer_settings(config, update_payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        cache_state = _load_observer_state()
        cache_state["enabled"] = bool(observer_settings["enabled"])
        cache_state["refreshIntervalMinutes"] = observer_settings["refreshIntervalMinutes"]
        cache_state["refreshIntervalSeconds"] = float(
            observer_settings["refreshIntervalMinutes"]
        ) * 60.0
        cache_state["updatedAt"] = _now_iso()
        Cache().observer_state.save(cache_state)
        _save_yaml_config(_DASHBOARD_CONFIG_PATH, config)
    return {
        "state": _serialize_observer_state(cache_state),
        "settings": observer_settings,
        "editTargets": [
            {
                "key": "observer",
                "label": "Dashboard observer",
                "icon": "wrench",
                "configPath": observer_settings["configPath"],
                "anchor": "observer-control",
            }
        ],
    }


@app.post("/api/admin/observer/run", tags=["admin"])
async def admin_run_observer(force: bool = False) -> dict[str, Any]:
    async with _ADMIN_LOCK:
        state = _load_observer_state()
        observer_settings = observer_settings_payload(
            load_dashboard_config(_DASHBOARD_CONFIG_PATH),
            path=_DASHBOARD_CONFIG_PATH,
        )
        enabled = bool(observer_settings["enabled"])
        state["enabled"] = enabled
        state["refreshIntervalMinutes"] = float(observer_settings["refreshIntervalMinutes"])
        state["refreshIntervalSeconds"] = float(observer_settings["refreshIntervalMinutes"]) * 60.0
        if not enabled and not force:
            raise HTTPException(status_code=409, detail="Observer is disabled")

        started_at = datetime.now()
        dbio = Database(".env")
        try:
            dbio.pull()
            observer = _build_observer(dbio)
            result = await asyncio.to_thread(observer.run_once)
            status = "ran" if result.automations_ran > 0 else "idle"
            state.update(
                {
                    "lastStatus": status,
                    "lastEvents": int(result.new_events),
                    "lastAutomationsRan": int(result.automations_ran),
                    "lastError": None,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            state.update(
                {
                    "lastStatus": "failed",
                    "lastEvents": None,
                    "lastAutomationsRan": None,
                    "lastError": f"{type(exc).__name__}: {exc}",
                }
            )
            raise HTTPException(status_code=500, detail=state["lastError"]) from exc
        finally:
            dbio.reset()
            finished_at = datetime.now()
            state["lastRunAt"] = finished_at.isoformat(timespec="seconds")
            state["lastDurationSeconds"] = round(
                (finished_at - started_at).total_seconds(), 3
            )
            state["updatedAt"] = _now_iso()
            Cache().observer_state.save(state)

    return {"state": _serialize_observer_state(state)}


def _log_files() -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for item in _runtime_log_sources():
        logs.append(
            {
                "source": item["id"],
                "label": item["label"],
                "category": item["kind"],
                "description": item["description"],
                "path": item["path"],
                "available": item["available"],
                "inspectOnly": item["inspectOnly"],
                "size": item["size"],
                "mtime": item["mtime"],
            }
        )
    return logs


@dataclass(frozen=True)
class _RuntimeLogSpec:
    key: str
    label: str
    category: str
    description: str
    relative_path: str


def _display_log_path(path: Path) -> str:
    resolved = path.resolve()
    for root in (_DATA_DIR.resolve(), Path(Cache().path).resolve()):
        try:
            return str(resolved.relative_to(root))
        except ValueError:
            continue
    return str(resolved)


def _runtime_log_specs() -> tuple[_RuntimeLogSpec, ...]:
    return (
        _RuntimeLogSpec(
            key="api",
            label="Backend API",
            category="backend",
            description="FastAPI and Uvicorn application output.",
            relative_path="dashboard/api.log",
        ),
        _RuntimeLogSpec(
            key="frontend",
            label="Frontend",
            category="frontend",
            description="Next.js dashboard server output.",
            relative_path="dashboard/frontend.log",
        ),
        _RuntimeLogSpec(
            key="observer",
            label="Observer",
            category="observer",
            description="Background observer polling and automation trigger output.",
            relative_path="dashboard/observer.log",
        ),
        _RuntimeLogSpec(
            key="triton",
            label="Triton",
            category="triton",
            description="Triton container logs tailed by the dashboard launcher.",
            relative_path="dashboard/triton.log",
        ),
        _RuntimeLogSpec(
            key="triton_inference",
            label="Triton Inference",
            category="triton",
            description="Per-request Triton model logs including grouped batch execution details.",
            relative_path="dashboard/triton-inference.log",
        ),
        _RuntimeLogSpec(
            key="automation",
            label="Automation Jobs",
            category="automation",
            description="Shared automation runner output outside the dashboard stack.",
            relative_path="automation.log",
        ),
    )


def _runtime_log_path(spec: _RuntimeLogSpec) -> Path:
    return (Path(Cache().path) / spec.relative_path).resolve()


def _runtime_log_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for spec in _runtime_log_specs():
        path = _runtime_log_path(spec)
        available = path.is_file()
        size: int | None = None
        mtime: str | None = None
        if available:
            try:
                stat = path.stat()
            except OSError:
                available = False
            else:
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        sources.append(
            {
                "id": spec.key,
                "label": spec.label,
                "kind": spec.category,
                "description": spec.description,
                "path": _display_log_path(path),
                "available": available,
                "inspectOnly": True,
                "size": size,
                "mtime": mtime,
            }
        )
    return sources


def _resolve_runtime_log_source(source: str) -> tuple[_RuntimeLogSpec, Path]:
    key = source.strip().lower()
    for spec in _runtime_log_specs():
        if spec.key == key:
            return spec, _runtime_log_path(spec)
    raise HTTPException(status_code=404, detail=f"Unknown runtime log source: {source}")


def _resolve_runtime_log_request(
    *, source: str | None = None, path: str | None = None
) -> tuple[_RuntimeLogSpec, Path]:
    if source is not None and source.strip():
        return _resolve_runtime_log_source(source)
    if path is not None and path.strip():
        normalized = path.strip()
        for spec in _runtime_log_specs():
            candidate = _runtime_log_path(spec)
            if normalized in {spec.relative_path, _display_log_path(candidate)}:
                return spec, candidate
        raise HTTPException(status_code=404, detail=f"Unknown runtime log path: {path}")
    raise HTTPException(status_code=400, detail="Missing runtime log source")


@app.get("/api/runtime/logs", tags=["runtime"])
async def runtime_logs() -> dict[str, Any]:
    return {"inspectOnly": True, "sources": _runtime_log_sources()}


@app.get("/api/runtime/logs/read", tags=["runtime"])
async def runtime_read_log(
    source: str | None = None,
    path: str | None = None,
    tail_lines: int = 120,
    page: int = 1,
) -> dict[str, Any]:
    spec, abs_path = _resolve_runtime_log_request(source=source, path=path)
    if not abs_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Runtime log is not available yet: {spec.label}",
        )

    stat = abs_path.stat()
    payload = _read_log_file(abs_path, tail_lines=tail_lines, page=page)
    return {
        "id": spec.key,
        "source": spec.key,
        "label": spec.label,
        "kind": spec.category,
        "category": spec.category,
        "description": spec.description,
        "path": _display_log_path(abs_path),
        "available": True,
        "inspectOnly": True,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        **payload,
    }


def _safe_data_path(rel_path: str, *, suffix: str | None = None) -> Path:
    raw = Path(rel_path).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (_DATA_DIR / raw).resolve()

    allowed_roots = {_DATA_DIR.resolve(), Path(Cache().path).resolve()}
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise HTTPException(
            status_code=400, detail="Path must be within data or cache directory"
        )
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
        raise HTTPException(
            status_code=404, detail=f"Unable to read log file: {exc}"
        ) from exc

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
async def admin_read_log(
    source: str | None = None,
    path: str | None = None,
    tail_lines: int = 40,
    page: int = 1,
) -> dict[str, Any]:
    spec, abs_path = _resolve_runtime_log_request(source=source, path=path)
    if not abs_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Runtime log is not available yet: {spec.label}",
        )
    stat = abs_path.stat()
    payload = _read_log_file(abs_path, tail_lines=tail_lines, page=page)
    return {
        "source": spec.key,
        "label": spec.label,
        "category": spec.category,
        "description": spec.description,
        "path": _display_log_path(abs_path),
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


def _generate_adjustment_file_content(
    mappings: dict[str, str], archived_parents: list[str] | None = None
) -> str:
    archived_parents = archived_parents or []
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
    content.append("# Archived projects allowed as parent/root targets in the UI")
    content.append("archived_parent_projects = [")
    for name in sorted(set(archived_parents)):
        content.append(f'    "{name}",')
    content.append("]")
    content.append("")
    return "\n".join(content)


def _load_mapping_file(filename: str) -> tuple[dict[str, str], list[str]]:
    personal_dir = _DATA_DIR / "personal"
    personal_dir.mkdir(parents=True, exist_ok=True)
    target = _safe_data_path(str(Path("personal") / filename), suffix=".py")
    if not target.exists():
        target.write_text(_generate_adjustment_file_content({}, []), encoding="utf-8")
        return {}, []

    # Match dataframe.py behavior (exec python file) so the UI shows the effective mapping.
    import importlib.util
    import sys

    module_name = "dashboard_adjustments"
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        return {}, []
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    mapping = getattr(module, ADJUSTMENTS_VARIABLE_NAME, {})
    archived_parents = getattr(module, "archived_parent_projects", [])
    if not isinstance(archived_parents, list) or not all(
        isinstance(name, str) for name in archived_parents
    ):
        archived_parents = []
    return (mapping if isinstance(mapping, dict) else {}), archived_parents


def _save_mapping_file(
    filename: str, mappings: dict[str, str], archived_parents: list[str]
) -> None:
    target = _safe_data_path(str(Path("personal") / filename), suffix=".py")
    target.write_text(
        _generate_adjustment_file_content(mappings, archived_parents), encoding="utf-8"
    )


def _load_projects_for_adjustments_sync(
    refresh: bool,
) -> tuple[list[str], list[str], list[str], list[str]]:
    if not refresh and _state.db is not None:
        dbio = _state.db
    else:
        dbio = Database(".env")
    if dbio is None:
        raise RuntimeError("Database unavailable")
    active_projects = dbio.fetch_projects(include_tasks=False)
    archived_projects = dbio.fetch_archived_projects()
    active_root = sorted(
        {
            p.project_entry.name
            for p in active_projects
            if p.project_entry.parent_id is None
        }
    )
    archived_root = sorted(
        {
            p.project_entry.name
            for p in archived_projects
            if p.project_entry.parent_id is None
        }
    )
    archived_names = sorted({p.project_entry.name for p in archived_projects})
    remappable_active_root = sorted(
        [name for name in active_root if name in _REMAPPABLE_ACTIVE_ROOT_PROJECTS]
    )
    return active_root, archived_root, archived_names, remappable_active_root


def _read_yaml_config(path: Path, *, required: bool = True) -> DictConfig:
    if not path.exists():
        if required:
            raise HTTPException(
                status_code=404, detail=f"Missing config file: {path.name}"
            )
        return OmegaConf.create({})
    try:
        loaded = OmegaConf.load(path)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Failed to read {path.name}: {exc}"
        ) from exc
    if loaded is None:
        return OmegaConf.create({})
    return cast(DictConfig, loaded)


def _save_yaml_config(path: Path, config: DictConfig) -> None:
    try:
        OmegaConf.save(config, path, resolve=False)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Failed to write {path.name}: {exc}"
        ) from exc


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
            raise HTTPException(
                status_code=400, detail="due_date_days_difference must be an integer"
            ) from exc
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
        payload["children"] = [
            _template_to_camel(child)
            for child in children
            if isinstance(child, Mapping)
        ]
    return payload


class _TaskIngestNode(BaseModel):
    content: str
    description: str | None = None
    children: list["_TaskIngestNode"] = Field(default_factory=list)


class _TaskIngestTree(BaseModel):
    tasks: list[_TaskIngestNode] = Field(default_factory=list)


_TaskIngestNode.model_rebuild()


_BULLET_LINE_RE = re.compile(r"^(?P<indent>\s*)(?:[-*+]|(?:\d+|[A-Za-z])[.)])\s+(?P<content>.+?)\s*$")


def _task_ingest_db() -> Database:
    if _state.db is not None:
        return _state.db
    return Database(str(_resolve_env_path()))


def _task_ingest_project_payload(projects: Sequence[Project]) -> list[dict[str, Any]]:
    by_id = {project.id: project for project in projects}

    def project_path(project: Project) -> list[str]:
        names: list[str] = []
        current: Project | None = project
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            names.append(current.project_entry.name)
            parent_id = current.project_entry.parent_id
            current = by_id.get(str(parent_id)) if parent_id else None
        return list(reversed(names))

    payload = []
    for project in projects:
        path = project_path(project)
        payload.append(
            {
                "id": project.id,
                "name": project.project_entry.name,
                "label": " / ".join(path),
                "parentId": project.project_entry.parent_id,
            }
        )
    payload.sort(key=lambda item: str(item["label"]).lower())
    return payload


def _load_task_ingest_projects_sync(refresh: bool) -> list[dict[str, Any]]:
    dbio = _task_ingest_db() if not refresh else Database(str(_resolve_env_path()))
    return _task_ingest_project_payload(dbio.fetch_projects(include_tasks=False))


def _task_ingest_total_nodes(tasks: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for task in tasks:
        total += 1
        children = task.get("children")
        if isinstance(children, list):
            total += _task_ingest_total_nodes(
                [child for child in children if isinstance(child, Mapping)]
            )
    return total


def _task_ingest_trim_text(value: Any) -> str:
    return _sanitize_text(value) or ""


def _normalize_task_ingest_node(
    raw: Mapping[str, Any], *, depth: int = 1, max_depth: int = 3
) -> dict[str, Any] | None:
    content = _task_ingest_trim_text(raw.get("content"))
    if not content:
        return None
    node: dict[str, Any] = {"content": content}
    description = _task_ingest_trim_text(raw.get("description"))
    if description:
        node["description"] = description
    if depth < max_depth:
        raw_children = raw.get("children")
        if isinstance(raw_children, list):
            children = [
                normalized
                for child in raw_children
                if isinstance(child, Mapping)
                for normalized in [_normalize_task_ingest_node(child, depth=depth + 1, max_depth=max_depth)]
                if normalized is not None
            ]
            if children:
                node["children"] = children
    return node


def _task_ingest_tree_payload(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        normalized
        for task in tasks
        if isinstance(task, Mapping)
        for normalized in [_normalize_task_ingest_node(task)]
        if normalized is not None
    ]


def _heuristic_task_ingest_tree(raw_content: str) -> list[dict[str, Any]]:
    lines = raw_content.splitlines()
    roots: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = [(-1, {"children": roots})]
    current_node: dict[str, Any] | None = None
    preamble: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            current_node = None
            continue
        match = _BULLET_LINE_RE.match(line)
        if match:
            indent = len(match.group("indent").replace("\t", "    "))
            content = _task_ingest_trim_text(match.group("content"))
            if not content:
                continue
            node = {"content": content, "children": []}
            while len(stack) > 1 and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            parent.setdefault("children", []).append(node)
            stack.append((indent, node))
            current_node = node
            continue
        if current_node is not None:
            description = _task_ingest_trim_text(current_node.get("description"))
            current_node["description"] = f"{description}\n{stripped}".strip() if description else stripped
        else:
            preamble.append(stripped)

    if roots:
        heading = _task_ingest_trim_text(preamble[0]) if preamble else ""
        if heading:
            wrapper = {"content": heading, "children": roots}
            if len(preamble) > 1:
                wrapper["description"] = "\n".join(preamble[1:])
            return [wrapper]
        return roots

    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n+", raw_content) if segment.strip()]
    if len(paragraphs) > 1:
        tasks: list[dict[str, Any]] = []
        for paragraph in paragraphs:
            paragraph_lines = [part.strip() for part in paragraph.splitlines() if part.strip()]
            if not paragraph_lines:
                continue
            node: dict[str, Any] = {"content": paragraph_lines[0]}
            if len(paragraph_lines) > 1:
                node["description"] = "\n".join(paragraph_lines[1:])
            tasks.append(node)
        if tasks:
            return tasks

    sentences = [
        sentence.strip(" -\t")
        for sentence in re.split(r"(?:\n|;|(?<=\.)\s+)", raw_content)
        if sentence.strip(" -\t")
    ]
    if not sentences:
        return []
    if len(sentences) == 1:
        return [{"content": sentences[0]}]
    return [{"content": sentence} for sentence in sentences[:8]]


def _task_ingest_from_breakdown(nodes: Sequence[BreakdownNode]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for node in nodes:
        item: dict[str, Any] = {"content": _task_ingest_trim_text(node.content)}
        if not item["content"]:
            continue
        description = _task_ingest_trim_text(node.description)
        if description:
            item["description"] = description
        children = _task_ingest_from_breakdown(node.children)
        if children:
            item["children"] = children
        payload.append(item)
    return payload


def _task_ingest_build_llm_messages(raw_content: str) -> list[dict[str, str]]:
    return [
        {
            "role": MessageRole.SYSTEM.value,
            "content": (
                "Rewrite the pasted source into an actionable Todoist task tree. "
                "Return only concrete tasks. Keep titles concise and imperative. "
                "Use descriptions only for supporting context. Keep nesting to at most 3 levels total."
            ),
        },
        {
            "role": MessageRole.USER.value,
            "content": raw_content,
        },
    ]


def _task_ingest_rewrite_with_llm_sync(raw_content: str) -> tuple[list[dict[str, Any]], str] | None:
    async_loaded_model = _LLM_CHAT_MODEL
    model: _LlmChatModel | None = async_loaded_model
    created_model = False
    if model is None:
        settings = _resolve_llm_chat_settings()
        backend = settings["backend"]
        if backend == "openai" and settings["openai"]["configured"]:
            secret_key = _task_ingest_trim_text(settings["openai"].get("secretKey"))
            if secret_key:
                model = OpenAIResponsesChatModel(
                    OpenAIChatConfig(
                        api_key=secret_key,
                        key_name=_task_ingest_trim_text(settings["openai"].get("keyName")),
                        model=str(settings["openai"].get("model") or DEFAULT_OPENAI_MODEL),
                        max_output_tokens=768,
                    )
                )
                created_model = True
        elif backend == "triton_local":
            triton_settings = settings["triton"]
            model = TritonGenerateChatModel(
                TritonChatConfig(
                    base_url=str(triton_settings["baseUrl"]),
                    model_name=str(triton_settings["modelName"]),
                    model_id=str(triton_settings["modelId"]),
                    max_output_tokens=768,
                )
            )
            created_model = True
    if model is None:
        return None
    try:
        breakdown = model.structured_chat(
            _task_ingest_build_llm_messages(raw_content),
            TaskBreakdown,
        )
        tasks = _task_ingest_tree_payload(_task_ingest_from_breakdown(breakdown.children))
        if tasks:
            source = "llm"
            if created_model and isinstance(model, TritonGenerateChatModel):
                source = "triton"
            elif created_model and isinstance(model, OpenAIResponsesChatModel):
                source = "openai"
            elif not created_model:
                source = "loaded-model"
            return tasks, source
    except Exception as exc:  # pragma: no cover - fallback path
        logger.warning(f"Task ingest LLM rewrite failed: {type(exc).__name__}: {exc}")
    return None


def _task_ingest_preview_sync(raw_content: str) -> tuple[list[dict[str, Any]], str]:
    llm_result = _task_ingest_rewrite_with_llm_sync(raw_content)
    if llm_result is not None:
        return llm_result
    return _task_ingest_tree_payload(_heuristic_task_ingest_tree(raw_content)), "outline"


def _task_ingest_create_node_sync(
    dbio: Database,
    *,
    project_id: str,
    node: Mapping[str, Any],
    parent_id: str | None = None,
    created: list[dict[str, Any]],
) -> None:
    payload = dbio.insert_task(
        content=str(node["content"]),
        description=_task_ingest_trim_text(node.get("description")) or None,
        project_id=project_id if parent_id is None else None,
        parent_id=parent_id,
    )
    task_id = _task_ingest_trim_text(payload.get("id"))
    if not task_id:
        raise RuntimeError(f"Failed to create task: {node['content']}")
    created.append(
        {
            "id": task_id,
            "content": str(node["content"]),
            "parentId": parent_id,
            "projectId": project_id,
        }
    )
    children = node.get("children")
    if not isinstance(children, list):
        return
    for child in children:
        if isinstance(child, Mapping):
            _task_ingest_create_node_sync(
                dbio,
                project_id=project_id,
                node=child,
                parent_id=task_id,
                created=created,
            )


def _task_ingest_create_sync(project_id: str, tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dbio = _task_ingest_db()
    created: list[dict[str, Any]] = []
    for task in tasks:
        _task_ingest_create_node_sync(
            dbio,
            project_id=project_id,
            node=task,
            created=created,
        )
    return created


@app.get("/api/admin/task_ingest/projects", tags=["admin"])
async def admin_task_ingest_projects(refresh: bool = False) -> dict[str, Any]:
    try:
        projects = await asyncio.to_thread(_load_task_ingest_projects_sync, refresh)
    except Exception as exc:  # pragma: no cover - network safety
        raise HTTPException(
            status_code=500, detail=f"Failed to load projects: {type(exc).__name__}"
        ) from exc
    return {"projects": projects}


@app.post("/api/admin/task_ingest/preview", tags=["admin"])
async def admin_task_ingest_preview(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    raw_content = _task_ingest_trim_text(payload.get("rawContent"))
    if not raw_content:
        raise HTTPException(status_code=400, detail="rawContent is required")
    tasks, source = await asyncio.to_thread(_task_ingest_preview_sync, raw_content)
    if not tasks:
        raise HTTPException(status_code=400, detail="Could not derive any tasks from the pasted content.")
    return {
        "source": source,
        "tasks": tasks,
        "topLevelCount": len(tasks),
        "totalCount": _task_ingest_total_nodes(tasks),
    }


@app.post("/api/admin/task_ingest/create", tags=["admin"])
async def admin_task_ingest_create(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    project_id = _task_ingest_trim_text(payload.get("projectId"))
    raw_content = _task_ingest_trim_text(payload.get("rawContent"))
    tasks_payload = payload.get("tasks")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required")
    if isinstance(tasks_payload, list):
        tasks = _task_ingest_tree_payload(
            [task for task in tasks_payload if isinstance(task, Mapping)]
        )
    elif raw_content:
        tasks, _ = await asyncio.to_thread(_task_ingest_preview_sync, raw_content)
    else:
        raise HTTPException(status_code=400, detail="tasks or rawContent is required")
    if not tasks:
        raise HTTPException(status_code=400, detail="No tasks to create")
    try:
        created = await asyncio.to_thread(_task_ingest_create_sync, project_id, tasks)
    except Exception as exc:  # pragma: no cover - network safety
        raise HTTPException(
            status_code=500, detail=f"Failed to create tasks: {exc}"
        ) from exc
    return {
        "created": created,
        "createdCount": len(created),
        "topLevelCount": len(tasks),
    }


@app.get("/api/admin/project_adjustments", tags=["admin"])
async def admin_project_adjustments(
    file: str | None = None, refresh: bool = False
) -> dict[str, Any]:
    """Return mapping files, current mapping content, and project lists for building adjustments."""

    selected = file or _available_mapping_files()[0]
    mappings, archived_parents = _load_mapping_file(selected)
    warning: str | None = None
    try:
        (
            active_root,
            archived_root,
            archived_names,
            remappable_active_root,
        ) = await asyncio.to_thread(
            _load_projects_for_adjustments_sync,
            refresh,
        )
    except Exception as exc:  # pragma: no cover - network safety
        logger.warning(f"Failed loading project lists for adjustments: {exc}")
        active_root = []
        archived_root = []
        archived_names = []
        remappable_active_root = []
        warning = f"Project list unavailable ({type(exc).__name__}). Showing saved mappings only."
    source_projects = sorted(set(archived_names) | set(remappable_active_root))
    unmapped_source_projects = [name for name in source_projects if name not in mappings]
    archived_parents = sorted(
        [name for name in archived_parents if name in archived_names]
    )

    return {
        "files": _available_mapping_files(),
        "selectedFile": selected,
        "mappings": mappings,
        "activeRootProjects": active_root,
        "archivedRootProjects": archived_root,
        "remappableActiveRootProjects": remappable_active_root,
        "archivedParentProjects": archived_parents,
        "archivedProjects": archived_names,
        "sourceProjects": source_projects,
        "unmappedSourceProjects": unmapped_source_projects,
        "warning": warning,
    }


@app.put("/api/admin/project_adjustments", tags=["admin"])
async def admin_save_project_adjustments(
    file: str,
    refresh: bool = True,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Save mapping dict to the selected mapping file."""

    mappings: dict[str, str]
    archived_parents: list[str]
    if isinstance(payload.get("mappings"), dict) or "archivedParents" in payload:
        mappings = payload.get("mappings") or {}
        archived_parents = payload.get("archivedParents") or []
    else:
        mappings = payload if isinstance(payload, dict) else {}
        archived_parents = []

    if not isinstance(mappings, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in mappings.items()
    ):
        raise HTTPException(
            status_code=400,
            detail="Body must be a JSON object of string->string mappings",
        )
    if not isinstance(archived_parents, list) or not all(
        isinstance(name, str) for name in archived_parents
    ):
        raise HTTPException(
            status_code=400, detail="archivedParents must be a list of strings"
        )

    async with _ADMIN_LOCK:
        _save_mapping_file(file, mappings, archived_parents)
        if refresh:
            await _ensure_state(refresh=True)
    return {
        "saved": True,
        "file": file,
        "count": len(mappings),
        "archivedParents": len(archived_parents),
    }


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
            raise HTTPException(
                status_code=400, detail=f"{field} must be an integer"
            ) from exc

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
        updates["max_total_tasks"] = _coerce_int(
            payload["maxTotalTasks"], "maxTotalTasks"
        )
    if "maxQueueDepth" in payload:
        updates["max_queue_depth"] = _coerce_int(
            payload["maxQueueDepth"], "maxQueueDepth"
        )
    if "autoQueueChildren" in payload:
        updates["auto_queue_children"] = bool(payload["autoQueueChildren"])

    if "variants" in payload:
        variants_raw = payload.get("variants")
        if not isinstance(variants_raw, Mapping):
            raise HTTPException(status_code=400, detail="variants must be an object")
        variants: dict[str, Any] = {}
        for key, value in variants_raw.items():
            if not isinstance(value, Mapping):
                raise HTTPException(
                    status_code=400, detail=f"Variant {key} must be an object"
                )
            instruction = str(value.get("instruction", "")).strip()
            variant_payload: dict[str, Any] = {"instruction": instruction}
            if "maxDepth" in value and value.get("maxDepth") not in (None, ""):
                variant_payload["max_depth"] = _coerce_int(
                    value.get("maxDepth"), "maxDepth"
                )
            if "maxChildren" in value and value.get("maxChildren") not in (None, ""):
                variant_payload["max_children"] = _coerce_int(
                    value.get("maxChildren"), "maxChildren"
                )
            if "queueDepth" in value and value.get("queueDepth") not in (None, ""):
                variant_payload["queue_depth"] = _coerce_int(
                    value.get("queueDepth"), "queueDepth"
                )
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
        snapshot = (
            OmegaConf.to_container(lb_config, resolve=False)
            if isinstance(lb_config, DictConfig)
            else lb_config
        )
        default_variant = updates.get("default_variant") or (
            snapshot.get("default_variant") if isinstance(snapshot, Mapping) else None
        )
        variants_value = updates.get("variants") or (
            snapshot.get("variants") if isinstance(snapshot, Mapping) else None
        )
        if (
            default_variant
            and isinstance(variants_value, Mapping)
            and default_variant not in variants_value
        ):
            raise HTTPException(
                status_code=400, detail="defaultVariant must exist in variants"
            )

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
        "flatLeafTemplate": config_data.get(
            "flat_leaf_template", defaults.flat_leaf_template
        ),
        "deepLeafTemplate": config_data.get(
            "deep_leaf_template", defaults.deep_leaf_template
        ),
        "flatLabelRegex": config_data.get(
            "flat_label_regex", defaults.flat_label_regex
        ),
        "deepLabelRegex": config_data.get(
            "deep_label_regex", defaults.deep_label_regex
        ),
    }


def _dashboard_settings_payload(config: DictConfig) -> dict[str, Any]:
    raw = config.get("urgency") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}
    defaults = DEFAULT_URGENCY_SETTINGS
    badge_labels = data.get("badge_labels") if isinstance(data.get("badge_labels"), Mapping) else {}
    badge_labels = badge_labels if isinstance(badge_labels, Mapping) else {}
    thresholds = data.get("warn_priority_thresholds")
    if not isinstance(thresholds, list):
        thresholds = list(defaults["warn_priority_thresholds"])
    fire_labels = data.get("fire_labels")
    if not isinstance(fire_labels, list):
        fire_label_value = str(data.get("fire_label", defaults["fire_label"])).strip()
        fire_labels = [fire_label_value] if fire_label_value else list(defaults["fire_labels"])
    try:
        config_path = str(_DASHBOARD_CONFIG_PATH.relative_to(_REPO_ROOT))
    except ValueError:
        config_path = str(_DASHBOARD_CONFIG_PATH)

    return {
        "enabled": bool(data.get("enabled", defaults["enabled"])),
        "fireLabel": data.get("fire_label", defaults["fire_label"]),
        "fireLabels": fire_labels,
        "warnPriorityThresholds": thresholds,
        "warnPriorityMinCount": data.get(
            "warn_priority_min_count", defaults["warn_priority_min_count"]
        ),
        "warnDueWithinDays": data.get(
            "warn_due_within_days", defaults["warn_due_within_days"]
        ),
        "warnDueMinCount": data.get(
            "warn_due_min_count", defaults["warn_due_min_count"]
        ),
        "warnDeadlineWithinDays": data.get(
            "warn_deadline_within_days", defaults["warn_deadline_within_days"]
        ),
        "warnDeadlineMinCount": data.get(
            "warn_deadline_min_count", defaults["warn_deadline_min_count"]
        ),
        "dangerOnFireLabel": bool(
            data.get("danger_on_fire_label", defaults["danger_on_fire_label"])
        ),
        "warnOnPriority": bool(
            data.get("warn_on_priority", defaults["warn_on_priority"])
        ),
        "warnOnDue": bool(data.get("warn_on_due", defaults["warn_on_due"])),
        "warnOnDeadline": bool(
            data.get("warn_on_deadline", defaults["warn_on_deadline"])
        ),
        "warnSummaryLabel": data.get(
            "warn_summary_label", defaults["warn_summary_label"]
        ),
        "dangerSummaryLabel": data.get(
            "danger_summary_label", defaults["danger_summary_label"]
        ),
        "badgeLabels": {
            "good": badge_labels.get("good", defaults["badge_labels"]["good"]),
            "warn": badge_labels.get("warn", defaults["badge_labels"]["warn"]),
            "danger": badge_labels.get("danger", defaults["badge_labels"]["danger"]),
        },
        "configPath": config_path,
    }


@app.get("/api/admin/dashboard/settings", tags=["admin"])
async def admin_dashboard_settings() -> dict[str, Any]:
    config = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
    try:
        config_path = str(_DASHBOARD_CONFIG_PATH.relative_to(_REPO_ROOT))
    except ValueError:
        config_path = str(_DASHBOARD_CONFIG_PATH)
    return {
        "settings": _dashboard_settings_payload(config),
        "editTargets": [
            {
                "key": "urgency",
                "label": "Urgency watch badge",
                "icon": "wrench",
                "configPath": config_path,
                "anchor": "dashboard-settings",
            }
        ],
    }


@app.get("/api/admin/dashboard/labels", tags=["admin"])
async def admin_dashboard_labels() -> dict[str, Any]:
    dbio = Database(str(_resolve_env_path()))
    label_colors = dbio.fetch_label_colors()
    labels: list[dict[str, Any]] = []
    for item in dbio.list_labels():
        name = item["name"].strip()
        labels.append(
            {
                "name": name,
                "color": label_colors.get(name),
            }
        )
    if not any(item["name"] == DEFAULT_URGENCY_SETTINGS["fire_label"] for item in labels):
        labels.append(
            {
                "name": DEFAULT_URGENCY_SETTINGS["fire_label"],
                "color": label_colors.get(DEFAULT_URGENCY_SETTINGS["fire_label"]),
            }
        )
    labels.sort(key=lambda item: item["name"].lower())
    return {"labels": labels}


@app.put("/api/admin/dashboard/settings", tags=["admin"])
async def admin_update_dashboard_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    config = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
    urgency = config.get("urgency") or {}
    if not isinstance(urgency, Mapping):
        urgency = {}
    urgency = dict(urgency)

    def _coerce_int(value: Any, field: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{field} must be an integer") from exc

    if "enabled" in payload:
        urgency["enabled"] = bool(payload["enabled"])
    if "fireLabel" in payload:
        urgency["fire_label"] = str(payload["fireLabel"]).strip()
    if "fireLabels" in payload:
        fire_labels = payload["fireLabels"]
        if not isinstance(fire_labels, Sequence) or isinstance(fire_labels, str):
            raise HTTPException(status_code=400, detail="fireLabels must be a list")
        urgency["fire_labels"] = [
            str(value).strip() for value in fire_labels if str(value).strip()
        ]
        if urgency["fire_labels"]:
            urgency["fire_label"] = urgency["fire_labels"][0]
    if "warnPriorityThresholds" in payload:
        thresholds = payload["warnPriorityThresholds"]
        if not isinstance(thresholds, Sequence):
            raise HTTPException(status_code=400, detail="warnPriorityThresholds must be a list")
        urgency["warn_priority_thresholds"] = [
            _coerce_int(value, "warnPriorityThresholds") for value in thresholds
        ]
    if "warnPriorityMinCount" in payload:
        urgency["warn_priority_min_count"] = max(
            1, _coerce_int(payload["warnPriorityMinCount"], "warnPriorityMinCount")
        )
    if "warnDueWithinDays" in payload:
        urgency["warn_due_within_days"] = _coerce_int(
            payload["warnDueWithinDays"], "warnDueWithinDays"
        )
    if "warnDueMinCount" in payload:
        urgency["warn_due_min_count"] = max(
            1, _coerce_int(payload["warnDueMinCount"], "warnDueMinCount")
        )
    if "warnDeadlineWithinDays" in payload:
        urgency["warn_deadline_within_days"] = _coerce_int(
            payload["warnDeadlineWithinDays"], "warnDeadlineWithinDays"
        )
    if "warnDeadlineMinCount" in payload:
        urgency["warn_deadline_min_count"] = max(
            1, _coerce_int(payload["warnDeadlineMinCount"], "warnDeadlineMinCount")
        )
    if "dangerOnFireLabel" in payload:
        urgency["danger_on_fire_label"] = bool(payload["dangerOnFireLabel"])
    if "warnOnPriority" in payload:
        urgency["warn_on_priority"] = bool(payload["warnOnPriority"])
    if "warnOnDue" in payload:
        urgency["warn_on_due"] = bool(payload["warnOnDue"])
    if "warnOnDeadline" in payload:
        urgency["warn_on_deadline"] = bool(payload["warnOnDeadline"])
    if "warnSummaryLabel" in payload:
        urgency["warn_summary_label"] = str(payload["warnSummaryLabel"]).strip()
    if "dangerSummaryLabel" in payload:
        urgency["danger_summary_label"] = str(payload["dangerSummaryLabel"]).strip()
    if "badgeLabels" in payload:
        badge_labels = payload["badgeLabels"]
        if not isinstance(badge_labels, Mapping):
            raise HTTPException(status_code=400, detail="badgeLabels must be an object")
        urgency["badge_labels"] = {
            "good": str(badge_labels.get("good") or DEFAULT_URGENCY_SETTINGS["badge_labels"]["good"]).strip(),
            "warn": str(badge_labels.get("warn") or DEFAULT_URGENCY_SETTINGS["badge_labels"]["warn"]).strip(),
            "danger": str(badge_labels.get("danger") or DEFAULT_URGENCY_SETTINGS["badge_labels"]["danger"]).strip(),
        }

    config["urgency"] = urgency
    async with _ADMIN_LOCK:
        _save_yaml_config(_DASHBOARD_CONFIG_PATH, config)

    try:
        config_path = str(_DASHBOARD_CONFIG_PATH.relative_to(_REPO_ROOT))
    except ValueError:
        config_path = str(_DASHBOARD_CONFIG_PATH)

    return {
        "saved": True,
        "settings": _dashboard_settings_payload(config),
        "editTargets": [
            {
                "key": "urgency",
                "label": "Urgency watch badge",
                "icon": "wrench",
                "configPath": config_path,
                "anchor": "dashboard-settings",
            }
        ],
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
        raise HTTPException(
            status_code=400, detail="flatLeafTemplate and deepLeafTemplate are required"
        )

    config = _read_yaml_config(_AUTOMATIONS_PATH)
    multiply_cfg = config.get("multiply") or {}
    existing = (
        OmegaConf.to_container(multiply_cfg, resolve=False) if multiply_cfg else {}
    )
    if not isinstance(existing, dict):
        existing = {}
    config_data = (
        existing.get("config") if isinstance(existing.get("config"), Mapping) else {}
    )
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
    task_templates = (
        OmegaConf.to_container(template_cfg.get("task_templates"), resolve=False)
        if template_cfg
        else {}
    )
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
        item
        for item in defaults
        if not (isinstance(item, Mapping) and entry_key in item)
    ]
    templates_cfg["defaults"] = defaults

    automations_cfg = _read_yaml_config(_AUTOMATIONS_PATH)
    template_cfg = automations_cfg.get("template") or {}
    task_templates = (
        OmegaConf.to_container(template_cfg.get("task_templates"), resolve=False)
        if template_cfg
        else {}
    )
    if isinstance(task_templates, dict) and safe_name in task_templates:
        del task_templates[safe_name]
    template_cfg["task_templates"] = task_templates
    automations_cfg["template"] = template_cfg
    async with _ADMIN_LOCK:
        _save_yaml_config(_TEMPLATES_REGISTRY_PATH, templates_cfg)
        _save_yaml_config(_AUTOMATIONS_PATH, automations_cfg)

    return {"deleted": True, "category": safe_category, "name": safe_name}
