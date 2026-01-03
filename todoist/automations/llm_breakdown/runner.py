from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger

from todoist.database.base import Database
from todoist.llm.llm_utils import (
    TaskFetcher,
    _build_ancestor_context,
    _get_parent_id,
    _merge_description_with_context,
    _render_ancestor_context,
    _task_from_api_payload,
)
from todoist.llm.types import MessageRole
from todoist.types import Task

from .models import (
    CurrentKey,
    ProgressKey,
    ProgressStatus,
    QueueContext,
    QueueItem,
    TaskBreakdown,
)


# === LLM BREAKDOWN RUNNER ====================================================


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


def run_breakdown(automation: Any, db: Database) -> None:
    logger.info("Running LLM Breakdown automation")
    projects = db.fetch_projects(include_tasks=True)
    all_tasks: list[Task] = [task for project in projects for task in project.tasks]
    logger.debug("Found {} tasks in total", len(all_tasks))

    children_by_parent = build_children_by_parent(all_tasks)
    tasks_by_id = build_task_lookup(all_tasks)
    fetched_tasks: dict[str, Task] = {}
    now = automation._now_iso()

    def fetch_task(task_id: str, refresh: bool = False) -> Task | None:
        cached = tasks_by_id.get(task_id) or fetched_tasks.get(task_id)
        if cached is not None and not refresh:
            return cached
        try:
            payload = db.fetch_task_by_id(task_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to fetch task {} for context: {}", task_id, exc)
            return cached
        task_obj = _task_from_api_payload(payload)
        if task_obj is None:
            return cached
        task_id_str = str(task_obj.id)
        fetched_tasks[task_id_str] = task_obj
        tasks_by_id[task_id_str] = task_obj
        v2_id = task_obj.task_entry.v2_id
        if v2_id is not None:
            v2_id_str = str(v2_id)
            fetched_tasks.setdefault(v2_id_str, task_obj)
            tasks_by_id.setdefault(v2_id_str, task_obj)
        return task_obj

    processed_ids: set[str] = set()
    track_processed = not automation.remove_label_after_processing
    previous_progress = automation._progress_load()
    if track_processed:
        raw_processed = previous_progress.get(ProgressKey.PROCESSED_IDS.value)
        if isinstance(raw_processed, list):
            processed_ids = {str(task_id) for task_id in raw_processed if isinstance(task_id, str)}

    queue_items = automation._queue_load()
    queue_additions: list[QueueItem] = []

    selection = collect_candidates(
        automation=automation,
        all_tasks=all_tasks,
        tasks_by_id=tasks_by_id,
        children_by_parent=children_by_parent,
        queue_items=queue_items,
        processed_ids=processed_ids,
        fetch_task=fetch_task,
    )
    candidates = selection.candidates
    queued_ids = selection.queued_ids
    drop_queue_ids = selection.drop_queue_ids

    if not candidates:
        if drop_queue_ids:
            remaining = [item for item in queue_items if item["task_id"] not in drop_queue_ids]
            automation._queue_save(remaining)
        if automation.track_progress:
            idle_progress = build_idle_progress(
                now=now,
                processed_ids=processed_ids,
                track_processed=track_processed,
            )
            automation._progress_save(idle_progress)
        logger.info("No LLM breakdown tasks queued.")
        return

    tasks_to_process = candidates[:automation.max_tasks_per_tick]
    tasks_total = len(candidates)
    tasks_pending = tasks_total - len(tasks_to_process)
    run_id = automation._new_run_id()

    progress = build_running_progress(
        now=now,
        run_id=run_id,
        tasks_total=tasks_total,
        tasks_pending=tasks_pending,
        processed_ids=processed_ids,
        track_processed=track_processed,
    )
    automation._progress_save(progress)

    try:
        llm = automation._get_llm()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to initialize LLM: {}", exc)
        mark_progress_failed(
            progress,
            error=f"{type(exc).__name__}: {exc}",
            now=automation._now_iso(),
        )
        automation._progress_save(progress)
        if drop_queue_ids:
            remaining = [item for item in queue_items if item["task_id"] not in drop_queue_ids]
            automation._queue_save(remaining)
        return

    completed = 0
    failed = 0
    processed_queue_ids: set[str] = set()

    for item in tasks_to_process:
        task = item.task
        label = item.label
        variant_key = item.variant
        depth = item.depth
        source = item.source

        progress[ProgressKey.CURRENT.value] = {
            CurrentKey.TASK_ID.value: task.id,
            CurrentKey.CONTENT.value: task.task_entry.content,
            CurrentKey.LABEL.value: label,
            CurrentKey.DEPTH.value: depth,
        }
        progress[ProgressKey.UPDATED_AT.value] = automation._now_iso()
        automation._progress_save(progress)

        variant_cfg = automation.variants.get(variant_key)
        if variant_cfg is None:
            variant_key, variant_cfg = automation._resolve_variant(label)
        variant_cfg = dict(variant_cfg)
        max_depth = int(variant_cfg.get("max_depth", automation.max_depth))
        max_children = int(variant_cfg.get("max_children", automation.max_children))
        max_total_tasks = int(variant_cfg.get("max_total_tasks", automation.max_total_tasks))
        queue_depth_limit = int(variant_cfg.get("queue_depth", automation.max_queue_depth))
        instruction = variant_cfg.get("instruction")
        if queue_depth_limit > 0:
            max_allowed = max(1, queue_depth_limit - depth + 1)
            max_depth = min(max_depth, max_allowed)

        system_prompt = automation._build_system_prompt(
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

        try:
            breakdown = llm.structured_chat(messages, TaskBreakdown)
        except ValueError as exc:
            logger.error("LLM breakdown failed for task {}: {}", task.id, exc)
            failed += 1
            processed_ids.add(task.id)
            append_progress_result(
                progress,
                task=task,
                status="failed",
                error=str(exc),
                depth=depth,
            )
            pending = tasks_total - (completed + failed)
            set_progress_counts(
                progress,
                completed=completed,
                failed=failed,
                pending=pending,
                total=tasks_total,
                now=automation._now_iso(),
                processed_ids=processed_ids,
                track_processed=track_processed,
                current=None,
            )
            automation._progress_save(progress)
            continue

        nodes = breakdown.children
        created_count = 0
        if not nodes:
            logger.info("LLM returned no subtasks for task {}", task.id)
            if automation.remove_label_after_processing and source == "label":
                automation._update_root_labels(db, task, label)
            completed += 1
        else:
            created = [0]
            queue_ctx = QueueContext(
                items=queue_additions,
                ids=queued_ids,
                next_depth=depth + 1,
                limit=queue_depth_limit,
                label=label,
                variant=variant_key,
                enabled=automation.auto_queue_children,
            )
            automation._insert_children(
                db,
                root_task=task,
                parent_id=task.id,
                nodes=nodes,
                depth=1,
                max_depth=max_depth,
                max_children=max_children,
                max_total_tasks=max_total_tasks,
                labels=automation._child_labels(task),
                created=created,
                queue_ctx=queue_ctx if automation.auto_queue_children else None,
            )
            created_count = created[0]
            if automation.remove_label_after_processing and source == "label":
                automation._update_root_labels(db, task, label)
            completed += 1

        append_progress_result(
            progress,
            task=task,
            status="completed",
            created_count=created_count,
            depth=depth,
        )
        processed_ids.add(task.id)
        if source == "queue":
            processed_queue_ids.add(task.id)
        pending = tasks_total - (completed + failed)
        set_progress_counts(
            progress,
            completed=completed,
            failed=failed,
            pending=pending,
            total=tasks_total,
            now=automation._now_iso(),
            processed_ids=processed_ids,
            track_processed=track_processed,
            current=None,
        )
        automation._progress_save(progress)

        logger.info(
            "Expanded task {} with label '{}' (variant={}, created={}, pending={})",
            task.id,
            label,
            variant_key,
            created_count,
            pending,
        )

    if queue_additions or drop_queue_ids or processed_queue_ids:
        queue_remaining = [
            item
            for item in queue_items
            if item["task_id"] not in drop_queue_ids and item["task_id"] not in processed_queue_ids
        ]
        queue_remaining.extend(queue_additions)
        automation._queue_save(queue_remaining)

    pending = tasks_total - (completed + failed)
    finalize_progress(
        progress,
        pending=pending,
        completed=completed,
        failed=failed,
        total=tasks_total,
        now=automation._now_iso(),
        processed_ids=processed_ids,
        track_processed=track_processed,
    )
    automation._progress_save(progress)


# === CANDIDATE SELECTION ====================================================


def collect_candidates(
    *,
    automation: Any,
    all_tasks: list[Task],
    tasks_by_id: dict[str, Task],
    children_by_parent: dict[str, list[Task]],
    queue_items: list[QueueItem],
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
        variant_key, _ = automation._resolve_variant(llm_label)
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


# === MESSAGES ===============================================================


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


# === TASK HELPERS ===========================================================


def build_children_by_parent(tasks: Iterable[Task]) -> dict[str, list[Task]]:
    children_by_parent: dict[str, list[Task]] = {}
    for task in tasks:
        parent_id = _get_parent_id(task)
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(task)
    return children_by_parent


def build_task_lookup(tasks: Iterable[Task]) -> dict[str, Task]:
    lookup: dict[str, Task] = {}
    for task in tasks:
        lookup[str(task.id)] = task
        v2_id = task.task_entry.v2_id
        if v2_id is not None:
            v2_id_str = str(v2_id)
            lookup.setdefault(v2_id_str, task)
    return lookup


def find_llm_label(labels: Iterable[str], prefix_lower: str) -> str | None:
    for label in labels:
        if label.lower().startswith(prefix_lower):
            return label
    return None


# === PROGRESS ===============================================================


def build_idle_progress(*, now: str, processed_ids: set[str], track_processed: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        ProgressKey.ACTIVE.value: False,
        ProgressKey.STATUS.value: ProgressStatus.IDLE.value,
        ProgressKey.RUN_ID.value: None,
        ProgressKey.STARTED_AT.value: None,
        ProgressKey.UPDATED_AT.value: now,
        ProgressKey.TASKS_TOTAL.value: 0,
        ProgressKey.TASKS_COMPLETED.value: 0,
        ProgressKey.TASKS_FAILED.value: 0,
        ProgressKey.TASKS_PENDING.value: 0,
        ProgressKey.CURRENT.value: None,
        ProgressKey.ERROR.value: None,
        ProgressKey.RESULTS.value: [],
    }
    if track_processed:
        payload[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)
    return payload


def build_running_progress(
    *,
    now: str,
    run_id: str,
    tasks_total: int,
    tasks_pending: int,
    processed_ids: set[str],
    track_processed: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        ProgressKey.ACTIVE.value: True,
        ProgressKey.STATUS.value: ProgressStatus.RUNNING.value,
        ProgressKey.RUN_ID.value: run_id,
        ProgressKey.STARTED_AT.value: now,
        ProgressKey.UPDATED_AT.value: now,
        ProgressKey.TASKS_TOTAL.value: tasks_total,
        ProgressKey.TASKS_COMPLETED.value: 0,
        ProgressKey.TASKS_FAILED.value: 0,
        ProgressKey.TASKS_PENDING.value: tasks_pending,
        ProgressKey.CURRENT.value: None,
        ProgressKey.ERROR.value: None,
        ProgressKey.RESULTS.value: [],
    }
    if track_processed:
        payload[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)
    return payload


def append_progress_result(
    progress: dict[str, Any],
    *,
    task: Task,
    status: str,
    created_count: int | None = None,
    error: str | None = None,
    depth: int | None = None,
    limit: int = 10,
) -> None:
    results = progress.get(ProgressKey.RESULTS.value)
    if not isinstance(results, list):
        results = []
        progress[ProgressKey.RESULTS.value] = results
    entry: dict[str, Any] = {
        "task_id": task.id,
        "content": task.task_entry.content,
        "status": status,
    }
    if created_count is not None:
        entry["created_count"] = created_count
    if error:
        entry["error"] = error
    if depth is not None:
        entry["depth"] = depth
    results.append(entry)
    if len(results) > limit:
        del results[:-limit]


def set_progress_counts(
    progress: dict[str, Any],
    *,
    completed: int,
    failed: int,
    pending: int,
    total: int,
    now: str,
    processed_ids: set[str],
    track_processed: bool,
    current: dict[str, Any] | None,
) -> None:
    progress.update(
        {
            ProgressKey.TASKS_COMPLETED.value: completed,
            ProgressKey.TASKS_FAILED.value: failed,
            ProgressKey.TASKS_PENDING.value: pending,
            ProgressKey.TASKS_TOTAL.value: total,
            ProgressKey.CURRENT.value: current,
            ProgressKey.UPDATED_AT.value: now,
        }
    )
    if track_processed:
        progress[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)


def mark_progress_failed(progress: dict[str, Any], *, error: str, now: str) -> None:
    progress.update(
        {
            ProgressKey.ACTIVE.value: False,
            ProgressKey.STATUS.value: ProgressStatus.FAILED.value,
            ProgressKey.ERROR.value: error,
            ProgressKey.UPDATED_AT.value: now,
        }
    )


def finalize_progress(
    progress: dict[str, Any],
    *,
    pending: int,
    completed: int,
    failed: int,
    total: int,
    now: str,
    processed_ids: set[str],
    track_processed: bool,
) -> None:
    set_progress_counts(
        progress,
        completed=completed,
        failed=failed,
        pending=pending,
        total=total,
        now=now,
        processed_ids=processed_ids,
        track_processed=track_processed,
        current=None,
    )
    progress[ProgressKey.ACTIVE.value] = pending > 0
    progress[ProgressKey.STATUS.value] = (
        ProgressStatus.RUNNING.value if pending > 0 else ProgressStatus.COMPLETED.value
    )
