# Multiply integration which look up over all active tasks, identify those with tag X2 X3 X5 or X10, then remove the tag and create new 2, 3, 5 or 10 tasks with the same content and other attributes. Only change is suffix of the task name identifying the multiplication factor.

from typing import Iterable
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.types import Task
from loguru import logger

MUL_LABELS = ['X2', 'X3', 'X5', 'X10']


class Multiply(Automation):
    def __init__(self):
        super().__init__("Multiply", 1)

    def _tick(self, db):
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: Iterable[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(list(all_tasks))} tasks in total")
        all_unique_labels = set(tag for task in all_tasks for tag in task.task_entry.labels)
        logger.debug(f"Found {len(all_unique_labels)} unique labels: {all_unique_labels}")

        tasks_to_multiply = list(
            filter(lambda task: any(tag in MUL_LABELS for tag in task.task_entry.labels), all_tasks))

        logger.info(f"Found {len(tasks_to_multiply)} tasks to multiply")
        for task in tasks_to_multiply:
            count_matched = len(list(filter(lambda tag: tag in MUL_LABELS, task.task_entry.labels)))
            if count_matched != 1:
                logger.error(f"Task {task.id} should have exactly one multiplication label")
                continue
            label = next(filter(lambda tag: tag in MUL_LABELS, task.task_entry.labels))
            mul_factor = int(label[1:])
            labels_of_new_task = list(filter(lambda tag: tag not in MUL_LABELS, task.task_entry.labels))
            for i in range(1, mul_factor + 1):
                logger.debug(f'Creating task {task.task_entry.content} x{i}')
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
