# pyright: reportUndefinedVariable=false
"""Task ingest and status update routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement


import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from todoist.web.routes.common import _sync_api_globals

router = APIRouter()

@router.get("/api/admin/task_ingest/projects", tags=["admin"])
async def admin_task_ingest_projects(refresh: bool = False) -> dict[str, Any]:
    _sync_api_globals(globals())
    try:
        projects = await asyncio.to_thread(_load_task_ingest_projects_sync, refresh)
    except Exception as exc:  # pragma: no cover - network safety
        raise HTTPException(
            status_code=500, detail=f"Failed to load projects: {type(exc).__name__}"
        ) from exc
    return {"projects": projects}

@router.post("/api/admin/task_ingest/preview", tags=["admin"])
async def admin_task_ingest_preview(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    raw_content = _task_ingest_trim_text(payload.get("rawContent"))
    if not raw_content:
        raise HTTPException(status_code=400, detail="rawContent is required")
    options = _task_ingest_options(payload)
    tasks, source = await asyncio.to_thread(
        _task_ingest_preview_sync,
        raw_content,
        max_depth=int(options["maxDepth"]),
        granularity=str(options["granularity"]),
        preference=str(options["preference"]),
        include_descriptions=bool(options["includeDescriptions"]),
    )
    if not tasks:
        raise HTTPException(status_code=400, detail="Could not derive any tasks from the pasted content.")
    return {
        "source": source,
        "tasks": tasks,
        "topLevelCount": len(tasks),
        "totalCount": _task_ingest_total_nodes(tasks),
        "maxDepth": options["maxDepth"],
        "granularity": options["granularity"],
        "preference": options["preference"],
        "includeDescriptions": options["includeDescriptions"],
    }

@router.post("/api/admin/task_ingest/create", tags=["admin"])
async def admin_task_ingest_create(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    project_id = _task_ingest_trim_text(payload.get("projectId"))
    raw_content = _task_ingest_trim_text(payload.get("rawContent"))
    tasks_payload = payload.get("tasks")
    options = _task_ingest_options(payload)
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required")
    if isinstance(tasks_payload, list):
        tasks = _task_ingest_tree_payload_with_options(
            [task for task in tasks_payload if isinstance(task, Mapping)],
            max_depth=int(options["maxDepth"]),
            include_descriptions=bool(options["includeDescriptions"]),
        )
    elif raw_content:
        tasks, _ = await asyncio.to_thread(
            _task_ingest_preview_sync,
            raw_content,
            max_depth=int(options["maxDepth"]),
            granularity=str(options["granularity"]),
            preference=str(options["preference"]),
            include_descriptions=bool(options["includeDescriptions"]),
        )
    else:
        raise HTTPException(status_code=400, detail="tasks or rawContent is required")
    if not tasks:
        raise HTTPException(status_code=400, detail="No tasks to create")
    try:
        created = await asyncio.to_thread(_task_ingest_create_sync, project_id, tasks)
    except Exception as exc:  # pragma: no cover - network safety
        raise HTTPException(
            status_code=500, detail=f"Failed to create tasks: {exc}"
        ) from exc
    return {
        "created": created,
        "createdCount": len(created),
        "topLevelCount": len(tasks),
    }

@router.get("/api/admin/status_update/projects", tags=["admin"])
async def admin_status_update_projects(refresh: bool = False) -> dict[str, Any]:
    _sync_api_globals(globals())
    try:
        projects = await asyncio.to_thread(_load_status_update_projects_sync, refresh)
    except Exception as exc:  # pragma: no cover - network safety
        raise HTTPException(
            status_code=500, detail=f"Failed to load projects: {type(exc).__name__}"
        ) from exc
    return {"projects": projects}

@router.post("/api/admin/status_update/generate", tags=["admin"])
async def admin_status_update_generate(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    raw_project_ids = payload.get("projectIds")
    if not isinstance(raw_project_ids, Sequence) or isinstance(raw_project_ids, str):
        raise HTTPException(status_code=400, detail="projectIds must be a list of strings")
    project_ids = [str(value).strip() for value in raw_project_ids if str(value).strip()]
    if not project_ids:
        raise HTTPException(status_code=400, detail="projectIds must contain at least one project id")

    beg = _status_update_parse_date(payload.get("beg"), field="beg")
    end = _status_update_parse_date(payload.get("end"), field="end")
    sync_label = _task_ingest_trim_text(payload.get("syncLabel"))
    preset = _task_ingest_trim_text(payload.get("preset"))
    await _ensure_state(refresh=False)
    dbio = _status_update_db()
    try:
        beg_dt = datetime.combine(beg, datetime.min.time())
        end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
        report = await asyncio.to_thread(
            build_status_update_report,
            dbio,
            project_ids=project_ids,
            beg=beg_dt,
            end=end_dt,
            sync_label=sync_label,
            df_activity=_state.df_activity,
            preset=preset,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - network safety
        raise HTTPException(
            status_code=500, detail=f"Failed to generate status update: {type(exc).__name__}"
        ) from exc
    selection = dict(report.get("selection") or {})
    requested_projects = list(selection.get("requestedProjects") or [])
    expanded_projects = list(selection.get("expandedProjects") or [])
    tasks = list(report.get("completedTasks") or [])

    project_payloads: list[dict[str, Any]] = []
    for project in expanded_projects:
        project_id = str(project.get("id") or "")
        project_tasks = [task for task in tasks if str(task.get("projectId") or "") == project_id]
        project_payloads.append(
            {
                "id": project_id,
                "name": project.get("name"),
                "label": project.get("label"),
                "completedCount": sum(int(task.get("completionCount") or 0) for task in project_tasks),
                "commentCount": sum(int(task.get("commentCount") or 0) for task in project_tasks),
                "storyPointCount": sum(int(task.get("storyPointCount") or 0) for task in project_tasks),
                "estimatedTaskCount": sum(1 for task in project_tasks if int(task.get("storyPoints") or 0) > 0),
                "tasks": project_tasks,
            }
        )

    selection.update(
        {
            "beg": beg.isoformat(),
            "end": end_dt.isoformat(timespec="seconds"),
            "projectIds": list(project_ids),
            "syncLabel": report.get("syncLabel") or sync_label or "Status update",
            "preset": preset or None,
        }
    )

    comment_count = sum(int(task.get("commentCount") or 0) for task in tasks)
    story_point_count = sum(int(task.get("storyPointCount") or 0) for task in tasks)
    estimated_task_count = sum(1 for task in tasks if int(task.get("storyPoints") or 0) > 0)
    report_summary = dict(report.get("summary") or {})
    report_stats = dict(report.get("stats") or {})
    response = {
        "generatedAt": report.get("generatedAt"),
        "syncLabel": report.get("syncLabel") or sync_label or "Status update",
        "range": {
            "beg": beg_dt.isoformat(timespec="seconds"),
            "end": end_dt.isoformat(timespec="seconds"),
        },
        "selection": selection,
        "summary": {
            "selectedProjectCount": int(report_summary.get("selectedProjectCount") or len(requested_projects)),
            "expandedProjectCount": int(report_summary.get("expandedProjectCount") or len(expanded_projects)),
            "completedEventCount": int(
                report_summary.get("completedEventCount") or len(report.get("completedTaskEvents") or [])
            ),
            "completedTaskCount": int(report_summary.get("completedTaskCount") or len(tasks)),
            "commentedTaskCount": int(
                report_summary.get("commentedTaskCount")
                or sum(1 for task in tasks if int(task.get("commentCount") or 0) > 0)
            ),
            "commentCount": int(report_summary.get("commentCount") or comment_count),
            "storyPointCount": int(report_summary.get("storyPointCount") or story_point_count),
            "estimatedTaskCount": int(report_summary.get("estimatedTaskCount") or estimated_task_count),
        },
        "summaryText": report.get("summaryText")
        or f"Completed {len(tasks)} tasks across {len(project_payloads)} projects, grounded by {comment_count} comments.",
        "stats": {
            "completedCount": int(report_stats.get("completedCount") or len(tasks)),
            "commentCount": int(report_stats.get("commentCount") or comment_count),
            "projectCount": int(report_stats.get("projectCount") or len(project_payloads)),
            "activityCount": int(report_stats.get("activityCount") or len(report.get("completedTaskEvents") or [])),
            "storyPointCount": int(report_stats.get("storyPointCount") or story_point_count),
            "estimatedTaskCount": int(report_stats.get("estimatedTaskCount") or estimated_task_count),
        },
        "projects": project_payloads,
        "tasks": tasks,
        "selectedProjects": requested_projects,
        "executiveSummary": report.get("executiveSummary") or [],
        "projectRollup": report.get("projectRollup") or [],
        "markdown": report.get("markdown"),
        "warnings": report.get("warnings") or [],
        "completedTasks": report.get("completedTasks") or [],
        "completedTaskEvents": report.get("completedTaskEvents") or [],
    }
    return response
