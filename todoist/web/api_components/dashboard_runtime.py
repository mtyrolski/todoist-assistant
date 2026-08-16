# pyright: reportUndefinedVariable=false, reportOptionalMemberAccess=false, reportArgumentType=false, reportUnboundVariable=false
"""Dashboard state, progress, and service-status runtime helpers."""

# pylint: disable=protected-access,cyclic-import,too-many-lines,undefined-variable,global-variable-undefined,used-before-assignment

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from todoist.database.base import Database
from todoist.core.types import Event, Project
from todoist.features.activity import (
    activity_history_boundary,
    load_activity_cache,
    merge_activity_cache,
    needs_activity_history,
)

ProgressLaneStatus = Literal["queued", "active", "done"]
ProgressValue = tuple[str, str | None, int, int, ProgressLaneStatus | None]


@dataclass(frozen=True, slots=True)
class _ArchivedActivityTarget:
    project_id: str
    label: str
    updated_at: str


_ARCHIVED_ACTIVITY_SCAN_STATE_VERSION = 1
_ARCHIVED_ACTIVITY_SENTINEL_LIMIT = 16


def _sync_api_globals() -> None:
    from todoist.web import api as web_api

    for name, value in vars(web_api).items():
        if name.startswith("__"):
            continue
        original = _ORIGINALS.get(name)
        if (
            original is not None
            and getattr(value, "_component_wrapper_for", None) == name
        ):
            globals()[name] = original
        else:
            globals()[name] = value


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


def _set_progress_sync(
    stage: str,
    *,
    step: int,
    detail: str,
    sub_current: int | None = None,
    sub_total: int | None = None,
    lane_id: str | None = None,
    lane_label: str | None = None,
    unit: str | None = None,
    lane_status: ProgressLaneStatus | None = None,
) -> None:
    _run_async_in_main_loop(
        _set_progress(
            stage,
            step=step,
            total_steps=_PROGRESS_TOTAL_STEPS,
            detail=detail,
            sub_current=sub_current,
            sub_total=sub_total,
            lane_id=lane_id,
            lane_label=lane_label,
            unit=unit,
            lane_status=lane_status,
        )
    )


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
            "lanes": [
                {
                    "id": lane.id,
                    "label": lane.label,
                    "detail": lane.detail,
                    "current": lane.current,
                    "total": lane.total,
                    "unit": lane.unit,
                    "status": lane.status,
                    "updatedAt": lane.updated_at,
                }
                for lane in sorted(
                    _progress_state.lanes.values(),
                    key=lambda item: item.label.casefold(),
                )
            ],
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
    lane_id: str | None = None,
    lane_label: str | None = None,
    unit: str | None = None,
    lane_status: ProgressLaneStatus | None = None,
) -> None:
    now = _now_iso()
    async with _PROGRESS_LOCK:
        if not _progress_state.active:
            _progress_state.started_at = now
            _progress_state.error = None
            _progress_state.lanes.clear()
        elif lane_id is None and _progress_state.stage != stage:
            _progress_state.lanes.clear()
        _progress_state.active = True
        _progress_state.stage = stage
        _progress_state.step = step
        _progress_state.total_steps = total_steps
        if lane_id is None:
            _progress_state.detail = detail
            _progress_state.sub_current = sub_current
            _progress_state.sub_total = sub_total
        _progress_state.updated_at = now
        if lane_id is not None:
            lane_current = max(sub_current or 0, 0)
            lane_total = max(sub_total or 0, 0)
            resolved_lane_status: ProgressLaneStatus
            if lane_status in {"queued", "active", "done"}:
                resolved_lane_status = lane_status
            elif lane_total > 0 and lane_current >= lane_total:
                resolved_lane_status = "done"
            else:
                resolved_lane_status = "active"
            _progress_state.lanes[lane_id] = _ProgressLane(
                id=lane_id,
                label=lane_label or lane_id,
                detail=detail or "",
                current=lane_current,
                total=lane_total,
                unit=unit,
                status=resolved_lane_status,
                updated_at=now,
            )


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
        _progress_state.lanes.clear()
        _progress_state.updated_at = now
        _progress_state.error = error


