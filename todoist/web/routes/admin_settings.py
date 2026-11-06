# pyright: reportUndefinedVariable=false
"""Admin settings and adjustment routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement

import asyncio
from typing import Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException

from todoist.web.dashboard_settings import apply_settings_patch, parse_settings_patch
from todoist.web.services.project_adjustments import (
    _manual_project_mapping_details,
    _resolve_automatic_project_mappings,
)
from todoist.web.routes.common import _sync_api_globals


def _sync_admin_globals() -> None:
    _sync_api_globals(globals())


router = APIRouter(dependencies=[Depends(_sync_admin_globals)])


def _dashboard_config_path() -> str:
    try:
        return str(_DASHBOARD_CONFIG_PATH.relative_to(_REPO_ROOT))
    except ValueError:
        return str(_DASHBOARD_CONFIG_PATH)


def _dashboard_edit_targets() -> list[dict[str, str]]:
    path = _dashboard_config_path()
    return [
        {
            "key": key,
            "label": label,
            "icon": "wrench",
            "configPath": path,
            "anchor": "dashboard-settings",
        }
        for key, label in (
            ("urgency", "Urgency watch badge"),
            ("plot-events", "Plot event markers"),
        )
    ]


def _dashboard_settings_response(config: Any, *, saved: bool = False) -> dict[str, Any]:
    payload = {
        "settings": _dashboard_settings_payload(config),
        "editTargets": _dashboard_edit_targets(),
    }
    return {"saved": True, **payload} if saved else payload


@router.get("/api/admin/project_adjustments", tags=["admin"])
async def admin_project_adjustments(
    file: str | None = None, refresh: bool = False
) -> dict[str, Any]:
    """Return mapping files, current mapping content, and project lists for building adjustments."""

    try:
        selected = (
            normalize_adjustment_filename(file)
            if file
            else _available_mapping_files()[0]
        )
        mappings, archived_parents = _load_mapping_file(selected)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    warning: str | None = None
    try:
        project_data = cast(
            tuple[Any, ...],
            await asyncio.to_thread(_load_projects_for_adjustments_sync, refresh),
        )
        active_root = cast(list[str], project_data[0])
        archived_root = cast(list[str], project_data[1])
        archived_names = cast(list[str], project_data[2])
        remappable_active_root = cast(list[str], project_data[3])
        project_records = cast(
            list[dict[str, Any]], project_data[4] if len(project_data) > 4 else []
        )
    except Exception as exc:  # pragma: no cover - network safety
        logger.warning(f"Failed loading project lists for adjustments: {exc}")
        active_root = []
        archived_root = []
        archived_names = []
        remappable_active_root = []
        project_records = []
        warning = f"Project list unavailable ({type(exc).__name__}). Showing saved mappings only."
    source_projects = sorted(set(archived_names) | set(remappable_active_root))
    automatic_mappings, automatic_mapping_details = _resolve_automatic_project_mappings(
        project_records,
        manual_mappings=mappings,
        archived_parent_projects=set(archived_parents),
    )
    mapping_provenance = {
        **{source_name: "automatic" for source_name in automatic_mappings},
        **{source_name: "manual" for source_name in mappings},
    }
    unmapped_source_projects = [
        name
        for name in source_projects
        if name not in mappings and name not in automatic_mappings
    ]
    archived_parents = sorted(
        [name for name in archived_parents if name in archived_names]
    )

    return {
        "files": _available_mapping_files(),
        "selectedFile": selected,
        "mappings": mappings,
        "automaticMappings": automatic_mappings,
        "mappingProvenance": mapping_provenance,
        "mappingDetails": [
            *_manual_project_mapping_details(project_records, mappings),
            *automatic_mapping_details,
        ],
        "activeRootProjects": active_root,
        "archivedRootProjects": archived_root,
        "remappableActiveRootProjects": remappable_active_root,
        "archivedParentProjects": archived_parents,
        "archivedProjects": archived_names,
        "sourceProjects": source_projects,
        "unmappedSourceProjects": unmapped_source_projects,
        "warning": warning,
    }


@router.put("/api/admin/project_adjustments", tags=["admin"])
async def admin_save_project_adjustments(
    file: str,
    refresh: bool = False,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Save mapping dict to the selected mapping file."""

    mappings: dict[str, str]
    archived_parents: list[str]
    refresh_warning: str | None = None
    if isinstance(payload.get("mappings"), dict) or "archivedParents" in payload:
        mappings = cast(dict[str, str], payload.get("mappings") or {})
        archived_parents = cast(list[str], payload.get("archivedParents") or [])
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

    try:
        safe_filename = normalize_adjustment_filename(file)
        project_lists = cast(
            tuple[list[str], list[str], list[str], list[str]],
            await asyncio.to_thread(
                _load_projects_for_adjustments_sync,
                False,
            ),
        )
        active_root = project_lists[0]
        archived_names = project_lists[2]
        remappable_active_root = project_lists[3]
        allowed_sources = set(archived_names) | set(remappable_active_root)
        allowed_targets = set(active_root) | set(archived_names)
        invalid_sources = sorted(set(mappings) - allowed_sources)
        invalid_targets = sorted(set(mappings.values()) - allowed_targets)
        invalid_archived_parents = sorted(set(archived_parents) - set(archived_names))
        if invalid_sources:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Mapping sources must be archived projects or explicitly "
                    f"remappable active roots: {', '.join(invalid_sources[:10])}"
                ),
            )
        if invalid_targets:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Mapping targets must be active roots or archived projects: "
                    f"{', '.join(invalid_targets[:10])}"
                ),
            )
        if invalid_archived_parents:
            raise HTTPException(
                status_code=400,
                detail=(
                    "archivedParents must contain archived projects only: "
                    f"{', '.join(invalid_archived_parents[:10])}"
                ),
            )
        async with _ADMIN_LOCK:
            _save_mapping_file(safe_filename, mappings, archived_parents)
            if refresh:
                try:
                    await _ensure_state(refresh=True)
                except Exception as exc:  # pragma: no cover - network safety
                    logger.warning(
                        f"Failed refreshing dashboard state after saving adjustments: {exc}"
                    )
                    refresh_warning = (
                        f"Saved, but dashboard refresh failed ({type(exc).__name__})."
                    )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "saved": True,
        "file": safe_filename,
        "count": len(mappings),
        "archivedParents": len(archived_parents),
        "warning": refresh_warning,
    }


@router.get("/api/admin/dashboard/settings", tags=["admin"])
async def admin_dashboard_settings() -> dict[str, Any]:
    config = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
    return _dashboard_settings_response(config)


@router.get("/api/admin/dashboard/labels", tags=["admin"])
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
    if not any(
        item["name"] == DEFAULT_URGENCY_SETTINGS["fire_label"] for item in labels
    ):
        labels.append(
            {
                "name": DEFAULT_URGENCY_SETTINGS["fire_label"],
                "color": label_colors.get(DEFAULT_URGENCY_SETTINGS["fire_label"]),
            }
        )
    labels.sort(key=lambda item: item["name"].lower())
    return {"labels": labels}


@router.put("/api/admin/dashboard/settings", tags=["admin"])
async def admin_update_dashboard_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    patch = parse_settings_patch(payload)
    async with _ADMIN_LOCK:
        config = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
        apply_settings_patch(config, patch)
        _save_yaml_config(_DASHBOARD_CONFIG_PATH, config)
        _state.home_payload_cache.clear()
    return _dashboard_settings_response(config, saved=True)
