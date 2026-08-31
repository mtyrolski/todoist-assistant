"""Admin automation, job, and observer backend services."""

# pylint: disable=global-statement

import asyncio
import contextlib
import io
import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import hydra
from fastapi import HTTPException
from loguru import logger
from omegaconf import DictConfig, OmegaConf

from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.observer import AutomationObserver
from todoist.features.activity import activity_sync_lock
from todoist.database.base import Database
from todoist.dashboard.settings import (
    load_dashboard_config,
    observer_settings_payload,
    update_observer_settings,
)
from todoist.core.env import EnvVar
from todoist.core.utils import Cache, LocalStorageError, get_log_level, load_config

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_config_dir() -> Path:
    override = os.getenv(str(EnvVar.CONFIG_DIR))
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / "configs"


_CONFIG_DIR = _resolve_config_dir()
AUTOMATIONS_PATH = _CONFIG_DIR / "automations.yaml"
DASHBOARD_CONFIG_PATH = _REPO_ROOT / "configs" / "dashboard.yaml"

ADMIN_AUTOMATIONS_LOCK = asyncio.Lock()
JOBS_LOCK = asyncio.Lock()


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
_SIGNAL_FIELDS = (
    "attemptCount",
    "successCount",
    "failureCount",
    "skipCount",
    "lastStatus",
    "lastStartedAt",
    "lastFinishedAt",
    "lastDurationSeconds",
    "lastError",
    "lastSuccessAt",
)
_OBSERVER_STATE_FIELDS = (
    "refreshIntervalMinutes",
    "refreshIntervalSeconds",
    "updatedAt",
    "lastRunAt",
    "lastDurationSeconds",
    "lastEvents",
    "lastAutomationsRan",
    "lastStatus",
    "lastError",
)
_JOB_FIELDS = (
    ("id", "id"),
    ("kind", "kind"),
    ("status", "status"),
    ("createdAt", "created_at"),
    ("startedAt", "started_at"),
    ("finishedAt", "finished_at"),
    ("result", "result"),
    ("error", "error"),
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _serialize_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return None


def _env_path(name: str, default: Path) -> Path:
    override = os.getenv(name)
    return Path(override).expanduser().resolve() if override else default


def _read_yaml_config(path: Path, *, required: bool = True) -> DictConfig:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return cast(DictConfig, OmegaConf.create({}))
    return cast(DictConfig, OmegaConf.load(path))


def _save_yaml_config(path: Path, config: DictConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(OmegaConf.to_yaml(config, resolve=False), encoding="utf-8")


def _dashboard_state_dir() -> Path:
    return _env_path(
        "DASHBOARD_STATE_DIR", _REPO_ROOT / ".cache" / "todoist-assistant" / "dashboard"
    )


def _dashboard_pid_dir() -> Path:
    return _env_path("DASHBOARD_PID_DIR", _dashboard_state_dir() / "pids")


def _load_automations(*, config_dir: Path | None = None) -> list[Automation]:
    resolved_dir = config_dir or _CONFIG_DIR
    config = load_config("automations", str(resolved_dir.resolve()))
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


def _automation_ref_key(value: Any) -> str | None:
    item = str(value).strip()
    if item.startswith("${") and item.endswith("}"):
        key = item[2:-1]
        if key and all(char.isalnum() or char in "_-" for char in key):
            return key
    return None


def _default_enabled_automation_keys(config: Mapping[str, Any]) -> list[str]:
    return _available_automation_keys(config)


def _configured_enabled_automation_keys(config: Mapping[str, Any]) -> list[str]:
    raw = config.get("automations")
    if not isinstance(raw, Sequence):
        return []

    target_to_keys: dict[str, list[str]] = {}
    for key in _available_automation_keys(config):
        if isinstance(section := config.get(key), Mapping) and isinstance(
            target := section.get("_target_"), str
        ):
            target_to_keys.setdefault(target, []).append(key)

    keys: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            matched = target_to_keys.get(str(item.get("_target_")), [])
            if len(matched) == 1:
                keys.append(matched[0])
        elif (key := _automation_ref_key(item)) is not None:
            keys.append(key)
    return keys


def _enabled_automation_keys(config: Mapping[str, Any]) -> list[str]:
    configured = _configured_enabled_automation_keys(config)
    if configured:
        return configured
    return _default_enabled_automation_keys(config)


def _automation_run_signal_metadata(automation_name: str) -> dict[str, Any]:
    payload = Cache().automation_run_signals.load()
    signals = payload if isinstance(payload, dict) else {}
    signal_payload = signals.get(automation_name)
    if not isinstance(signal_payload, Mapping):
        return {}
    return {field: signal_payload.get(field) for field in _SIGNAL_FIELDS}


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
        **_automation_run_signal_metadata(automation.name),
    }


def _automation_metadata_for_key(
    config: DictConfig, key: str, *, enabled: bool
) -> dict[str, Any]:
    section = config.get(key)
    if not isinstance(section, Mapping):
        raise ValueError(f"Automation section missing or invalid: {key}")
    automation = cast(Automation, hydra.utils.instantiate(section))
    payload = {
        **_automation_launch_metadata(automation),
        "key": key,
        "enabled": enabled,
        "defaultEnabled": key in _default_enabled_automation_keys(config),
        "target": str(section.get("_target_") or ""),
    }
    return payload


def _load_automation_inventory(
    *, config_dir: Path | None = None
) -> list[dict[str, Any]]:
    resolved_dir = config_dir or _CONFIG_DIR
    config = cast(DictConfig, load_config("automations", str(resolved_dir.resolve())))
    available_keys = _available_automation_keys(config)
    enabled_keys = set(_enabled_automation_keys(config))
    inventory: list[dict[str, Any]] = []
    for key in available_keys:
        inventory.append(
            _automation_metadata_for_key(config, key, enabled=key in enabled_keys)
        )
    return inventory


def _enabled_refs(config: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    key_set = set(keys)
    return [
        _automation_ref(key)
        for key in _available_automation_keys(config)
        if key in key_set
    ]


def _save_enabled_automations(keys: Sequence[str], *, path: Path | None = None) -> None:
    config_path = path or AUTOMATIONS_PATH
    config = _read_yaml_config(config_path)
    config["automations"] = _enabled_refs(config, keys)
    _save_yaml_config(config_path, config)


def _set_automation_enabled(
    key: str,
    *,
    enabled: bool,
    path: Path | None = None,
) -> bool:
    config_path = path or AUTOMATIONS_PATH
    config = _read_yaml_config(config_path)
    available_keys = _available_automation_keys(config)
    if key not in available_keys:
        return False

    next_keys = [item for item in _enabled_automation_keys(config) if item != key]
    if enabled:
        next_keys = [item for item in available_keys if item in next_keys]
        if key not in next_keys:
            next_keys.insert(max(0, available_keys.index(key)), key)
    config["automations"] = _enabled_refs(config, next_keys)
    _save_yaml_config(config_path, config)
    return True


def _restart_dashboard_observer_if_managed(
    *, pid_dir: Path | None = None, state_dir: Path | None = None
) -> bool:
    resolved_pid_dir = pid_dir or _dashboard_pid_dir()
    resolved_state_dir = state_dir or _dashboard_state_dir()
    observer_pid_path = resolved_pid_dir / "observer.pid"
    if not observer_pid_path.exists():
        return False

    try:
        observer_pid = int(observer_pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        logger.warning(
            "Dashboard observer PID file is unreadable: {}", observer_pid_path
        )
        return False

    try:
        os.kill(observer_pid, 0)
    except OSError:
        logger.warning("Dashboard observer PID is stale: {}", observer_pid)
        return False

    try:
        os.kill(observer_pid, signal.SIGTERM)
    except OSError as exc:
        logger.warning("Failed to stop dashboard observer {}: {}", observer_pid, exc)
        return False

    observer_log_path = resolved_state_dir / "observer.log"
    observer_log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HYDRA_FULL_ERROR"] = "1"
    with observer_log_path.open("ab") as observer_log:
        process = subprocess.Popen(  # noqa: S603  # pylint: disable=consider-using-with
            [
                "uv",
                "run",
                "python3",
                "-m",
                "todoist.run_observer",
                "--config-dir",
                str(_CONFIG_DIR),
                "--config-name",
                "automations",
            ],
            cwd=str(_REPO_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=observer_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    observer_pid_path.write_text(str(process.pid), encoding="utf-8")
    logger.info("Restarted managed dashboard observer with pid {}", process.pid)
    return True


def _load_observer_state(*, cache: Cache | None = None) -> dict[str, Any]:
    storage = cache or Cache()
    try:
        payload = storage.observer_state.load()
    except LocalStorageError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return payload


def _serialize_observer_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"enabled": bool(payload.get("enabled", True))} | {
        field: payload.get(field) for field in _OBSERVER_STATE_FIELDS
    }


def _observer_edit_targets(
    observer_settings: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "key": "observer",
            "label": "Dashboard observer",
            "icon": "wrench",
            "configPath": observer_settings["configPath"],
            "anchor": "observer-control",
        }
    ]


def _build_observer(
    db: Database, *, config_dir: Path | None = None
) -> AutomationObserver:
    resolved_dir = config_dir or _CONFIG_DIR
    config = load_config("automations", str(resolved_dir.resolve()))
    activity_automation: Activity = hydra.utils.instantiate(
        cast(DictConfig, config).activity
    )
    automations: list[Automation] = hydra.utils.instantiate(
        cast(DictConfig, config).automations
    )
    short_automations = [auto for auto in automations if not isinstance(auto, Activity)]
    return AutomationObserver(
        db=db,
        automations=short_automations,
        activity=activity_automation,
    )


async def _save_job(job: _AdminJob) -> None:
    async with JOBS_LOCK:
        _JOBS[job.id] = job


async def _get_job(job_id: str) -> _AdminJob:
    async with JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job id")
        return job


async def _update_job(job_id: str, **fields: Any) -> None:
    async with JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)


async def _finish_job(job_id: str, status: str, **fields: Any) -> None:
    await _update_job(job_id, status=status, finished_at=_now_iso(), **fields)


def _run_automation_sync(
    automation: Automation,
    *,
    dbio: Database,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    output_stream = io.StringIO()
    started_at = datetime.now()
    task_delegations = None
    error: str | None = None
    with (
        contextlib.redirect_stdout(output_stream),
        contextlib.redirect_stderr(output_stream),
    ):
        loguru_handler_id = logger.add(
            output_stream, format="{message}", level=get_log_level()
        )
        try:
            logger.info("Manual automation run started: {}", automation.name)
            task_delegations = automation.tick(dbio)
            logger.info("Manual automation run completed: {}", automation.name)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Automation {} failed during manual run: {}",
                automation.name,
                error,
            )
            if not continue_on_error:
                raise
        finally:
            if error:
                logger.error("Manual automation run failed: {}", automation.name)
            logger.remove(loguru_handler_id)
    finished_at = datetime.now()
    return {
        "name": automation.name,
        "startedAt": started_at.isoformat(timespec="seconds"),
        "finishedAt": finished_at.isoformat(timespec="seconds"),
        "durationSeconds": round((finished_at - started_at).total_seconds(), 3),
        "output": output_stream.getvalue(),
        "taskDelegations": task_delegations,
        "status": "failed" if error else "completed",
        "error": error,
    }


def _run_all_automations_sync(*, dbio: Database) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    for automation in _load_automations():
        result = _run_automation_sync(
            automation,
            dbio=dbio,
            continue_on_error=True,
        )
        results.append(result)
        dbio.reset()

    failed = sum(item["status"] == "failed" for item in results)
    return {
        "results": results,
        "summary": {"completed": len(results) - failed, "failed": failed, "skipped": 0},
    }


async def _run_with_db(func: Any, *args: Any) -> Any:
    dbio = Database(".env")
    with activity_sync_lock():
        await asyncio.to_thread(dbio.pull)
    try:
        return await asyncio.to_thread(func, *args, dbio=dbio)
    finally:
        await asyncio.to_thread(dbio.reset)


async def _run_job(job_id: str, func: Any, *args: Any) -> None:
    await _update_job(job_id, status="running", started_at=_now_iso())
    try:
        async with ADMIN_AUTOMATIONS_LOCK:
            result = await func(*args)
        await _finish_job(job_id, "done", result=result)
    except Exception as exc:  # pragma: no cover - defensive
        await _finish_job(job_id, "failed", error=f"{type(exc).__name__}: {exc}")


async def _run_named_automation(name: str) -> dict[str, Any]:
    automations = {a.name: a for a in _load_automations()}
    if name not in automations:
        raise HTTPException(status_code=404, detail=f"Unknown automation: {name}")
    return cast(
        dict[str, Any], await _run_with_db(_run_automation_sync, automations[name])
    )


async def _run_automation_job(*, job_id: str, name: str) -> None:
    await _run_job(job_id, _run_named_automation, name)


async def _run_all_automations_job(*, job_id: str) -> None:
    await _run_job(job_id, _run_with_db, _run_all_automations_sync)


def _serialize_job(job: _AdminJob) -> dict[str, Any]:
    return {payload_key: getattr(job, attr) for payload_key, attr in _JOB_FIELDS}


def _admin_observer_payload(
    state: Mapping[str, Any], observer_settings: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "state": _serialize_observer_state(state),
        "settings": observer_settings,
        "editTargets": _observer_edit_targets(observer_settings),
    }


async def admin_automations_payload() -> dict[str, Any]:
    try:
        automations = _load_automation_inventory()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load automations: {}", exc)
        return {"automations": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"automations": automations, "configPath": str(AUTOMATIONS_PATH)}


async def admin_observer_state() -> dict[str, Any]:
    config = load_dashboard_config(DASHBOARD_CONFIG_PATH)
    state = _load_observer_state()
    observer_settings = observer_settings_payload(config, path=DASHBOARD_CONFIG_PATH)
    state["enabled"] = bool(observer_settings["enabled"])
    state["refreshIntervalMinutes"] = float(observer_settings["refreshIntervalMinutes"])
    state["refreshIntervalSeconds"] = (
        float(observer_settings["refreshIntervalMinutes"]) * 60.0
    )
    return _admin_observer_payload(state, observer_settings)


async def admin_set_observer(payload: Any) -> dict[str, Any]:
    if isinstance(payload, bool):
        update_payload: dict[str, Any] = {"enabled": payload}
    elif isinstance(payload, dict):
        update_payload = payload
    else:
        raise HTTPException(
            status_code=400, detail="Body must be a JSON object or boolean"
        )

    async with ADMIN_AUTOMATIONS_LOCK:
        config = load_dashboard_config(DASHBOARD_CONFIG_PATH)
        observer_settings = update_observer_settings(config, update_payload)
        cache_state = _load_observer_state()
        cache_state["enabled"] = bool(observer_settings["enabled"])
        cache_state["refreshIntervalMinutes"] = observer_settings[
            "refreshIntervalMinutes"
        ]
        cache_state["refreshIntervalSeconds"] = (
            float(observer_settings["refreshIntervalMinutes"]) * 60.0
        )
        cache_state["updatedAt"] = _now_iso()
        Cache().observer_state.save(cache_state)
        _save_yaml_config(DASHBOARD_CONFIG_PATH, config)
    return _admin_observer_payload(cache_state, observer_settings)


async def admin_run_observer(*, force: bool = False) -> dict[str, Any]:
    async with ADMIN_AUTOMATIONS_LOCK:
        state = _load_observer_state()
        observer_settings = observer_settings_payload(
            load_dashboard_config(DASHBOARD_CONFIG_PATH),
            path=DASHBOARD_CONFIG_PATH,
        )
        enabled = bool(observer_settings["enabled"])
        state["enabled"] = enabled
        state["refreshIntervalMinutes"] = float(
            observer_settings["refreshIntervalMinutes"]
        )
        state["refreshIntervalSeconds"] = (
            float(observer_settings["refreshIntervalMinutes"]) * 60.0
        )
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
            raise HTTPException(
                status_code=500,
                detail=state["lastError"],
            ) from exc
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


async def admin_run_automation(name: str, *, refresh: bool = False) -> dict[str, Any]:
    _ = refresh
    async with ADMIN_AUTOMATIONS_LOCK:
        return await _run_named_automation(name)


async def admin_run_all_automations(*, refresh: bool = False) -> dict[str, Any]:
    _ = refresh
    async with ADMIN_AUTOMATIONS_LOCK:
        return cast(dict[str, Any], await _run_with_db(_run_all_automations_sync))


async def admin_job(job_id: str) -> dict[str, Any]:
    job = await _get_job(job_id)
    return _serialize_job(job)


async def admin_run_automation_async(name: str) -> dict[str, Any]:
    job = _AdminJob(
        id=str(uuid4()),
        kind="automation",
        status="queued",
        created_at=_now_iso(),
    )
    await _save_job(job)
    asyncio.create_task(_run_automation_job(job_id=job.id, name=name))
    return {"jobId": job.id, "status": job.status}


async def admin_run_all_automations_async() -> dict[str, Any]:
    job = _AdminJob(
        id=str(uuid4()),
        kind="automations",
        status="queued",
        created_at=_now_iso(),
    )
    await _save_job(job)
    asyncio.create_task(_run_all_automations_job(job_id=job.id))
    return {"jobId": job.id, "status": job.status}
