from datetime import date

import pandas as pd

from tests.factories import make_project, make_task
from todoist.web.dashboard_payload import (
    FIRE_TASK_LABEL,
    count_labeled_tasks,
    evaluate_urgency_status,
    extract_metrics_dict,
)


def test_count_labeled_tasks_matches_fire_label_case_insensitively() -> None:
    projects = [
        make_project(
            tasks=[
                make_task("a", labels=[FIRE_TASK_LABEL]),
                make_task("b", labels=["Fire \U0001F9EF\U0001F692"]),
                make_task("c", labels=["other"]),
            ]
        ),
        make_project(tasks=[make_task("d", labels=[FIRE_TASK_LABEL, "extra"])]),
    ]

    assert count_labeled_tasks(projects, label_name=FIRE_TASK_LABEL) == 3


def test_extract_metrics_dict_keeps_period_metrics_only() -> None:
    df = pd.DataFrame(
        [
            {"date": "2025-01-14", "id": "e1", "title": "x", "type": "completed"},
            {"date": "2025-01-10", "id": "e2", "title": "y", "type": "added"},
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    periods = {
        "beg": pd.Timestamp("2025-01-08"),
        "end": pd.Timestamp("2025-01-15"),
        "prevBeg": pd.Timestamp("2025-01-01"),
        "prevEnd": pd.Timestamp("2025-01-08"),
    }
    metrics = extract_metrics_dict(df, periods)

    assert [metric["name"] for metric in metrics] == [
        "Events",
        "Completed Tasks",
        "Added Tasks",
        "Rescheduled Tasks",
    ]


def test_evaluate_urgency_status_returns_good_when_clear() -> None:
    today = date(2026, 3, 20)
    projects = [
        make_project(
            tasks=[
                make_task("a", priority=1),
                make_task("b", due={"date": "2026-03-21"}),
                make_task("c", deadline={"date": "2026-03-22"}),
            ]
        )
    ]

    status = evaluate_urgency_status(projects, today=today)

    assert status["state"] == "good"
    assert status["badgeLabel"] == "OK"
    assert status["total"] == 0
    assert status["counts"] == {
        "fireTasks": 0,
        "p1Tasks": 0,
        "p2Tasks": 0,
        "dueTasks": 0,
        "deadlineTasks": 0,
    }
    assert status["todayLabel"] == "2026-03-20"


def test_evaluate_urgency_status_returns_warn_for_priority_and_dates() -> None:
    today = date(2026, 3, 20)
    projects = [
        make_project(
            tasks=[
                make_task("p1", priority=4),
                make_task("p2", priority=3),
                make_task("due", due={"date": "2026-03-20"}),
                make_task("deadline", deadline={"date": "2026-03-20"}),
            ]
        )
    ]

    status = evaluate_urgency_status(projects, today=today)

    assert status["state"] == "warn"
    assert status["badgeLabel"] == "Watch"
    assert status["title"] == "Attention needed"
    assert status["total"] == 4
    assert status["counts"] == {
        "fireTasks": 0,
        "p1Tasks": 1,
        "p2Tasks": 1,
        "dueTasks": 1,
        "deadlineTasks": 1,
    }


def test_evaluate_urgency_status_returns_danger_for_fire_tasks() -> None:
    today = date(2026, 3, 20)
    projects = [
        make_project(
            tasks=[
                make_task("fire", labels=[FIRE_TASK_LABEL]),
                make_task("normal", priority=1, due={"date": "2026-03-21"}),
            ]
        )
    ]

    status = evaluate_urgency_status(projects, today=today)

    assert status["state"] == "danger"
    assert status["badgeLabel"] == "Urgent"
    assert status["title"] == "Urgent attention needed"
    assert status["total"] == 1
    assert status["counts"]["fireTasks"] == 1


def test_evaluate_urgency_status_respects_custom_settings() -> None:
    today = date(2026, 3, 20)
    projects = [
        make_project(
            tasks=[
                make_task("p1", priority=4),
                make_task("due", due={"date": "2026-03-25"}),
                make_task("fire", labels=[FIRE_TASK_LABEL]),
            ]
        )
    ]

    status = evaluate_urgency_status(
        projects,
        today=today,
        settings={
            "enabled": True,
            "danger_on_fire_label": False,
            "warn_on_priority": True,
            "warn_priority_thresholds": [4],
            "warn_on_due": True,
            "warn_due_within_days": 7,
            "warn_on_deadline": False,
            "badge_labels": {"good": "Clear", "warn": "Heads up", "danger": "Stop"},
        },
    )

    assert status["state"] == "warn"
    assert status["badgeLabel"] == "Heads up"
    assert status["total"] == 2
    assert status["counts"]["fireTasks"] == 0
    assert status["counts"]["p1Tasks"] == 1
    assert status["counts"]["dueTasks"] == 1
