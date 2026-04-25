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


def _post_task_comment(db: Database, task_id: str, content: str) -> None:
    try:
        db.create_comment(task_id=task_id, content=content)
    except Exception as exc:  # pragma: no cover - comment audit must not block rollout
        logger.warning("Failed to create LLM breakdown comment for task {}: {}", task_id, exc)


def _llm_descriptor(automation: Any, llm: Any) -> str:
    backend = getattr(automation, "_llm_backend", None) or "unknown"
    config = getattr(llm, "config", None)
    model = (
        getattr(config, "model_id", None)
        or getattr(config, "model", None)
        or getattr(llm, "model_id", None)
        or "unknown"
    )
    return f"{backend} / {model}"


def _comment_header() -> str:
    return "Todoist Assistant LLM Breakdown"


def _start_comment(*, run_id: str, request: Any, llm_descriptor: str) -> str:
    return "\n".join(
        [
            _comment_header(),
            "Status: started",
            f"Run: {run_id}",
            f"Model: {llm_descriptor}",
            f"Variant: {request.variant_key}",
            f"Depth: {request.depth}",
            f"Source: {request.source}",
        ]
    )


def _failure_comment(*, run_id: str, error_message: str) -> str:
    return _failure_comment_with_action(
        run_id=run_id,
        error_message=error_message,
        action="Label kept for retry.",
    )


def _failure_comment_with_action(*, run_id: str, error_message: str, action: str) -> str:
    return "\n".join(
        [
            _comment_header(),
            "Status: failed",
            f"Run: {run_id}",
            f"Error: {error_message}",
            action,
        ]
    )


def _fallback_comment(*, run_id: str, reason: str) -> str:
    return "\n".join(
        [
            _comment_header(),
            "Status: fallback",
            f"Run: {run_id}",
            f"Reason: {reason}",
        ]
    )


def _node_content(node: Any) -> str:
    return str(getattr(node, "content", "") or "").strip()


def _completion_comment(
    *,
    run_id: str,
    created_count: int,
    nodes: list[Any],
    fallback_reason: str | None,
) -> str:
    lines = [
        _comment_header(),
        "Status: completed",
        f"Run: {run_id}",
        f"Created subtasks: {created_count}",
    ]
    if fallback_reason:
        lines.append(f"Fallback reason: {fallback_reason}")
    titles = [_node_content(node) for node in nodes]
    titles = [title for title in titles if title]
    if titles:
        lines.append("Planned children:")
        lines.extend(f"- {title}" for title in titles[:10])
    return "\n".join(lines)


def _task_failure_comment_count(db: Database, task_id: str) -> int:
    try:
        comments = db.fetch_task_comments(task_id)
    except Exception as exc:  # pragma: no cover - defensive retry policy
        logger.warning("Failed to fetch LLM breakdown comments for task {}: {}", task_id, exc)
        return 0
    return sum(
        1
        for comment in comments
        if isinstance(comment, dict)
        and _comment_header() in str(comment.get("content") or "")
        and "Status: failed" in str(comment.get("content") or "")
    )


def _failure_action_for_task(
    automation: Any,
    db: Database,
    *,
    task: Task,
    label: str,
    source: str,
) -> str:
    failure_count = _task_failure_comment_count(db, task.id) + 1
    max_failures = int(getattr(automation, "max_failures_per_task", 3))
    failed_label = str(getattr(automation, "failed_label", "llm-breakdown-failed"))
    if source == "label" and failure_count >= max_failures:
        automation.mark_root_failed(db, task, label)
        return f"Failure limit reached ({failure_count}/{max_failures}); replaced label with {failed_label}."
    return f"Label kept for retry ({failure_count}/{max_failures})."


