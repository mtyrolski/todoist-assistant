"""Definitions for Todoist API endpoints."""


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

    API_BASE = "https://api.todoist.com/api/v1"

    # Tasks
    CREATE_TASK = Endpoint("create_task", "POST", f"{API_BASE}/tasks")
    GET_TASK = Endpoint("get_task", "GET", f"{API_BASE}/tasks/{{task_id}}")
    UPDATE_TASK = Endpoint("update_task", "POST", f"{API_BASE}/tasks/{{task_id}}")
    DELETE_TASK = Endpoint("delete_task", "DELETE", f"{API_BASE}/tasks/{{task_id}}")
    CREATE_COMMENT = Endpoint("create_comment", "POST", f"{API_BASE}/comments")

    # Labels
    LIST_LABELS = Endpoint("list_labels", "GET", f"{API_BASE}/labels")

    # Activity
    LIST_ACTIVITY = Endpoint("list_activity", "GET", f"{API_BASE}/activities")

    # Projects
    LIST_PROJECTS = Endpoint("list_projects", "GET", f"{API_BASE}/projects")
    LIST_ARCHIVED_PROJECTS = Endpoint("list_archived_projects", "GET", f"{API_BASE}/projects/archived")
    GET_PROJECT = Endpoint("get_project", "GET", f"{API_BASE}/projects/{{project_id}}")
    GET_PROJECT_FULL = Endpoint("get_project_full", "GET", f"{API_BASE}/projects/{{project_id}}/full")

    # Sync
    SYNC = Endpoint("sync", "POST", f"{API_BASE}/sync")
