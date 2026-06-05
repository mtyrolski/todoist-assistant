"""Create nested Todoist task trees from JSON payloads."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from loguru import logger

from todoist.database.base import Database


TASK_INSERT_FIELDS = {
    "content",
    "description",
    "section_id",
    "order",
    "labels",
    "priority",
    "due_string",
    "due_date",
    "due_datetime",
    "due_lang",
    "assignee_id",
    "duration",
    "duration_unit",
    "deadline_date",
    "deadline_lang",
}

CAMEL_TO_SNAKE_FIELDS = {
    "sectionId": "section_id",
    "dueString": "due_string",
    "dueDate": "due_date",
    "dueDatetime": "due_datetime",
    "dueLang": "due_lang",
    "assigneeId": "assignee_id",
    "durationUnit": "duration_unit",
    "deadlineDate": "deadline_date",
    "deadlineLang": "deadline_lang",
}


@dataclass(frozen=True)
class TaskTreeNode:
    """Validated node accepted by the task tree importer."""

    content: str
    description: str | None = None
    labels: list[str] = field(default_factory=list)
    priority: int | None = None
    due_string: str | None = None
    due_date: str | None = None
    due_datetime: str | None = None
    due_lang: str | None = None
    section_id: str | None = None
    order: int | None = None
    assignee_id: int | str | None = None
    duration: int | None = None
    duration_unit: str | None = None
    deadline_date: str | None = None
    deadline_lang: str | None = None
    children: list["TaskTreeNode"] = field(default_factory=list)


@dataclass(frozen=True)
class TaskTreePayload:
    """Validated tree import payload."""

    tasks: list[TaskTreeNode]
    project_id: str | None = None
    parent_id: str | None = None
    labels: list[str] = field(default_factory=list)


def load_task_tree_json(source: str) -> object:
    """Load a task tree JSON document from inline JSON, stdin text, or a file reference."""

    raw = source.strip()
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    return json.loads(raw)


def normalize_task_tree_payload(
    raw: object, *, project_id: str | None = None
) -> TaskTreePayload:
    """Validate and normalize a JSON task tree payload."""

    if isinstance(raw, list):
        payload = {"tasks": raw}
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        raise ValueError("Payload must be a JSON object or an array of task nodes.")

    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError("Payload must contain a 'tasks' array.")

    payload_project_id = _optional_text(
        payload.get("projectId") or payload.get("project_id")
    )
    effective_project_id = project_id or payload_project_id
    parent_id = _optional_text(payload.get("parentId") or payload.get("parent_id"))
    labels = _normalize_labels(payload.get("labels"))
    tasks = [
        _normalize_node(item, path=f"tasks[{index}]")
        for index, item in enumerate(raw_tasks)
    ]
    if not tasks:
        raise ValueError("Payload must contain at least one task.")

    return TaskTreePayload(
        tasks=tasks,
        project_id=effective_project_id,
        parent_id=parent_id,
        labels=labels,
    )


def render_task_tree_plan(payload: TaskTreePayload) -> str:
    """Render a readable creation plan for dry-runs and logs."""

    lines: list[str] = []
    for index, task in enumerate(payload.tasks, start=1):
        _append_plan_lines(
            lines, task, prefix=f"{index}.", inherited_labels=payload.labels
        )
    return "\n".join(lines)


def create_task_tree(
    payload: TaskTreePayload,
    *,
    db: Database,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Create the task tree sequentially so children use the created parent IDs."""

    created: list[dict[str, Any]] = []
    if dry_run:
        logger.info("Dry-run task tree import:\n{}", render_task_tree_plan(payload))
        return created

    for task in payload.tasks:
        _create_node(
            db,
            payload=payload,
            node=task,
            inherited_labels=payload.labels,
            parent_id=payload.parent_id,
            created=created,
        )
    return created


