from datetime import date, datetime

import pandas as pd
import plotly.graph_objects as go

from tests.factories import make_project, make_task
from todoist.web.dashboard_payload import (
    add_plot_event_markers,
    apply_date_axis_viewport,
    compute_plot_history_beg,
    FIRE_TASK_LABEL,
    count_labeled_tasks,
    evaluate_urgency_status,
    extract_metrics_dict,
    normalize_plot_events,
)


def _assert_counts_include(status: dict[str, object], **expected: int) -> None:
    counts = status["counts"]
    assert isinstance(counts, dict)
    assert {key: counts[key] for key in expected} == expected


def test_count_labeled_tasks_matches_fire_label_case_insensitively() -> None:
    projects = [
        make_project(
            tasks=[
                make_task("a", labels=[FIRE_TASK_LABEL]),
                make_task("b", labels=["Fire \U0001f9ef\U0001f692"]),
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
        "Undone Completions",
        "Rescheduled Tasks",
    ]


def test_scrollable_date_axis_keeps_history_with_viewport() -> None:
    df = pd.DataFrame(
        [
            {"date": "2024-01-01", "type": "completed"},
            {"date": "2025-01-01", "type": "completed"},
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    history_beg = compute_plot_history_beg(
        df,
        end=datetime(2025, 1, 15),
    )
    fig = apply_date_axis_viewport(
        go.Figure(),
        beg=datetime(2024, 12, 15),
        end=datetime(2025, 1, 15),
    )

    assert history_beg == pd.Timestamp("2024-01-01").to_pydatetime()
    assert fig.layout.xaxis.range[0] == pd.Timestamp("2024-12-15").to_pydatetime()
    assert fig.layout.xaxis.rangeslider.visible is True


def test_plot_events_are_normalized_and_added_as_vertical_markers() -> None:
    events = normalize_plot_events(
        {
            "plot_events": [
                {"date": "2025-01-05", "label": "Launch", "color": "#00ffaa"},
                {"date": "invalid", "label": "Skip"},
            ]
        }
    )
    fig = add_plot_event_markers(
        go.Figure(),
        events,
        beg=datetime(2025, 1, 1),
        end=datetime(2025, 1, 31),
    )

    assert events == [{"date": "2025-01-05", "label": "Launch", "color": "#00ffaa"}]
    assert len(fig.layout.shapes) == 1
    assert fig.layout.shapes[0].line.width == 4
    assert len(fig.layout.annotations) == 1
    assert fig.layout.annotations[0].text == "Launch"


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
        "p3Tasks": 0,
        "p4Tasks": 0,
        "priorityTasks": 0,
        "dueTasks": 0,
        "deadlineTasks": 0,
    }
    assert status["visibleChips"] == [
        "fireTasks",
        "p1Tasks",
        "p2Tasks",
        "dueTasks",
        "deadlineTasks",
    ]
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
        "p3Tasks": 0,
        "p4Tasks": 0,
        "priorityTasks": 2,
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
    _assert_counts_include(status, fireTasks=1)


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
    _assert_counts_include(status, fireTasks=0, p1Tasks=1, priorityTasks=1, dueTasks=1)
    assert status["visibleChips"] == ["p1Tasks", "dueTasks"]
    assert (
        status["summary"]
        == "2 active tasks match the configured priority and due date thresholds."
    )


def test_evaluate_urgency_status_supports_multi_labels_and_minimum_thresholds() -> None:
    today = date(2026, 3, 20)
    projects = [
        make_project(
            tasks=[
                make_task("fire-1", labels=["fire 🧯🚒"]),
                make_task("fire-2", labels=["hot"]),
                make_task("p2", priority=3),
                make_task("p3", priority=2),
                make_task("due", due={"date": "2026-03-20"}),
                make_task("deadline", deadline={"date": "2026-03-20"}),
            ]
        )
    ]

    status = evaluate_urgency_status(
        projects,
        today=today,
        settings={
            "enabled": True,
            "fire_labels": ["fire 🧯🚒", "hot"],
            "warn_priority_thresholds": [3, 2],
            "warn_priority_min_count": 2,
            "warn_due_within_days": 0,
            "warn_due_min_count": 2,
            "warn_deadline_within_days": 0,
            "warn_deadline_min_count": 1,
        },
    )

    assert status["state"] == "danger"
    _assert_counts_include(
        status,
        fireTasks=2,
        p2Tasks=1,
        p3Tasks=1,
        priorityTasks=2,
        dueTasks=1,
        deadlineTasks=1,
    )


def test_urgency_honors_loaded_yaml_rules_and_empty_selections():
    from omegaconf import OmegaConf

    projects = [
        make_project(tasks=[make_task("a", priority=4, labels=[FIRE_TASK_LABEL])])
    ]
    settings = OmegaConf.create(
        {
            "fire_labels": [],
            "warn_priority_thresholds": [],
            "warn_on_due": False,
            "warn_on_deadline": False,
        }
    )
    assert evaluate_urgency_status(projects, settings=settings)["state"] == "good"
    settings.fire_labels = [FIRE_TASK_LABEL]
    settings.danger_summary_label = "Custom red alert"
    status = evaluate_urgency_status(projects, settings=settings)
    assert status["state"] == "danger"
    assert status["title"] == "Custom red alert"
    settings.danger_on_fire_label = False
    settings.warn_priority_thresholds = [4]
    settings.warn_priority_min_count = 2
    assert evaluate_urgency_status(projects, settings=settings)["state"] == "good"


def test_automatic_plot_range_includes_newest_cached_completion():
    from todoist.web.dashboard_payload import compute_plot_range

    df = pd.DataFrame({'type': ['completed']}, index=pd.to_datetime(['2026-10-31T20:00:00']))
    _, end = compute_plot_range(df, weeks=12, beg=None, end=None)
    assert df.index[0] < end
