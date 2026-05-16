# pyright: reportUndefinedVariable=false
"""Runtime, token, timezone, and log routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from todoist.web.routes.common import _sync_api_globals

router = APIRouter()

@router.get("/api/admin/api_token", tags=["admin"])
async def admin_api_token_status() -> dict[str, Any]:
    _sync_api_globals(globals())
    token = _resolve_api_key()
    env_path = _resolve_env_path()
    return {
        "configured": bool(token),
        "masked": _mask_api_key(token),
        "envPath": _safe_display_path(env_path, root=_REPO_ROOT),
    }

@router.post("/api/admin/api_token", tags=["admin"])
async def admin_set_api_token(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _sync_api_globals(globals())
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
    _sync_api_globals(globals())
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

@router.delete("/api/admin/api_token", tags=["admin"])
async def admin_clear_api_token() -> dict[str, Any]:
    _sync_api_globals(globals())
    env_path = _resolve_env_path()
    if env_path.exists():
        unset_key(str(env_path), "API_KEY")
    os.environ.pop("API_KEY", None)
    return {"configured": False, "masked": "", "envPath": _safe_display_path(env_path, root=_REPO_ROOT)}

@router.get("/api/admin/timezone", tags=["admin"])
async def admin_timezone_status() -> dict[str, Any]:
    _sync_api_globals(globals())
    return _resolve_timezone_status()

@router.post("/api/admin/timezone", tags=["admin"])
async def admin_set_timezone(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _sync_api_globals(globals())
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
    _sync_api_globals(globals())
    env_path = _resolve_env_path()
    if env_path.exists():
        unset_key(str(env_path), str(EnvVar.TIMEZONE))
    os.environ.pop(str(EnvVar.TIMEZONE), None)
    return _resolve_timezone_status()

@router.get("/api/runtime/logs", tags=["runtime"])
async def runtime_logs() -> dict[str, Any]:
    _sync_api_globals(globals())
    return {"inspectOnly": True, "sources": _runtime_log_sources()}

@router.get("/api/runtime/logs/read", tags=["runtime"])
async def runtime_read_log(
    source: str | None = None,
    path: str | None = None,
    tail_lines: int = 120,
    page: int = 1,
) -> dict[str, Any]:
    _sync_api_globals(globals())
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

@router.get("/api/admin/logs", tags=["admin"])
async def admin_logs() -> dict[str, Any]:
    _sync_api_globals(globals())
    return {"logs": _log_files()}

@router.get("/api/admin/logs/read", tags=["admin"])
async def admin_read_log(
    source: str | None = None,
    path: str | None = None,
    tail_lines: int = 40,
    page: int = 1,
) -> dict[str, Any]:
    _sync_api_globals(globals())
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
