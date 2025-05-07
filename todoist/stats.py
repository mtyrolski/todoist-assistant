from datetime import datetime
from functools import partial
from typing import Any

from loguru import logger

from todoist.types import Project


def all_tasks(project: Project):
    return len(project.tasks)


def priority_tasks(project: Project, prio: int) -> int:
    """
    Returns the number of tasks with a given priority in a project.
    :param project: The project to check.
    :param prio: The priority to check for.
    :return: The number of tasks with the given priority.
    """
    return len(list(filter(lambda task: task.task_entry.priority == prio, project.tasks)))


p1_tasks = partial(priority_tasks, prio=4)
p2_tasks = partial(priority_tasks, prio=3)
p3_tasks = partial(priority_tasks, prio=2)
p4_tasks = partial(priority_tasks, prio=1)


def any_labels(project: Project):
    return len([task for task in project.tasks if len(task.task_entry.labels) > 0])


def try_parse_date(date: str) -> datetime | None:
    parsing_formats = ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%fZ']

    for fmt in parsing_formats:
        try:
            return datetime.strptime(date, fmt)
        except ValueError:
            pass
    logger.error(f"Could not parse date {date} with any of the formats {parsing_formats}")
    return None


def extract_task_due_date(due: str | None | dict[str, Any]) -> datetime | None:
    if due is None:
        return None

    due_raw = due if isinstance(due, str) else due['date']
    return try_parse_date(due_raw)
