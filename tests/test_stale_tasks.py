from datetime import datetime

from tests.factories import make_task
from todoist.stale_tasks import StaleTaskConfig, evaluate_task_staleness


def test_evaluate_task_staleness_marks_old_task() -> None:
    task = make_task(
        "task-old",
        labels=["work"],
        added_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-15T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 2, 20, 12, 0, 0),
        config=StaleTaskConfig(old_after_days=30, very_old_after_days=90),
    )

    assert decision.state == "old"
    assert decision.reason == "old"
    assert decision.stale_days == 36
    assert decision.desired_labels == ["work", "old"]
    assert decision.should_update is True


def test_evaluate_task_staleness_marks_very_old_task_and_replaces_old_label() -> None:
    task = make_task(
        "task-very-old",
        labels=["work", "old"],
        added_at="2024-01-01T00:00:00Z",
        updated_at="2024-12-01T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 4, 5, 9, 0, 0),
        config=StaleTaskConfig(old_after_days=30, very_old_after_days=90),
    )

    assert decision.state == "very_old"
    assert decision.reason == "very_old"
    assert decision.desired_labels == ["work", "very-old"]
    assert decision.should_update is True


def test_evaluate_task_staleness_clears_managed_labels_when_task_is_fresh() -> None:
    task = make_task(
        "task-fresh",
        labels=["ops", "old", "very-old"],
        added_at="2025-03-01T00:00:00Z",
        updated_at="2025-03-18T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 3, 20, 10, 0, 0),
        config=StaleTaskConfig(old_after_days=30, very_old_after_days=90),
    )

    assert decision.state == "fresh"
    assert decision.desired_labels == ["ops"]
    assert decision.should_update is True


def test_evaluate_task_staleness_skips_exempt_label() -> None:
    task = make_task(
        "task-exempt",
        labels=["no_stale", "work"],
        added_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 3, 20, 10, 0, 0),
        config=StaleTaskConfig(),
    )

    assert decision.state == "skip"
    assert decision.reason == "exempt_label"
    assert decision.desired_labels is None
    assert decision.should_update is False


def test_evaluate_task_staleness_skips_recurring_task() -> None:
    task = make_task(
        "task-recurring",
        labels=["work"],
        due={"date": "2025-03-28", "is_recurring": True},
        added_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 3, 20, 10, 0, 0),
        config=StaleTaskConfig(),
    )

    assert decision.state == "skip"
    assert decision.reason == "recurring"


def test_evaluate_task_staleness_skips_due_soon_task() -> None:
    task = make_task(
        "task-due-soon",
        labels=["work"],
        due={"date": "2025-03-22", "is_recurring": False},
        added_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 3, 20, 10, 0, 0),
        config=StaleTaskConfig(exclude_due_within_days=7),
    )

    assert decision.state == "skip"
    assert decision.reason == "due_soon"


def test_evaluate_task_staleness_skips_overdue_task() -> None:
    task = make_task(
        "task-overdue",
        labels=["work"],
        due={"date": "2025-03-15", "is_recurring": False},
        added_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 3, 20, 10, 0, 0),
        config=StaleTaskConfig(exclude_overdue=True),
    )

    assert decision.state == "skip"
    assert decision.reason == "overdue"


def test_evaluate_task_staleness_skips_subtask_by_default() -> None:
    task = make_task(
        "task-child",
        labels=["work"],
        parent_id="parent-1",
        added_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 3, 20, 10, 0, 0),
        config=StaleTaskConfig(apply_to_subtasks=False),
    )

    assert decision.state == "skip"
    assert decision.reason == "subtask"


def test_evaluate_task_staleness_uses_added_at_when_updated_at_is_missing() -> None:
    task = make_task(
        "task-added-only",
        labels=["work"],
        added_at="2025-01-01T00:00:00Z",
        updated_at="",
    )

    decision = evaluate_task_staleness(
        task,
        now=datetime(2025, 2, 20, 10, 0, 0),
        config=StaleTaskConfig(old_after_days=30, very_old_after_days=90),
    )

    assert decision.state == "old"
    assert decision.last_touched_at == datetime(2025, 1, 1, 0, 0, 0)
