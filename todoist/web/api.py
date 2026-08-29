# pyright: reportFunctionMemberAccess=false, reportPossiblyUnboundVariable=false
# pylint: disable=global-statement,too-many-lines,protected-access,unused-import

import asyncio
from collections.abc import Mapping, Sequence
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass, field
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
from todoist.core.types import Event, Project
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
from todoist.dashboard.settings import (
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
    multiplication_settings_payload as _multiplication_settings_payload,
    stale_tasks_settings_payload as _stale_tasks_settings_payload,
)
from todoist.web.api_components.configuration import (
    read_yaml_config as _read_yaml_config,
    save_yaml_config as _save_yaml_config,
)
from todoist.web.api_components import dashboard_runtime as _dashboard_runtime_component
from todoist.web.api_components import (
    automation_runtime as _automation_runtime_component,
)
from todoist.core.utils import (
    Cache,
    LocalStorageError,
    automation_log_path,
    configure_runtime_logging,
    get_log_level,
    load_config,
    resolve_cache_dir,
    set_tqdm_progress_callback,
    get_tqdm_progress_callback,
)
from todoist.core.env import EnvVar
from dotenv import dotenv_values, set_key, unset_key
from todoist.core.version import get_version

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
ProgressLaneStatus = Literal["queued", "active", "done"]


class _DashboardState:
    def __init__(self) -> None:
        self.last_refresh_s: float = 0.0
        self.db: Database | None = None
        self.df_activity: pd.DataFrame | None = None
        self.active_projects: list[Project] | None = None
        self.archived_projects: list[Project] | None = None
        self.project_colors: dict[str, str] | None = None
        self.home_payload_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self.demo_mode: bool = False
        self.activity_cache_signature: dict[str, int] | None = None

    def is_ready_for(
        self,
        *,
        demo_mode: bool,
        activity_cache_signature: dict[str, int] | None = None,
    ) -> bool:
        return (
            self.df_activity is not None
            and self.active_projects is not None
            and self.project_colors is not None
            and self.demo_mode == demo_mode
            and self.activity_cache_signature == activity_cache_signature
        )


@dataclass
class _ProgressLane:
    id: str
    label: str
    detail: str
    current: int
    total: int
    unit: str | None
    status: ProgressLaneStatus
    updated_at: str


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
    lanes: dict[str, _ProgressLane] = field(default_factory=dict)
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
_DASHBOARD_STATE_SCHEMA_VERSION = 3
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

_REMAPPABLE_ACTIVE_ROOT_PROJECTS = frozenset({"Inbox"})


def _call_dashboard_runtime(name: str, *args: Any, **kwargs: Any) -> Any:
    _dashboard_runtime_component._sync_api_globals()
    return getattr(_dashboard_runtime_component, name)(*args, **kwargs)


def _make_dashboard_runtime_wrapper(name: str):
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        return _call_dashboard_runtime(name, *args, **kwargs)

    _wrapper.__name__ = name
    _wrapper._component_wrapper_for = name
    return _wrapper


for _component_wrapper_name in _dashboard_runtime_component._COMPONENT_EXPORTS:
    globals()[_component_wrapper_name] = _make_dashboard_runtime_wrapper(
        _component_wrapper_name
    )
del _component_wrapper_name
_ensure_state = _make_dashboard_runtime_wrapper("_ensure_state")
_progress_snapshot = _make_dashboard_runtime_wrapper("_progress_snapshot")
_service_statuses = _make_dashboard_runtime_wrapper("_service_statuses")


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
    if not any(
        candidate == root or root in candidate.parents for root in allowed_roots
    ):
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
) -> tuple[list[str], list[str], list[str], list[str], list[dict[str, Any]]]:
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
    projects_by_id = {
        str(project.id): project for project in [*active_projects, *archived_projects]
    }
    project_records: list[dict[str, Any]] = []
    for project in projects_by_id.values():
        ancestors: list[dict[str, str]] = []
        current: Project | None = project
        visited: set[str] = set()
        while current is not None and str(current.id) not in visited:
            current_id = str(current.id)
            visited.add(current_id)
            ancestors.append(
                {
                    "id": current_id,
                    "name": str(current.project_entry.name),
                }
            )
            parent_id = (
                current.project_entry.parent_id or current.project_entry.v2_parent_id
            )
            current = (
                projects_by_id.get(str(parent_id)) if parent_id is not None else None
            )
        root = ancestors[-1]
        project_records.append(
            {
                "id": str(project.id),
                "name": str(project.project_entry.name),
                "isArchived": bool(project.is_archived),
                "ancestors": ancestors,
                "rootId": root["id"],
                "rootName": root["name"],
            }
        )
    return (
        active_root,
        archived_root,
        archived_names,
        remappable_active_root,
        project_records,
    )


