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
        all_tasks: list[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(all_tasks)} tasks in total")
        all_unique_labels = set(tag for task in all_tasks for tag in task.task_entry.labels)
        logger.debug(f"Found {len(all_unique_labels)} unique labels")

        tasks_to_multiply = list(
            filter(lambda task: any(is_multiplication_label(tag) for tag in task.task_entry.labels), all_tasks))

        # Sort by depth so parent tasks are processed before their subtasks.
        # Depth is computed from the parent chain (root tasks have depth 0).
        task_by_id: dict[str, Task] = {task.id: task for task in all_tasks}
        depth_cache: dict[str, int] = {}

        def depth(task: Task) -> int:
            task_id = task.id
            if task_id in depth_cache:
                return depth_cache[task_id]

            seen: set[str] = set()
            current: Task | None = task
            current_depth = 0
            while current is not None:
                if current.id in seen:
                    logger.warning(
                        f"Detected parent cycle while computing depth for task {task_id}; treating as root"
                    )
                    current_depth = 0
                    break
                seen.add(current.id)

                parent_id = current.task_entry.parent_id or current.task_entry.v2_parent_id
                if parent_id is None:
                    break

                parent = task_by_id.get(parent_id)
                if parent is None:
                    # Parent not present in the fetched snapshot; treat as root boundary.
                    break

                # If we already know the parent's depth, we can finish quickly.
                if parent.id in depth_cache:
                    current_depth += 1 + depth_cache[parent.id]
                    break

                current_depth += 1
                current = parent

            depth_cache[task_id] = current_depth
            return current_depth

        tasks_to_multiply.sort(key=depth)

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
