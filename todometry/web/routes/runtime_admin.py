"""Runtime, token, timezone, and log routes."""

from datetime import datetime
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, set_key, unset_key
from fastapi import APIRouter, Body, HTTPException

from todometry.core.env import EnvVar
from todometry.core.utils import Cache
from todometry.web.api_components import logs
from todometry.web.api_components.runtime import (
    REPO_ROOT as _REPO_ROOT,
    detect_system_timezone as _detect_system_timezone,
    is_valid_timezone_name as _is_valid_timezone_name,
    looks_like_api_key as _looks_like_api_key,
    mask_api_key as _mask_api_key,
    normalize_api_key as _normalize_api_key,
    normalize_timezone as _normalize_timezone,
    resolve_data_dir as _resolve_data_dir,
    resolve_env_path as _resolve_env_path,
    safe_display_path as _safe_display_path,
    validate_api_token as _validate_api_token,
)

router = APIRouter()


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


def _admin_api_token_from_env_path() -> tuple[str, Path]:
    env_path = _resolve_env_path()
    token = _normalize_api_key(os.getenv("API_KEY"))
    if not token and env_path.exists():
        token = _normalize_api_key(dotenv_values(env_path).get("API_KEY"))
        if token:
            os.environ["API_KEY"] = token
    return token, env_path


@router.get("/api/admin/api_token", tags=["admin"])
async def admin_api_token_status() -> dict[str, Any]:
    token, env_path = _admin_api_token_from_env_path()
    return {
        "configured": bool(token),
        "masked": _mask_api_key(token),
        "envPath": _safe_display_path(env_path, root=_REPO_ROOT),
    }


@router.post("/api/admin/api_token", tags=["admin"])
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
        "envPath": _safe_display_path(env_path, root=_REPO_ROOT),
        "validated": bool(validate),
        "labelsCount": labels_count,
    }


@router.post("/api/admin/api_token/validate", tags=["admin"])
async def admin_validate_api_token(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    resolved_token, _ = _admin_api_token_from_env_path()
    token = _normalize_api_key(payload.get("token")) or resolved_token
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


@router.delete("/api/admin/api_token", tags=["admin"])
async def admin_clear_api_token() -> dict[str, Any]:
    env_path = _resolve_env_path()
    if env_path.exists():
        unset_key(str(env_path), "API_KEY")
    os.environ.pop("API_KEY", None)
    return {
        "configured": False,
        "masked": "",
        "envPath": _safe_display_path(env_path, root=_REPO_ROOT),
    }


@router.get("/api/admin/timezone", tags=["admin"])
async def admin_timezone_status() -> dict[str, Any]:
    return _resolve_timezone_status()


@router.post("/api/admin/timezone", tags=["admin"])
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


@router.delete("/api/admin/timezone", tags=["admin"])
async def admin_clear_timezone() -> dict[str, Any]:
    env_path = _resolve_env_path()
    if env_path.exists():
        unset_key(str(env_path), str(EnvVar.TIMEZONE))
    os.environ.pop(str(EnvVar.TIMEZONE), None)
    return _resolve_timezone_status()


@router.get("/api/runtime/logs", tags=["runtime"])
async def runtime_logs() -> dict[str, Any]:
    return {
        "inspectOnly": True,
        "sources": logs.runtime_log_sources(
            data_dir=_resolve_data_dir(), cache_dir=Path(Cache().path)
        ),
    }


@router.get("/api/runtime/logs/read", tags=["runtime"])
async def runtime_read_log(
    source: str | None = None,
    path: str | None = None,
    tail_lines: int = 120,
    page: int = 1,
) -> dict[str, Any]:
    spec, abs_path = logs.resolve_runtime_log_request(
        data_dir=_resolve_data_dir(),
        cache_dir=Path(Cache().path),
        source=source,
        path=path,
    )
    if not abs_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Runtime log is not available yet: {spec.label}",
        )

    stat = abs_path.stat()
    payload = logs.read_log_file(abs_path, tail_lines=tail_lines, page=page)
    return {
        "id": spec.key,
        "source": spec.key,
        "label": spec.label,
        "kind": spec.category,
        "category": spec.category,
        "description": spec.description,
        "path": logs.display_log_path(
            abs_path, data_dir=_resolve_data_dir(), cache_dir=Path(Cache().path)
        ),
        "available": True,
        "inspectOnly": True,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        **payload,
    }


@router.get("/api/admin/logs", tags=["admin"])
async def admin_logs() -> dict[str, Any]:
    sources = logs.runtime_log_sources(
        data_dir=_resolve_data_dir(), cache_dir=Path(Cache().path)
    )
    return {
        "logs": [
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
            for item in sources
        ]
    }


@router.get("/api/admin/logs/read", tags=["admin"])
async def admin_read_log(
    source: str | None = None,
    path: str | None = None,
    tail_lines: int = 40,
    page: int = 1,
) -> dict[str, Any]:
    spec, abs_path = logs.resolve_runtime_log_request(
        data_dir=_resolve_data_dir(),
        cache_dir=Path(Cache().path),
        source=source,
        path=path,
    )
    if not abs_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Runtime log is not available yet: {spec.label}",
        )
    stat = abs_path.stat()
    payload = logs.read_log_file(abs_path, tail_lines=tail_lines, page=page)
    return {
        "source": spec.key,
        "label": spec.label,
        "category": spec.category,
        "description": spec.description,
        "path": logs.display_log_path(
            abs_path, data_dir=_resolve_data_dir(), cache_dir=Path(Cache().path)
        ),
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        **payload,
    }