def _build_tqdm_progress_callback() -> Callable[..., None]:
    last_updates: dict[str, float] = {}
    last_values: dict[str, ProgressValue] = {}
    callback_lock = Lock()
    adaptive_activity_stages = {
        "Backfilling activity history",
        "Fetching activity history",
        "Fetching archived project activity",
    }

    def _callback(
        desc: str,
        current: int,
        total: int,
        unit: str | None,
        detail_override: str | None = None,
        lane_id: str | None = None,
        lane_label: str | None = None,
        lane_status: ProgressLaneStatus | None = None,
    ) -> None:
        if desc in adaptive_activity_stages and unit == "page":
            return
        now = time.time()
        progress_value = (desc, unit, current, total, lane_status)
        progress_key = lane_id or "__aggregate__"
        with callback_lock:
            last_update = last_updates.get(progress_key, 0.0)
            if (
                progress_value == last_values.get(progress_key)
                and (now - last_update) < 0.4
            ):
                return
            if current != total and (now - last_update) < 0.35:
                return
            last_values[progress_key] = progress_value
            last_updates[progress_key] = now
        step = _TQDM_STEP_MAP.get(desc, _progress_state.step or 1)
        unit_suffix = f" {unit}" if unit else ""
        detail = detail_override or f"{desc}: {current}/{total}{unit_suffix}"
        _set_progress_sync(
            desc or "Working",
            step=step,
            detail=detail,
            sub_current=current,
            sub_total=total,
            lane_id=lane_id,
            lane_label=lane_label,
            unit=unit,
            lane_status=lane_status,
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


def _adjustments_cache_signature() -> list[dict[str, int | str]]:
    personal_dir = resolve_personal_dir()
    if not personal_dir.exists():
        return []

    signatures: list[dict[str, int | str]] = []
    for path in sorted(personal_dir.iterdir()):
        if not path.is_file() or path.suffix != ".py":
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        signatures.append(
            {
                "name": path.name,
                "mtime_ns": int(stat.st_mtime_ns),
                "size": int(stat.st_size),
            }
        )
    return signatures


def _coerce_activity_datetime_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _project_parent_id(project: Project) -> str | None:
    return project.project_entry.parent_id or project.project_entry.v2_parent_id


def _project_has_candidate_ancestor(
    project: Project,
    *,
    projects_by_id: dict[str, Project],
    candidate_names: set[str],
) -> bool:
    visited: set[str] = set()
    parent_id = _project_parent_id(project)
    while parent_id and parent_id not in visited:
        visited.add(parent_id)
        parent = projects_by_id.get(parent_id)
        if parent is None:
            return False
        if parent.project_entry.name in candidate_names:
            return True
        parent_id = _project_parent_id(parent)
    return False


def _configured_archived_parent_projects(
    dbio: Database,
) -> dict[str, _ArchivedActivityTarget]:
    from todoist.database.dataframe import (
        get_adjusting_archived_parent_projects,
        get_adjusting_mapping,
    )

    archived_parent_names = set(get_adjusting_archived_parent_projects())
    if not archived_parent_names:
        return {}

    link_mapping = get_adjusting_mapping()
    candidate_names = set(archived_parent_names)
    candidate_names.update(
        source_name
        for source_name, target_name in link_mapping.items()
        if source_name in archived_parent_names or target_name in archived_parent_names
    )

    projects = dbio.fetch_projects(include_tasks=False) + dbio.fetch_archived_projects()
    projects_by_id = {project.id: project for project in projects}
    target_projects: dict[str, _ArchivedActivityTarget] = {}
    for project in projects:
        if not project.is_archived:
            continue
        if (
            project.project_entry.name in candidate_names
            or _project_has_candidate_ancestor(
                project,
                projects_by_id=projects_by_id,
                candidate_names=candidate_names,
            )
        ):
            project_id = str(project.id)
            target_projects[project_id] = _ArchivedActivityTarget(
                project_id=project_id,
                label=str(project.project_entry.name),
                updated_at=str(project.project_entry.updated_at or ""),
            )
    return target_projects


def _load_archived_activity_scan_fingerprints(
    cached_events: set[Event],
) -> dict[str, str]:
    try:
        payload = Cache().archived_activity_scans.load()
    except LocalStorageError:
        return {}
    if (
        not isinstance(payload, Mapping)
        or payload.get("version") != _ARCHIVED_ACTIVITY_SCAN_STATE_VERSION
    ):
        return {}

    sentinels = payload.get("activitySentinels")
    if not isinstance(sentinels, list) or not all(
        isinstance(event_id, str) for event_id in sentinels
    ):
        return {}
    cached_event_ids = {str(event.id) for event in cached_events}
    if not set(sentinels).issubset(cached_event_ids):
        logger.info(
            "Archived activity scan state invalidated because cached activity "
            "sentinels are missing."
        )
        return {}

    projects = payload.get("projects")
    if not isinstance(projects, Mapping):
        return {}
    return {
        str(project_id): str(entry.get("projectUpdatedAt") or "")
        for project_id, entry in projects.items()
        if isinstance(entry, Mapping)
    }


def _save_archived_activity_scan_fingerprints(
    fingerprints: Mapping[str, str],
    scanned_targets: Mapping[str, _ArchivedActivityTarget],
    cached_events: set[Event],
) -> None:
    completed_at = _now_iso()
    merged_fingerprints = dict(fingerprints)
    merged_fingerprints.update(
        {
            project_id: target.updated_at
            for project_id, target in scanned_targets.items()
        }
    )
    event_ids = sorted({str(event.id) for event in cached_events})
    Cache().archived_activity_scans.save(
        {
            "version": _ARCHIVED_ACTIVITY_SCAN_STATE_VERSION,
            "activitySentinels": event_ids[:_ARCHIVED_ACTIVITY_SENTINEL_LIMIT],
            "projects": {
                project_id: {
                    "projectUpdatedAt": project_updated_at,
                    "completedAt": completed_at,
                }
                for project_id, project_updated_at in merged_fingerprints.items()
            },
        }
    )


def _fetch_configured_archived_parent_activity(
    dbio: Database,
    cached_events: set[Event],
) -> set[Event]:
    targets = _configured_archived_parent_projects(dbio)
    if not targets:
        return set()

    fingerprints = _load_archived_activity_scan_fingerprints(cached_events)
    pending_targets = {
        project_id: target
        for project_id, target in targets.items()
        if not target.updated_at or fingerprints.get(project_id) != target.updated_at
    }
    skipped_projects = len(targets) - len(pending_targets)
    if not pending_targets:
        logger.info(
            "Skipping archived activity fetch for {} unchanged project(s).",
            skipped_projects,
        )
        _set_progress_sync(
            "Fetching archived project activity",
            step=1,
            detail=(
                f"Archived activity cache is current; skipped "
                f"{skipped_projects} unchanged project(s)"
            ),
            sub_current=skipped_projects,
            sub_total=skipped_projects,
        )
        return set()

    now_utc = datetime.now(timezone.utc)
    date_from = now_utc - timedelta(weeks=520)
    date_to = now_utc
    logger.info(
        "Fetching scoped activity for {} changed archived project(s); skipped {} unchanged.",
        len(pending_targets),
        skipped_projects,
    )
    fetched_events = dbio.fetch_activity_for_parent_projects(
        pending_targets,
        date_from=date_from,
        date_to=date_to,
        window_weeks=52,
        events_already_fetched=set(cached_events),
        progress_desc="Fetching archived project activity",
        progress_lane_labels={
            project_id: target.label for project_id, target in pending_targets.items()
        },
    )
    recent_events = {
        event
        for event in fetched_events
        if _coerce_activity_datetime_utc(event.date) >= date_from
    }
    try:
        _save_archived_activity_scan_fingerprints(
            fingerprints,
            pending_targets,
            cached_events | recent_events,
        )
    except LocalStorageError as exc:
        logger.warning(f"Failed to save archived activity scan state: {exc}")
    return recent_events


def _persist_state_to_disk_cache(*, demo_mode: bool) -> None:
    df_activity = _state.df_activity
    active_projects = _state.active_projects
    archived_projects = _state.archived_projects
    project_colors = _state.project_colors
    if (
        df_activity is None
        or active_projects is None
        or archived_projects is None
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
        "adjustments_cache_signature": _adjustments_cache_signature(),
        "df_activity": df_activity,
        "active_projects": active_projects,
        "archived_projects": archived_projects,
        "project_colors": project_colors,
    }
    try:
        Cache().dashboard_state.save(payload)
    except (LocalStorageError, OSError, TypeError) as exc:
        logger.warning(f"Failed to persist dashboard state cache: {exc}")


def _dashboard_cache_payload_is_current(
    payload: dict[str, Any], *, demo_mode: bool
) -> bool:
    if payload.get("version") != _DASHBOARD_STATE_SCHEMA_VERSION:
        return False
    if bool(payload.get("demo_mode", False)) != demo_mode:
        return False
    if (
        demo_mode
        and payload.get("demo_state_version") != _DEMO_DASHBOARD_STATE_SCHEMA_VERSION
    ):
        return False
    return (
        payload.get("activity_cache_signature") == _activity_cache_signature()
        and payload.get("adjustments_cache_signature") == _adjustments_cache_signature()
    )


def _load_state_from_disk_cache(*, demo_mode: bool) -> bool:
    try:
        payload = Cache().dashboard_state.load()
    except LocalStorageError:
        return False
    if not isinstance(payload, dict) or not _dashboard_cache_payload_is_current(
        payload, demo_mode=demo_mode
    ):
        return False

    df_activity = payload.get("df_activity")
    active_projects = payload.get("active_projects")
    archived_projects = payload.get("archived_projects")
    project_colors = payload.get("project_colors")
    if not (
        isinstance(df_activity, pd.DataFrame)
        and isinstance(active_projects, list)
        and isinstance(archived_projects, list)
        and isinstance(project_colors, dict)
    ):
        return False

    _state.db = None
    _state.df_activity = _normalize_activity_df(df_activity)
    _state.active_projects = active_projects
    _state.archived_projects = archived_projects
    _state.project_colors = {str(k): str(v) for k, v in project_colors.items()}
    _state.last_refresh_s = float(payload.get("last_refresh_s") or time.time())
    _state.home_payload_cache = {}
    _state.demo_mode = demo_mode
    logger.info(
        "Loaded dashboard state cache from disk "
        f"(events={len(df_activity)}, active_projects={len(active_projects)}, "
        f"archived_projects={len(archived_projects)})"
    )
    return True


def _activity_fetch_window_config() -> tuple[int, int]:
    cfg = _read_yaml_config(_AUTOMATIONS_PATH, required=False)
    activity_cfg = cfg.get("activity") if isinstance(cfg, DictConfig) else None
    if not isinstance(activity_cfg, Mapping):
        return 10, 2
    return (
        int(activity_cfg.get("nweeks_window_size", 10)),
        int(activity_cfg.get("early_stop_after_n_windows", 2)),
    )


def _refresh_state_sync(*, demo_mode: bool) -> None:
    global _activity_backfill_attempted
    # Reset progress state to clear any stale information from previous failed refreshes
    _run_async_in_main_loop(_finish_progress(error=None))

    previous_callback = get_tqdm_progress_callback()
    set_tqdm_progress_callback(_build_tqdm_progress_callback())

    error: str | None = None
    history_scan_succeeded = False
    try:
        _set_progress_sync(
            "Checking Todoist updates",
            step=1,
            detail="Refreshing project and task data from Todoist",
        )
        dbio = Database(".env")
        dbio.pull()

        try:
            cached_events = load_activity_cache()
        except LocalStorageError:
            cached_events = set()
        _set_progress_sync(
            "Checking activity cache",
            step=1,
            detail=f"Loaded {len(cached_events)} cached activity event(s)",
        )

        if _resolve_api_key():
            try:
                _set_progress_sync(
                    "Fetching recent activity",
                    step=1,
                    detail="Refreshing the newest activity pages",
                )
                recent_events = set(dbio.fetch_activity_recent(max_pages=2))
                cached_events = merge_activity_cache(recent_events)
                logger.info(
                    "Activity sync recent phase complete: fetched={}; cached={}",
                    len(recent_events),
                    len(cached_events),
                )

                if not _activity_backfill_attempted and needs_activity_history(
                    cached_events
                ):
                    nweeks, early_stop = _activity_fetch_window_config()
                    history_boundary = activity_history_boundary(cached_events)
                    logger.info(
                        "Activity cache needs history recovery (window={}w, stop={}, boundary={}).",
                        nweeks,
                        early_stop,
                        history_boundary.isoformat() if history_boundary else "now",
                    )
                    _set_progress_sync(
                        "Fetching activity history",
                        step=1,
                        detail=(
                            f"Backfilling older activity before "
                            f"{history_boundary.isoformat() if history_boundary else 'now'} "
                            f"in {nweeks}-week windows"
                        ),
                    )
                    history_events = dbio.fetch_activity_history(
                        nweeks_window_size=nweeks,
                        early_stop_after_n_windows=early_stop,
                        events_already_fetched=set(cached_events),
                        date_to=history_boundary,
                        progress_desc="Fetching activity history",
                    )
                    cached_events = merge_activity_cache(set(history_events))
                    logger.info(
                        "Activity sync history phase complete: cached={}",
                        len(cached_events),
                    )
                    history_scan_succeeded = True
                else:
                    _set_progress_sync(
                        "Checking activity cache",
                        step=1,
                        detail=(
                            f"Cache has {len(cached_events)} event(s); "
                            "history backfill is not needed"
                        ),
                    )
            except Exception as exc:  # pragma: no cover - network-dependent
                logger.warning(f"Failed to refresh activity cache: {exc}")
            finally:
                if history_scan_succeeded or not needs_activity_history(cached_events):
                    _activity_backfill_attempted = True

        if _resolve_api_key():
            try:
                try:
                    cached_events = load_activity_cache()
                except LocalStorageError:
                    cached_events = set()
                archived_parent_events = _fetch_configured_archived_parent_activity(
                    dbio,
                    set(cached_events),
                )
                if archived_parent_events:
                    merged_events = merge_activity_cache(archived_parent_events)
                    logger.info(
                        "Merged {} scoped archived-parent event(s) into activity cache; total={}.",
                        len(archived_parent_events),
                        len(merged_events),
                    )
            except Exception as exc:  # pragma: no cover - network-dependent
                logger.warning(
                    f"Failed to fetch scoped archived-parent activity: {exc}"
                )

        _set_progress_sync(
            "Resolving project hierarchy",
            step=2,
            detail="Resolving roots across active and archived projects",
        )
        try:
            df_activity = _normalize_activity_df(load_activity_data(dbio))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Failed to load activity data; using empty dataset: {exc}")
            df_activity = _empty_activity_df()

        _set_progress_sync(
            "Preparing dashboard data",
            step=3,
            detail="Loading metadata and caches",
        )
        active_projects = dbio.fetch_projects(include_tasks=True)
        archived_projects = dbio.fetch_archived_projects()

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
        from todoist.database.dataframe import get_adjusting_mapping

        for source_name, target_name in get_adjusting_mapping().items():
            if target_name not in project_colors and source_name in project_colors:
                project_colors[target_name] = project_colors[source_name]

        _state.db = dbio
        _state.df_activity = df_activity
        _state.active_projects = active_projects
        _state.archived_projects = archived_projects
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
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(
                timespec="seconds"
            ),
            "size": stat.st_size,
        }
    except OSError:
        return {"path": str(path_obj), "mtime": None, "size": None}


