from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from todoist.stats import extract_task_due_date, try_parse_date
from todoist.types import Project, Task

StaleState = Literal["skip", "fresh", "old", "very_old"]


@dataclass(frozen=True, slots=True)
class StaleTaskConfig:
    old_after_days: int = 30
    very_old_after_days: int = 90
    old_label: str = "old"
    very_old_label: str = "very-old"
    exempt_labels: tuple[str, ...] = ("no_stale", "track_habit")
    exclude_recurring: bool = True
    exclude_due_within_days: int = 7
    exclude_overdue: bool = True
    apply_to_subtasks: bool = False


@dataclass(frozen=True, slots=True)
class StaleTaskDecision:
    state: StaleState
    reason: str
    stale_days: int | None
    last_touched_at: datetime | None
    due_at: datetime | None
    desired_labels: list[str] | None
    should_update: bool


def _normalize_label(label: str) -> str:
    return label.strip().lower()


def _managed_label_names(config: StaleTaskConfig) -> tuple[str, str]:
    return (_normalize_label(config.old_label), _normalize_label(config.very_old_label))


def _task_last_touched_at(task: Task) -> datetime | None:
    candidates = [
        try_parse_date(value)
        for value in [task.task_entry.updated_at, task.task_entry.added_at]
        if isinstance(value, str) and value
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    if not candidates:
        return None
    return max(candidates)


def _desired_labels_for_state(
    current_labels: Sequence[str],
    *,
    state: Literal["fresh", "old", "very_old"],
    config: StaleTaskConfig,
) -> list[str]:
    managed_labels = set(_managed_label_names(config))
    preserved = [
        label
        for label in current_labels
        if _normalize_label(label) not in managed_labels
    ]
    if state == "old":
        return [*preserved, config.old_label]
    if state == "very_old":
        return [*preserved, config.very_old_label]
    return preserved


def evaluate_task_staleness(
    task: Task,
    *,
    now: datetime,
    config: StaleTaskConfig,
) -> StaleTaskDecision:
    def skip(reason: str, due_at: datetime | None = None) -> StaleTaskDecision:
        return StaleTaskDecision(
            state="skip",
            reason=reason,
            stale_days=None,
            last_touched_at=None,
            due_at=due_at,
            desired_labels=None,
            should_update=False,
        )

    current_labels = list(task.task_entry.labels or [])
    normalized_labels = {_normalize_label(label) for label in current_labels}
    exempt_labels = {_normalize_label(label) for label in config.exempt_labels}
    due_at = extract_task_due_date(task.task_entry.due)

    skip_reason: str | None = None
    if normalized_labels & exempt_labels:
        skip_reason = "exempt_label"
    elif config.exclude_recurring and task.is_recurring:
        skip_reason = "recurring"
    elif not config.apply_to_subtasks and task.task_entry.parent_id is not None:
        skip_reason = "subtask"

    if skip_reason is not None:
        return skip(skip_reason)
    if due_at is not None:
        due_day_delta = (due_at.date() - now.date()).days
        if config.exclude_overdue and due_day_delta < 0:
            return skip("overdue", due_at=due_at)
        if 0 <= due_day_delta <= config.exclude_due_within_days:
            return skip("due_soon", due_at=due_at)

    last_touched_at = _task_last_touched_at(task)
    if last_touched_at is None:
        return skip("missing_timestamp", due_at=due_at)

    stale_days = max(0, (now.date() - last_touched_at.date()).days)
    state: Literal["fresh", "old", "very_old"] = "fresh"
    if stale_days >= config.very_old_after_days:
        state = "very_old"
    elif stale_days >= config.old_after_days:
        state = "old"

    desired_labels = _desired_labels_for_state(current_labels, state=state, config=config)
    should_update = desired_labels != current_labels
    return StaleTaskDecision(
        state=state,
        reason=state,
        stale_days=stale_days,
        last_touched_at=last_touched_at,
        due_at=due_at,
        desired_labels=desired_labels,
        should_update=should_update,
    )


def flatten_project_tasks(projects: Sequence[Project]) -> list[tuple[Project, Task]]:
    return [
        (project, task)
        for project in projects
        for task in project.tasks
    ]
