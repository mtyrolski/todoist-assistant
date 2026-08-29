from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from todoist.core.types import Project


def review_context(activity: pd.DataFrame, projects: list[Project]) -> dict[str, Any]:
    frame = activity.copy()
    frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame.loc[~frame.index.isna()]
    if frame.empty:
        return {"activity": "No cached activity is available.", "projects": []}

    end = frame.index.max().normalize() + timedelta(days=1)
    current_start = end - timedelta(days=7)
    previous_start = current_start - timedelta(days=7)
    completed = frame.loc[frame["event_type"] == "completed"]
    current = completed.loc[(completed.index >= current_start) & (completed.index < end)]
    previous = completed.loc[(completed.index >= previous_start) & (completed.index < current_start)]
    current_by_project = _project_counts(current)
    previous_by_project = _project_counts(previous)
    weekly_history = (
        completed.groupby(completed.index.to_period("W-MON")).size().tail(8)
    )
    density = current.groupby(current.index.day_name()).size().reindex(
        [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ],
        fill_value=0,
    )
    hours = current.groupby(current.index.hour).size().sort_values(ascending=False).head(3)
    return {
        "period": {
            "start": current_start.date().isoformat(),
            "end": (end - timedelta(days=1)).date().isoformat(),
        },
        "completions": {
            "current": int(len(current)),
            "previous": int(len(previous)),
        },
        "project_completions": {
            "current": current_by_project,
            "previous": previous_by_project,
        },
        "weekly_completion_history": [
            {"week": str(week.start_time.date()), "completed": int(count)}
            for week, count in weekly_history.items()
        ],
        "workday_density": {
            str(day): int(count) for day, count in density.items()
        },
        "peak_completion_hours": [
            {"hour": int(hour), "count": int(count)} for hour, count in hours.items()
        ],
        "projects": _project_snapshots(projects),
    }


def _project_counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty or "root_project_name" not in frame:
        return {}
    counts = (
        frame["root_project_name"]
        .fillna("Unassigned")
        .astype(str)
        .value_counts()
        .head(10)
    )
    return {name: int(count) for name, count in counts.items()}


def _project_snapshots(projects: list[Project]) -> list[dict[str, Any]]:
    names = {str(project.id): project.project_entry.name for project in projects}
    return [
        _project_snapshot(project, names)
        for project in projects
        if not project.is_archived
    ]


def _project_snapshot(project: Project, names: dict[str, str]) -> dict[str, Any]:
    entry = project.project_entry
    parent_id = entry.parent_id or entry.v2_parent_id
    active_tasks = sum(
        not task.task_entry.checked and not task.task_entry.is_deleted
        for task in project.tasks
    )
    return {
        "id": str(project.id),
        "name": entry.name,
        "parent_id": parent_id,
        "parent_name": names.get(str(parent_id)),
        "active_tasks": active_tasks,
    }
