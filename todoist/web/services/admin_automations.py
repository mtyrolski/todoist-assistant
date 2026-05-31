"""Admin automation, job, and observer backend services."""

# pylint: disable=global-statement


import asyncio
import contextlib
import io
import os
import re
import signal
import subprocess
import threading
from uuid import uuid4
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import hydra
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from fastapi import HTTPException
from loguru import logger
from omegaconf import DictConfig, OmegaConf

from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.gmail_tasks import (
    GmailTasksAutomation,
    resolve_gmail_credentials_path,
    resolve_gmail_token_path,
)
from todoist.automations.observer import AutomationObserver
from todoist.database.base import Database
from todoist.dashboard_settings import (
    load_dashboard_config,
    observer_settings_payload,
    update_observer_settings,
)
from todoist.env import EnvVar
from todoist.llm import DEFAULT_MODEL_ID, DEFAULT_TRITON_MODEL_NAME, DEFAULT_TRITON_URL
from todoist.utils import Cache, LocalStorageError, get_log_level, load_config

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


@dataclass
class _PendingGmailAuthSession:
    state: str
    auth_url: str
    redirect_uri: str
    started_at: str
    completed: bool = False
    error: str | None = None


_JOBS: dict[str, _AdminJob] = {}
_GMAIL_AUTH_LOCK = threading.Lock()
_GMAIL_AUTH_SESSION: _PendingGmailAuthSession | None = None
_OAUTHLIB_INSECURE_TRANSPORT = "OAUTHLIB_INSECURE_TRANSPORT"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _serialize_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return None


