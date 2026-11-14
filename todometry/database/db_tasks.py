import uuid
from typing import Any

from loguru import logger

from todometry.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todometry.core.constants import TaskField


class DatabaseTasks:
    """Create tasks through the Todoist API."""

    def __init__(self):
        super().__init__()
        self._api_client = TodoistAPIClient()

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
