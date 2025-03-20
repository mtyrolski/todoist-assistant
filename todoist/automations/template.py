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
        
    def _tick(self, db: Database) -> None:
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
            due_date = task.task_entry.due_datetime
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

def get_default_template() -> dict:
    return {
        # Meetings, calls, syncs etc.
        'call': TaskTemplate('Call', 'Call someone', 0, children=[
            TaskTemplate('Setup meeting', 'Should be put on calendar.', due_date_days_difference=-3),
            TaskTemplate('Prepare agenda', 'Prepare agenda for the meeting', due_date_days_difference=-1), 
            TaskTemplate('Prepare notes', 'Prepare notes for the meeting', due_date_days_difference=-1),
            TaskTemplate('Attend meeting', 'Attend the meeting', due_date_days_difference=0),
            TaskTemplate('Write minutes', 'Write minutes for the meeting', due_date_days_difference=0),
            TaskTemplate('E-Mail follow up', 'Follow up on the meeting with notes', due_date_days_difference=0),
        ]),
        
        # Reading paper
        'literature': TaskTemplate('Read Paper', 'Read a research paper', 0, children=[
            TaskTemplate('Find paper', 'Find the paper to read', due_date_days_difference=-7),
            TaskTemplate('Print paper', 'Print the paper', due_date_days_difference=-6),
            TaskTemplate('Read paper', 'Spend time reading the paper', due_date_days_difference=0),
            TaskTemplate('Summarize paper', 'Write a summary of the paper', due_date_days_difference=1),
            TaskTemplate('Discuss paper', 'Discuss the content of the paper with peers', due_date_days_difference=2),
        ]),
        
        # Writing a report
        'report': TaskTemplate('Write Report', 'Write a detailed report', 0, children=[
            TaskTemplate('Research topic', 'Research the topic for the report', due_date_days_difference=-10),
            TaskTemplate('Outline report', 'Create an outline for the report', due_date_days_difference=-7),
            TaskTemplate('Draft report', 'Write the first draft of the report', due_date_days_difference=-5),
            TaskTemplate('Review draft', 'Review and revise the draft', due_date_days_difference=-3),
            TaskTemplate('Finalize report', 'Finalize the report', due_date_days_difference=-1),
        ]),
        
        # Project management
        'project_management': TaskTemplate('Project Management', 'Manage a project', 0, children=[
            TaskTemplate('Define project scope', 'Define the scope of the project', due_date_days_difference=-30),
            TaskTemplate('Create project plan', 'Create a detailed project plan', due_date_days_difference=-25),
            TaskTemplate('Assign tasks', 'Assign tasks to team members', due_date_days_difference=-20),
            TaskTemplate('Track progress', 'Track the progress of the project', due_date_days_difference=0),
            TaskTemplate('Review milestones', 'Review milestones and deliverables', due_date_days_difference=5),
            TaskTemplate('Close project', 'Close the project', due_date_days_difference=30),
        ]),
        
        # Onboarding new employee
        'onboarding': TaskTemplate('Onboarding', 'Onboard a new employee', 0, children=[
            TaskTemplate('Prepare workstation', 'Prepare the workstation for the new employee', due_date_days_difference=-7),
            TaskTemplate('Introduce team', 'Introduce the new employee to the team', due_date_days_difference=0),
            TaskTemplate('Provide training', 'Provide necessary training', due_date_days_difference=1),
            TaskTemplate('Assign mentor', 'Assign a mentor to the new employee', due_date_days_difference=2),
            TaskTemplate('Review progress', 'Review the progress of the new employee', due_date_days_difference=14),
        ]),
        
        # Event planning
        'event_planning': TaskTemplate('Event Planning', 'Plan an event', 0, children=[
            TaskTemplate('Define event objectives', 'Define the objectives of the event', due_date_days_difference=-60),
            TaskTemplate('Create event budget', 'Create a budget for the event', due_date_days_difference=-50),
            TaskTemplate('Book venue', 'Book the venue for the event', due_date_days_difference=-45),
            TaskTemplate('Send invitations', 'Send out invitations', due_date_days_difference=-30),
            TaskTemplate('Plan agenda', 'Plan the agenda for the event', due_date_days_difference=-20),
            TaskTemplate('Execute event', 'Execute the event', due_date_days_difference=0),
            TaskTemplate('Follow up', 'Follow up with attendees', due_date_days_difference=7),
        ]),
    }

if __name__ == "__main__":
    # Example usage
    template = Template({
        'daily': TaskTemplate('Daily', 'Daily tasks', 0, children=[
            TaskTemplate('Morning', 'Morning tasks', due_date_days_difference=5),
            TaskTemplate('Afternoon', 'Afternoon tasks', children=[TaskTemplate('Lunch', 'Lunch tasks', priority=1)]),
            TaskTemplate('Evening', 'Evening tasks')
        ]),
    })
    
    db = Database('.env')
    
    template.tick(db)
     