def _safe_display_path(path: Path, *, root: Path | None = None) -> str:
    if root is not None:
        try:
            return str(path.relative_to(root))
        except ValueError:
            pass
    name = path.name.strip()
    return name or str(path)


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
    override = os.getenv("DASHBOARD_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _REPO_ROOT / ".cache" / "todoist-assistant" / "dashboard"


def _dashboard_pid_dir() -> Path:
    override = os.getenv("DASHBOARD_PID_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _dashboard_state_dir() / "pids"


def _clear_gmail_auth_session() -> None:
    global _GMAIL_AUTH_SESSION
    with _GMAIL_AUTH_LOCK:
        _GMAIL_AUTH_SESSION = None


def _current_gmail_auth_session() -> _PendingGmailAuthSession | None:
    with _GMAIL_AUTH_LOCK:
        return _GMAIL_AUTH_SESSION


def _write_gmail_token(credentials: Credentials) -> None:
    token_path = resolve_gmail_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


@contextlib.contextmanager
def _allow_insecure_oauth_transport() -> Any:
    previous = os.environ.get(_OAUTHLIB_INSECURE_TRANSPORT)
    os.environ[_OAUTHLIB_INSECURE_TRANSPORT] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_OAUTHLIB_INSECURE_TRANSPORT, None)
        else:
            os.environ[_OAUTHLIB_INSECURE_TRANSPORT] = previous


def _load_automations(*, config_dir: Path | None = None) -> list[Automation]:
    resolved_dir = config_dir or _CONFIG_DIR
    config = load_config("automations", str(resolved_dir.resolve()))
    automations: list[Automation] = hydra.utils.instantiate(cast(DictConfig, config).automations)
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


def _automation_requires_auth(key: str) -> bool:
    return key in {"gmail_tasks"}


def _default_enabled_automation_keys(config: Mapping[str, Any]) -> list[str]:
    return [key for key in _available_automation_keys(config) if not _automation_requires_auth(key)]


def _configured_enabled_automation_keys(config: Mapping[str, Any]) -> list[str]:
    raw = config.get("automations")
    if not isinstance(raw, Sequence):
        return []
    target_to_keys: dict[str, list[str]] = {}
    for key in _available_automation_keys(config):
        section = config.get(key)
        if isinstance(section, Mapping):
            target = section.get("_target_")
            if isinstance(target, str) and target:
                target_to_keys.setdefault(target, []).append(key)
    keys: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            target = item.get("_target_")
            if isinstance(target, str):
                matched_keys = target_to_keys.get(target, [])
                if len(matched_keys) == 1:
                    keys.append(matched_keys[0])
                    continue
            continue
        item_str = str(item).strip()
        match = re.fullmatch(r"\$\{([a-zA-Z0-9_-]+)\}", item_str)
        if match:
            keys.append(match.group(1))
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
    return {
        "attemptCount": signal_payload.get("attemptCount"),
        "successCount": signal_payload.get("successCount"),
        "failureCount": signal_payload.get("failureCount"),
        "skipCount": signal_payload.get("skipCount"),
        "lastStatus": signal_payload.get("lastStatus"),
        "lastStartedAt": signal_payload.get("lastStartedAt"),
        "lastFinishedAt": signal_payload.get("lastFinishedAt"),
        "lastDurationSeconds": signal_payload.get("lastDurationSeconds"),
        "lastError": signal_payload.get("lastError"),
        "lastSuccessAt": signal_payload.get("lastSuccessAt"),
    }


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


def _automation_metadata_for_key(config: DictConfig, key: str, *, enabled: bool) -> dict[str, Any]:
    section = config.get(key)
    if not isinstance(section, Mapping):
        raise ValueError(f"Automation section missing or invalid: {key}")
    automation = cast(Automation, hydra.utils.instantiate(section))
    payload = {
        **_automation_launch_metadata(automation),
        "key": key,
        "enabled": enabled,
        "authRequired": _automation_requires_auth(key),
        "defaultEnabled": key in _default_enabled_automation_keys(config),
        "target": str(section.get("_target_") or ""),
    }
    if key == "gmail_tasks":
        payload["connection"] = _gmail_automation_status()
    return payload


def _load_automation_inventory(*, config_dir: Path | None = None) -> list[dict[str, Any]]:
    resolved_dir = config_dir or _CONFIG_DIR
    config = cast(DictConfig, load_config("automations", str(resolved_dir.resolve())))
    available_keys = _available_automation_keys(config)
    enabled_keys = set(_enabled_automation_keys(config))
    inventory: list[dict[str, Any]] = []
    for key in available_keys:
        inventory.append(_automation_metadata_for_key(config, key, enabled=key in enabled_keys))
    return inventory


def _save_enabled_automations(keys: Sequence[str], *, path: Path | None = None) -> None:
    config_path = path or AUTOMATIONS_PATH
    config = _read_yaml_config(config_path)
    available_keys = _available_automation_keys(config)
    normalized = [key for key in available_keys if key in set(keys)]
    config["automations"] = [_automation_ref(key) for key in normalized]
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

    enabled_keys = _enabled_automation_keys(config)
    next_keys = [item for item in enabled_keys if item != key]
    if enabled:
        insert_at = max(0, available_keys.index(key))
        ordered = [item for item in available_keys if item in next_keys]
        if key not in ordered:
            ordered.insert(insert_at, key)
        next_keys = ordered

    config["automations"] = [_automation_ref(item) for item in next_keys]
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
        logger.warning("Dashboard observer PID file is unreadable: {}", observer_pid_path)
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
    env["TODOIST_AGENT_MODEL_ID"] = os.getenv(str(EnvVar.AGENT_MODEL_ID), DEFAULT_MODEL_ID)
    env["TODOIST_AGENT_TRITON_MODEL_NAME"] = os.getenv(
        str(EnvVar.AGENT_TRITON_MODEL_NAME), DEFAULT_TRITON_MODEL_NAME
    )
    env["TODOIST_AGENT_TRITON_URL"] = os.getenv(
        str(EnvVar.AGENT_TRITON_URL), DEFAULT_TRITON_URL
    )

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


def _gmail_automation_status(
    *,
    credentials_path: Path | None = None,
    token_path: Path | None = None,
) -> dict[str, Any]:
    resolved_credentials_path = credentials_path or resolve_gmail_credentials_path()
    resolved_token_path = token_path or resolve_gmail_token_path()
    credentials_present = resolved_credentials_path.exists()
    token_present = resolved_token_path.exists()
    connected = False
    token_detail = "Missing token"
    if token_present:
        try:
            creds = Credentials.from_authorized_user_file(
                str(resolved_token_path), GmailTasksAutomation.SCOPES
            )
            connected = bool(getattr(creds, "valid", False))
            if connected:
                token_detail = "Authorized"
                _clear_gmail_auth_session()
            elif getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
                token_detail = "Token expired but refreshable"
            else:
                token_detail = "Token present but invalid"
        except Exception as exc:  # pragma: no cover - defensive
            token_detail = f"Token unreadable ({type(exc).__name__})"
    session = _current_gmail_auth_session()
    pending_auth: dict[str, Any] | None = None
    if session is not None and not session.completed:
        pending_auth = {
            "active": True,
            "authUrl": session.auth_url,
            "redirectUri": session.redirect_uri,
            "startedAt": session.started_at,
            "error": session.error,
        }
    elif session is not None and session.error:
        pending_auth = {
            "active": False,
            "authUrl": session.auth_url,
            "redirectUri": session.redirect_uri,
            "startedAt": session.started_at,
            "error": session.error,
        }
        if token_present:
            _clear_gmail_auth_session()

    status = {
        "credentialsPresent": credentials_present,
        "tokenPresent": token_present,
        "connected": connected,
        "credentialsPath": _safe_display_path(resolved_credentials_path, root=_REPO_ROOT),
        "tokenPath": _safe_display_path(resolved_token_path, root=_REPO_ROOT),
        "detail": token_detail if credentials_present else "Missing Gmail credentials file",
        "setupDocPath": _safe_display_path(_REPO_ROOT / "docs" / "gmail_setup.md", root=_REPO_ROOT),
    }
    if pending_auth is not None:
        status["pendingAuth"] = pending_auth
    return status


def _start_gmail_manual_auth_session(
    *,
    credentials_path: Path | None = None,
) -> _PendingGmailAuthSession:
    global _GMAIL_AUTH_SESSION

    resolved_credentials_path = credentials_path or resolve_gmail_credentials_path()
    if not resolved_credentials_path.exists():
        raise FileNotFoundError("gmail_credentials.json is required before connecting Gmail.")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(resolved_credentials_path), GmailTasksAutomation.SCOPES
    )

    class _OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            nonlocal flow
            server = cast(ThreadingHTTPServer, self.server)
            current_url = f"http://127.0.0.1:{server.server_address[1]}{self.path}"
            try:
                with _allow_insecure_oauth_transport():
                    flow.fetch_token(authorization_response=current_url)
                credentials = cast(Credentials, flow.credentials)
                _write_gmail_token(credentials)
                _set_automation_enabled("gmail_tasks", enabled=True)
                _restart_dashboard_observer_if_managed()
                with _GMAIL_AUTH_LOCK:
                    if _GMAIL_AUTH_SESSION is not None:
                        _GMAIL_AUTH_SESSION.completed = True
                        _GMAIL_AUTH_SESSION.error = None
                body = (
                    "<html><body style='font-family:system-ui,sans-serif;padding:24px'>"
                    "<h1>Gmail connected</h1>"
                    "<p>You can return to the control panel and refresh the automation state.</p>"
                    "</body></html>"
                )
                self.send_response(200)
            except Exception as exc:  # pragma: no cover - callback failures are browser driven
                with _GMAIL_AUTH_LOCK:
                    if _GMAIL_AUTH_SESSION is not None:
                        _GMAIL_AUTH_SESSION.error = f"{type(exc).__name__}: {exc}"
                body = (
                    "<html><body style='font-family:system-ui,sans-serif;padding:24px'>"
                    "<h1>Gmail authorization failed</h1>"
                    f"<p>{type(exc).__name__}: {exc}</p>"
                    "</body></html>"
                )
                self.send_response(500)

            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003  # pylint: disable=redefined-builtin
            message = format % args if args else format
            logger.info("Gmail OAuth callback: {}", message)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _OAuthCallbackHandler)
    server.timeout = 300
    flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    with _allow_insecure_oauth_transport():
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

    session = _PendingGmailAuthSession(
        state=str(state),
        auth_url=str(auth_url),
        redirect_uri=str(flow.redirect_uri),
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    with _GMAIL_AUTH_LOCK:
        _GMAIL_AUTH_SESSION = session

    def _serve_once() -> None:
        try:
            server.handle_request()
        finally:
            server.server_close()

    threading.Thread(target=_serve_once, name="gmail-oauth-callback", daemon=True).start()
    return session


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


def _observer_edit_targets(observer_settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "key": "observer",
            "label": "Dashboard observer",
            "icon": "wrench",
            "configPath": observer_settings["configPath"],
            "anchor": "observer-control",
        }
    ]


