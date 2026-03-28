from typing import Any

from loguru import logger

from todoist.database.base import Database
from todoist.llm.llm_utils import (
    _task_from_api_payload,
)
from todoist.types import Task

from .generation import generate_breakdowns
from .models import (
    CurrentKey,
    InsertContext,
    ProgressKey,
    QueueContext,
    QueueItem,
)
from .planning import (
    build_children_by_parent,
    build_task_lookup,
    collect_candidates,
    prepare_breakdown_request,
)
from .progress import (
    append_progress_result,
    build_idle_progress,
    build_running_progress,
    finalize_progress,
    mark_progress_failed,
    set_progress_counts,
)


def run_breakdown(automation: Any, db: Database) -> None:
    logger.info("Running LLM Breakdown automation")
    projects = db.fetch_projects(include_tasks=True)
    all_tasks: list[Task] = [task for project in projects for task in project.tasks]
    logger.debug(f"Found {len(all_tasks)} tasks in total")

    children_by_parent = build_children_by_parent(all_tasks)
    tasks_by_id = build_task_lookup(all_tasks)
    fetched_tasks: dict[str, Task] = {}
    now = automation.now_iso()

    def fetch_task(task_id: str, refresh: bool = False) -> Task | None:
        cached = tasks_by_id.get(task_id) or fetched_tasks.get(task_id)
        if cached is not None and not refresh:
            return cached
        try:
            payload = db.fetch_task_by_id(task_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Failed to fetch task {task_id} for context: {exc}")
            return cached
        task_obj = _task_from_api_payload(payload)
        if task_obj is None:
            return cached
        task_id_str = str(task_obj.id)
        fetched_tasks[task_id_str] = task_obj
        tasks_by_id[task_id_str] = task_obj
        return task_obj

    processed_ids: set[str] = set()
    track_processed = not automation.remove_label_after_processing
    previous_progress = automation.progress_load()
    if track_processed:
        raw_processed = previous_progress.get(ProgressKey.PROCESSED_IDS.value)
        if isinstance(raw_processed, list):
            processed_ids = {str(task_id) for task_id in raw_processed if isinstance(task_id, str)}

    queue_items = automation.queue_load()
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
            automation.queue_save(remaining)
        if automation.track_progress:
            idle_progress = build_idle_progress(
                now=now,
                processed_ids=processed_ids,
                track_processed=track_processed,
            )
            automation.progress_save(idle_progress)
        logger.info("No LLM breakdown tasks queued.")
        return

    limit = automation.max_tasks_per_tick
    tasks_to_process = candidates[:limit] if limit > 0 else candidates
    tasks_total = len(candidates)
    tasks_pending = tasks_total - len(tasks_to_process)
    run_id = automation.new_run_id()

    progress = build_running_progress(
        now=now,
        run_id=run_id,
        tasks_total=tasks_total,
        tasks_pending=tasks_pending,
        processed_ids=processed_ids,
        track_processed=track_processed,
    )
    automation.progress_save(progress)

    try:
        llm = automation.get_llm()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Failed to initialize LLM: {exc}")
        mark_progress_failed(
            progress,
            error=f"{type(exc).__name__}: {exc}",
            now=automation.now_iso(),
        )
        automation.progress_save(progress)
        if drop_queue_ids:
            remaining = [item for item in queue_items if item["task_id"] not in drop_queue_ids]
            automation.queue_save(remaining)
        return

    prepared_requests = [
        prepare_breakdown_request(
            automation=automation,
            item=item,
            tasks_by_id=tasks_by_id,
            fetch_task=fetch_task,
        )
        for item in tasks_to_process
    ]
    generation_results = generate_breakdowns(
        automation=automation,
        llm=llm,
        prepared_requests=prepared_requests,
    )

    completed = 0
    failed = 0
    processed_queue_ids: set[str] = set()

    for result in generation_results:
        request = result.request
        task = request.task
        label = request.label
        depth = request.depth
        source = request.source

        progress[ProgressKey.CURRENT.value] = {
            CurrentKey.TASK_ID.value: task.id,
            CurrentKey.CONTENT.value: task.task_entry.content,
            CurrentKey.LABEL.value: label,
            CurrentKey.DEPTH.value: depth,
        }
        progress[ProgressKey.UPDATED_AT.value] = automation.now_iso()
        automation.progress_save(progress)

        if result.error is not None or result.breakdown is None:
            logger.error("LLM breakdown failed for task {}: {}", task.id, result.error)
            failed += 1
            processed_ids.add(task.id)
            append_progress_result(
                progress,
                task=task,
                status="failed",
                error=result.error or "unknown error",
                depth=depth,
            )
            pending = tasks_total - (completed + failed)
            set_progress_counts(
                progress,
                completed=completed,
                failed=failed,
                pending=pending,
                total=tasks_total,
                now=automation.now_iso(),
                processed_ids=processed_ids,
                track_processed=track_processed,
                current=None,
            )
            automation.progress_save(progress)
            continue

        nodes = result.breakdown.children
        created_count = 0
        if not nodes:
            logger.info(f"LLM returned no subtasks for task {task.id}")
            if automation.remove_label_after_processing and source == "label":
                automation.update_root_labels(db, task, label)
            completed += 1
        else:
            created = [0]
            queue_ctx = QueueContext(
                items=queue_additions,
                ids=queued_ids,
                next_depth=depth + 1,
                limit=request.queue_depth_limit,
                label=label,
                variant=request.variant_key,
                enabled=automation.auto_queue_children,
            )
            automation.insert_children(
                db,
                root_task=task,
                parent_id=task.id,
                nodes=nodes,
                depth=1,
                context=InsertContext(
                    max_depth=request.max_depth,
                    max_children=request.max_children,
                    max_total_tasks=request.max_total_tasks,
                    labels=automation.child_labels(task),
                    created=created,
                    queue_ctx=queue_ctx if automation.auto_queue_children else None,
                ),
            )
            created_count = created[0]
            if automation.remove_label_after_processing and source == "label":
                automation.update_root_labels(db, task, label)
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
            now=automation.now_iso(),
            processed_ids=processed_ids,
            track_processed=track_processed,
            current=None,
        )
        automation.progress_save(progress)

        logger.info(
            "Expanded task {} with label '{}' (variant={}, created={}, pending={})",
            task.id,
            label,
            request.variant_key,
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
        automation.queue_save(queue_remaining)

    pending = tasks_total - (completed + failed)
    finalize_progress(
        progress,
        pending=pending,
        completed=completed,
        failed=failed,
        total=tasks_total,
        now=automation.now_iso(),
        processed_ids=processed_ids,
        track_processed=track_processed,
    )
    automation.progress_save(progress)