def create_task_tree_from_json(
    raw: object,
    *,
    dotenv_path: str,
    project_id: str | None = None,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Validate JSON and create the described task tree."""

    payload = normalize_task_tree_payload(raw, project_id=project_id)
    db = Database(dotenv_path)
    return create_task_tree(payload, db=db, dry_run=dry_run)


def _create_node(
    db: Database,
    *,
    payload: TaskTreePayload,
    node: TaskTreeNode,
    inherited_labels: Sequence[str],
    parent_id: str | None,
    created: list[dict[str, Any]],
) -> None:
    labels = _merge_labels(inherited_labels, node.labels)
    insert_payload = _node_insert_payload(node, labels=labels)
    if parent_id:
        insert_payload["parent_id"] = parent_id
    elif payload.project_id:
        insert_payload["project_id"] = payload.project_id
    else:
        raise ValueError(
            "projectId is required for top-level tasks unless parentId is provided."
        )

    logger.info(
        "Creating Todoist task '{}' under {}.",
        node.content,
        f"parent {parent_id}" if parent_id else f"project {payload.project_id}",
    )
    result = db.insert_task(**insert_payload)
    task_id = _optional_text(result.get("id"))
    if not task_id:
        raise RuntimeError(f"Failed to create task: {node.content}")

    created.append(
        {
            "id": task_id,
            "content": node.content,
            "parentId": parent_id,
            "projectId": payload.project_id,
        }
    )
    for child in node.children:
        _create_node(
            db,
            payload=payload,
            node=child,
            inherited_labels=labels,
            parent_id=task_id,
            created=created,
        )


def _normalize_node(raw: object, *, path: str) -> TaskTreeNode:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must be an object.")
    item = _normalize_keys(raw)
    content = _optional_text(item.get("content"))
    if not content:
        raise ValueError(f"{path}.content is required.")

    children_raw = item.get("children", [])
    if children_raw is None:
        children_raw = []
    if not isinstance(children_raw, list):
        raise ValueError(f"{path}.children must be an array when provided.")

    labels = _normalize_labels(item.get("labels"))
    priority = _optional_int(item.get("priority"), field_name=f"{path}.priority")
    if priority is not None and priority not in {1, 2, 3, 4}:
        raise ValueError(f"{path}.priority must be between 1 and 4.")

    duration = _optional_int(item.get("duration"), field_name=f"{path}.duration")
    order = _optional_int(item.get("order"), field_name=f"{path}.order")

    return TaskTreeNode(
        content=content,
        description=_optional_text(item.get("description")),
        labels=labels,
        priority=priority,
        due_string=_optional_text(item.get("due_string")),
        due_date=_optional_text(item.get("due_date")),
        due_datetime=_optional_text(item.get("due_datetime")),
        due_lang=_optional_text(item.get("due_lang")),
        section_id=_optional_text(item.get("section_id")),
        order=order,
        assignee_id=_optional_text(item.get("assignee_id")),
        duration=duration,
        duration_unit=_optional_text(item.get("duration_unit")),
        deadline_date=_optional_text(item.get("deadline_date")),
        deadline_lang=_optional_text(item.get("deadline_lang")),
        children=[
            _normalize_node(child, path=f"{path}.children[{index}]")
            for index, child in enumerate(children_raw)
        ],
    )


def _node_insert_payload(
    node: TaskTreeNode, *, labels: Sequence[str]
) -> dict[str, Any]:
    payload = {
        field_name: getattr(node, field_name)
        for field_name in TASK_INSERT_FIELDS
        if hasattr(node, field_name) and getattr(node, field_name) is not None
    }
    if labels:
        payload["labels"] = list(labels)
    return payload


def _append_plan_lines(
    lines: list[str],
    node: TaskTreeNode,
    *,
    prefix: str,
    inherited_labels: Sequence[str],
) -> None:
    labels = _merge_labels(inherited_labels, node.labels)
    suffix = f" labels={labels}" if labels else ""
    due = node.due_string or node.due_date or node.due_datetime
    if due:
        suffix += f" due={due!r}"
    lines.append(f"{prefix} {node.content}{suffix}")
    for index, child in enumerate(node.children, start=1):
        _append_plan_lines(
            lines,
            child,
            prefix=f"{prefix}{index}.",
            inherited_labels=labels,
        )


def _normalize_keys(raw: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        normalized[CAMEL_TO_SNAKE_FIELDS.get(str(key), str(key))] = value
    return normalized


def _normalize_labels(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("labels must be an array of strings.")
    labels: list[str] = []
    for label in value:
        text = _optional_text(label)
        if text:
            labels.append(text.removeprefix("@"))
    return labels


def _merge_labels(*groups: Sequence[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for label in group:
            normalized = label.removeprefix("@").strip()
            if normalized and normalized not in seen:
                merged.append(normalized)
                seen.add(normalized)
    return merged


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object, *, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer.")
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an integer.")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