def run_breakdown(automation: Any, db: Database) -> None:
    logger.info("Running LLM Breakdown automation")
    projects = db.fetch_projects(include_tasks=True)
    all_tasks: list[Task] = [task for project in projects for task in project.tasks]
    logger.debug(f"Found {len(all_tasks)} tasks in total")

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
        queue_items=queue_items,
        processed_ids=processed_ids,
        fetch_task=fetch_task,
    )
    candidates = selection.candidates
    queued_ids = selection.queued_ids
    drop_queue_ids = selection.drop_queue_ids
    cleanup_label_tasks = selection.cleanup_label_tasks

    logger.info(
        "LLM breakdown selection prepared {} candidate(s), {} cleanup task(s), {} dropped queue item(s)",
        len(candidates),
        len(cleanup_label_tasks),
        len(drop_queue_ids),
    )

    for item in cleanup_label_tasks:
        logger.info(
            "Removing processed rollout label '{}' from task {} because children already exist",
            item.label,
            item.task.id,
        )
        automation.update_root_labels(db, item.task, item.label)

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
    logger.info(
        "LLM breakdown will process {} task(s) this tick (candidates={}, max_tasks_per_tick={})",
        len(tasks_to_process),
        tasks_total,
        limit,
    )
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
    llm_descriptor = _llm_descriptor(automation, llm)
    for request in prepared_requests:
        _post_task_comment(
            db,
            request.task.id,
            _start_comment(run_id=run_id, request=request, llm_descriptor=llm_descriptor),
        )
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

        fallback_reason: str | None = None
        if result.error is not None or result.breakdown is None:
            error_message = result.error or "unknown error"
            logger.error("LLM breakdown failed for task {}: {}", task.id, error_message)
            action = _failure_action_for_task(
                automation,
                db,
                task=task,
                label=label,
                source=source,
            )
            _post_task_comment(
                db,
                task.id,
                _failure_comment_with_action(
                    run_id=run_id,
                    error_message=error_message,
                    action=action,
                ),
            )
            failed += 1
            append_progress_result(
                progress,
                task=task,
                status="failed",
                created_count=0,
                error=error_message,
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
        if not nodes:
            fallback_reason = "empty breakdown"
            logger.info(f"LLM returned no subtasks for task {task.id}")
            nodes = automation.fallback_nodes(task, reason=fallback_reason)
            logger.warning(
                "Using fallback breakdown for task {} after empty result",
                task.id,
            )
            _post_task_comment(
                db,
                task.id,
                _fallback_comment(run_id=run_id, reason=fallback_reason),
            )

        created_count = 0

        def _insert_nodes(
            candidate_nodes: list[Any],
            *,
            current_depth: int = depth,
            current_label: str = label,
            current_request: Any = request,
            current_task: Task = task,
        ) -> tuple[InsertContext, int]:
            created = [0]
            queue_ctx = QueueContext(
                items=queue_additions,
                ids=queued_ids,
                next_depth=current_depth + 1,
                limit=current_request.queue_depth_limit,
                label=current_label,
                variant=current_request.variant_key,
                enabled=automation.auto_queue_children,
            )
            context = InsertContext(
                max_depth=current_request.max_depth,
                max_children=current_request.max_children,
                max_total_tasks=current_request.max_total_tasks,
                labels=automation.child_labels(current_task),
                created=created,
                queue_ctx=queue_ctx if automation.auto_queue_children else None,
            )
            automation.insert_children(
                db,
                root_task=current_task,
                parent_id=current_task.id,
                nodes=candidate_nodes,
                depth=1,
                context=context,
            )
            return context, created[0]

        context, created_count = _insert_nodes(nodes)
        if context.errors and created_count == 0 and fallback_reason is None:
            error_message = "; ".join(context.errors[:3])
            if len(context.errors) > 3:
                error_message = f"{error_message}; and {len(context.errors) - 3} more"
            fallback_reason = error_message
            logger.warning(
                "Retrying task {} with fallback breakdown after insert errors",
                task.id,
            )
            _post_task_comment(
                db,
                task.id,
                _fallback_comment(run_id=run_id, reason=error_message),
            )
            context, created_count = _insert_nodes(
                automation.fallback_nodes(task, reason=error_message)
            )

        if context.errors:
            error_message = "; ".join(context.errors[:3])
            if len(context.errors) > 3:
                error_message = f"{error_message}; and {len(context.errors) - 3} more"
            logger.error("LLM breakdown insert failed for task {}: {}", task.id, error_message)
            _post_task_comment(
                db,
                task.id,
                _failure_comment(run_id=run_id, error_message=error_message),
            )
            failed += 1
            processed_ids.add(task.id)
            if created_count > 0 and source == "queue":
                processed_queue_ids.add(task.id)
            if (
                created_count > 0
                and automation.remove_label_after_processing
                and source == "label"
            ):
                automation.update_root_labels(db, task, label)
            append_progress_result(
                progress,
                task=task,
                status="failed",
                created_count=created_count,
                error=error_message,
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
        if automation.remove_label_after_processing and source == "label":
            automation.update_root_labels(db, task, label)
        completed += 1
        _post_task_comment(
            db,
            task.id,
            _completion_comment(
                run_id=run_id,
                created_count=created_count,
                nodes=nodes,
                fallback_reason=fallback_reason,
            ),
        )

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
