
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from typing import Any

from loguru import logger

from todoist.llm.llm_utils import (
    TaskFetcher,
    _build_ancestor_context,
    _get_parent_id,
    _merge_description_with_context,
    _render_ancestor_context,
)
from todoist.llm.types import MessageRole
from todoist.types import Task


@dataclass(frozen=True)
class BreakdownCandidate:
    task: Task
    label: str
    variant: str
    depth: int
    source: str


@dataclass
class CandidateSelection:
    candidates: list[BreakdownCandidate]
    queued_ids: set[str]
    drop_queue_ids: set[str]


@dataclass(frozen=True)
class PreparedBreakdownRequest:
    task: Task
    label: str
    variant_key: str
    variant_cfg: dict[str, Any]
    depth: int
    source: str
    max_depth: int
    max_children: int
    max_total_tasks: int
    queue_depth_limit: int
    messages: list[dict[str, str]]


def prepare_breakdown_request(
    *,
    automation: Any,
    item: BreakdownCandidate,
    tasks_by_id: Mapping[str, Task],
    fetch_task: TaskFetcher,
) -> PreparedBreakdownRequest:
    task = item.task
    label = item.label
    variant_key = item.variant
    depth = item.depth
    source = item.source

    variant_cfg = automation.variants.get(variant_key)
    if variant_cfg is None:
        variant_key, variant_cfg = automation.resolve_variant(label)
    resolved_variant_cfg = dict(variant_cfg)
    max_depth = int(resolved_variant_cfg.get("max_depth", automation.max_depth))
    max_children = int(resolved_variant_cfg.get("max_children", automation.max_children))
    max_total_tasks = int(resolved_variant_cfg.get("max_total_tasks", automation.max_total_tasks))
    queue_depth_limit = int(resolved_variant_cfg.get("queue_depth", automation.max_queue_depth))
    instruction = resolved_variant_cfg.get("instruction")
    if queue_depth_limit > 0:
        max_allowed = max(1, queue_depth_limit - depth + 1)
        max_depth = min(max_depth, max_allowed)

    system_prompt = automation.build_system_prompt(
        max_depth=max_depth,
        max_children=max_children,
        instruction=instruction,
    )
    messages = build_messages(
        task=task,
        tasks_by_id=tasks_by_id,
        fetch_task=fetch_task,
        system_prompt=system_prompt,
        variant_key=variant_key,
        max_depth=max_depth,
        max_children=max_children,
    )
    return PreparedBreakdownRequest(
        task=task,
        label=label,
        variant_key=variant_key,
        variant_cfg=resolved_variant_cfg,
        depth=depth,
        source=source,
        max_depth=max_depth,
        max_children=max_children,
        max_total_tasks=max_total_tasks,
        queue_depth_limit=queue_depth_limit,
        messages=messages,
    )


def collect_candidates(
    *,
    automation: Any,
    all_tasks: list[Task],
    tasks_by_id: dict[str, Task],
    children_by_parent: dict[str, list[Task]],
    queue_items: list[dict[str, Any]],
    processed_ids: set[str],
    fetch_task: TaskFetcher,
) -> CandidateSelection:
    queued_ids = {item["task_id"] for item in queue_items}
    drop_queue_ids: set[str] = set()
    candidates: list[BreakdownCandidate] = []

    for item in queue_items:
        task_id = item["task_id"]
        task = tasks_by_id.get(task_id) or fetch_task(task_id, False)
        if task is None:
            drop_queue_ids.add(task_id)
            continue
        if not automation.allow_existing_children and children_by_parent.get(task.id):
            logger.info("Skipping queued task {} (already has children)", task.id)
            drop_queue_ids.add(task_id)
            continue
        if task.id in processed_ids:
            drop_queue_ids.add(task_id)
            continue
        candidates.append(
            BreakdownCandidate(
                task=task,
                label=item["label"],
                variant=item["variant"],
                depth=item["depth"],
                source="queue",
            )
        )

    queued_ids -= drop_queue_ids
    for task in all_tasks:
        if task.id in queued_ids:
            continue
        llm_label = find_llm_label(task.task_entry.labels, automation.label_prefix_lower)
        if llm_label is None:
            continue
        if not automation.allow_existing_children and children_by_parent.get(task.id):
            logger.info("Skipping task {} (already has children)", task.id)
            continue
        if task.id in processed_ids:
            continue
        variant_key, _ = automation.resolve_variant(llm_label)
        candidates.append(
            BreakdownCandidate(
                task=task,
                label=llm_label,
                variant=variant_key,
                depth=1,
                source="label",
            )
        )

    return CandidateSelection(
        candidates=candidates,
        queued_ids=queued_ids,
        drop_queue_ids=drop_queue_ids,
    )


def build_messages(
    *,
    task: Task,
    tasks_by_id: Mapping[str, Task],
    fetch_task: TaskFetcher,
    system_prompt: str,
    variant_key: str,
    max_depth: int,
    max_children: int,
) -> list[dict[str, str]]:
    ancestor_context = _build_ancestor_context(task, tasks_by_id, fetch_task)
    ancestor_summary = _render_ancestor_context(ancestor_context)
    task_description = _merge_description_with_context(
        task.task_entry.description,
        ancestor_summary,
    )
    payload: dict[str, object] = {
        "task": {
            "content": task.task_entry.content,
            "description": task_description,
        },
        "ancestors": ancestor_context,
        "variant": variant_key,
        "constraints": {
            "max_depth": max_depth,
            "max_children": max_children,
        },
    }
    if ancestor_summary:
        payload["ancestor_context"] = ancestor_summary

    return [
        {"role": MessageRole.SYSTEM, "content": system_prompt},
        {"role": MessageRole.USER, "content": json.dumps(payload, ensure_ascii=False)},
    ]


def build_children_by_parent(tasks: Iterable[Task]) -> dict[str, list[Task]]:
    children_by_parent: dict[str, list[Task]] = {}
    for task in tasks:
        parent_id = _get_parent_id(task)
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(task)
    return children_by_parent


def build_task_lookup(tasks: Iterable[Task]) -> dict[str, Task]:
    return {str(task.id): task for task in tasks}


def find_llm_label(labels: Iterable[str], prefix_lower: str) -> str | None:
    for label in labels:
        if label.lower().startswith(prefix_lower):
            return label
    return None
