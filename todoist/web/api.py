# pyright: reportFunctionMemberAccess=false, reportPossiblyUnboundVariable=false
# pylint: disable=global-statement,too-many-lines,protected-access,unused-import

import asyncio
from collections.abc import Mapping, Sequence
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4
import contextlib
import io
import os
import re
import os.path
from pathlib import Path
import signal
import subprocess
import threading

import time

import pandas as pd
import numpy as np
import hydra
import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger
from omegaconf import DictConfig, OmegaConf
from todoist.database.base import Database
from todoist.database.dataframe import (
    DEFAULT_ADJUSTMENTS_FILENAME,
    load_adjustments_file,
    load_activity_data,
    normalize_adjustment_filename,
    render_adjustments_file_content,
    resolve_personal_dir,
)
from todoist.status_update import build_status_update_report, load_status_update_projects
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
from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.gmail_tasks import (
    GmailTasksAutomation,
    resolve_gmail_credentials_path,
    resolve_gmail_token_path,
)
from todoist.automations.observer import AutomationObserver
from todoist.automations.llm_breakdown.config import (
    BASE_SYSTEM_PROMPT,
)
from todoist.automations.llm_breakdown.models import ProgressKey
from todoist.automations.llm_breakdown.models import TaskBreakdown, BreakdownNode
from todoist.llm import (
    CodexCliChatModel,
    DEFAULT_CODEX_MODEL,
    DEFAULT_MODEL_ID,
    DEFAULT_TRITON_MODEL_NAME,
    DEFAULT_TRITON_URL,
    MessageRole,
    TritonChatConfig,
    TritonGenerateChatModel,
)
from todoist.llm.codex_llm import codex_config_from_values
from todoist.llm.llm_utils import _sanitize_text
from todoist.llm.usage import load_llm_usage_summary
from todoist.llm.model_catalog import CODEX_MODEL_OPTIONS, TRITON_MODEL_OPTIONS
from todoist.dashboard_settings import (
    load_dashboard_config,
    observer_settings_payload,
    resolve_dashboard_config_path,
)
from todoist.web.dashboard_payload import (
    DEFAULT_URGENCY_SETTINGS,
    compute_plot_range as _compute_plot_range,
    empty_activity_df as _empty_activity_df,
    evaluate_urgency_status as _evaluate_urgency_status,
    normalize_activity_df as _normalize_activity_df,
    normalize_plot_events as _normalize_plot_events,
)
from todoist.web.routes.admin_automations import router as _admin_automations_router
from todoist.web.routes.api_routes import router as _api_routes_router
from todoist.web.api_components.logs import (
    RuntimeLogSpec as _RuntimeLogSpec,
    display_log_path as _component_display_log_path,
    read_log_file as _read_log_file,
    resolve_runtime_log_request as _component_resolve_runtime_log_request,
    resolve_runtime_log_source as _component_resolve_runtime_log_source,
    runtime_log_path as _component_runtime_log_path,
    runtime_log_sources as _component_runtime_log_sources,
)
from todoist.web.api_components.runtime import (
    REPO_ROOT as _REPO_ROOT,
    dashboard_pid_dir as _dashboard_pid_dir,
    dashboard_state_dir as _dashboard_state_dir,
    detect_system_timezone as _detect_system_timezone,
    is_valid_timezone_name as _is_valid_timezone_name,
    looks_like_api_key as _looks_like_api_key,
    mask_api_key as _mask_api_key,
    normalize_api_key as _normalize_api_key,
    normalize_timezone as _normalize_timezone,
    resolve_api_key as _resolve_api_key,
    resolve_config_dir as _resolve_config_dir,
    resolve_data_dir as _resolve_data_dir,
    resolve_env_path as _resolve_env_path,
    safe_display_path as _safe_display_path,
    validate_api_token as _validate_api_token,
)
from todoist.web.api_components.settings import (
    dashboard_settings_payload as _component_dashboard_settings_payload,
    llm_breakdown_settings_payload as _llm_breakdown_settings_payload,
    multiplication_settings_payload as _multiplication_settings_payload,
    stale_tasks_settings_payload as _stale_tasks_settings_payload,
)
from todoist.web.api_components.templates import (
    ensure_identifier as _ensure_identifier,
    load_defaults_list as _load_defaults_list,
    normalize_template_node as _normalize_template_node,
    read_yaml_config as _read_yaml_config,
    save_yaml_config as _save_yaml_config,
    template_defaults_key as _template_defaults_key,
    template_path as _component_template_path,
    template_summary as _component_template_summary,
    template_to_camel as _template_to_camel,
)
from todoist.web.api_components import llm_chat as _llm_chat_component
from todoist.web.api_components import task_ingest as _task_ingest_component
from todoist.web.api_components import dashboard_runtime as _dashboard_runtime_component
from todoist.web.api_components import automation_runtime as _automation_runtime_component
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
app.include_router(_admin_automations_router)
app.include_router(_api_routes_router)

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
_DASHBOARD_STATE_SCHEMA_VERSION = 2
_DEMO_DASHBOARD_STATE_SCHEMA_VERSION = 2
_main_loop: asyncio.AbstractEventLoop | None = None
_TQDM_STEP_MAP = {
    "Checking Todoist updates": 1,
    "Querying project data": 1,
    "Checking activity cache": 1,
    "Backfilling activity history": 1,
    "Fetching activity history": 1,
    "Fetching recent activity": 1,
    "Fetching archived project activity": 1,
    "Resolving project hierarchy": 2,
    "Building project hierarchy": 2,
    "Querying activity data": 1,
}

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

