"""Reusable factories for creating Todoist domain objects in tests."""

from typing import Any

from todoist.types import Project, ProjectEntry, Task, TaskEntry

_DEFAULT_TIMESTAMP = "2024-01-01T00:00:00Z"


def make_project_entry(
    *,
    project_id: str = "project123",
    name: str = "Test Project",
    color: str = "blue",
    **overrides: Any,
) -> ProjectEntry:
    payload: dict[str, Any] = {
        "id": project_id,
        "name": name,
        "color": color,
        "parent_id": None,
        "child_order": 1,
        "view_style": "list",
        "is_favorite": False,
        "is_archived": False,
        "is_deleted": False,
        "is_frozen": False,
        "can_assign_tasks": True,
        "shared": False,
        "created_at": _DEFAULT_TIMESTAMP,
        "updated_at": _DEFAULT_TIMESTAMP,
        "v2_id": f"v2_{project_id}",
        "v2_parent_id": None,
        "sync_id": None,
        "collapsed": False,
    }
    payload.update(overrides)
    return ProjectEntry(**payload)


def make_task_entry(
    task_id: str = "task123",
    *,
    content: str | None = None,
    project_id: str = "project123",
    section_id: str = "section123",
    priority: int = 1,
    labels: list[str] | None = None,
    due: str | None | dict[str, Any] = None,
    **overrides: Any,
) -> TaskEntry:
    payload: dict[str, Any] = {
        "id": task_id,
        "is_deleted": False,
        "added_at": _DEFAULT_TIMESTAMP,
        "child_order": 1,
        "responsible_uid": None,
        "content": content or f"Task {task_id}",
        "description": "",
        "user_id": "user123",
        "assigned_by_uid": "user123",
        "project_id": project_id,
        "section_id": section_id,
        "sync_id": None,
        "collapsed": False,
        "due": due,
        "parent_id": None,
        "labels": labels or [],
        "checked": False,
        "priority": priority,
        "note_count": 0,
        "added_by_uid": "user123",
        "completed_at": None,
        "deadline": None,
        "duration": None,
        "updated_at": _DEFAULT_TIMESTAMP,
        "v2_id": f"v2_{task_id}",
        "v2_parent_id": None,
        "v2_project_id": f"v2_{project_id}",
        "v2_section_id": f"v2_{section_id}",
        "day_order": None,
    }
    payload.update(overrides)
    return TaskEntry(**payload)


def make_task(
    task_id: str = "task123",
    *,
    task_entry: TaskEntry | None = None,
    **task_entry_overrides: Any,
) -> Task:
    entry = task_entry or make_task_entry(task_id=task_id, **task_entry_overrides)
    return Task(id=task_id, task_entry=entry)


def make_project(
    *,
    project_id: str = "project123",
    project_entry: ProjectEntry | None = None,
    tasks: list[Task] | None = None,
    is_archived: bool = False,
    **project_entry_overrides: Any,
) -> Project:
    entry = project_entry or make_project_entry(project_id=project_id, **project_entry_overrides)
    return Project(
        id=project_id,
        project_entry=entry,
        tasks=list(tasks or []),
        is_archived=is_archived,
    )
