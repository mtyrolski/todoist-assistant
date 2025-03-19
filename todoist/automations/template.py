from inspect import signature
from typing import Final, Iterable
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.types import Task, TaskEntry
from loguru import logger
from datetime import datetime, timedelta

FROM_TEMPLATE_LABEL_PREFIX: Final[str] = 'template-'

class TaskTemplate:
    def __init__(self, 
                 content: str,
                 description: str = None,
                 due_date_days_difference: int | None = None,
                 priority: int = 4,
                 children: list['TaskTemplate'] = []):
        self.due_date_days_difference = due_date_days_difference
        self.content = content
        self.description = description
        self.priority = priority
        self.children: list['TaskTemplate'] = children
        

    def walk(self, skip_root=False):
        if not skip_root:
            yield self
        for child in self.children:
            yield from child.walk()

class Template(Automation):
    def __init__(self, task_templates: dict[str, TaskTemplate]):
        super().__init__("Template", 1)
        self.task_templates = task_templates
        
    def _tick(self, db):
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: Iterable[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(list(all_tasks))} tasks in total")
        all_unique_labels = set(tag for task in all_tasks for tag in task.task_entry.labels)
        logger.debug(f"Found {len(all_unique_labels)} unique labels: {all_unique_labels}")

        task_to_initialize_from_template = list(
            filter(lambda task: any(tag.startswith(FROM_TEMPLATE_LABEL_PREFIX) for tag in task.task_entry.labels), all_tasks))
        
        logger.info(f"Found {len(task_to_initialize_from_template)} tasks to initialize from template")
        
        def insert_subtasks(root_task: Task, parent_id: int, task_template: TaskTemplate, parent_due_date: datetime | None):
            for child in task_template.children:
                if child.due_date_days_difference is not None and parent_due_date is not None:
                    subtask_due_date = (parent_due_date + timedelta(days=child.due_date_days_difference)).strftime('%Y-%m-%d')
                else:
                    subtask_due_date = None

                child_insertion_result = db.insert_task(
                    content=child.content, 
                    description=child.description, 
                    project_id=task.task_entry.project_id, 
                    parent_id=parent_id, 
                    priority=child.priority, 
                    due_date=subtask_due_date
                )
                
                if 'id' in child_insertion_result:
                    insert_subtasks(root_task, child_insertion_result['id'], child, parent_due_date)
                else:
                    logger.error(f"Failed to insert subtask {child.content}")
        
        for task in task_to_initialize_from_template:
            template_label = next(filter(lambda tag: tag.startswith(FROM_TEMPLATE_LABEL_PREFIX), task.task_entry.labels))
            template_name = template_label[len(FROM_TEMPLATE_LABEL_PREFIX):]
            if template_name not in self.task_templates:
                logger.error(f"Template {template_name} not found")
                continue
            template_ = self.task_templates[template_name]
            
            
            # Calculate the due date for the root task
            due_date = datetime.strptime(task.task_entry.due, '%Y-%m-%d') if task.task_entry.due else None
            root_task_due_date = due_date.strftime('%Y-%m-%d') if due_date else None

            labels_root = list(filter(lambda tag: not tag.startswith(FROM_TEMPLATE_LABEL_PREFIX), task.task_entry.labels))  
            root_insertion_result: dict = db.insert_task_from_template(
                task,
                content=f'{template_.content}: {task.task_entry.content}', 
                description=template_.description, 
                priority=template_.priority, 
                due_date=root_task_due_date,
                labels=labels_root
            )
            
            if root_insertion_result is None or 'id' not in root_insertion_result:
                logger.error(f"Failed to initialize task from template {template_name}")
                continue
                    
            root_task_id: str = db.fetch_task_by_id(root_insertion_result['id'])
            fix_mapping = {
                'creator_id': 'user_id'
            }
            
            drop_mapping = {'self'}
            root_task_entry = root_task_id | fix_mapping
            root_task_entry = {k: v for k, v in root_task_entry.items() if k in signature(TaskEntry.__init__).parameters}
            lacking_params = set(signature(TaskEntry.__init__).parameters) - set(root_task_entry.keys())
            for param in lacking_params:
                root_task_entry[param] = None

            for drop in drop_mapping:
                root_task_entry.pop(drop, None)
                
            
            root_task = Task(id=root_insertion_result['id'], task_entry=TaskEntry(**root_task_entry))
            insert_subtasks(root_task, root_insertion_result['id'], template_, due_date)
            
            db.remove_task(task.id)
            logger.info(f"Initialized task {task.id} from template {template_name}")        
            
if __name__ == "__main__":
    # Example usage
    template = Template({
        'daily': TaskTemplate('Daily', 'Daily tasks', 0, children=[
            TaskTemplate('Morning', 'Morning tasks'),
            TaskTemplate('Afternoon', 'Afternoon tasks', children=[TaskTemplate('Lunch', 'Lunch tasks', priority=1)]),
            TaskTemplate('Evening', 'Evening tasks')
        ]),
    })
    
    db = Database('.env')
    
    template.tick(db)
     
