
import inspect
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from typing import Any

from loguru import logger
from tqdm import tqdm

from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.api.client import EndpointCallResult
from todoist.types import Task
from todoist.utils import MaxRetriesExceeded, RETRY_MAX_ATTEMPTS, with_retry


class DatabaseTasks:
    """Database class to manage tasks in the Todoist API"""
    def __init__(self):
        super().__init__()
        self._api_client = TodoistAPIClient()

    def reset(self):
        pass

    @property
    def last_call_details(self) -> EndpointCallResult | None:
        """Expose metadata about the most recent API call."""

        return self._api_client.last_call_result

    def insert_task_from_template(self, task: Task, **overrrides: Any) -> dict[str, Any]:
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

    def insert_task(
        self,
        content: str,
        description: str | None = None,
        project_id: str | None = None,
        section_id: str | None = None,
        parent_id: str | None = None,
        order: int | None = None,
        labels: list[str] | None = None,
        priority: int = 1,
        due_string: str | None = None,
        due_date: str | None = None,
        due_datetime: str | None = None,
        due_lang: str | None = None,
        assignee_id: int | str | None = None,
        duration: int | None = None,
        duration_unit: str | None = None,
        deadline_date: str | None = None,
        deadline_lang: str | None = None,
    ) -> dict[str, Any]:
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

        payload = {k: v for k, v in payload.items() if v is not None}

        spec = RequestSpec(
            endpoint=TodoistEndpoints.CREATE_TASK,
            headers={
                "Content-Type": "application/json",
                "X-Request-Id": str(uuid.uuid4()),
            },
            json_body=payload,
            rate_limited=True,
        )

        logger.debug("Creating task via Todoist API", payload=payload)
        result: Any | None = self._api_client.request_json(spec, operation_name="create task")
        if result is None:
            logger.error("Todoist API returned empty response for task creation")
            return {}
        if isinstance(result, dict):
            return result
        return {"result": result}

    def remove_task(self, task_id: str) -> bool:
        """
        Removes (deletes) the specified task from the Todoist API.

        Returns:
        - True if the task was removed successfully.
        - False otherwise.
        """
        spec = RequestSpec(
            endpoint=TodoistEndpoints.DELETE_TASK.format(task_id=task_id),
            headers={
                "Content-Type": "application/json",
                "X-Request-Id": str(uuid.uuid4()),
            },
        )

        logger.debug("Deleting task", task_id=task_id)
        result = self._api_client.request(spec, operation_name=f"delete task {task_id}")
        if result.status_code not in (200, 204):
            logger.error("Unexpected status when deleting task", status=result.status_code)
            return False
        if result.text:
            logger.debug("Todoist delete response", body=result.text)
        return True

    def update_task(
        self,
        task_id: str,
        *,
        content: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        priority: int | None = None,
        due_string: str | None = None,
        due_date: str | None = None,
        due_datetime: str | None = None,
        due_lang: str | None = None,
        duration: int | None = None,
        duration_unit: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing task via the Todoist REST API.

        Note: Todoist REST `POST /rest/v2/tasks/{task_id}` may return either:
        - `204 No Content` (common; empty body)
        - `200 OK` with a JSON task payload

        This method returns the JSON payload when present, otherwise `{}`.
        """

        payload = {
            "content": content,
            "description": description,
            "labels": labels,
            "priority": priority,
            "due_string": due_string,
            "due_date": due_date,
            "due_datetime": due_datetime,
            "due_lang": due_lang,
            "duration": duration,
            "duration_unit": duration_unit,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        if not payload:
            return {}

        spec = RequestSpec(
            endpoint=TodoistEndpoints.UPDATE_TASK.format(task_id=task_id),
            headers={
                "Content-Type": "application/json",
                "X-Request-Id": str(uuid.uuid4()),
            },
            json_body=payload,
            rate_limited=True,
        )

        logger.debug("Updating task via Todoist API", task_id=task_id, payload=payload)
        call_result = self._api_client.request(
            spec,
            expect_json=True,
            operation_name=f"update task {task_id}",
        )
        if call_result.json is None:
            return {}
        if isinstance(call_result.json, dict):
            return call_result.json
        return {"result": call_result.json}

    def update_task_content(self, task_id: str, content: str) -> dict[str, Any]:
        """Convenience helper to update task content only."""

        return self.update_task(task_id, content=content)

    def fetch_task_by_id(self, task_id: str) -> dict[str, Any]:
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
        spec = RequestSpec(
            endpoint=TodoistEndpoints.GET_TASK.format(task_id=task_id),
            headers={"Content-Type": "application/json"},
        )

        result: Any | None = self._api_client.request_json(spec, operation_name=f"fetch task {task_id}")
        if result is None:
            logger.error("Todoist API returned empty response for fetch_task_by_id")
            return {}
        if isinstance(result, dict):
            return result
        return {"result": result}

    def insert_tasks(self, tasks_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Inserts multiple tasks into the Todoist API in parallel using threading.
        
        This method provides thread-safe parallel task insertion with retry logic,
        similar to how fetch_projects works in db_projects.py.

        Parameters:
        - tasks_data (list[dict]): List of dictionaries, where each dictionary contains
          the parameters for insert_task (content, description, project_id, etc.)

        Returns:
        - list[dict]: List of responses from the Todoist API in the same order as input.
          Failed insertions will have an empty dict.
          
        Example:
            tasks_data = [
                {"content": "Buy milk", "project_id": "123", "priority": 2},
                {"content": "Call dentist", "due_string": "tomorrow"},
            ]
            results = db.insert_tasks(tasks_data)
        """
        if not tasks_data:
            logger.info("No tasks to insert")
            return []

        def insert_single_task(task_data: dict[str, Any], index: int) -> dict[str, Any]:
            """Insert a single task with its data."""
            try:
                return self.insert_task(**task_data)
            except (RuntimeError, ValueError, TypeError, KeyError) as e:
                logger.error(f"Failed to insert task at index {index}: {e.__class__.__name__}: {e}")
                return {}

        def insert_single_task_with_retry(task_data: dict[str, Any], index: int) -> dict[str, Any]:
            """Insert a single task with built-in retry logic."""
            return with_retry(
                partial(insert_single_task, task_data, index),
                operation_name=f"insert task {index} (content: {task_data.get('content', 'N/A')})",
                max_attempts=RETRY_MAX_ATTEMPTS
            )

        logger.info(f"Inserting {len(tasks_data)} tasks with thread pool")
        max_workers = min(8, len(tasks_data))
        ordered_results: list[dict[str, Any] | None] = [None] * len(tasks_data)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(insert_single_task_with_retry, task_data, idx): idx
                for idx, task_data in enumerate(tasks_data)
            }
            for future in tqdm(
                as_completed(future_to_index),
                total=len(tasks_data),
                desc='Inserting tasks',
                unit='task',
                position=0,
                leave=True
            ):
                idx = future_to_index[future]
                try:
                    result = future.result(timeout=60)
                except (MaxRetriesExceeded, RuntimeError, ValueError, TypeError, OSError) as e:  # pragma: no cover - defensive
                    logger.error(f"Failed inserting task at index {idx}: {e.__class__.__name__}: {e}")
                    result = {}
                ordered_results[idx] = result
                logger.debug(f"Inserted task {idx+1}/{len(tasks_data)}")

        # Replace any remaining None with empty dicts (should be rare)
        for i in range(len(ordered_results)):
            if ordered_results[i] is None:
                ordered_results[i] = {}

        return [result or {} for result in ordered_results]
