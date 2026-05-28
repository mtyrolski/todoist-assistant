# pyright: reportUndefinedVariable=false
"""Admin settings, templates, and adjustment routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, cast

from fastapi import APIRouter, Body, HTTPException

from todoist.web.routes.common import _sync_api_globals

router = APIRouter()

@router.get("/api/admin/project_adjustments", tags=["admin"])
async def admin_project_adjustments(
    file: str | None = None, refresh: bool = False
) -> dict[str, Any]:
    _sync_api_globals(globals())
    """Return mapping files, current mapping content, and project lists for building adjustments."""

    try:
        selected = normalize_adjustment_filename(file) if file else _available_mapping_files()[0]
        mappings, archived_parents = _load_mapping_file(selected)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    warning: str | None = None
    try:
        (
            active_root,
            archived_root,
            archived_names,
            remappable_active_root,
        ) = cast(
            tuple[list[str], list[str], list[str], list[str]],
            await asyncio.to_thread(
                _load_projects_for_adjustments_sync,
                refresh,
            ),
        )
    except Exception as exc:  # pragma: no cover - network safety
        logger.warning(f"Failed loading project lists for adjustments: {exc}")
        active_root = []
        archived_root = []
        archived_names = []
        remappable_active_root = []
        warning = f"Project list unavailable ({type(exc).__name__}). Showing saved mappings only."
    source_projects = sorted(set(archived_names) | set(remappable_active_root))
    unmapped_source_projects = [name for name in source_projects if name not in mappings]
    archived_parents = sorted(
        [name for name in archived_parents if name in archived_names]
    )

    return {
        "files": _available_mapping_files(),
        "selectedFile": selected,
        "mappings": mappings,
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
    refresh: bool = True,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
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
                    logger.warning(f"Failed refreshing dashboard state after saving adjustments: {exc}")
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

@router.get("/api/admin/llm_breakdown/settings", tags=["admin"])
async def admin_llm_breakdown_settings() -> dict[str, Any]:
    _sync_api_globals(globals())
    config = _read_yaml_config(_AUTOMATIONS_PATH)
    return {
        "settings": _llm_breakdown_settings_payload(config),
        "basePrompt": BASE_SYSTEM_PROMPT,
    }

@router.put("/api/admin/llm_breakdown/settings", tags=["admin"])
async def admin_update_llm_breakdown_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    config = _read_yaml_config(_AUTOMATIONS_PATH)
    lb_config = config.get("llm_breakdown") or {}

    def _coerce_int(value: Any, field: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail=f"{field} must be an integer"
            ) from exc

    updates: dict[str, Any] = {}
    if "labelPrefix" in payload:
        updates["label_prefix"] = str(payload["labelPrefix"]).strip()
    if "defaultVariant" in payload:
        updates["default_variant"] = str(payload["defaultVariant"]).strip()
    if "maxDepth" in payload:
        updates["max_depth"] = _coerce_int(payload["maxDepth"], "maxDepth")
    if "maxChildren" in payload:
        updates["max_children"] = _coerce_int(payload["maxChildren"], "maxChildren")
    if "maxTotalTasks" in payload:
        updates["max_total_tasks"] = _coerce_int(
            payload["maxTotalTasks"], "maxTotalTasks"
        )
    if "maxQueueDepth" in payload:
        updates["max_queue_depth"] = _coerce_int(
            payload["maxQueueDepth"], "maxQueueDepth"
        )
    if "autoQueueChildren" in payload:
        updates["auto_queue_children"] = bool(payload["autoQueueChildren"])

    if "variants" in payload:
        variants_raw = payload.get("variants")
        if not isinstance(variants_raw, Mapping):
            raise HTTPException(status_code=400, detail="variants must be an object")
        variants: dict[str, Any] = {}
        for key, value in variants_raw.items():
            if not isinstance(value, Mapping):
                raise HTTPException(
                    status_code=400, detail=f"Variant {key} must be an object"
                )
            instruction = str(value.get("instruction", "")).strip()
            variant_payload: dict[str, Any] = {"instruction": instruction}
            if "maxDepth" in value and value.get("maxDepth") not in (None, ""):
                variant_payload["max_depth"] = _coerce_int(
                    value.get("maxDepth"), "maxDepth"
                )
            if "maxChildren" in value and value.get("maxChildren") not in (None, ""):
                variant_payload["max_children"] = _coerce_int(
                    value.get("maxChildren"), "maxChildren"
                )
            if "queueDepth" in value and value.get("queueDepth") not in (None, ""):
                variant_payload["queue_depth"] = _coerce_int(
                    value.get("queueDepth"), "queueDepth"
                )
            variants[str(key).strip()] = variant_payload
        updates["variants"] = variants

    if isinstance(lb_config, DictConfig):
        for key, value in updates.items():
            lb_config[key] = value
    elif isinstance(lb_config, dict):
        lb_config.update(updates)
    else:
        lb_config = updates

    if "variants" in updates or "default_variant" in updates:
        snapshot = (
            OmegaConf.to_container(lb_config, resolve=False)
            if isinstance(lb_config, DictConfig)
            else lb_config
        )
        default_variant = updates.get("default_variant") or (
            snapshot.get("default_variant") if isinstance(snapshot, Mapping) else None
        )
        variants_value = updates.get("variants") or (
            snapshot.get("variants") if isinstance(snapshot, Mapping) else None
        )
        if (
            default_variant
            and isinstance(variants_value, Mapping)
            and default_variant not in variants_value
        ):
            raise HTTPException(
                status_code=400, detail="defaultVariant must exist in variants"
            )

    config["llm_breakdown"] = lb_config
    async with _ADMIN_LOCK:
        _save_yaml_config(_AUTOMATIONS_PATH, config)

    return {
        "saved": True,
        "settings": _llm_breakdown_settings_payload(config),
        "basePrompt": BASE_SYSTEM_PROMPT,
    }

@router.get("/api/admin/dashboard/settings", tags=["admin"])
async def admin_dashboard_settings() -> dict[str, Any]:
    _sync_api_globals(globals())
    config = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
    try:
        config_path = str(_DASHBOARD_CONFIG_PATH.relative_to(_REPO_ROOT))
    except ValueError:
        config_path = str(_DASHBOARD_CONFIG_PATH)
    return {
        "settings": _dashboard_settings_payload(config),
        "editTargets": [
            {
                "key": "urgency",
                "label": "Urgency watch badge",
                "icon": "wrench",
                "configPath": config_path,
                "anchor": "dashboard-settings",
            },
            {
                "key": "plot-events",
                "label": "Plot event markers",
                "icon": "wrench",
                "configPath": config_path,
                "anchor": "dashboard-settings",
            },
        ],
    }

@router.get("/api/admin/dashboard/labels", tags=["admin"])
async def admin_dashboard_labels() -> dict[str, Any]:
    _sync_api_globals(globals())
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
    if not any(item["name"] == DEFAULT_URGENCY_SETTINGS["fire_label"] for item in labels):
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
    _sync_api_globals(globals())
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    config = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
    urgency = config.get("urgency") or {}
    if not isinstance(urgency, Mapping):
        urgency = {}
    urgency = dict(urgency)

    def _coerce_int(value: Any, field: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{field} must be an integer") from exc

    if "enabled" in payload:
        urgency["enabled"] = bool(payload["enabled"])
    if "fireLabel" in payload:
        urgency["fire_label"] = str(payload["fireLabel"]).strip()
    if "fireLabels" in payload:
        fire_labels = payload["fireLabels"]
        if not isinstance(fire_labels, Sequence) or isinstance(fire_labels, str):
            raise HTTPException(status_code=400, detail="fireLabels must be a list")
        urgency["fire_labels"] = [
            str(value).strip() for value in fire_labels if str(value).strip()
        ]
        if urgency["fire_labels"]:
            urgency["fire_label"] = urgency["fire_labels"][0]
    if "warnPriorityThresholds" in payload:
        thresholds = payload["warnPriorityThresholds"]
        if not isinstance(thresholds, Sequence):
            raise HTTPException(status_code=400, detail="warnPriorityThresholds must be a list")
        urgency["warn_priority_thresholds"] = [
            _coerce_int(value, "warnPriorityThresholds") for value in thresholds
        ]
    if "warnPriorityMinCount" in payload:
        urgency["warn_priority_min_count"] = max(
            1, _coerce_int(payload["warnPriorityMinCount"], "warnPriorityMinCount")
        )
    if "warnDueWithinDays" in payload:
        urgency["warn_due_within_days"] = _coerce_int(
            payload["warnDueWithinDays"], "warnDueWithinDays"
        )
    if "warnDueMinCount" in payload:
        urgency["warn_due_min_count"] = max(
            1, _coerce_int(payload["warnDueMinCount"], "warnDueMinCount")
        )
    if "warnDeadlineWithinDays" in payload:
        urgency["warn_deadline_within_days"] = _coerce_int(
            payload["warnDeadlineWithinDays"], "warnDeadlineWithinDays"
        )
    if "warnDeadlineMinCount" in payload:
        urgency["warn_deadline_min_count"] = max(
            1, _coerce_int(payload["warnDeadlineMinCount"], "warnDeadlineMinCount")
        )
    if "dangerOnFireLabel" in payload:
        urgency["danger_on_fire_label"] = bool(payload["dangerOnFireLabel"])
    if "warnOnPriority" in payload:
        urgency["warn_on_priority"] = bool(payload["warnOnPriority"])
    if "warnOnDue" in payload:
        urgency["warn_on_due"] = bool(payload["warnOnDue"])
    if "warnOnDeadline" in payload:
        urgency["warn_on_deadline"] = bool(payload["warnOnDeadline"])
    if "warnSummaryLabel" in payload:
        urgency["warn_summary_label"] = str(payload["warnSummaryLabel"]).strip()
    if "dangerSummaryLabel" in payload:
        urgency["danger_summary_label"] = str(payload["dangerSummaryLabel"]).strip()
    if "badgeLabels" in payload:
        badge_labels = payload["badgeLabels"]
        if not isinstance(badge_labels, Mapping):
            raise HTTPException(status_code=400, detail="badgeLabels must be an object")
        urgency["badge_labels"] = {
            "good": str(badge_labels.get("good") or DEFAULT_URGENCY_SETTINGS["badge_labels"]["good"]).strip(),
            "warn": str(badge_labels.get("warn") or DEFAULT_URGENCY_SETTINGS["badge_labels"]["warn"]).strip(),
            "danger": str(badge_labels.get("danger") or DEFAULT_URGENCY_SETTINGS["badge_labels"]["danger"]).strip(),
        }
    normalized_events: list[dict[str, str]] = []
    if "plotEvents" in payload:
        plot_events = payload["plotEvents"]
        if not isinstance(plot_events, Sequence) or isinstance(plot_events, str):
            raise HTTPException(status_code=400, detail="plotEvents must be a list")
        for item in plot_events:
            if not isinstance(item, Mapping):
                raise HTTPException(status_code=400, detail="plotEvents entries must be objects")
            raw_date = str(item.get("date") or "").strip()
            raw_label = str(item.get("label") or "").strip()
            if not raw_date and not raw_label:
                continue
            if not raw_date or not raw_label:
                raise HTTPException(status_code=400, detail="plot event date and label are required")
            parsed_date = _compute_plot_range(
                _empty_activity_df(),
                weeks=1,
                beg=raw_date,
                end=raw_date,
            )[0]
            normalized_events.append(
                {
                    "date": parsed_date.strftime("%Y-%m-%d"),
                    "label": raw_label,
                    "color": str(item.get("color") or "#ff6b7a").strip(),
                }
            )

    config["urgency"] = urgency
    if "plotEvents" in payload:
        config["plot_events"] = normalized_events
    async with _ADMIN_LOCK:
        _save_yaml_config(_DASHBOARD_CONFIG_PATH, config)

    try:
        config_path = str(_DASHBOARD_CONFIG_PATH.relative_to(_REPO_ROOT))
    except ValueError:
        config_path = str(_DASHBOARD_CONFIG_PATH)

    return {
        "saved": True,
        "settings": _dashboard_settings_payload(config),
        "editTargets": [
            {
                "key": "urgency",
                "label": "Urgency watch badge",
                "icon": "wrench",
                "configPath": config_path,
                "anchor": "dashboard-settings",
            },
            {
                "key": "plot-events",
                "label": "Plot event markers",
                "icon": "wrench",
                "configPath": config_path,
                "anchor": "dashboard-settings",
            },
        ],
    }

@router.get("/api/admin/multiplication", tags=["admin"])
async def admin_multiplication_settings() -> dict[str, Any]:
    _sync_api_globals(globals())
    config = _read_yaml_config(_AUTOMATIONS_PATH)
    return {"settings": _multiplication_settings_payload(config)}

@router.put("/api/admin/multiplication", tags=["admin"])
async def admin_update_multiplication_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    flat_template = str(payload.get("flatLeafTemplate", "")).strip()
    deep_template = str(payload.get("deepLeafTemplate", "")).strip()
    if not flat_template or not deep_template:
        raise HTTPException(
            status_code=400, detail="flatLeafTemplate and deepLeafTemplate are required"
        )

    config = _read_yaml_config(_AUTOMATIONS_PATH)
    multiply_cfg = config.get("multiply") or {}
    existing = (
        OmegaConf.to_container(multiply_cfg, resolve=False) if multiply_cfg else {}
    )
    if not isinstance(existing, dict):
        existing = {}
    config_data = (
        existing.get("config") if isinstance(existing.get("config"), Mapping) else {}
    )
    if not isinstance(config_data, Mapping):
        config_data = {}
    config_data = dict(config_data)
    config_data["flat_leaf_template"] = flat_template
    config_data["deep_leaf_template"] = deep_template
    if "deepChildLabel" in payload:
        deep_child_label = str(payload.get("deepChildLabel", "")).strip()
        if not deep_child_label:
            raise HTTPException(status_code=400, detail="deepChildLabel is required")
        config_data["deep_child_label"] = deep_child_label
    if "cleanupUnusedLabels" in payload:
        config_data["cleanup_unused_labels"] = bool(payload.get("cleanupUnusedLabels"))
    if "cleanupUnusedLabelsAfterDays" in payload:
        raw_days = payload.get("cleanupUnusedLabelsAfterDays")
        if raw_days is None:
            raise HTTPException(
                status_code=400,
                detail="cleanupUnusedLabelsAfterDays must be a non-negative integer",
            )
        try:
            config_data["cleanup_unused_labels_after_days"] = max(
                0,
                int(raw_days),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="cleanupUnusedLabelsAfterDays must be a non-negative integer",
            ) from exc

    existing["config"] = config_data
    config["multiply"] = existing

    async with _ADMIN_LOCK:
        _save_yaml_config(_AUTOMATIONS_PATH, config)

    return {"saved": True, "settings": _multiplication_settings_payload(config)}

@router.get("/api/admin/stale_tasks", tags=["admin"])
async def admin_stale_tasks_settings() -> dict[str, Any]:
    _sync_api_globals(globals())
    config = _read_yaml_config(_AUTOMATIONS_PATH)
    return {"settings": _stale_tasks_settings_payload(config)}

@router.put("/api/admin/stale_tasks", tags=["admin"])
async def admin_update_stale_tasks_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    def non_negative_int(key: str) -> int:
        raw_value = payload.get(key)
        if raw_value is None:
            raise HTTPException(
                status_code=400,
                detail=f"{key} must be a non-negative integer",
            )
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"{key} must be a non-negative integer",
            ) from exc

    old_after_days = non_negative_int("oldAfterDays")
    very_old_after_days = non_negative_int("veryOldAfterDays")
    delete_after_warning_days = non_negative_int("deleteAfterWarningDays")
    warning_label = str(payload.get("warningLabel", "")).strip()
    very_old_label = str(payload.get("veryOldLabel", "")).strip()
    if not warning_label or not very_old_label:
        raise HTTPException(
            status_code=400,
            detail="warningLabel and veryOldLabel are required",
        )
    if very_old_after_days < old_after_days:
        raise HTTPException(
            status_code=400,
            detail="veryOldAfterDays must be greater than or equal to oldAfterDays",
        )

    config = _read_yaml_config(_AUTOMATIONS_PATH)
    stale_cfg = config.get("stale_tasks") or {}
    existing = OmegaConf.to_container(stale_cfg, resolve=False) if stale_cfg else {}
    if not isinstance(existing, dict):
        existing = {}
    config_data = existing.get("config") if isinstance(existing.get("config"), Mapping) else {}
    if not isinstance(config_data, Mapping):
        config_data = {}
    config_data = dict(config_data)
    config_data["old_after_days"] = old_after_days
    config_data["very_old_after_days"] = very_old_after_days
    config_data["old_label"] = warning_label
    config_data["very_old_label"] = very_old_label
    config_data["delete_after_warning_days"] = delete_after_warning_days
    existing["config"] = config_data
    if "dryRun" in payload:
        existing["dry_run"] = bool(payload.get("dryRun"))
    if "maxUpdatesPerTick" in payload:
        existing["max_updates_per_tick"] = non_negative_int("maxUpdatesPerTick")
    config["stale_tasks"] = existing

    async with _ADMIN_LOCK:
        _save_yaml_config(_AUTOMATIONS_PATH, config)

    return {"saved": True, "settings": _stale_tasks_settings_payload(config)}

@router.get("/api/admin/templates", tags=["admin"])
async def admin_templates() -> dict[str, Any]:
    _sync_api_globals(globals())
    if not _TEMPLATES_DIR.exists():
        return {"templates": [], "categories": []}
    templates: list[dict[str, Any]] = []
    categories: set[str] = set()
    for category_dir in sorted(_TEMPLATES_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        categories.add(category_dir.name)
        for file in sorted(category_dir.glob("*.yaml")):
            templates.append(_template_summary(file))
    return {"templates": templates, "categories": sorted(categories)}

@router.get("/api/admin/templates/{category}/{name}", tags=["admin"])
async def admin_template_detail(category: str, name: str) -> dict[str, Any]:
    _sync_api_globals(globals())
    safe_category = _ensure_identifier(category, label="category")
    safe_name = _ensure_identifier(name, label="template name")
    path = _template_path(safe_category, safe_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    cfg = _read_yaml_config(path)
    data = OmegaConf.to_container(cfg, resolve=False)
    if not isinstance(data, dict):
        data = {}
    template_payload = cast(Mapping[str, Any], data)
    return {
        "category": safe_category,
        "name": safe_name,
        "label": f"template-{safe_name}",
        "template": _template_to_camel(template_payload),
    }

@router.post("/api/admin/templates", tags=["admin"])
async def admin_create_template(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    category = _ensure_identifier(str(payload.get("category", "")), label="category")
    name = _ensure_identifier(str(payload.get("name", "")), label="template name")
    template = payload.get("template")
    if not isinstance(template, Mapping):
        raise HTTPException(status_code=400, detail="template must be an object")

    path = _template_path(category, name)
    if path.exists():
        raise HTTPException(status_code=409, detail="Template already exists")

    normalized = _normalize_template_node(template)
    path.parent.mkdir(parents=True, exist_ok=True)
    _save_yaml_config(path, OmegaConf.create(normalized))

    templates_cfg = _read_yaml_config(_TEMPLATES_REGISTRY_PATH)
    defaults = _load_defaults_list(templates_cfg)
    entry_key = _template_defaults_key(category, name)
    if not any(isinstance(item, Mapping) and entry_key in item for item in defaults):
        defaults.append({entry_key: name})
        templates_cfg["defaults"] = defaults

    automations_cfg = _read_yaml_config(_AUTOMATIONS_PATH)
    template_cfg = automations_cfg.get("template") or {}
    task_templates = (
        OmegaConf.to_container(template_cfg.get("task_templates"), resolve=False)
        if template_cfg
        else {}
    )
    if not isinstance(task_templates, dict):
        task_templates = {}
    task_templates[name] = f"${{{category}.{name}}}"
    template_cfg["task_templates"] = task_templates
    automations_cfg["template"] = template_cfg
    async with _ADMIN_LOCK:
        _save_yaml_config(_TEMPLATES_REGISTRY_PATH, templates_cfg)
        _save_yaml_config(_AUTOMATIONS_PATH, automations_cfg)

    return {"created": True, "category": category, "name": name}

@router.put("/api/admin/templates/{category}/{name}", tags=["admin"])
async def admin_update_template(
    category: str,
    name: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    safe_category = _ensure_identifier(category, label="category")
    safe_name = _ensure_identifier(name, label="template name")
    template = payload.get("template")
    if not isinstance(template, Mapping):
        raise HTTPException(status_code=400, detail="template must be an object")

    path = _template_path(safe_category, safe_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    normalized = _normalize_template_node(template)
    async with _ADMIN_LOCK:
        _save_yaml_config(path, OmegaConf.create(normalized))
    return {"saved": True, "category": safe_category, "name": safe_name}

@router.delete("/api/admin/templates/{category}/{name}", tags=["admin"])
async def admin_delete_template(category: str, name: str) -> dict[str, Any]:
    _sync_api_globals(globals())
    safe_category = _ensure_identifier(category, label="category")
    safe_name = _ensure_identifier(name, label="template name")
    path = _template_path(safe_category, safe_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    path.unlink()

    templates_cfg = _read_yaml_config(_TEMPLATES_REGISTRY_PATH)
    defaults = _load_defaults_list(templates_cfg)
    entry_key = _template_defaults_key(safe_category, safe_name)
    defaults = [
        item
        for item in defaults
        if not (isinstance(item, Mapping) and entry_key in item)
    ]
    templates_cfg["defaults"] = defaults

    automations_cfg = _read_yaml_config(_AUTOMATIONS_PATH)
    template_cfg = automations_cfg.get("template") or {}
    task_templates = (
        OmegaConf.to_container(template_cfg.get("task_templates"), resolve=False)
        if template_cfg
        else {}
    )
    if isinstance(task_templates, dict) and safe_name in task_templates:
        del task_templates[safe_name]
    template_cfg["task_templates"] = task_templates
    automations_cfg["template"] = template_cfg
    async with _ADMIN_LOCK:
        _save_yaml_config(_TEMPLATES_REGISTRY_PATH, templates_cfg)
        _save_yaml_config(_AUTOMATIONS_PATH, automations_cfg)

    return {"deleted": True, "category": safe_category, "name": safe_name}
