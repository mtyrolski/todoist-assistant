from datetime import UTC, date, datetime

import pytest

from tests.factories import make_project, make_task
from tests.unit.database.helpers import make_event
from todoist.dashboard._plot_task_counts import (
    plot_task_count_trend,
    reconstruct_task_count_history,
)


def _event(
    event_id: str,
    task_id: str,
    event_type: str,
    when: datetime,
    **extra: object,
):
    event = make_event(
        event_id,
        date=when,
        event_date=when.isoformat(),
    )
    event.event_entry.object_id = task_id
    event.event_entry.event_type = event_type
    event.event_entry.extra_data.update(extra)
    return event


def test_reconstruct_task_count_history_walks_item_lifecycle_backward() -> None:
    projects = [
        make_project(
            tasks=[
                make_task(
                    "active",
                    priority=4,
                    added_at="2026-10-03T09:00:00Z",
                ),
                make_task(
                    "persistent",
                    priority=1,
                    added_at="2026-10-02T08:00:00Z",
                ),
            ]
        )
    ]
    events = [
        _event(
            "completed-old",
            "old",
            "completed",
            datetime(2026, 10, 4, 18, tzinfo=UTC),
            priority=3,
            date_added="2026-10-02T07:00:00Z",
        ),
        _event(
            "priority-active",
            "active",
            "updated",
            datetime(2026, 10, 4, 12, tzinfo=UTC),
            priority=4,
            last_priority=1,
        ),
        _event(
            "added-active",
            "active",
            "added",
            datetime(2026, 10, 3, 9, tzinfo=UTC),
        ),
    ]

    history = reconstruct_task_count_history(
        projects,
        events,
        today=date(2026, 10, 5),
    )

    relevant_history = [row for row in history if row["date"] >= "2026-10-01"]
    assert [row["date"] for row in relevant_history] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
        "2026-10-05",
    ]
    assert [row["total"] for row in relevant_history] == [0, 2, 3, 2, 2]
    assert [row["p1"] for row in relevant_history] == [0, 0, 0, 1, 1]
    assert [row["p2"] for row in relevant_history] == [0, 1, 1, 0, 0]
    assert [row["p4"] for row in relevant_history] == [0, 1, 2, 1, 1]


def test_reconstruction_defaults_known_historical_task_priority_to_normal() -> None:
    completed = _event(
        "completed-old",
        "old",
        "completed",
        datetime(2026, 10, 4, 18, tzinfo=UTC),
        date_added="2026-10-03T08:00:00Z",
    )

    history = reconstruct_task_count_history(
        [],
        [completed],
        today=date(2026, 10, 5),
    )

    assert history[0]["date"] == "2026-10-02"
    assert history[0]["total"] == 0
    added_day = next(row for row in history if row["date"] == "2026-10-03")
    assert added_day["total"] == 1
    assert added_day["p4"] == 1
    assert history[-1]["total"] == 0


def test_current_task_does_not_exist_before_its_added_at_without_added_event() -> None:
    projects = [
        make_project(
            tasks=[
                make_task(
                    "recent",
                    priority=1,
                    added_at="2026-09-01T10:00:00Z",
                )
            ]
        )
    ]
    old_boundary = _event(
        "old-boundary",
        "already-absent",
        "added",
        datetime(2022, 7, 25, 9, tzinfo=UTC),
    )

    history = reconstruct_task_count_history(
        projects,
        [old_boundary],
        today=date(2026, 10, 2),
    )

    assert history[0]["date"] == "2022-07-24"
    assert history[0]["total"] == 0
    assert next(row for row in history if row["date"] == "2026-08-31")["total"] == 0
    assert next(row for row in history if row["date"] == "2026-09-01")["total"] == 1


def test_task_count_trend_spans_cached_history_and_keeps_real_hover_counts() -> None:
    projects = [make_project(tasks=[make_task("active", priority=4)])]
    added = _event(
        "added-active",
        "active",
        "added",
        datetime(2022, 7, 25, 9, tzinfo=UTC),
    )

    figure = plot_task_count_trend(
        projects,
        [added],
        today=date(2026, 10, 2),
    )

    assert [trace.name for trace in figure.data] == [
        "All tasks",
        "P1",
        "P2",
        "P3",
        "P4",
    ]
    assert figure.data[0].x[0] == "2022-07-24"
    assert figure.data[0].x[-1] == "2026-10-02"
    assert list(figure.data[0].customdata)[-1] == 1
    assert list(figure.data[0].y)[-1] == pytest.approx(1.0)
    assert figure.data[0].line.shape == "spline"
    assert figure.data[0].line.smoothing == pytest.approx(0.7)
    assert figure.layout.yaxis.title.text == "Active tasks (softened scale)"
    assert figure.layout.xaxis.rangeslider.visible is True