def _build_observer(db: Database, *, config_dir: Path | None = None) -> AutomationObserver:
    resolved_dir = config_dir or _CONFIG_DIR
    config = load_config("automations", str(resolved_dir.resolve()))
    activity_automation: Activity = hydra.utils.instantiate(cast(DictConfig, config).activity)
    automations: list[Automation] = hydra.utils.instantiate(cast(DictConfig, config).automations)
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
        loguru_handler_id = logger.add(output_stream, format="{message}", level=get_log_level())
        try:
            task_delegations = automation.tick(dbio)
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
    completed = 0
    failed = 0

    for automation in _load_automations():
        result = _run_automation_sync(
            automation,
            dbio=dbio,
            continue_on_error=True,
        )
        results.append(result)
        if result["status"] == "failed":
            failed += 1
        else:
            completed += 1
        dbio.reset()

    return {
        "results": results,
        "summary": {
            "completed": completed,
            "failed": failed,
            "skipped": 0,
        },
    }


async def _run_automation_job(*, job_id: str, name: str) -> None:
    await _update_job(job_id, status="running", started_at=_now_iso())
    try:
        async with ADMIN_AUTOMATIONS_LOCK:
            automations = {a.name: a for a in _load_automations()}
            if name not in automations:
                raise HTTPException(status_code=404, detail=f"Unknown automation: {name}")

            dbio = Database(".env")
            dbio.pull()
            result = await asyncio.to_thread(_run_automation_sync, automations[name], dbio=dbio)
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
        async with ADMIN_AUTOMATIONS_LOCK:
            dbio = Database(".env")
            dbio.pull()
            result = await asyncio.to_thread(_run_all_automations_sync, dbio=dbio)

        await _update_job(job_id, status="done", finished_at=_now_iso(), result=result)
    except Exception as exc:  # pragma: no cover - defensive
        await _update_job(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error=f"{type(exc).__name__}: {exc}",
        )


