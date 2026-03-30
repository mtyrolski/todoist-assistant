from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Protocol, Sequence, cast

import pandas as pd
from loguru import logger

from todoist.database.base import Database
from todoist.database.dataframe import load_activity_data
from todoist.types import Project


class StatusUpdateDatabase(Protocol):
    def fetch_projects(self, include_tasks: bool = False) -> Sequence[Project]: ...

    def fetch_archived_projects(self) -> Sequence[Project]: ...

    def fetch_task_comments(self, task_id: str) -> Sequence[dict[str, Any]]: ...


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _truncate(text: str, *, max_len: int = 180) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[: max_len - 1].rstrip()}…"


def _project_path(project: Project, projects_by_id: dict[str, Project]) -> list[str]:
    names: list[str] = []
    current: Project | None = project
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        names.append(current.project_entry.name)
        parent_id = current.project_entry.parent_id
        current = projects_by_id.get(str(parent_id)) if parent_id else None
    return list(reversed(names))


def status_update_project_payload(projects: Sequence[Project]) -> list[dict[str, Any]]:
    by_id = {project.id: project for project in projects}
    payload = []
    for project in projects:
        path = _project_path(project, by_id)
        payload.append(
            {
                "id": project.id,
                "name": project.project_entry.name,
                "label": " / ".join(path),
                "parentId": project.project_entry.parent_id,
            }
        )
    payload.sort(key=lambda item: str(item["label"]).lower())
    return payload


def load_status_update_projects(dbio: StatusUpdateDatabase) -> list[dict[str, Any]]:
    projects = list(dbio.fetch_projects(include_tasks=False)) + list(dbio.fetch_archived_projects())
    return status_update_project_payload(projects)


def _build_project_index(projects: Sequence[Project]) -> tuple[dict[str, Project], dict[str, list[str]]]:
    project_index = {project.id: project for project in projects}
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for project in projects:
        parent_id = project.project_entry.parent_id
        if parent_id is None:
            continue
        parent_key = str(parent_id)
        if parent_key in project_index:
            children_by_parent[parent_key].append(project.id)
    for child_ids in children_by_parent.values():
        child_ids.sort(key=lambda project_id: project_index[project_id].project_entry.name.lower())
    return project_index, children_by_parent