def _service_statuses() -> list[dict[str, Any]]:
    api_key_set = bool(_resolve_api_key())
    cache_activity = _stat_file(_cache_runtime_path("activity.joblib"))
    automation_log = _stat_file(automation_log_path())
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

    service_specs = (
        ("Todoist token", api_key_set, "API_KEY set", "API_KEY missing"),
        ("Activity cache", cache_activity, cache_activity, "activity.joblib missing"),
        ("Automation log", automation_log, automation_log, "automation.log missing"),
    )
    return [
        {
            "name": name,
            "status": "ok" if available else "warn",
            "detail": ok_detail if available else missing_detail,
        }
        for name, available, ok_detail, missing_detail in service_specs
    ] + [{"name": "Observer", "status": observer_status, "detail": observer_detail}]


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


_COMPONENT_EXPORTS = (
    "_env_demo_mode",
    "_run_async_in_main_loop",
    "_progress_snapshot",
    "_set_progress",
    "_finish_progress",
    "_build_tqdm_progress_callback",
    "_activity_cache_signature",
    "_persist_state_to_disk_cache",
    "_load_state_from_disk_cache",
    "_refresh_state_sync",
    "_ensure_state",
    "_cache_runtime_path",
    "_stat_file",
    "_service_statuses",
    "_llm_breakdown_snapshot",
)
_ORIGINALS = {name: globals()[name] for name in _COMPONENT_EXPORTS}
