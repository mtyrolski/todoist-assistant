# pyright: reportFunctionMemberAccess=false, reportPossiblyUnboundVariable=false
# pylint: disable=global-statement,too-many-lines,protected-access,unused-import

import asyncio
from collections.abc import Mapping, Sequence
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4
import contextlib
import io
import os
import re
import os.path
from pathlib import Path
import signal
import subprocess

import time

import pandas as pd
import numpy as np
from loguru import logger
from omegaconf import DictConfig, OmegaConf
from todometry.database.base import Database
from todometry.database.dataframe import (
    DEFAULT_ADJUSTMENTS_FILENAME,
    load_adjustments_file,
    load_activity_data,
    normalize_adjustment_filename,
    render_adjustments_file_content,
    resolve_personal_dir,
)
from todometry.core.types import Event, Project
from todometry.dashboard._plot_activity import (
    plot_events_over_time,
    plot_heatmap_of_events_by_day_and_hour,
)
from todometry.dashboard._plot_lifespans import plot_task_lifespans
from todometry.dashboard._plot_periodic import (
    cumsum_completed_tasks_periodically,
    plot_completed_tasks_periodically,
)
from todometry.dashboard._plot_project_hierarchy import (
    plot_active_project_hierarchy_sunburst as plot_active_project_hierarchy,
)
from todometry.dashboard._plot_weekly_trend import plot_weekly_completion_trend
from todometry.dashboard.settings import (
    load_dashboard_config,
    resolve_dashboard_config_path,
)
from todometry.web.dashboard_payload import (
    DEFAULT_URGENCY_SETTINGS,
    compute_plot_range as _compute_plot_range,
    empty_activity_df as _empty_activity_df,
    evaluate_urgency_status as _evaluate_urgency_status,
    normalize_activity_df as _normalize_activity_df,
    normalize_plot_events as _normalize_plot_events,
)
from todometry.web.routes.api_routes import router as _api_routes_router
from todometry.web.api_components.runtime import (
    REPO_ROOT as _REPO_ROOT,
    dashboard_pid_dir as _dashboard_pid_dir,
    dashboard_state_dir as _dashboard_state_dir,
    resolve_api_key as _resolve_api_key,
    resolve_env_path as _resolve_env_path,
)
from todometry.web.api_components.settings import (
    dashboard_settings_payload as _component_dashboard_settings_payload,
)
from todometry.web.api_components.configuration import (
    read_yaml_config as _read_yaml_config,
    save_yaml_config as _save_yaml_config,
)
from todometry.web.api_components import dashboard_runtime as _dashboard_runtime_component
from todometry.core.utils import (
    Cache,
    LocalStorageError,
    configure_runtime_logging,
    get_log_level,
    resolve_cache_dir,
    set_tqdm_progress_callback,
    get_tqdm_progress_callback,
)
from todometry.core.env import EnvVar
from dotenv import dotenv_values, set_key, unset_key
from todometry.core.version import get_version

configure_runtime_logging()

# FastAPI application powering the new web dashboard.
app = FastAPI(title="Telemetry for Todoist API", version=get_version())

# Allow the local Next.js dev server to talk to the API without CORS issues.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
        self.last_refresh_attempt_s: float = 0.0
        self.last_refresh_error: str | None = None
        self.refresh_task: asyncio.Task[None] | None = None
        self.main_loop: asyncio.AbstractEventLoop | None = None
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
_PROGRESS_LOCK = asyncio.Lock()
_PROGRESS_TOTAL_STEPS = 3
_DASHBOARD_STATE_SCHEMA_VERSION = 5
_DEMO_DASHBOARD_STATE_SCHEMA_VERSION = 2
_main_loop: asyncio.AbstractEventLoop | None = None
_TQDM_STEP_MAP = {
    "Checking Todoist updates": 1,
    "Querying project data": 1,
    "Fetching initial project data": 1,
    "Querying changed project data": 1,
    "Reconciling project data": 1,
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


_DASHBOARD_CONFIG_PATH = resolve_dashboard_config_path()


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
            if not (p.project_entry.parent_id or p.project_entry.v2_parent_id)
        }
    )
    archived_root = sorted(
        {
            p.project_entry.name
            for p in archived_projects
            if not (p.project_entry.parent_id or p.project_entry.v2_parent_id)
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


def _dashboard_settings_payload(config: DictConfig) -> dict[str, Any]:
    return _component_dashboard_settings_payload(
        config,
        dashboard_config_path=_DASHBOARD_CONFIG_PATH,
        repo_root=_REPO_ROOT,
    )
