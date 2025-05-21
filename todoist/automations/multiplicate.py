import re
from typing import Iterable
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.types import Task
from loguru import logger


def is_multiplication_label(tag: str) -> bool:
    return bool(re.match(r"X\d+$", tag))


def extract_multiplication_factor(tag: str) -> int:
    match = re.match(r"X(\d+)$", tag)
    if match:
        return int(match.group(1))
    raise ValueError(f"Invalid multiplication label: {tag}")


class Multiply(Automation):
    def __init__(self):
        super().__init__("Multiply", 0.1)

    def _tick(self, db):
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: Iterable[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(list(all_tasks))} tasks in total")
        all_unique_labels = set(tag for task in all_tasks for tag in task.task_entry.labels)
        logger.debug(f"Found {len(all_unique_labels)} unique labels")

        tasks_to_multiply = list(
            filter(lambda task: any(is_multiplication_label(tag) for tag in task.task_entry.labels), all_tasks))

        logger.info(f"Found {len(tasks_to_multiply)} tasks to multiply")
        for task in tasks_to_multiply:
            matched_labels = list(filter(is_multiplication_label, task.task_entry.labels))
            if len(matched_labels) != 1:
                logger.error(f"Task {task.id} should have exactly one multiplication label, found: {matched_labels}")
                continue
            label = matched_labels[0]
            try:
                mul_factor = extract_multiplication_factor(label)
            except ValueError as e:
                logger.error(f"Error processing task {task.id}: {e}")
                continue

            labels_of_new_task = list(filter(lambda tag: not is_multiplication_label(tag), task.task_entry.labels))
            for i in range(1, mul_factor + 1):
                logger.debug(f"Creating task {task.task_entry.content} x{i}")
                db.insert_task_from_template(task, content=f"{task.task_entry.content} x{i}", labels=labels_of_new_task)
            logger.debug(f"Removing task {task.id}")
            if db.remove_task(task.id):
                logger.debug(f"Task {task.id} removed")


def main():
    multiply = Multiply()
    db = Database('.env')
    multiply.tick(db)


if __name__ == '__main__':
    main()
