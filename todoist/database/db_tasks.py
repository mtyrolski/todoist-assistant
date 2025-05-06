import json
import uuid
from subprocess import run, PIPE, DEVNULL
from todoist.utils import get_api_key, try_n_times
from loguru import logger
from functools import partial
from todoist.types import Task
import inspect


class DatabaseTasks:
    """Database class to manage tasks in the Todoist API"""
    def __init__(self):
        super().__init__()

    def reset(self):
        pass

    def insert_task_from_template(self, task: Task, **overrrides) -> dict:
        """
        Insert a task into the database using a template and optional overrides.
        This method creates a new task by merging the task template provided in the
        'task' parameter with any keyword arguments passed as overrides. It first
        validates that the keys in the overrides are a subset of the parameters accepted
        by the 'insert_task' method. If any invalid keys are detected, it logs an error
        and returns a dictionary with an error message.
        The merging process combines the task template's attributes (obtained from
        task.task_entry.__dict__) with the overrides, and then filters the resulting
        dictionary to include only the keys that match the parameters expected by
        'insert_task'.
        Parameters:
            task (Task): The task template containing default task attributes.
            **overrrides: Arbitrary keyword arguments that override attributes from
                          the task template.
        Returns:
            dict: A dictionary indicating success or containing an error message if the
                  override keys are invalid.
        """
        param_names = inspect.signature(self.insert_task).parameters.keys()
        if any(k not in param_names for k in overrrides.keys()):
            logger.error(f'Invalid overrides: {overrrides.keys()} are not subset of {param_names}')
            return {'error': 'Invalid overrides'}

        merged_kwargs = {**task.task_entry.kwargs, **overrrides}
        final_kwargs = {k: v for k, v in merged_kwargs.items() if k in param_names}
        return self.insert_task(**final_kwargs)

    def insert_task(self,
                    content: str,
                    description: str = None,
                    project_id: str = None,
                    section_id: str = None,
                    parent_id: str = None,
                    order: int = None,
                    labels: list[str] = None,
                    priority: int = 1,
                    due_string: str = None,
                    due_date: str = None,
                    due_datetime: str = None,
                    due_lang: str = None,
                    assignee_id: str = None,
                    duration: int = None,
                    duration_unit: str = None,
                    deadline_date: str = None,
                    deadline_lang: str = None) -> dict:
        """
        Inserts a new task into the Todoist API.

        Parameters:
        - content (str): Task content. This value may contain markdown-formatted text and hyperlinks.
        - description (str): A description for the task.
        - project_id (str): Task project ID. If not set, task is put to user's Inbox.
        - section_id (str): ID of section to put task into.
        - parent_id (str): Parent task ID.
        - order (int): Non-zero integer value used by clients to sort tasks under the same parent.
        - labels (list[str]): The task's labels (a list of names that may represent either personal or shared labels).
        - priority (int): Task priority from 1 (normal) to 4 (urgent).
        - due_string (str): Human defined task due date (ex.: "next Monday", "Tomorrow").
        - due_date (str): Specific date in YYYY-MM-DD format relative to user’s timezone.
        - due_datetime (str): Specific date and time in RFC3339 format in UTC.
        - due_lang (str): 2-letter code specifying language in case due_string is not written in English.
        - assignee_id (str): The responsible user ID (only applies to shared tasks).
        - duration (int): A positive integer for the amount of duration_unit the task will take.
        - duration_unit (str): The unit of time that the duration field above represents. Must be either minute or day.
        - deadline_date (str): Specific date in YYYY-MM-DD format relative to user’s timezone.
        - deadline_lang (str): 2-letter code specifying language of deadline.

        Returns:
        - dict: Response from the Todoist API.
        Example response:
            {'id': '3501',
            'assigner_id': None,
            'assignee_id': None,
            'project_id': '226095',
            'section_id': None,
            'parent_id': None,
            'order': 3,
            'content': 'Buy milk',
            'description': '',
            'is_completed': False,
            'labels': [],
            'priority': 1,
            'comment_count': 0,
            'creator_id': '381',
            'created_at': '2025-03-13T21:16:27.284770Z',
            'due': None,
            'duration': None,
            'deadline': None}
        """
        url = "https://api.todoist.com/rest/v2/tasks"
        headers = {
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
            "Authorization": f"Bearer {get_api_key()}"
        }

        payload = {
            "content": content,
            "description": description,
            "project_id": project_id,
            "section_id": section_id,
            "parent_id": parent_id,
            "order": order,
            "labels": labels,
            "priority": priority,
            "due_string": due_string,
            "due_date": due_date,
            "due_datetime": due_datetime,
            "due_lang": due_lang,
            "assignee_id": assignee_id,
            "duration": duration,
            "duration_unit": duration_unit,
            "deadline_date": deadline_date,
            "deadline_lang": deadline_lang
        }

        # Remove keys with None values
        payload = {k: v for k, v in payload.items() if v is not None}
        cmds = [
            "curl", url, "-X", "POST", "--data",
            json.dumps(payload), "-H", "Content-Type: application/json", "-H",
            f"X-Request-Id: {headers['X-Request-Id']}", "-H", f"Authorization: {headers['Authorization']}"
        ]

        response = run(cmds, stdout=PIPE, stderr=PIPE, check=True)

        load_fn = partial(json.loads, response.stdout)

        decoded_result = try_n_times(load_fn, 3)
        if decoded_result is None:
            logger.error(f'Response: {response.stdout}')
            logger.error(f'Type: {type(decoded_result)}')
            logger.error(f'Keys: {decoded_result.keys()}')

        return decoded_result

    def remove_task(self, task_id: str) -> bool:
        """
        Removes (deletes) the specified task from the Todoist API.

        Returns:
        - True if the task was removed successfully.
        - False otherwise.
        """
        url = f"https://api.todoist.com/rest/v2/tasks/{task_id}"
        headers = {
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
            "Authorization": f"Bearer {get_api_key()}"
        }

        cmds = [
            "curl", url, "-X", "DELETE", "-H", "Content-Type: application/json", "-H",
            f"X-Request-Id: {headers['X-Request-Id']}", "-H", f"Authorization: {headers['Authorization']}"
        ]

        response = run(cmds, stdout=PIPE, stderr=DEVNULL, check=False)
        if response.returncode != 0:
            logger.error("Error deleting task from Todoist.")
            return False

        # No content (204) is returned for successful DELETE calls to Todoist
        if not response.stdout.strip():
            return True

        # If there's content, attempt to parse it
        try:
            decoded_result = json.loads(response.stdout)
            logger.debug(f"Response after delete: {decoded_result}")
        except json.JSONDecodeError:
            # If it fails to decode, consider it non-fatal
            logger.debug("Empty or invalid JSON returned after delete.")
            return True

        return True

    def fetch_task_by_id(self, task_id: str) -> dict:
        """
        Fetches a task by its ID from the Todoist API.

        Parameters:
        - task_id (str): The ID of the task to fetch.

        Returns:
        - dict: Response from the Todoist API containing task details.
        Example response:
            {
                "id": "2995104339",
                "content": "Buy Milk",
                "description": "",
                "project_id": "2203306141",
                "section_id": "7025",
                "parent_id": "2995104589",
                "order": 1,
                "labels": ["Food", "Shopping"],
                "priority": 1,
                "due": {
                    "date": "2016-09-01",
                    "is_recurring": false,
                    "datetime": "2016-09-01T12:00:00.000000Z",
                    "string": "tomorrow at 12",
                    "timezone": "Europe/Moscow"
                },
                "deadline": {
                    "date": "2016-09-04"
                },
                "duration": null,
                "is_completed": false,
                "url": "https://todoist.com/showTask?id=2995104339"
            }
        """
        url = f"https://api.todoist.com/rest/v2/tasks/{task_id}"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {get_api_key()}"}

        cmds = [
            "curl", url, "-X", "GET", "-H", "Content-Type: application/json", "-H",
            f"Authorization: {headers['Authorization']}"
        ]

        response = run(cmds, stdout=PIPE, stderr=DEVNULL, check=True)

        load_fn = partial(json.loads, response.stdout)

        decoded_result = try_n_times(load_fn, 3)
        if decoded_result is None:
            logger.error(f'Type: {type(decoded_result)}')
            logger.error(f'Keys: {decoded_result.keys()}')

        return decoded_result
