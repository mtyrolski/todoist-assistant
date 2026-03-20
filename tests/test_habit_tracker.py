from datetime import datetime
from typing import cast

import pandas as pd

from tests.factories import make_project, make_project_entry, make_task
from todoist.automations.habit_tracker import HabitTracker
from todoist.database.base import Database
from todoist.habit_tracker import TrackedHabitTask, summarize_tracked_habits


def _habit_df() -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "date": "2025-01-03",
                "task_id": "habit-1",
                "type": "completed",
            },
            {
                "date": "2025-01-07",
                "task_id": "habit-1",
                "type": "completed",
            },
            {
                "date": "2025-01-08",
                "task_id": "habit-1",
                "type": "rescheduled",
            },
            {
                "date": "2025-01-09",
                "task_id": "habit-2",
                "type": "completed",
            },
            {
                "date": "2025-01-10",
                "task_id": "habit-2",
                "type": "completed",
            },
            {
                "date": "2025-01-10",
                "task_id": "other-task",
                "type": "completed",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def test_summarize_tracked_habits_builds_weekly_and_all_time_counts() -> None:
    tracked_tasks = [
        TrackedHabitTask(
            task_id="habit-1",
            content="Morning walk",
            project_id="project-1",
            project_name="Health",
            project_color="green",
        ),
        TrackedHabitTask(
            task_id="habit-2",
            content="Journal",
            project_id="project-2",
            project_name="Growth",
            project_color="blue",
        ),
    ]

    summary = summarize_tracked_habits(
        _habit_df(),
        tracked_tasks,
        anchor=datetime(2025, 1, 15, 12, 0, 0),
        history_weeks=2,
    )

    assert summary["label"] == "2025-01-06 to 2025-01-12"
    assert summary["trackedCount"] == 2
    assert summary["totals"] == {
        "weeklyCompleted": 3,
        "weeklyRescheduled": 1,
        "allTimeCompleted": 4,
        "allTimeRescheduled": 1,
    }
    assert summary["history"] == [
        {"label": "2024-12-30 to 2025-01-05", "completed": 1, "rescheduled": 0},
        {"label": "2025-01-06 to 2025-01-12", "completed": 3, "rescheduled": 1},
    ]

    first_item = summary["items"][0]
    second_item = summary["items"][1]
    assert first_item["name"] == "Journal"
    assert first_item["weeklyCompleted"] == 2
    assert first_item["weeklyRescheduled"] == 0
    assert first_item["reliability"] == 100.0
    assert second_item["name"] == "Morning walk"
    assert second_item["weeklyCompleted"] == 1
    assert second_item["weeklyRescheduled"] == 1
    assert second_item["allTimeCompleted"] == 2
    assert second_item["allTimeRescheduled"] == 1
    assert abs(second_item["reliability"] - 66.67) < 0.01


def test_habit_tracker_posts_comment_once_per_task_and_week(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)

    tracked_task = make_task("habit-1", content="Morning walk", labels=["track_habit"])
    untracked_task = make_task("task-2", content="Inbox zero", labels=["ops"])
    project = make_project(
        project_id="project-1",
        project_entry=make_project_entry(project_id="project-1", name="Health"),
        tasks=[tracked_task, untracked_task],
    )

    comments: list[tuple[str, str]] = []

    class _FakeDb:
        def fetch_projects(self, include_tasks: bool = True):
            assert include_tasks is True
            return [project]

        def create_comment(self, *, task_id: str, content: str):
            comments.append((task_id, content))
            return {"task_id": task_id, "content": content}

    monkeypatch.setattr(
        "todoist.automations.habit_tracker.automation.load_activity_data",
        lambda db: _habit_df(),
    )
    monkeypatch.setattr(
        "todoist.automations.habit_tracker.automation.datetime",
        type(
            "_FixedDateTime",
            (),
            {"now": staticmethod(lambda: datetime(2025, 1, 15, 12, 0, 0))},
        ),
    )

    automation = HabitTracker(history_weeks=4, frequency_in_minutes=0)

    first_run = automation.tick(cast(Database, _FakeDb()))
    second_run = automation.tick(cast(Database, _FakeDb()))

    assert len(first_run) == 1
    assert second_run == []
    assert comments == [
        (
            "habit-1",
            "\n".join(
                [
                    "Habit tracker update for 2025-01-06 to 2025-01-12",
                    "",
                    "- Completed this week: 1",
                    "- Rescheduled this week: 1",
                    "- All-time completions: 2",
                    "- All-time reschedules: 1",
                    "- Reliability: 66.67%",
                ]
            ),
        )
    ]
