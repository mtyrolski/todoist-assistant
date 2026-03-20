

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha1
from typing import Any, Sequence, cast

import pandas as pd

from todoist.types import Project

TRACK_HABIT_LABEL = "track_habit"
DEFAULT_HABIT_HISTORY_WEEKS = 8


def normalize_label_name(value: str) -> str:
    return value.strip().lstrip("@").lower()


@dataclass(frozen=True, slots=True)
class TrackedHabitTask:
    task_id: str
    content: str
    project_id: str
    project_name: str
    project_color: str


def extract_tracked_habit_tasks(
    projects: Sequence[Project],
    *,
    label_name: str = TRACK_HABIT_LABEL,
) -> list[TrackedHabitTask]:
    normalized_label = normalize_label_name(label_name)
    tracked: list[TrackedHabitTask] = []
    for project in projects:
        for task in project.tasks:
            task_labels = {
                normalize_label_name(str(label))
                for label in (task.task_entry.labels or [])
            }
            if normalized_label not in task_labels:
                continue
            tracked.append(
                TrackedHabitTask(
                    task_id=str(task.id),
                    content=str(task.task_entry.content),
                    project_id=str(project.id),
                    project_name=str(project.project_entry.name),
                    project_color=str(project.project_entry.color),
                )
            )
    tracked.sort(key=lambda item: (item.project_name.lower(), item.content.lower(), item.task_id))
    return tracked


def last_full_week_bounds(anchor: datetime | None = None) -> tuple[datetime, datetime, str]:
    reference = anchor or datetime.now()
    week_start = datetime.combine(
        reference.date() - timedelta(days=reference.weekday()),
        datetime.min.time(),
    )
    last_week_end = week_start
    last_week_start = last_week_end - timedelta(days=7)
    label = (
        f"{last_week_start.strftime('%Y-%m-%d')} "
        f"to {(last_week_end - timedelta(days=1)).strftime('%Y-%m-%d')}"
    )
    return last_week_start, last_week_end, label


def summarize_tracked_habits(
    df_activity: pd.DataFrame | None,
    tracked_tasks: Sequence[TrackedHabitTask],
    *,
    anchor: datetime | None = None,
    history_weeks: int = DEFAULT_HABIT_HISTORY_WEEKS,
) -> dict[str, Any]:
    history_weeks = max(1, history_weeks)
    week_beg, week_end, label = last_full_week_bounds(anchor)

    history: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    tracked_ids = {task.task_id for task in tracked_tasks}

    if df_activity is None or df_activity.empty or not tracked_ids:
        filtered = pd.DataFrame(columns=["task_id", "type"])
        filtered.index = pd.to_datetime(pd.Index([], name="date"))
    else:
        task_id_series = cast(pd.Series, df_activity["task_id"]).astype(str)
        filtered = cast(
            pd.DataFrame,
            df_activity[task_id_series.isin(list(tracked_ids))].copy(),
        )

    for offset in reversed(range(history_weeks)):
        end = week_end - timedelta(days=7 * offset)
        beg = end - timedelta(days=7)
        in_window = filtered[(filtered.index >= beg) & (filtered.index < end)]
        history.append(
            {
                "label": (
                    f"{beg.strftime('%Y-%m-%d')} "
                    f"to {(end - timedelta(days=1)).strftime('%Y-%m-%d')}"
                ),
                "completed": int((in_window["type"] == "completed").sum()),
                "rescheduled": int((in_window["type"] == "rescheduled").sum()),
            }
        )

    for task in tracked_tasks:
        task_df = cast(
            pd.DataFrame,
            filtered[cast(pd.Series, filtered["task_id"]).astype(str) == task.task_id],
        )
        weekly_df = cast(
            pd.DataFrame,
            task_df[(task_df.index >= week_beg) & (task_df.index < week_end)],
        )
        weekly_completed = int((weekly_df["type"] == "completed").sum())
        weekly_rescheduled = int((weekly_df["type"] == "rescheduled").sum())
        all_time_completed = int((task_df["type"] == "completed").sum())
        all_time_rescheduled = int((task_df["type"] == "rescheduled").sum())
        reliability_base = all_time_completed + all_time_rescheduled
        reliability = (
            round((all_time_completed / reliability_base) * 100, 2)
            if reliability_base
            else None
        )
        items.append(
            {
                "taskId": task.task_id,
                "name": task.content,
                "projectId": task.project_id,
                "projectName": task.project_name,
                "color": task.project_color,
                "weeklyCompleted": weekly_completed,
                "weeklyRescheduled": weekly_rescheduled,
                "allTimeCompleted": all_time_completed,
                "allTimeRescheduled": all_time_rescheduled,
                "reliability": reliability,
            }
        )

    items.sort(
        key=lambda item: (
            -int(item["weeklyCompleted"]),
            int(item["weeklyRescheduled"]),
            -int(item["allTimeCompleted"]),
            str(item["name"]).lower(),
        )
    )

    total_weekly_completed = sum(int(item["weeklyCompleted"]) for item in items)
    total_weekly_rescheduled = sum(int(item["weeklyRescheduled"]) for item in items)
    total_all_time_completed = sum(int(item["allTimeCompleted"]) for item in items)
    total_all_time_rescheduled = sum(int(item["allTimeRescheduled"]) for item in items)

    return {
        "label": label,
        "weekBeg": week_beg.strftime("%Y-%m-%d"),
        "weekEnd": (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "trackedCount": len(tracked_tasks),
        "totals": {
            "weeklyCompleted": total_weekly_completed,
            "weeklyRescheduled": total_weekly_rescheduled,
            "allTimeCompleted": total_all_time_completed,
            "allTimeRescheduled": total_all_time_rescheduled,
        },
        "items": items,
        "history": history,
    }


def render_habit_comment(task_summary: dict[str, Any], *, period_label: str) -> str:
    reliability = task_summary.get("reliability")
    reliability_line = (
        f"- Reliability: {float(reliability):.2f}%"
        if reliability is not None
        else "- Reliability: N/A"
    )
    return "\n".join(
        [
            f"Habit tracker update for {period_label}",
            "",
            f"- Completed this week: {int(task_summary.get('weeklyCompleted', 0))}",
            f"- Rescheduled this week: {int(task_summary.get('weeklyRescheduled', 0))}",
            f"- All-time completions: {int(task_summary.get('allTimeCompleted', 0))}",
            f"- All-time reschedules: {int(task_summary.get('allTimeRescheduled', 0))}",
            reliability_line,
        ]
    )


def habit_comment_fingerprint(task_summary: dict[str, Any], *, period_label: str) -> str:
    payload = (
        f"{period_label}|{task_summary.get('taskId')}|"
        f"{task_summary.get('weeklyCompleted')}|{task_summary.get('weeklyRescheduled')}|"
        f"{task_summary.get('allTimeCompleted')}|{task_summary.get('allTimeRescheduled')}"
    )
    return sha1(payload.encode("utf-8")).hexdigest()
