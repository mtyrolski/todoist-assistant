from __future__ import annotations

from typing import cast

import pandas as pd
from loguru import logger

from todoist.types import Task


def process_rescheduled_tasks(df_activity: pd.DataFrame, active_tasks: list[Task]) -> pd.DataFrame:
    rescheduled_counts = (
        df_activity[df_activity["type"] == "rescheduled"]
        .groupby(["title", "parent_project_name", "root_project_name"])
        .size()
    )
    rescheduled_counts = cast(pd.Series, rescheduled_counts)
    rescheduled_tasks = cast(
        pd.DataFrame,
        rescheduled_counts.sort_values(ascending=False).reset_index(name="reschedule_count"),
    )

    active_recurring_tasks = filter(lambda task: task.is_recurring, active_tasks)
    recurring_task_names = set(task.task_entry.content for task in active_recurring_tasks)

    filtered_tasks = cast(
        pd.DataFrame,
        rescheduled_tasks[~rescheduled_tasks["title"].isin(list(recurring_task_names))],
    )
    logger.debug(f"Found {len(filtered_tasks)} rescheduled tasks")
    return filtered_tasks

