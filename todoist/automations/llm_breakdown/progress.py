from __future__ import annotations

from typing import Any

from todoist.types import Task

from .models import ProgressKey, ProgressStatus


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
