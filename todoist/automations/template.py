from inspect import signature
from typing import Any, Final, Iterable, Mapping
from todoist.automations.base import Automation
from todoist.constants import TaskField
from todoist.database.base import Database
from todoist.types import Task, TaskEntry
from loguru import logger
from datetime import datetime, timedelta
import hydra
from omegaconf import DictConfig

FROM_TEMPLATE_LABEL_PREFIX: Final[str] = 'template-'


class TaskTemplate:
    """
    A template representation of a task, allowing for nested child tasks.
    Attributes:
        content (str): The main text or title of the task.
        description (str, optional): Additional details about the task.
        due_date_days_difference (int or None, optional): The number of days from today until the task is due. Defaults to 0
            (same day as the parent) when not provided.
        priority (int): The priority level of the task, where a higher value indicates higher priority. Defaults to 1.
        children (list[TaskTemplate]): A list of child TaskTemplate objects representing subtasks.
    """
    def __init__(self,
                 content: str,
                 description: str | None = None,
                 due_date_days_difference: int | None = 0,
                 priority: int = 1,
                 children: list['TaskTemplate'] | None = None):
        self.due_date_days_difference = due_date_days_difference
        self.content = content
        self.description = description
        self.priority = priority
        self.children: list['TaskTemplate'] = children or []

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | 'TaskTemplate') -> 'TaskTemplate':
        """Create a :class:`TaskTemplate` from a plain mapping.

        The YAML config files used to rely on Hydra targets for every task and
        subtask. This helper lets us load simpler dictionaries by applying the
        defaults defined in :class:`TaskTemplate` and recursively converting
        children.
        """

        if isinstance(config, TaskTemplate):
            return config

        content = config.get(TaskField.CONTENT.value)
        if content is None:
            raise ValueError(
                f"Missing required field '{TaskField.CONTENT.value}' in TaskTemplate config: {config}"
            )
        description = config.get(TaskField.DESCRIPTION.value)
        due_date_days_difference = config.get('due_date_days_difference', 0)
        priority = config.get(TaskField.PRIORITY.value, 1)
        children = [cls.from_config(child) for child in config.get('children', [])]

        return cls(content=content,
                   description=description,
                   due_date_days_difference=due_date_days_difference,
                   priority=priority,
                   children=children)

    @classmethod
    def priority_on_todoist(cls, priority: int) -> int:
        """
        Converts a priority value to the corresponding Todoist priority level.
        Args:
            priority (int): The priority value to convert.
        Returns:
            int: The corresponding Todoist priority level.
        """
        return 4 - priority

    def walk(self, skip_root=False) -> Iterable['TaskTemplate']:
        """
        Recursively iterates over the current node and its descendants in a depth-first manner.

        Args:
            skip_root (bool): If True, the generator skips yielding the current node (self) and only yields its children. Defaults to False.

        Yields:
            The current node and all descendant nodes (recursively) unless skip_root is True.
        """
        if not skip_root:
            yield self
        for child in self.children:
            yield from child.walk()


class Template(Automation):
    def __init__(self, task_templates: dict[str, TaskTemplate | Mapping[str, Any]]):
        super().__init__("Template", 0.1)
        self.task_templates = {
            name: TaskTemplate.from_config(task_template)
            for name, task_template in task_templates.items()
        }

    def _tick(self, db: Database) -> None:
        logger.info("Running Template automation")
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: Iterable[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(list(all_tasks))} tasks in total")
        all_unique_labels = set(tag for task in all_tasks for tag in task.task_entry.labels)
        logger.debug(f"Found {len(all_unique_labels)} unique labels")

        task_to_initialize_from_template = list(
            filter(lambda task: any(tag.startswith(FROM_TEMPLATE_LABEL_PREFIX) for tag in task.task_entry.labels),
                   all_tasks))

        logger.info(f"Found {len(task_to_initialize_from_template)} tasks to initialize from template")

        def insert_subtasks(root_task: Task, parent_id: int, task_template: TaskTemplate,
                            parent_due_date: datetime | None):
            for child in task_template.children:
                if child.due_date_days_difference is not None and parent_due_date is not None:
                    subtask_due_date = (parent_due_date +
                                        timedelta(days=child.due_date_days_difference)).strftime('%Y-%m-%d')
                else:
                    subtask_due_date = None

                child_insertion_result = db.insert_task(content=child.content,
                                                        description=child.description,
                                                        project_id=task.task_entry.project_id,
                                                        parent_id=parent_id,
                                                        priority=child.priority,
                                                        due_date=subtask_due_date)

                if 'id' in child_insertion_result:
                    insert_subtasks(root_task, child_insertion_result['id'], child, parent_due_date)
                else:
                    logger.error(f"Failed to insert subtask {child.content}")

        for task in task_to_initialize_from_template:
            template_label = next(filter(lambda tag: tag.startswith(FROM_TEMPLATE_LABEL_PREFIX),
                                         task.task_entry.labels))
            template_name = template_label[len(FROM_TEMPLATE_LABEL_PREFIX):]
            if template_name not in self.task_templates:
                logger.error(f"Template {template_name} not found")
                continue
            template_ = self.task_templates[template_name]

            # Calculate the due date for the root task
            if task.task_entry.due_datetime is None:
                due_datetime_child = None
                due_datetime_child_str = None
            else:
                due_datetime_parent = task.task_entry.due_datetime
                due_datetime_child = (due_datetime_parent + timedelta(days=template_.due_date_days_difference))
                due_datetime_child_str = due_datetime_child.strftime('%Y-%m-%dT%H:%M:%S')
            labels_root = list(
                filter(lambda tag: not tag.startswith(FROM_TEMPLATE_LABEL_PREFIX), task.task_entry.labels))
            root_insertion_result: dict = db.insert_task_from_template(
                task,
                content=f'{template_.content}: {task.task_entry.content}',
                description=template_.description,
                priority=task.task_entry.priority,
                due_datetime=due_datetime_child_str,
                labels=labels_root)

            if root_insertion_result is None or 'id' not in root_insertion_result:
                logger.error(f"Failed to initialize task from template {template_name}")
                continue

            root_task_id: str = db.fetch_task_by_id(root_insertion_result['id'])
            fix_mapping = {'creator_id': 'user_id'}

            drop_mapping = {'self'}
            root_task_entry = root_task_id | fix_mapping
            root_task_entry = {
                k: v for k, v in root_task_entry.items() if k in signature(TaskEntry.__init__).parameters
            }
            lacking_params = set(signature(TaskEntry.__init__).parameters) - set(root_task_entry.keys())
            for param in lacking_params:
                root_task_entry[param] = None

            for drop in drop_mapping:
                root_task_entry.pop(drop, None)

            root_task = Task(id=root_insertion_result['id'], task_entry=TaskEntry(**root_task_entry))
            insert_subtasks(root_task, root_insertion_result['id'], template_, due_datetime_child)

            db.remove_task(task.id)
            logger.info(f"Initialized task {task.id} from template {template_name}")


# pylint: disable=missing-function-docstring
@hydra.main(version_base=None, config_path=None)
def main(config: DictConfig) -> None:
    db = Database('.env')
    single_templates = hydra.utils.instantiate(config.automations)
    template = Template(single_templates)
    template.tick(db)


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
