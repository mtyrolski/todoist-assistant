

from datetime import datetime
from typing import Any

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.database.dataframe import load_activity_data
from todoist.habit_tracker import (
    TRACK_HABIT_LABEL,
    DEFAULT_HABIT_HISTORY_WEEKS,
    extract_tracked_habit_tasks,
    habit_comment_fingerprint,
    render_habit_comment,
    summarize_tracked_habits,
)
from todoist.utils import Cache


class HabitTracker(Automation):
    def __init__(
        self,
        name: str = "Habit Tracker",
        frequency_in_minutes: float = 60.0 * 24.0 * 7.0,
        label_name: str = TRACK_HABIT_LABEL,
        history_weeks: int = DEFAULT_HABIT_HISTORY_WEEKS,
    ) -> None:
        super().__init__(name=name, frequency=frequency_in_minutes, is_long=False)
        self.label_name = label_name
        self.history_weeks = history_weeks

    def _tick(self, db: Database) -> list[dict[str, Any]]:
        active_projects = db.fetch_projects(include_tasks=True)
        tracked_tasks = extract_tracked_habit_tasks(
            active_projects, label_name=self.label_name
        )
        if not tracked_tasks:
            logger.info(
                "Habit tracker found no tasks labeled '{}'; skipping.",
                self.label_name,
            )
            return []

        df_activity = load_activity_data(db)
        summary = summarize_tracked_habits(
            df_activity,
            tracked_tasks,
            anchor=datetime.now(),
            history_weeks=self.history_weeks,
        )
        period_label = str(summary["label"])
        period_key = str(summary["weekEnd"])

        cache = Cache()
        posted_by_task = cache.habit_tracker_posts.load()
        results: list[dict[str, Any]] = []

        for item in summary["items"]:
            task_id = str(item["taskId"])
            fingerprint = habit_comment_fingerprint(item, period_label=period_label)
            task_posts = posted_by_task.get(task_id, {})
            if not isinstance(task_posts, dict):
                task_posts = {}
            if task_posts.get(period_key) == fingerprint:
                logger.debug(
                    "Habit tracker already posted summary for task {} and week {}",
                    task_id,
                    period_key,
                )
                continue

            comment = render_habit_comment(item, period_label=period_label)
            db.create_comment(task_id=task_id, content=comment)
            task_posts[period_key] = fingerprint
            posted_by_task[task_id] = task_posts
            results.append(
                {
                    "taskId": task_id,
                    "period": period_label,
                    "weeklyCompleted": item["weeklyCompleted"],
                    "weeklyRescheduled": item["weeklyRescheduled"],
                }
            )

        cache.habit_tracker_posts.save(posted_by_task)
        logger.info(
            "Habit tracker posted {} weekly update(s) for {} tracked task(s).",
            len(results),
            len(tracked_tasks),
        )
        return results
