import inspect
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from typing import Any, TypeVar

from loguru import logger
from tqdm import tqdm

from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.core.constants import TaskField
from todoist.api.client import EndpointCallResult
from todoist.core.types import Task
from todoist.features.ai_context import is_non_removable_content
from todoist.core.utils import (
    MaxRetriesExceeded,
    RETRY_MAX_ATTEMPTS,
    with_retry,
    get_max_concurrent_requests,
)

T = TypeVar("T")


@dataclass(frozen=True)
class TaskTemplateInsertRequest:
    template: Task
    overrides: dict[str, object]


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

    @staticmethod
    def _json_object_response(
        result: object, *, empty_error: str | None
    ) -> dict[str, Any]:
        if result is None:
            if empty_error is not None:
                logger.error(empty_error)
            return {}
        return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _json_headers(*, request_id: bool = True) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if request_id:
            headers["X-Request-Id"] = str(uuid.uuid4())
        return headers

    @staticmethod
    def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if value is not None}

    def _run_ordered_insert_batch(
        self,
        items: list[T],
        *,
        desc: str,
        operation_name: Callable[[T, int], str],
        insert_one: Callable[[T, int], dict[str, Any]],
        failure_label: str,
    ) -> list[dict[str, Any]]:
        logger.info(f"Inserting {len(items)} {desc.lower()} with thread pool")
        ordered_results: list[dict[str, Any] | None] = [None] * len(items)

        def insert_with_retry(item: T, index: int) -> dict[str, Any]:
            return with_retry(
                partial(insert_one, item, index),
                operation_name=operation_name(item, index),
                max_attempts=RETRY_MAX_ATTEMPTS,
            )

        with ThreadPoolExecutor(
            max_workers=min(get_max_concurrent_requests(), len(items))
        ) as executor:
            future_to_index = {
                executor.submit(insert_with_retry, item, idx): idx
                for idx, item in enumerate(items)
            }
            for future in tqdm(
                as_completed(future_to_index),
                total=len(items),
                desc=f"Inserting {desc}",
                unit="task",
                position=0,
                leave=True,
            ):
                idx = future_to_index[future]
                try:
                    result = future.result(timeout=60)
                except (
                    MaxRetriesExceeded,
                    RuntimeError,
                    ValueError,
                    TypeError,
                    OSError,
                ) as exc:  # pragma: no cover - defensive
                    logger.error(
                        f"Failed inserting {failure_label} at index {idx}: "
                        f"{exc.__class__.__name__}: {exc}"
                    )
                    result = {}
                ordered_results[idx] = result
                logger.debug(f"Inserted {failure_label} {idx + 1}/{len(items)}")

        return [result or {} for result in ordered_results]

    def insert_task_from_template(
        self, task: Task, **overrrides: Any
    ) -> dict[str, Any]:
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
            logger.error(
                f"Invalid overrides: {overrrides.keys()} are not subset of {param_names}"
            )
            return {"error": "Invalid overrides"}

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
        """Create a task via Todoist and return the decoded JSON payload."""
        payload = self._drop_none(
            {
                TaskField.CONTENT.value: content,
                TaskField.DESCRIPTION.value: description,
                TaskField.PROJECT_ID.value: project_id,
                TaskField.SECTION_ID.value: section_id,
                TaskField.PARENT_ID.value: parent_id,
                TaskField.ORDER.value: order,
                TaskField.LABELS.value: labels,
                TaskField.PRIORITY.value: priority,
                TaskField.DUE_STRING.value: due_string,
                TaskField.DUE_DATE.value: due_date,
                TaskField.DUE_DATETIME.value: due_datetime,
                TaskField.DUE_LANG.value: due_lang,
                TaskField.ASSIGNEE_ID.value: assignee_id,
                TaskField.DURATION.value: duration,
                TaskField.DURATION_UNIT.value: duration_unit,
                TaskField.DEADLINE_DATE.value: deadline_date,
                TaskField.DEADLINE_LANG.value: deadline_lang,
            }
        )

        spec = RequestSpec(
            endpoint=TodoistEndpoints.CREATE_TASK,
            headers=self._json_headers(),
            json_body=payload,
            rate_limited=True,
        )

        logger.debug("Creating task via Todoist API", payload=payload)
        result = self._api_client.request_json(spec, operation_name="create task")
        return self._json_object_response(
            result, empty_error="Todoist API returned empty response for task creation"
        )

    def remove_task(self, task_id: str) -> bool:
        """
        Removes (deletes) the specified task from the Todoist API.

        Returns:
        - True if the task was removed successfully.
        - False otherwise.
        """
        task_payload = self.fetch_task_by_id(task_id)
        if is_non_removable_content(task_payload.get("content")):
            logger.warning(
                "Refusing to delete protected task {} ({!r}); titles beginning with '* ' are non-removable.",
                task_id,
                task_payload.get("content"),
            )
            return False

        spec = RequestSpec(
            endpoint=TodoistEndpoints.DELETE_TASK.format(task_id=task_id),
            headers=self._json_headers(),
        )

        logger.debug("Deleting task", task_id=task_id)
        result = self._api_client.request(spec, operation_name=f"delete task {task_id}")
        if result.status_code not in (200, 204):
            logger.error(
                "Unexpected status when deleting task", status=result.status_code
            )
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

        Note: Todoist `POST /api/v1/tasks/{task_id}` may return either:
        - `204 No Content` (common; empty body)
        - `200 OK` with a JSON task payload

        This method returns the JSON payload when present, otherwise `{}`.
        """

        payload = self._drop_none(
            {
                TaskField.CONTENT.value: content,
                TaskField.DESCRIPTION.value: description,
                TaskField.LABELS.value: labels,
                TaskField.PRIORITY.value: priority,
                TaskField.DUE_STRING.value: due_string,
                TaskField.DUE_DATE.value: due_date,
                TaskField.DUE_DATETIME.value: due_datetime,
                TaskField.DUE_LANG.value: due_lang,
                TaskField.DURATION.value: duration,
                TaskField.DURATION_UNIT.value: duration_unit,
            }
        )
        if not payload:
            return {}

        spec = RequestSpec(
            endpoint=TodoistEndpoints.UPDATE_TASK.format(task_id=task_id),
            headers=self._json_headers(),
            json_body=payload,
            rate_limited=True,
        )

        logger.debug("Updating task via Todoist API", task_id=task_id, payload=payload)
        call_result = self._api_client.request(
            spec,
            expect_json=True,
            operation_name=f"update task {task_id}",
        )
        return self._json_object_response(call_result.json, empty_error=None)

    def update_task_content(self, task_id: str, content: str) -> dict[str, Any]:
        """Convenience helper to update task content only."""

        return self.update_task(task_id, content=content)

    def create_comment(
        self,
        *,
        content: str,
        task_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a Todoist comment for a task or project."""

        if bool(task_id) == bool(project_id):
            raise ValueError("Provide exactly one of task_id or project_id")

        payload: dict[str, Any] = {"content": content}
        if task_id is not None:
            payload["task_id"] = task_id
        if project_id is not None:
            payload["project_id"] = project_id

        spec = RequestSpec(
            endpoint=TodoistEndpoints.CREATE_COMMENT,
            headers=self._json_headers(),
            json_body=payload,
            rate_limited=True,
        )

        logger.debug("Creating Todoist comment", payload=payload)
        result = self._api_client.request_json(spec, operation_name="create comment")
        return self._json_object_response(
            result,
            empty_error="Todoist API returned empty response for comment creation",
        )

    def fetch_task_comments(self, task_id: str) -> list[dict[str, Any]]:
        """Fetch all comments attached to a task."""

        cursor: str | None = None
        comments: list[dict[str, Any]] = []

        while True:
            params: dict[str, str | int] = {"task_id": task_id}
            if cursor:
                params["cursor"] = cursor
            spec = RequestSpec(
                endpoint=TodoistEndpoints.LIST_COMMENTS,
                params=params,
                rate_limited=True,
            )
            payload = self._api_client.request_json(
                spec, operation_name=f"fetch task comments {task_id}"
            )

            page_comments, next_cursor = self._extract_comments_page(
                payload, operation_name=f"fetch task comments {task_id}"
            )
            comments.extend(page_comments)
            if not next_cursor:
                break
            cursor = next_cursor

        return comments

    def fetch_task_by_id(self, task_id: str) -> dict[str, Any]:
        """Fetch a task by ID from Todoist."""
        spec = RequestSpec(
            endpoint=TodoistEndpoints.GET_TASK.format(task_id=task_id),
            headers=self._json_headers(request_id=False),
        )

        result = self._api_client.request_json(
            spec, operation_name=f"fetch task {task_id}"
        )
        return self._json_object_response(
            result,
            empty_error="Todoist API returned empty response for fetch_task_by_id",
        )

    @staticmethod
    def _extract_comments_page(
        payload: object, *, operation_name: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        if isinstance(payload, list):
            comments = [item for item in payload if isinstance(item, dict)]
            if len(comments) != len(payload):
                raise RuntimeError(
                    f"Unexpected non-object comment record in {operation_name} response"
                )
            return comments, None

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected payload type returned from {operation_name}: {type(payload).__name__}"
            )

        raw_comments = payload.get("results")
        if raw_comments is None:
            raw_comments = payload.get("comments")
        if not isinstance(raw_comments, list):
            raise RuntimeError(
                f"Unexpected results payload returned from {operation_name}"
            )

        comments = [item for item in raw_comments if isinstance(item, dict)]
        if len(comments) != len(raw_comments):
            raise RuntimeError(
                f"Unexpected non-object comment record in {operation_name} response"
            )

        next_cursor = payload.get("next_cursor")
        return comments, str(next_cursor) if isinstance(next_cursor, str) else None

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
                logger.error(
                    f"Failed to insert task at index {index}: {e.__class__.__name__}: {e}"
                )
                return {}

        return self._run_ordered_insert_batch(
            tasks_data,
            desc="tasks",
            operation_name=lambda task_data, index: (
                f"insert task {index} "
                f"(content: {task_data.get(TaskField.CONTENT.value, 'N/A')})"
            ),
            insert_one=insert_single_task,
            failure_label="task",
        )

    def insert_tasks_from_templates(
        self,
        requests: list[TaskTemplateInsertRequest],
    ) -> list[dict[str, Any]]:
        """Insert multiple tasks from templates in parallel.

        Each request clones a source ``Task`` and applies the provided overrides
        through :meth:`insert_task_from_template`.
        """
        if not requests:
            logger.info("No template tasks to insert")
            return []

        def insert_single_request(
            request: TaskTemplateInsertRequest,
            index: int,
        ) -> dict[str, Any]:
            try:
                return self.insert_task_from_template(
                    request.template,
                    **request.overrides,
                )
            except (RuntimeError, ValueError, TypeError, KeyError) as exc:
                logger.error(
                    f"Failed to insert template task at index {index}: "
                    f"{exc.__class__.__name__}: {exc}"
                )
                return {}

        return self._run_ordered_insert_batch(
            requests,
            desc="template tasks",
            operation_name=lambda request, index: (
                f"insert template task {index} "
                f"(content: {request.overrides.get(TaskField.CONTENT.value, request.template.task_entry.content)})"
            ),
            insert_one=insert_single_request,
            failure_label="template task",
        )