_DATA_DIR = _resolve_data_dir()
_CONFIG_DIR = _resolve_config_dir()
_AUTOMATIONS_PATH = _CONFIG_DIR / "automations.yaml"
_DASHBOARD_CONFIG_PATH = resolve_dashboard_config_path()
_TEMPLATES_REGISTRY_PATH = _CONFIG_DIR / "templates.yaml"
_TEMPLATES_DIR = _CONFIG_DIR / "templates"
_TRITON_MODEL_OPTIONS = TRITON_MODEL_OPTIONS
_CODEX_MODEL_OPTIONS = CODEX_MODEL_OPTIONS

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
        "envPath": _safe_display_path(env_path, root=_REPO_ROOT),
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
_LLM_CHAT_BACKEND_DEFAULT = "disabled"
_LLM_CHAT_BACKEND_LABELS = {
    "disabled": "Disabled",
    "triton_local": "Triton local",
    "codex": "Codex",
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

_LlmChatModel = CodexCliChatModel | TritonGenerateChatModel

_LLM_CHAT_MODEL: _LlmChatModel | None = None
_LLM_CHAT_MODEL_LOADING = False
_LLM_CHAT_MODEL_LOCK = asyncio.Lock()
_LLM_CHAT_STORAGE_LOCK = asyncio.Lock()
_LLM_CHAT_WORKER_LOCK = asyncio.Lock()
_LLM_CHAT_WORKER_RUNNING = False
_LLM_CHAT_AGENT = None
_LLM_CHAT_AGENT_LOCK = asyncio.Lock()

def _call_dashboard_runtime(name: str, *args: Any, **kwargs: Any) -> Any:
    _dashboard_runtime_component._sync_api_globals()
    return getattr(_dashboard_runtime_component, name)(*args, **kwargs)

def _env_demo_mode() -> bool:
    return bool(_call_dashboard_runtime("_env_demo_mode"))

def _run_async_in_main_loop(coro: Any) -> Any:
    return _call_dashboard_runtime("_run_async_in_main_loop", coro)

async def _progress_snapshot() -> dict[str, Any]:
    return await _call_dashboard_runtime("_progress_snapshot")

async def _set_progress(stage: str, step: int, total_steps: int = _PROGRESS_TOTAL_STEPS) -> None:
    await _call_dashboard_runtime("_set_progress", stage, step, total_steps)

async def _finish_progress(error: str | None = None) -> None:
    await _call_dashboard_runtime("_finish_progress", error)

def _build_tqdm_progress_callback():
    return _call_dashboard_runtime("_build_tqdm_progress_callback")

def _activity_cache_signature() -> dict[str, int] | None:
    return _call_dashboard_runtime("_activity_cache_signature")


def _persist_state_to_disk_cache(*, demo_mode: bool) -> None:
    _call_dashboard_runtime("_persist_state_to_disk_cache", demo_mode=demo_mode)


def _load_state_from_disk_cache(*, demo_mode: bool) -> bool:
    return bool(_call_dashboard_runtime("_load_state_from_disk_cache", demo_mode=demo_mode))


def _refresh_state_sync(*, demo_mode: bool) -> None:
    _call_dashboard_runtime("_refresh_state_sync", demo_mode=demo_mode)


async def _ensure_state(refresh: bool, *, demo_mode: bool | None = None) -> None:
    await _call_dashboard_runtime("_ensure_state", refresh, demo_mode=demo_mode)


def _cache_runtime_path(filename: str) -> Path:
    return _call_dashboard_runtime("_cache_runtime_path", filename)


def _stat_file(path: str | Path) -> dict[str, Any] | None:
    return _call_dashboard_runtime("_stat_file", path)


def _service_statuses() -> list[dict[str, Any]]:
    return _call_dashboard_runtime("_service_statuses")


def _llm_breakdown_snapshot() -> dict[str, Any]:
    return _call_dashboard_runtime("_llm_breakdown_snapshot")


for _component_wrapper_name in _dashboard_runtime_component._COMPONENT_EXPORTS:
    globals()[_component_wrapper_name]._component_wrapper_for = _component_wrapper_name
del _component_wrapper_name


def _normalize_chat_message(raw: Any) -> dict[str, Any] | None:
    return _llm_chat_component._normalize_chat_message(raw)
def _normalize_chat_conversation(raw: Any) -> dict[str, Any] | None:
    return _llm_chat_component._normalize_chat_conversation(raw)
def _normalize_chat_queue_item(raw: Any) -> dict[str, Any] | None:
    return _llm_chat_component._normalize_chat_queue_item(raw)
def _load_llm_chat_conversations() -> list[dict[str, Any]]:
    return _llm_chat_component._load_llm_chat_conversations()
def _save_llm_chat_conversations(conversations: list[dict[str, Any]]) -> None:
    return _llm_chat_component._save_llm_chat_conversations(conversations)
def _load_llm_chat_queue() -> list[dict[str, Any]]:
    return _llm_chat_component._load_llm_chat_queue()
def _save_llm_chat_queue(items: list[dict[str, Any]]) -> None:
    return _llm_chat_component._save_llm_chat_queue(items)
def _truncate_text(value: str, limit: int = 120) -> str:
    return _llm_chat_component._truncate_text(value, limit)
def _conversation_summary(conv: dict[str, Any]) -> dict[str, Any]:
    return _llm_chat_component._conversation_summary(conv)
def _queue_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _llm_chat_component._queue_item_payload(item)
def _parse_iso_timestamp(value: Any) -> datetime | None:
    return _llm_chat_component._parse_iso_timestamp(value)
def _expire_llm_chat_queue(queue: list[dict[str, Any]], now_dt: datetime) -> bool:
    return _llm_chat_component._expire_llm_chat_queue(queue, now_dt)
def _prune_queue(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _llm_chat_component._prune_queue(queue)
def _available_llm_chat_devices() -> list[str]:
    return _llm_chat_component._available_llm_chat_devices()
def _llm_model_options_payload(
    options: Sequence[Mapping[str, str]], selected: str
) -> list[dict[str, Any]]:
    return _llm_chat_component._llm_model_options_payload(options, selected)
def _normalize_llm_chat_backend(raw: Any) -> str:
    return _llm_chat_component._normalize_llm_chat_backend(raw)
def _normalize_llm_chat_device(raw: Any, *, available_devices: Sequence[str]) -> str:
    return _llm_chat_component._normalize_llm_chat_device(raw, available_devices=available_devices)
def _resolve_triton_settings(file_values: Mapping[str, Any]) -> dict[str, Any]:
    return _llm_chat_component._resolve_triton_settings(file_values)
def _resolve_codex_settings(file_values: Mapping[str, Any]) -> dict[str, Any]:
    return _llm_chat_component._resolve_codex_settings(file_values)
def _triton_ready(triton_settings: Mapping[str, Any]) -> bool:
    return _llm_chat_component._triton_ready(triton_settings)
def _resolve_llm_chat_settings() -> dict[str, Any]:
    return _llm_chat_component._resolve_llm_chat_settings()
async def _reset_llm_chat_runtime() -> None:
    global _LLM_CHAT_MODEL, _LLM_CHAT_MODEL_LOADING, _LLM_CHAT_AGENT
    async with _LLM_CHAT_MODEL_LOCK:
        _LLM_CHAT_MODEL = None
        _LLM_CHAT_MODEL_LOADING = False
    async with _LLM_CHAT_AGENT_LOCK:
        _LLM_CHAT_AGENT = None


def _public_llm_chat_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return _llm_chat_component._public_llm_chat_settings(settings)
def _build_llm_from_settings(
    settings: Mapping[str, Any],
    *,
    max_output_tokens: int,
) -> _LlmChatModel:
    return _llm_chat_component._build_llm_from_settings(settings, max_output_tokens=max_output_tokens)
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
        model = await asyncio.to_thread(
            _build_llm_from_settings,
            settings,
            max_output_tokens=256,
        )
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
    return _llm_chat_component._build_chat_messages(conversation, user_content)
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
        if _LLM_CHAT_MODEL is None and _LLM_CHAT_MODEL_LOADING:
            return
        if _LLM_CHAT_MODEL is None and _resolve_llm_chat_settings()["backend"] != "codex":
            return
        _LLM_CHAT_WORKER_RUNNING = True
    asyncio.create_task(_run_llm_chat_queue())


async def _load_inline_codex_chat_model() -> tuple[_LlmChatModel | None, str | None]:
    global _LLM_CHAT_MODEL, _LLM_CHAT_MODEL_LOADING
    settings = _resolve_llm_chat_settings()
    if settings["backend"] != "codex":
        return None, "Model not loaded. Click Enable in the dashboard first."

    async with _LLM_CHAT_MODEL_LOCK:
        if _LLM_CHAT_MODEL is not None:
            return _LLM_CHAT_MODEL, None
        if _LLM_CHAT_MODEL_LOADING:
            return None, "Model is still loading."
        _LLM_CHAT_MODEL_LOADING = True

    try:
        model = await asyncio.to_thread(
            _build_llm_from_settings,
            settings,
            max_output_tokens=256,
        )
        async with _LLM_CHAT_MODEL_LOCK:
            _LLM_CHAT_MODEL = model
        return model, None
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Failed to load inline Codex chat model: {exc}")
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        async with _LLM_CHAT_MODEL_LOCK:
            _LLM_CHAT_MODEL_LOADING = False


async def _run_llm_chat_queue_inline() -> None:
    global _LLM_CHAT_WORKER_RUNNING
    async with _LLM_CHAT_WORKER_LOCK:
        if _LLM_CHAT_WORKER_RUNNING:
            return
        _LLM_CHAT_WORKER_RUNNING = True
    await _run_llm_chat_queue()


async def _run_llm_chat_queue() -> None:
    global _LLM_CHAT_WORKER_RUNNING
    try:
        while True:
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

            async with _LLM_CHAT_MODEL_LOCK:
                model = _LLM_CHAT_MODEL
            if model is None:
                model, load_error = await _load_inline_codex_chat_model()
                if model is None:
                    async with _LLM_CHAT_STORAGE_LOCK:
                        queue = _load_llm_chat_queue()
                        for item in queue:
                            if item.get("id") == next_item["id"]:
                                if item.get("status") != "running":
                                    break
                                item["status"] = "failed"
                                item["finished_at"] = _now_iso()
                                item["error"] = load_error or "Model unavailable"
                                break
                        _save_llm_chat_queue(queue)
                    continue

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
    return await _llm_chat_component._llm_chat_snapshot()


for _component_wrapper_name in _llm_chat_component._COMPONENT_EXPORTS:
    if _component_wrapper_name in globals():
        globals()[_component_wrapper_name]._component_wrapper_for = _component_wrapper_name
del _component_wrapper_name


def _call_automation_runtime(name: str, *args: Any, **kwargs: Any) -> Any:
    _automation_runtime_component._sync_api_globals()
    return getattr(_automation_runtime_component, name)(*args, **kwargs)


def _make_automation_runtime_wrapper(name: str):
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return _call_automation_runtime(name, *args, **kwargs)

    _wrapper.__name__ = name
    _wrapper._component_wrapper_for = name
    return _wrapper


_AUTOMATION_RUNTIME_EXPORTS = (
    "_serialize_dt",
    "_run_automation_sync",
    "_run_all_automations_sync",
    "_load_automations",
    "_available_automation_keys",
    "_automation_ref",
    "_automation_requires_auth",
    "_default_enabled_automation_keys",
    "_configured_enabled_automation_keys",
    "_enabled_automation_keys",
    "_clear_gmail_auth_session",
    "_current_gmail_auth_session",
    "_write_gmail_token",
    "_allow_insecure_oauth_transport",
    "_start_gmail_manual_auth_session",
    "_gmail_automation_status",
    "_automation_metadata_for_key",
    "_load_automation_inventory",
    "_save_enabled_automations",
    "_set_automation_enabled",
    "_restart_dashboard_observer_if_managed",
    "_automation_run_signal_metadata",
    "_automation_launch_metadata",
    "_load_observer_state",
    "_serialize_observer_state",
    "_build_observer",
)
for _name in _AUTOMATION_RUNTIME_EXPORTS:
    globals()[_name] = _make_automation_runtime_wrapper(_name)
_PendingGmailAuthSession = _automation_runtime_component._PendingGmailAuthSession


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


def _display_log_path(path: Path) -> str:
    return _component_display_log_path(
        path, data_dir=_DATA_DIR, cache_dir=Path(Cache().path)
    )


def _runtime_log_path(spec: _RuntimeLogSpec) -> Path:
    return _component_runtime_log_path(spec, cache_dir=Path(Cache().path))


def _runtime_log_sources() -> list[dict[str, Any]]:
    return _component_runtime_log_sources(
        data_dir=_DATA_DIR, cache_dir=Path(Cache().path)
    )


def _resolve_runtime_log_source(source: str) -> tuple[_RuntimeLogSpec, Path]:
    return _component_resolve_runtime_log_source(source, cache_dir=Path(Cache().path))


def _resolve_runtime_log_request(
    *, source: str | None = None, path: str | None = None
) -> tuple[_RuntimeLogSpec, Path]:
    return _component_resolve_runtime_log_request(
        data_dir=_DATA_DIR,
        cache_dir=Path(Cache().path),
        source=source,
        path=path,
    )


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


def _available_mapping_files() -> list[str]:
    personal_dir = resolve_personal_dir()
    if not personal_dir.exists():
        return [DEFAULT_ADJUSTMENTS_FILENAME]

    mapping_files: list[str] = []
    for file in sorted(personal_dir.iterdir()):
        if not file.is_file() or file.name.startswith("__") or file.suffix != ".py":
            continue
        try:
            normalized = normalize_adjustment_filename(file.name)
            load_adjustments_file(file)
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping invalid project adjustment file {}: {}", file, exc)
            continue
        mapping_files.append(normalized)

    return sorted(mapping_files) if mapping_files else [DEFAULT_ADJUSTMENTS_FILENAME]


def _load_mapping_file(filename: str) -> tuple[dict[str, str], list[str]]:
    safe_filename = normalize_adjustment_filename(filename)
    personal_dir = resolve_personal_dir()
    personal_dir.mkdir(parents=True, exist_ok=True)
    target = personal_dir / safe_filename
    if not target.exists():
        target.write_text(render_adjustments_file_content({}, []), encoding="utf-8")
        return {}, []
    return load_adjustments_file(target)


def _save_mapping_file(
    filename: str, mappings: dict[str, str], archived_parents: list[str]
) -> None:
    safe_filename = normalize_adjustment_filename(filename)
    personal_dir = resolve_personal_dir()
    personal_dir.mkdir(parents=True, exist_ok=True)
    target = personal_dir / safe_filename
    target.write_text(
        render_adjustments_file_content(mappings, archived_parents),
        encoding="utf-8",
    )


def _load_projects_for_adjustments_sync(
    refresh: bool,
) -> tuple[list[str], list[str], list[str], list[str]]:
    if not refresh and _state.db is not None:
        dbio = _state.db
    else:
        dbio = Database(str(_resolve_env_path()))
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


_TaskIngestNode = _task_ingest_component._TaskIngestNode
_TaskIngestTree = _task_ingest_component._TaskIngestTree

def _call_task_ingest_component(name: str, *args: Any, **kwargs: Any) -> Any:
    _task_ingest_component._sync_api_globals()
    return getattr(_task_ingest_component, name)(*args, **kwargs)


def _make_task_ingest_wrapper(name: str):
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return _call_task_ingest_component(name, *args, **kwargs)

    _wrapper.__name__ = name
    _wrapper._component_wrapper_for = name
    return _wrapper


for _name in _task_ingest_component._COMPONENT_EXPORTS:
    if _name not in {"_TaskIngestNode", "_TaskIngestTree"}:
        globals()[_name] = _make_task_ingest_wrapper(_name)

def _status_update_db() -> Database:
    if _state.db is not None:
        return _state.db
    return Database(str(_resolve_env_path()))


def _dashboard_settings_payload(config: DictConfig) -> dict[str, Any]:
    return _component_dashboard_settings_payload(
        config,
        dashboard_config_path=_DASHBOARD_CONFIG_PATH,
        repo_root=_REPO_ROOT,
    )


def _template_summary(path: Path) -> dict[str, Any]:
    return _component_template_summary(
        path,
        config_dir=_CONFIG_DIR,
        read_config=lambda item: _read_yaml_config(item),
    )