def _expand_project_scope(
    selected_project_ids: Sequence[str],
    *,
    project_index: dict[str, Project],
    children_by_parent: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    requested: list[str] = []
    missing: list[str] = []
    seen_requested: set[str] = set()
    for project_id in selected_project_ids:
        project_key = str(project_id)
        if project_key in seen_requested:
            continue
        seen_requested.add(project_key)
        if project_key in project_index:
            requested.append(project_key)
        else:
            missing.append(project_key)

    expanded: list[str] = []
    seen: set[str] = set()

    def visit(project_id: str) -> None:
        stack = [project_id]
        while stack:
            current = stack.pop()
            if current in seen or current not in project_index:
                continue
            seen.add(current)
            expanded.append(current)
            child_ids = list(children_by_parent.get(current, []))
            for child_id in reversed(child_ids):
                stack.append(child_id)

    for project_id in requested:
        visit(project_id)

    return expanded, missing


def _normalize_dataframe(df_activity: pd.DataFrame) -> pd.DataFrame:
    normalized = df_activity.copy()
    normalized.index = pd.to_datetime(normalized.index)
    return normalized


def _filter_completed_tasks(
    df_activity: pd.DataFrame,
    *,
    beg: datetime,
    end: datetime,
    project_scope_ids: Sequence[str],
) -> pd.DataFrame:
    if df_activity.empty or not project_scope_ids:
        return df_activity.iloc[0:0].copy()

    normalized = _normalize_dataframe(df_activity)
    if "type" not in normalized.columns or "parent_project_id" not in normalized.columns:
        raise RuntimeError("Activity dataframe is missing required columns")

    project_scope = {str(project_id) for project_id in project_scope_ids}
    mask = (
        (normalized.index >= pd.Timestamp(beg))
        & (normalized.index < pd.Timestamp(end))
        & (cast(pd.Series, normalized["type"]).astype(str) == "completed")
        & (cast(pd.Series, normalized["parent_project_id"]).astype(str).isin(project_scope))
    )
    return cast(pd.DataFrame, normalized[mask].copy())


def _get_project_title(project: Project, project_index: dict[str, Project]) -> str:
    path = _project_path(project, project_index)
    return " / ".join(path)


def _get_project_name(project_id: str, project_index: dict[str, Project]) -> str:
    project = project_index.get(project_id)
    if project is None:
        return project_id or "(unknown)"
    return project.project_entry.name


def _build_comment_summary(
    comments: Sequence[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for comment in comments:
        if len(summary) >= limit:
            break
        content = _clean_text(comment.get("content") or comment.get("text") or comment.get("body"))
        if not content:
            continue
        summary.append(
            {
                "id": str(comment.get("id") or ""),
                "content": content,
                "snippet": _truncate(content),
                "createdAt": _clean_text(comment.get("posted_at") or comment.get("created_at") or comment.get("createdAt"))
                or None,
            }
        )
    return summary


def _format_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    text = _clean_text(value)
    return text or None


def build_status_update_report(
    dbio: StatusUpdateDatabase,
    *,
    project_ids: Sequence[str],
    beg: datetime,
    end: datetime,
    sync_label: str | None = None,
    comment_limit_per_task: int = 3,
    comment_fetcher: Callable[[str], Sequence[dict[str, Any]]] | None = None,
    df_activity: pd.DataFrame | None = None,
    preset: str | None = None,
) -> dict[str, Any]:
    if beg >= end:
        raise ValueError("beg must be before end")

    projects = list(dbio.fetch_projects(include_tasks=False)) + list(dbio.fetch_archived_projects())
    project_index, children_by_parent = _build_project_index(projects)
    expanded_ids, missing_project_ids = _expand_project_scope(
        project_ids,
        project_index=project_index,
        children_by_parent=children_by_parent,
    )
    if not expanded_ids:
        raise ValueError("project_ids must include at least one known project")

    activity_df = load_activity_data(cast(Database, dbio)) if df_activity is None else df_activity
    completed_df = _filter_completed_tasks(
        activity_df,
        beg=beg,
        end=end,
        project_scope_ids=expanded_ids,
    )

    selected_projects = [
        project_index[project_id]
        for project_id in dict.fromkeys(str(project_id) for project_id in project_ids)
        if project_id in project_index
    ]
    expanded_projects = [project_index[project_id] for project_id in expanded_ids]
    requested_project_payload = status_update_project_payload(selected_projects)
    expanded_project_payload = status_update_project_payload(expanded_projects)

    completion_rows: list[dict[str, Any]] = []
    tasks_by_id: dict[str, dict[str, Any]] = {}
    if not completed_df.empty:
        ordered_rows = completed_df.sort_index()
        for _, row in ordered_rows.iterrows():
            task_id = _clean_text(row.get("task_id"))
            if not task_id:
                continue
            project_id = _clean_text(row.get("parent_project_id"))
            project_name = _clean_text(row.get("parent_project_name")) or _get_project_name(project_id, project_index)
            completed_at = _format_iso_date(row.name)
            task_record = tasks_by_id.setdefault(
                task_id,
                {
                    "taskId": task_id,
                    "content": _clean_text(row.get("title")) or "(untitled task)",
                    "projectId": project_id or None,
                    "projectName": project_name or "(unknown)",
                    "projectLabel": _get_project_title(project_index[project_id], project_index)
                    if project_id in project_index
                    else project_name or "(unknown)",
                    "rootProjectId": _clean_text(row.get("root_project_id")) or None,
                    "rootProjectName": _clean_text(row.get("root_project_name")) or None,
                    "completedAt": None,
                    "completionHistory": [],
                    "completionCount": 0,
                    "comments": [],
                    "commentCount": 0,
                },
            )
            task_record["completionCount"] += 1
            if completed_at:
                task_record["completionHistory"].append(completed_at)
                task_record["completedAt"] = completed_at
            completion_rows.append(
                {
                    "taskId": task_id,
                    "projectId": project_id or None,
                    "projectName": project_name or "(unknown)",
                    "completedAt": completed_at,
                }
            )

    warnings: list[str] = []
    comment_fetcher = comment_fetcher or dbio.fetch_task_comments
    for task_id, task_record in tasks_by_id.items():
        try:
            raw_comments = list(comment_fetcher(task_id))
        except Exception as exc:  # pragma: no cover - network and API safety
            logger.warning("Failed to load comments for task {}: {}", task_id, exc)
            warnings.append(f"Comments unavailable for task {task_id}: {type(exc).__name__}")
            raw_comments = []
        comments = _build_comment_summary(raw_comments, limit=comment_limit_per_task)
        task_record["comments"] = comments
        task_record["commentCount"] = len(raw_comments)

    tasks = sorted(
        tasks_by_id.values(),
        key=lambda item: (
            -int(item["completionCount"]),
            str(item["projectLabel"]).lower(),
            str(item["content"]).lower(),
            str(item["taskId"]),
        ),
    )

    grouped_tasks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped_tasks[str(task["projectId"] or "")].append(task)

    for task_list in grouped_tasks.values():
        task_list.sort(
            key=lambda item: (
                -int(item["completionCount"]),
                -len(item["completionHistory"]),
                str(item["content"]).lower(),
                str(item["taskId"]),
            )
        )

    total_completion_events = len(completion_rows)
    total_unique_tasks = len(tasks)
    total_commented_tasks = sum(1 for item in tasks if int(item["commentCount"]) > 0)
    total_comments_loaded = sum(int(item["commentCount"]) for item in tasks)

    report_label = sync_label or "Status update"
    period_beg = beg.isoformat(timespec="seconds")
    period_end = end.isoformat(timespec="seconds")

    markdown_lines = [
        f"# {report_label}",
        "",
        f"- Range: {period_beg} to {period_end}",
        f"- Selected projects: {len(selected_projects)}",
        f"- Expanded project scope: {len(expanded_projects)}",
        f"- Completed task events: {total_completion_events}",
        f"- Unique completed tasks: {total_unique_tasks}",
        f"- Tasks with comments: {total_commented_tasks}",
    ]
    if missing_project_ids:
        markdown_lines.append(f"- Missing project ids ignored: {', '.join(sorted(missing_project_ids))}")

    markdown_lines.extend(["", "## Accomplishments"])
    if not tasks:
        markdown_lines.extend(["No completed tasks were found for the selected projects and range."])
    else:
        for project in expanded_projects:
            project_tasks = grouped_tasks.get(project.id)
            if not project_tasks:
                continue
            markdown_lines.extend(["", f"### {_get_project_title(project, project_index)}"])
            for task in project_tasks:
                completion_dates = ", ".join(str(value) for value in task["completionHistory"])
                markdown_lines.append(
                    f"- {task['content']} ({int(task['completionCount'])} completion"
                    f"{'s' if int(task['completionCount']) != 1 else ''})"
                )
                markdown_lines.append(f"  - Completed at: {completion_dates}")
                if task["comments"]:
                    markdown_lines.append("  - Comments:")
                    for comment in task["comments"]:
                        markdown_lines.append(f"    - {comment['snippet']}")
                else:
                    markdown_lines.append("  - Comments: none")

    stats = {
        "completedCount": total_unique_tasks,
        "commentCount": total_comments_loaded,
        "projectCount": len(expanded_projects),
        "activityCount": total_completion_events,
    }
    summary_text = (
        f"Completed {total_unique_tasks} task{'s' if total_unique_tasks != 1 else ''} "
        f"across {len(expanded_projects)} project{'s' if len(expanded_projects) != 1 else ''}"
    )
    if total_comments_loaded:
        summary_text += f", grounded by {total_comments_loaded} comment{'s' if total_comments_loaded != 1 else ''}."
    else:
        summary_text += "."

    return {
        "title": report_label,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "syncLabel": report_label,
        "range": {
            "beg": period_beg,
            "end": period_end,
        },
        "selection": {
            "requestedProjectIds": list(dict.fromkeys(str(project_id) for project_id in project_ids)),
            "requestedProjects": requested_project_payload,
            "expandedProjectIds": expanded_ids,
            "expandedProjects": expanded_project_payload,
            "syncLabel": report_label,
            "preset": _clean_text(preset) or None,
        },
        "summary": {
            "selectedProjectCount": len(selected_projects),
            "expandedProjectCount": len(expanded_projects),
            "completedEventCount": total_completion_events,
            "completedTaskCount": total_unique_tasks,
            "commentedTaskCount": total_commented_tasks,
            "commentCount": total_comments_loaded,
        },
        "summaryText": summary_text,
        "stats": stats,
        "selectedProjects": requested_project_payload,
        "completedTasks": tasks,
        "tasks": tasks,
        "completedTaskEvents": completion_rows,
        "markdown": "\n".join(markdown_lines).strip(),
        "warnings": warnings,
    }
