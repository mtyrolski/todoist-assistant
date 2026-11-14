"""Reconstructed active task counts across cached Todoist activity history."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from math import sqrt

import plotly.graph_objects as go

from todometry.core.types import Event, Project
from todometry.dashboard._plot_common import apply_dashboard_axes

_COLORS = ("#e8ecf2", "#ff7777", "#ffbd69", "#8bd0ff", "#a7e3a1")
_SERIES = (
    ("total", "All tasks"),
    ("p1", "P1"),
    ("p2", "P2"),
    ("p3", "P3"),
    ("p4", "P4"),
)


def _soft_scale(value: int) -> float:
    return sqrt(max(value, 0))


def _priority(value: object, *, fallback: int = 1) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed in (1, 2, 3, 4) else fallback


def _event_timestamp(event: Event) -> float:
    event_date = event.date
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=UTC)
    return event_date.timestamp()


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError:
        return None


def _counts(task_priorities: dict[str, int]) -> dict[str, int]:
    priorities = [0, 0, 0, 0]
    for priority in task_priorities.values():
        priorities[4 - _priority(priority)] += 1
    return {
        "total": len(task_priorities),
        "p1": priorities[0],
        "p2": priorities[1],
        "p3": priorities[2],
        "p4": priorities[3],
    }


def reconstruct_task_count_history(
    active_projects: list[Project],
    events: Iterable[Event],
    *,
    today: date,
) -> list[dict[str, int | str]]:
    """Walk cached item events backward from today's exact active task state."""
    active_tasks = [task for project in active_projects for task in project.tasks]
    task_priorities = {
        str(task.id): _priority(task.task_entry.priority) for task in active_tasks
    }
    added_days_by_task = {
        str(task.id): added_day
        for task in active_tasks
        if (added_day := _as_date(task.task_entry.added_at)) is not None
    }
    item_events = [
        event
        for event in events
        if event.event_entry.object_type == "item" and event.date.date() <= today
    ]
    if not item_events:
        return [{"date": today.isoformat(), **_counts(task_priorities)}]

    item_events.sort(key=_event_timestamp, reverse=True)
    priority_hints = dict(task_priorities)
    for event in item_events:
        task_id = str(event.event_entry.object_id or "")
        if not task_id:
            continue
        extra = event.event_entry.extra_data or {}
        if event.event_entry.event_type == "added":
            event_day = event.date.date()
            known_day = added_days_by_task.get(task_id)
            if known_day is None or event_day < known_day:
                added_days_by_task[task_id] = event_day
        if task_id not in priority_hints and "priority" in extra:
            priority_hints[task_id] = _priority(extra["priority"])
        elif task_id not in priority_hints and "last_priority" in extra:
            priority_hints[task_id] = _priority(extra["last_priority"])
        if task_id not in added_days_by_task:
            added_day = _as_date(extra.get("date_added"))
            if added_day is not None:
                added_days_by_task[task_id] = added_day

    events_by_day: dict[date, list[Event]] = defaultdict(list)
    for event in item_events:
        events_by_day[event.date.date()].append(event)

    task_ids_by_added_day: dict[date, set[str]] = defaultdict(set)
    for task_id, added_day in added_days_by_task.items():
        if added_day <= today:
            task_ids_by_added_day[added_day].add(task_id)

    snapshots: dict[date, dict[str, int | str]] = {}
    cursor = today
    history_days = set(events_by_day) | set(task_ids_by_added_day)
    for event_day in sorted(history_days, reverse=True):
        while cursor >= event_day:
            snapshots[cursor] = {"date": cursor.isoformat(), **_counts(task_priorities)}
            if cursor == event_day:
                break
            cursor -= timedelta(days=1)

        for event in events_by_day.get(event_day, []):
            entry = event.event_entry
            task_id = str(entry.object_id or "")
            if not task_id:
                continue
            extra = entry.extra_data or {}
            event_type = entry.event_type

            if event_type in {"completed", "deleted"}:
                if task_id not in task_priorities and task_id in added_days_by_task:
                    task_priorities[task_id] = _priority(
                        extra.get("priority"),
                        fallback=priority_hints.get(task_id, 1),
                    )
            elif event_type in {"added", "uncompleted"}:
                task_priorities.pop(task_id, None)
            elif (
                event_type == "updated"
                and "last_priority" in extra
                and task_id in task_priorities
            ):
                task_priorities[task_id] = _priority(extra["last_priority"])

        for task_id in task_ids_by_added_day.get(event_day, set()):
            task_priorities.pop(task_id, None)

        cursor = event_day - timedelta(days=1)

    snapshots[cursor] = {"date": cursor.isoformat(), **_counts(task_priorities)}
    return [snapshots[day] for day in sorted(snapshots)]


def plot_task_count_trend(
    active_projects: list[Project],
    events: Iterable[Event],
    *,
    today: date,
) -> go.Figure:
    """Plot reconstructed daily active counts over all cached activity history."""
    snapshots = reconstruct_task_count_history(active_projects, events, today=today)
    fig = go.Figure()
    dates = [row["date"] for row in snapshots]
    for (key, label), color in zip(_SERIES, _COLORS):
        counts = [int(row[key]) for row in snapshots]
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[_soft_scale(value) for value in counts],
                customdata=counts,
                name=label,
                mode="lines",
                line={
                    "color": color,
                    "width": 2.5,
                    "shape": "spline",
                    "smoothing": 0.7,
                },
                hovertemplate=(
                    "%{x}<br>%{customdata:,} tasks<extra>" + label + "</extra>"
                ),
            )
        )

    maximum_count = max(int(row["total"]) for row in snapshots)
    tick_counts = [0, 10, 50, 100, 250, 500, 1000, 1500, 2000, 2500, 3000]
    tick_counts = [value for value in tick_counts if value <= maximum_count * 1.2]
    first_day = date.fromisoformat(str(dates[0]))
    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="#111318",
        paper_bgcolor="#111318",
        xaxis={
            "title": "Date",
            "type": "date",
            "tickformat": "%b %-d\n%Y",
            "range": [
                (first_day - timedelta(days=1)).isoformat(),
                (today + timedelta(days=1)).isoformat(),
            ],
            "rangeslider": {"visible": len(snapshots) > 1, "thickness": 0.08},
        },
        yaxis={
            "title": "Active tasks (softened scale)",
            "tickmode": "array",
            "tickvals": [_soft_scale(value) for value in tick_counts],
            "ticktext": [f"{value:,}" for value in tick_counts],
            "rangemode": "tozero",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.03,
            "xanchor": "left",
            "x": 0,
            "bgcolor": "rgba(17,19,24,0.72)",
            "font": {"size": 11, "color": "#e6e6e6"},
        },
        margin={"l": 56, "r": 32, "t": 84, "b": 72},
        hovermode="x unified",
    )
    return apply_dashboard_axes(fig)
