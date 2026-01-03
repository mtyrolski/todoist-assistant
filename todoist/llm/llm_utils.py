from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from loguru import logger

from todoist.types import Task


# === LLM UTILS ===============================================================

TaskFetcher: TypeAlias = Callable[[str, bool], Task | None]


@dataclass
class _AncestorTaskEntry:
    content: str
    description: str
    project_id: str = ""
    labels: list[str] = field(default_factory=list)
    parent_id: str | None = None
    v2_parent_id: str | None = None
    v2_id: str | None = None


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _get_parent_id(task: Task) -> str | None:
    parent_id = task.task_entry.parent_id or task.task_entry.v2_parent_id
    if parent_id is None:
        return None
    return str(parent_id)


def _task_from_api_payload(payload: Mapping[str, Any] | None) -> Task | None:
    if not isinstance(payload, Mapping):
        return None
    task_id = payload.get("id")
    if task_id is None:
        return None
    content = _sanitize_text(payload.get("content")) or ""
    description = _sanitize_text(payload.get("description")) or ""
    project_id = _sanitize_text(payload.get("project_id")) or ""
    labels_raw = payload.get("labels")
    labels: list[str] = []
    if isinstance(labels_raw, list):
        labels = [str(label) for label in labels_raw if label is not None]
    parent_id = payload.get("parent_id")
    v2_parent_id = payload.get("v2_parent_id")
    v2_id = payload.get("v2_id")
    entry = _AncestorTaskEntry(
        content=content,
        description=description,
        project_id=project_id,
        labels=labels,
        parent_id=str(parent_id) if parent_id is not None else None,
        v2_parent_id=str(v2_parent_id) if v2_parent_id is not None else None,
        v2_id=str(v2_id) if v2_id is not None else None,
    )
    return Task(id=str(task_id), task_entry=entry)


def _render_ancestor_context(ancestors: Iterable[Mapping[str, str | None]]) -> str | None:
    parts: list[str] = []
    for ancestor in ancestors:
        content = _sanitize_text(ancestor.get("content"))
        description = _sanitize_text(ancestor.get("description"))
        if content and description:
            parts.append(f"{content} ({description})")
        elif content:
            parts.append(content)
        elif description:
            parts.append(description)
    return " > ".join(parts) if parts else None


def _merge_description_with_context(description: str | None, context: str | None) -> str | None:
    description = _sanitize_text(description)
    context = _sanitize_text(context)
    if not context:
        return description
    if not description:
        return f"Context: {context}"
    return f"{description}\nContext: {context}"


def _build_ancestor_context(
    task: Task,
    tasks_by_id: Mapping[str, Task],
    fetch_task: TaskFetcher | None = None,
) -> list[dict[str, str | None]]:
    ancestors: list[dict[str, str | None]] = []
    seen: set[str] = set()
    parent_id = _get_parent_id(task)
    while parent_id:
        if parent_id in seen:
            logger.warning("Detected cycle in task ancestry for task {}", task.id)
            break
        seen.add(parent_id)
        parent = tasks_by_id.get(parent_id)
        if parent is None and fetch_task is not None:
            parent = fetch_task(parent_id, False)
        if parent is None:
            break
        if fetch_task is not None and not _sanitize_text(parent.task_entry.description):
            refreshed = fetch_task(parent_id, True)
            if refreshed is not None:
                parent = refreshed
        ancestors.append(
            {
                "content": parent.task_entry.content,
                "description": parent.task_entry.description,
            }
        )
        parent_id = _get_parent_id(parent)
    ancestors.reverse()
    return ancestors
