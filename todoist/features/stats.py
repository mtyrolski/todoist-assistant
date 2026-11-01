from datetime import datetime
from functools import partial
from typing import Any

from loguru import logger

from todoist.core.types import Project


def priority_tasks(project: Project, prio: int) -> int:
    """
    Returns the number of tasks with a given priority in a project.
    :param project: The project to check.
    :param prio: The priority to check for.
    :return: The number of tasks with the given priority.
    """
    return sum(task.task_entry.priority == prio for task in project.tasks)


p1_tasks = partial(priority_tasks, prio=4)
p2_tasks = partial(priority_tasks, prio=3)
p3_tasks = partial(priority_tasks, prio=2)
p4_tasks = partial(priority_tasks, prio=1)


def try_parse_date(date: str) -> datetime | None:
    try:
        # Due dates describe the task's calendar date; preserve its wall clock.
        return datetime.fromisoformat(date.strip()).replace(tzinfo=None)
    except (TypeError, ValueError, AttributeError):
        logger.error("Could not parse date {}", date)
        return None


def extract_task_due_date(due: str | None | dict[str, Any]) -> datetime | None:
    if due is None:
        return None

    due_raw = due if isinstance(due, str) else due.get("date")
    return try_parse_date(due_raw) if isinstance(due_raw, str) else None
