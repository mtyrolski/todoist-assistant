"""FastAPI routes for the admin automation surface."""

# pylint: disable=protected-access,cyclic-import

import asyncio
from typing import Any

from fastapi import APIRouter, Body
from todoist.dashboard.settings import update_observer_settings

from todoist.web.services.admin_automations import (
    admin_job,
    admin_run_all_automations_async,
    admin_run_automation_async,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _web_api():
    from todoist.web import api as web_api

    return web_api


@router.get("/automations")
async def get_admin_automations() -> dict[str, Any]:
    web_api = _web_api()
    try:
        automations = web_api._load_automation_inventory()
    except Exception as exc:  # pragma: no cover - defensive
        web_api.logger.warning(f"Failed to load automations: {exc}")
        return {"automations": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"automations": automations, "configPath": str(web_api._AUTOMATIONS_PATH)}


@router.post("/automations/{key}/enabled")
async def set_admin_automation_enabled(
    key: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    web_api = _web_api()
    async with web_api._ADMIN_LOCK:
        config = web_api._read_yaml_config(web_api._AUTOMATIONS_PATH)
        available_keys = web_api._available_automation_keys(config)
        if key not in available_keys:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404, detail=f"Unknown automation key: {key}"
            )
        web_api._set_automation_enabled(key, enabled=enabled)
        web_api._restart_dashboard_observer_if_managed()
    return await get_admin_automations()


@router.get("/automations/gmail/status")
async def gmail_status() -> dict[str, Any]:
    return _web_api()._gmail_automation_status()


@router.post("/automations/gmail/connect")
async def gmail_connect() -> dict[str, Any]:
    web_api = _web_api()
    status = web_api._gmail_automation_status()
    if not status["credentialsPresent"]:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="gmail_credentials.json is required before connecting Gmail.",
        )
    if status["connected"]:
        return status
    pending_auth = status.get("pendingAuth")
    if isinstance(pending_auth, dict) and pending_auth.get("active"):
        status["authUrl"] = pending_auth.get("authUrl")
        status["redirectUri"] = pending_auth.get("redirectUri")
        return status
    session = await asyncio.to_thread(web_api._start_gmail_manual_auth_session)
    next_status = web_api._gmail_automation_status()
    next_status["authUrl"] = session.auth_url
    next_status["redirectUri"] = session.redirect_uri
    return next_status


@router.delete("/automations/gmail/connect")
async def gmail_disconnect() -> dict[str, Any]:
    web_api = _web_api()
    token_path = web_api.resolve_gmail_token_path()
    if token_path.exists():
        token_path.unlink()
    web_api._clear_gmail_auth_session()
    return web_api._gmail_automation_status()


@router.get("/jobs/{job_id}")
async def get_admin_job(job_id: str) -> dict[str, Any]:
    return await admin_job(job_id)


@router.post("/automations/run")
async def run_admin_automation(name: str, refresh: bool = False) -> dict[str, Any]:
    web_api = _web_api()
    async with web_api._ADMIN_LOCK:
        automations = {a.name: a for a in web_api._load_automations()}
        if name not in automations:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Unknown automation: {name}")

        dbio = web_api.Database(".env")
        dbio.pull()
        result = await asyncio.to_thread(
            web_api._run_automation_sync, automations[name], dbio=dbio
        )
        dbio.reset()

    if refresh:
        await web_api._ensure_state(refresh=True)
    return result


@router.post("/automations/run_all")
async def run_admin_automations(refresh: bool = False) -> dict[str, Any]:
    web_api = _web_api()
    async with web_api._ADMIN_LOCK:
        dbio = web_api.Database(".env")
        dbio.pull()
        result = await asyncio.to_thread(web_api._run_all_automations_sync, dbio=dbio)

    if refresh:
        await web_api._ensure_state(refresh=True)
    return result


@router.post("/automations/run_async")
async def run_admin_automation_async(name: str) -> dict[str, Any]:
    return await admin_run_automation_async(name)


@router.post("/automations/run_all_async")
async def run_admin_automations_async() -> dict[str, Any]:
    return await admin_run_all_automations_async()


@router.get("/observer")
async def get_admin_observer_state() -> dict[str, Any]:
    web_api = _web_api()
    config = web_api.load_dashboard_config(web_api._DASHBOARD_CONFIG_PATH)
    state = web_api._load_observer_state()
    observer_settings = web_api.observer_settings_payload(
        config, path=web_api._DASHBOARD_CONFIG_PATH
    )
    state["enabled"] = bool(observer_settings["enabled"])
    state["refreshIntervalMinutes"] = float(observer_settings["refreshIntervalMinutes"])
    state["refreshIntervalSeconds"] = (
        float(observer_settings["refreshIntervalMinutes"]) * 60.0
    )
    return {
        "state": web_api._serialize_observer_state(state),
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


@router.post("/observer")
async def set_admin_observer(payload: Any = Body(...)) -> dict[str, Any]:
    web_api = _web_api()
    if isinstance(payload, bool):
        update_payload: dict[str, Any] = {"enabled": payload}
    elif isinstance(payload, dict):
        update_payload = payload
    else:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400, detail="Body must be a JSON object or boolean"
        )

    async with web_api._ADMIN_LOCK:
        config = web_api.load_dashboard_config(web_api._DASHBOARD_CONFIG_PATH)
        try:
            observer_settings = update_observer_settings(config, update_payload)
        except ValueError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail=str(exc)) from exc
        cache_state = web_api._load_observer_state()
        cache_state["enabled"] = bool(observer_settings["enabled"])
        cache_state["refreshIntervalMinutes"] = observer_settings[
            "refreshIntervalMinutes"
        ]
        cache_state["refreshIntervalSeconds"] = (
            float(observer_settings["refreshIntervalMinutes"]) * 60.0
        )
        cache_state["updatedAt"] = web_api._now_iso()
        web_api.Cache().observer_state.save(cache_state)
        web_api._save_yaml_config(web_api._DASHBOARD_CONFIG_PATH, config)
    return {
        "state": web_api._serialize_observer_state(cache_state),
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


@router.post("/observer/run")
async def run_admin_observer(force: bool = False) -> dict[str, Any]:
    web_api = _web_api()
    async with web_api._ADMIN_LOCK:
        state = web_api._load_observer_state()
        observer_settings = web_api.observer_settings_payload(
            web_api.load_dashboard_config(web_api._DASHBOARD_CONFIG_PATH),
            path=web_api._DASHBOARD_CONFIG_PATH,
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
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail="Observer is disabled")

        started_at = web_api.datetime.now()
        dbio = web_api.Database(".env")
        try:
            dbio.pull()
            observer = web_api._build_observer(dbio)
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
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=state["lastError"]) from exc
        finally:
            dbio.reset()
            finished_at = web_api.datetime.now()
            state["lastRunAt"] = finished_at.isoformat(timespec="seconds")
            state["lastDurationSeconds"] = round(
                (finished_at - started_at).total_seconds(), 3
            )
            state["updatedAt"] = web_api._now_iso()
            web_api.Cache().observer_state.save(state)

    return {"state": web_api._serialize_observer_state(state)}