def _preferred_adjustment_project_id(
    project_name: str, project_records: list[dict[str, Any]]
) -> str | None:
    matches = [
        record for record in project_records if record.get("name") == project_name
    ]
    active_matches = [record for record in matches if not record.get("isArchived")]
    preferred = active_matches or matches
    if len(preferred) != 1:
        return None
    return str(preferred[0]["id"])


def _resolve_automatic_project_mappings(
    project_records: list[dict[str, Any]],
    *,
    manual_mappings: dict[str, str],
    archived_parent_projects: set[str],
) -> tuple[dict[str, str], list[dict[str, str | None]]]:
    """Infer archived-project root assignments not overridden by saved mappings."""

    candidates: dict[str, set[str]] = {}
    candidate_details: list[dict[str, str | None]] = []
    for record in project_records:
        if not record.get("isArchived"):
            continue
        source_name = str(record.get("name") or "")
        if (
            not source_name
            or source_name in manual_mappings
            or source_name in archived_parent_projects
        ):
            continue
        ancestors = cast(list[dict[str, str]], record.get("ancestors") or [])
        if not ancestors:
            continue

        promoted_parent = next(
            (
                ancestor
                for ancestor in ancestors
                if ancestor["name"] in archived_parent_projects
            ),
            None,
        )
        manual_ancestor = next(
            (ancestor for ancestor in ancestors if ancestor["name"] in manual_mappings),
            None,
        )
        if promoted_parent is not None:
            target_name = promoted_parent["name"]
            target_id = promoted_parent["id"]
        elif manual_ancestor is not None:
            target_name = manual_mappings[manual_ancestor["name"]]
            target_id = _preferred_adjustment_project_id(target_name, project_records)
        else:
            target_name = str(record.get("rootName") or "")
            target_id = str(record.get("rootId") or "") or None
        if not target_name or target_name == source_name:
            continue

        candidates.setdefault(source_name, set()).add(target_name)
        candidate_details.append(
            {
                "sourceProject": source_name,
                "sourceProjectId": str(record.get("id") or "") or None,
                "parentProject": target_name,
                "parentProjectId": target_id,
                "provenance": "automatic",
            }
        )

    automatic_mappings = {
        source_name: next(iter(target_names))
        for source_name, target_names in sorted(candidates.items())
        if len(target_names) == 1
    }
    details = [
        detail
        for detail in candidate_details
        if automatic_mappings.get(str(detail["sourceProject"]))
        == detail["parentProject"]
    ]
    return automatic_mappings, details


def _manual_project_mapping_details(
    project_records: list[dict[str, Any]], manual_mappings: dict[str, str]
) -> list[dict[str, str | None]]:
    details: list[dict[str, str | None]] = []
    for source_name, target_name in sorted(manual_mappings.items()):
        source_records = [
            record for record in project_records if record.get("name") == source_name
        ] or [{}]
        target_id = _preferred_adjustment_project_id(target_name, project_records)
        for record in source_records:
            details.append(
                {
                    "sourceProject": source_name,
                    "sourceProjectId": str(record.get("id") or "") or None,
                    "parentProject": target_name,
                    "parentProjectId": target_id,
                    "provenance": "manual",
                }
            )
    return details


def _dashboard_settings_payload(config: DictConfig) -> dict[str, Any]:
    return _component_dashboard_settings_payload(
        config,
        dashboard_config_path=_DASHBOARD_CONFIG_PATH,
        repo_root=_REPO_ROOT,
    )