def _serialize_job(job: _AdminJob) -> dict[str, Any]:
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


def _admin_observer_payload(state: Mapping[str, Any], observer_settings: Mapping[str, Any]) -> dict[str, Any]:
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


async def admin_gmail_connect_status() -> dict[str, Any]:
    return _gmail_automation_status()


async def admin_gmail_connect_start() -> dict[str, Any]:
    status = _gmail_automation_status()
    if not status["credentialsPresent"]:
        raise HTTPException(
            status_code=400,
            detail="gmail_credentials.json is required before connecting Gmail.",
        )
    if status["connected"]:
        return status
    pending_auth = status.get("pendingAuth")
    if isinstance(pending_auth, Mapping) and pending_auth.get("active"):
        status["authUrl"] = pending_auth.get("authUrl")
        status["redirectUri"] = pending_auth.get("redirectUri")
        return status
    session = await asyncio.to_thread(_start_gmail_manual_auth_session)
    next_status = _gmail_automation_status()
    next_status["authUrl"] = session.auth_url
    next_status["redirectUri"] = session.redirect_uri
    return next_status


async def admin_gmail_disconnect() -> dict[str, Any]:
    token_path = resolve_gmail_token_path()
    if token_path.exists():
        token_path.unlink()
    _clear_gmail_auth_session()
    return _gmail_automation_status()


async def admin_observer_state() -> dict[str, Any]:
    config = load_dashboard_config(DASHBOARD_CONFIG_PATH)
    state = _load_observer_state()
    observer_settings = observer_settings_payload(config, path=DASHBOARD_CONFIG_PATH)
    state["enabled"] = bool(observer_settings["enabled"])
    state["refreshIntervalMinutes"] = float(observer_settings["refreshIntervalMinutes"])
    state["refreshIntervalSeconds"] = float(observer_settings["refreshIntervalMinutes"]) * 60.0
    return _admin_observer_payload(state, observer_settings)


async def admin_set_observer(payload: Any) -> dict[str, Any]:
    if isinstance(payload, bool):
        update_payload: dict[str, Any] = {"enabled": payload}
    elif isinstance(payload, dict):
        update_payload = payload
    else:
        raise HTTPException(status_code=400, detail="Body must be a JSON object or boolean")

    async with ADMIN_AUTOMATIONS_LOCK:
        config = load_dashboard_config(DASHBOARD_CONFIG_PATH)
        observer_settings = update_observer_settings(config, update_payload)
        cache_state = _load_observer_state()
        cache_state["enabled"] = bool(observer_settings["enabled"])
        cache_state["refreshIntervalMinutes"] = observer_settings["refreshIntervalMinutes"]
        cache_state["refreshIntervalSeconds"] = float(observer_settings["refreshIntervalMinutes"]) * 60.0
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
            raise HTTPException(
                status_code=500,
                detail=state["lastError"],
            ) from exc
        finally:
            dbio.reset()
            finished_at = datetime.now()
            state["lastRunAt"] = finished_at.isoformat(timespec="seconds")
            state["lastDurationSeconds"] = round((finished_at - started_at).total_seconds(), 3)
            state["updatedAt"] = _now_iso()
            Cache().observer_state.save(state)

    return {"state": _serialize_observer_state(state)}


async def admin_run_automation(name: str, *, refresh: bool = False) -> dict[str, Any]:
    async with ADMIN_AUTOMATIONS_LOCK:
        automations = {a.name: a for a in _load_automations()}
        if name not in automations:
            raise HTTPException(status_code=404, detail=f"Unknown automation: {name}")

        dbio = Database(".env")
        dbio.pull()
        result = await asyncio.to_thread(_run_automation_sync, automations[name], dbio=dbio)
        dbio.reset()

        if refresh:
            return result
        return result


async def admin_run_all_automations(*, refresh: bool = False) -> dict[str, Any]:
    async with ADMIN_AUTOMATIONS_LOCK:
        dbio = Database(".env")
        dbio.pull()
        result = await asyncio.to_thread(_run_all_automations_sync, dbio=dbio)

        if refresh:
            return result
        return result


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
