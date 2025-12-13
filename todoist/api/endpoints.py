"""Definitions for Todoist API endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Endpoint:
    """A strongly typed definition of an API endpoint."""

    name: str
    method: str
    url: str

    def format(self, **kwargs) -> "Endpoint":
        """Return a new endpoint with ``url`` formatted using ``kwargs``."""

        return Endpoint(name=self.name, method=self.method, url=self.url.format(**kwargs))


class TodoistEndpoints:
    """Central registry of Todoist HTTP endpoints."""

    REST_BASE = "https://api.todoist.com/rest/v2"
    SYNC_BASE = "https://api.todoist.com/sync/v9"

    # Tasks
    CREATE_TASK = Endpoint("create_task", "POST", f"{REST_BASE}/tasks")
    GET_TASK = Endpoint("get_task", "GET", f"{REST_BASE}/tasks/{{task_id}}")
    UPDATE_TASK = Endpoint("update_task", "POST", f"{REST_BASE}/tasks/{{task_id}}")
    DELETE_TASK = Endpoint("delete_task", "DELETE", f"{REST_BASE}/tasks/{{task_id}}")

    # Labels
    LIST_LABELS = Endpoint("list_labels", "GET", f"{REST_BASE}/labels")

    # Activity
    LIST_ACTIVITY = Endpoint("list_activity", "GET", f"{SYNC_BASE}/activity/get")

    # Projects
    LIST_ARCHIVED_PROJECTS = Endpoint("list_archived_projects", "GET", f"{SYNC_BASE}/projects/get_archived")
    GET_PROJECT_DATA = Endpoint("get_project_data", "POST", f"{SYNC_BASE}/projects/get_data")
    SYNC_PROJECTS = Endpoint("sync_projects", "POST", f"{SYNC_BASE}/sync")
