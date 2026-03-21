from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import cast, Optional

from loguru import logger
from tqdm import tqdm
from functools import partial
from todoist.types import Project, Task, ProjectEntry, TaskEntry
from todoist.utils import (
    TODOIST_COLOR_NAME_TO_RGB,
    safe_instantiate_entry,
    try_n_times,
    with_retry,
    RETRY_MAX_ATTEMPTS,
    report_tqdm_progress,
    get_max_concurrent_requests,
)
from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.api.client import EndpointCallResult


class DatabaseProjects:
    def __init__(self):
        super().__init__()
        self._api_client = TodoistAPIClient()
        self.archived_projects_cache: dict[str, Project] | None = None    # Not initialized yet
        self.projects_cache: list[Project] | None = None    # Not initialized yet
        self.mapping_project_id_to_root_cache: dict[str, Project] | None = None    # Not initialized yet
        self.mapping_project_name_to_color: dict[str, str] | None = None    # Not initialized yet

    def pull(self):
        self.fetch_archived_projects()
        self.fetch_projects(include_tasks=True)

    def reset(self):
        self.archived_projects_cache = None
        self.projects_cache = None
        self.mapping_project_id_to_root_cache = None
        self.pull()

    @property
    def last_call_details(self) -> EndpointCallResult | None:
        """Expose metadata about the most recent API call."""

        return self._api_client.last_call_result

    def fetch_archived_projects(self) -> list[Project]:
        if self.archived_projects_cache is not None:
            return list(self.archived_projects_cache.values())

        try:
            data_dicts = self._fetch_paginated_results(
                endpoint=TodoistEndpoints.LIST_ARCHIVED_PROJECTS,
                operation_name="list archived projects",
            )
        except Exception as exc:  # pragma: no cover - network safety
            logger.warning(f"Failed fetching archived projects: {exc}")
            self.archived_projects_cache = {}
            return []
        entries = map(lambda raw_dict: safe_instantiate_entry(ProjectEntry, **raw_dict), data_dicts)
        self.archived_projects_cache = {
            entry.id: Project(id=entry.id, project_entry=entry, tasks=[], is_archived=True) for entry in entries
        }
        return list(self.archived_projects_cache.values())

    def fetch_project_by_id(self, project_id: str, include_archived_in_search: bool = False) -> Project:
        """
        Does not include tasks. Falls back to the archived projects if the project is not found
        """
        spec = RequestSpec(
            endpoint=TodoistEndpoints.GET_PROJECT.format(project_id=project_id),
            rate_limited=True,
        )

        try:
            result_dict = self._api_client.request_json(
                spec, operation_name=f"get project {project_id}"
            )
        except Exception:
            if include_archived_in_search:
                if self.archived_projects_cache is None:
                    logger.info("Fetching archived projects")
                    archived = self.fetch_archived_projects()
                    self.archived_projects_cache = {project.id: project for project in archived}
                archived_project = self.archived_projects_cache.get(project_id, None)
                if archived_project is not None:
                    return archived_project
            raise

        if not isinstance(result_dict, dict):
            logger.error(f"Unexpected payload returned when fetching project {project_id}")
            raise RuntimeError(f"Todoist API returned invalid data for project {project_id}")

        project = safe_instantiate_entry(ProjectEntry, **result_dict)
        return Project(id=project.id, project_entry=project, tasks=[], is_archived=False)

    def fetch_projects(self, include_tasks: bool = True) -> list[Project]:
        logger.debug(f"Fetching projects (include_tasks={include_tasks})")
        if self.projects_cache is not None:
            logger.debug("Using cached projects")
            return self.projects_cache
        logger.debug("Projects not fetched yet. Fetching now.")

        result: list[Project] = []
        projects: list[ProjectEntry] = self._fetch_projects_data()

        if not include_tasks:
            return list(
                map(lambda project: Project(id=project.id, project_entry=project, tasks=[], is_archived=False),
                    projects))

        def process_project(project: ProjectEntry) -> Project:
            task_entries: list[TaskEntry] = self.fetch_project_tasks(project.id)
            tasks: list[Task] = [Task(id=task.id, task_entry=task) for task in task_entries]
            return Project(id=project.id, project_entry=project, tasks=tasks, is_archived=False)

        def process_project_with_retry(project: ProjectEntry) -> Project:
            """Process project with built-in retry logic."""
            return with_retry(
                partial(process_project, project),
                operation_name=f"fetch project {project.id}",
                max_attempts=RETRY_MAX_ATTEMPTS
            )

        if not projects:
            logger.info("No projects returned from API.")
            self.projects_cache = []
            return self.projects_cache

        logger.info(f"Fetching {len(projects)} projects (include_tasks={include_tasks}) with thread pool")
        max_workers = min(get_max_concurrent_requests(), len(projects))
        ordered_results: list[Optional[Project]] = [None] * len(projects)
        total_projects = len(projects)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {executor.submit(process_project_with_retry, proj): idx for idx, proj in enumerate(projects)}
            for completed, future in enumerate(
                tqdm(
                    as_completed(future_to_index),
                    total=total_projects,
                    desc='Querying project data',
                    unit='project',
                    position=0,
                    leave=True,
                ),
                start=1,
            ):
                idx = future_to_index[future]
                try:
                    proj_result = future.result(timeout=60)
                except (RuntimeError, ValueError, OSError) as e:  # pragma: no cover - defensive narrow
                    logger.error(f"Failed fetching project index {idx}: {e.__class__.__name__}: {e}")
                    proj_result = Project(id=projects[idx].id, project_entry=projects[idx], tasks=[], is_archived=False)
                ordered_results[idx] = proj_result
                logger.debug(f"Fetched tasks for project {proj_result.project_entry.name} ({idx+1}/{len(projects)})")
                report_tqdm_progress("Querying project data", completed, total_projects, "project")

        # Replace any remaining None with empty project shells (should be rare)
        for i, maybe_proj in enumerate(ordered_results):
            if maybe_proj is None:
                pentry = projects[i]
                ordered_results[i] = Project(id=pentry.id, project_entry=pentry, tasks=[], is_archived=False)

        result = cast(list[Project], ordered_results)  # ordered list of projects

        self.projects_cache = result
        return self.projects_cache

    def fetch_project_tasks(self, project_id: str) -> list[TaskEntry]:
        spec = RequestSpec(
            endpoint=TodoistEndpoints.GET_PROJECT_FULL.format(project_id=project_id),
            rate_limited=True,
        )

        result_dict = self._api_client.request_json(
            spec, operation_name=f"get project tasks {project_id}"
        )
        if not isinstance(result_dict, dict):
            raise RuntimeError(f"Unexpected payload returned when fetching project tasks {project_id}")

        tasks_data = result_dict.get("tasks")
        if not isinstance(tasks_data, list):
            raise RuntimeError(f"Unexpected tasks payload returned when fetching project tasks {project_id}")

        tasks: list[TaskEntry] = []
        for task in tasks_data:
            if not isinstance(task, dict):
                raise RuntimeError(f"Unexpected task record returned when fetching project tasks {project_id}")
            tasks.append(safe_instantiate_entry(TaskEntry, **task))

        return tasks

    def fetch_mapping_project_id_to_name(self) -> dict[str, str]:
        mapping: dict[str, str] = {
            project.id: project.project_entry.name for project in self.fetch_projects(include_tasks=False)
        }

        mapping.update({project.id: project.project_entry.name for project in self.fetch_archived_projects()})
        return mapping

    def fetch_mapping_project_name_to_id(self) -> dict[str, str]:
        mapping: dict[str, str] = {
            project.project_entry.name: project.id for project in self.fetch_projects(include_tasks=False)
        }

        mapping.update({project.project_entry.name: project.id for project in self.fetch_archived_projects()})
        return mapping

    def fetch_mapping_project_id_to_root(self) -> dict[str, "Project"]:
        if self.mapping_project_id_to_root_cache is not None:
            return self.mapping_project_id_to_root_cache

        archived_projects = {project.id: project for project in self.fetch_archived_projects()}
        projects = {project.id: project for project in self.fetch_projects(include_tasks=False)}
        all_projects = {**archived_projects, **projects}
        mapping_project_id_to_root: dict[str, Project] = {}

        logger.info("Building project hierarchy (active + archived) in memory")
        if not all_projects:
            self.mapping_project_id_to_root_cache = {}
            return self.mapping_project_id_to_root_cache

        # Project id -> root project id memoization to avoid repeated parent-chain traversals.
        root_id_cache: dict[str, str | None] = {}
        # Fallback roots resolved from API when parent chains reference unknown ids.
        fallback_root_cache: dict[str, Project | None] = {}

        all_project_ids = list(all_projects.keys())
        total_projects = len(all_project_ids)
        for completed, project_id in enumerate(
            tqdm(all_project_ids, total=total_projects, desc='Building project hierarchy', unit='project'),
            start=1,
        ):
            root_id = self._resolve_root_project_id_in_memory(
                project_id=project_id,
                all_projects=all_projects,
                root_id_cache=root_id_cache,
                fallback_root_cache=fallback_root_cache,
            )
            if root_id is None:
                report_tqdm_progress("Building project hierarchy", completed, total_projects, "project")
                continue

            root_project = all_projects.get(root_id)
            if root_project is None:
                root_project = fallback_root_cache.get(root_id)
            if root_project is not None:
                mapping_project_id_to_root[project_id] = root_project

            report_tqdm_progress("Building project hierarchy", completed, total_projects, "project")

        self.mapping_project_id_to_root_cache = mapping_project_id_to_root
        return self.mapping_project_id_to_root_cache

    def fetch_mapping_project_id_to_color(self) -> dict[str, str]:
        """
        Fetches a mapping of project IDs to their associated colors.
        """

        mapping: dict[str, str] = {
            project.id: project.project_entry.color for project in self.fetch_projects(include_tasks=False)
        }

        mapping.update({project.id: project.project_entry.color for project in self.fetch_archived_projects()})
        mapping.update({
            project.id: TODOIST_COLOR_NAME_TO_RGB[project.project_entry.color]
            for project in self.fetch_projects(include_tasks=False)
        })
        mapping.update({
            project.id: TODOIST_COLOR_NAME_TO_RGB[project.project_entry.color]
            for project in self.fetch_archived_projects()
        })

        self.mapping_project_name_to_color = mapping

        return mapping

    def fetch_mapping_project_name_to_color(self) -> dict[str, str]:
        """
        Fetches a mapping of project names to their associated colors.
        """
        if self.mapping_project_name_to_color is not None:
            return self.mapping_project_name_to_color

        id_to_color = self.fetch_mapping_project_id_to_color()
        id_to_name = self.fetch_mapping_project_id_to_name()
        name_to_color = {id_to_name[project_id]: color for project_id, color in id_to_color.items()}
        self.mapping_project_name_to_color = name_to_color
        return name_to_color

    def _get_root_project(self, project_id: str) -> Optional[Project]:
        """Resolve the root ancestor project following parent chain."""
        project = try_n_times(partial(self.fetch_project_by_id, project_id), 3)
        if project is None:
            logger.error(f"Could not fetch project {project_id} after retries")
            return None
        parent_id = project.project_entry.parent_id
        if parent_id is None:
            return project
        # Recurse up
        return self._get_root_project(parent_id)

    def _resolve_root_project_id_in_memory(
        self,
        *,
        project_id: str,
        all_projects: dict[str, Project],
        root_id_cache: dict[str, str | None],
        fallback_root_cache: dict[str, Project | None],
    ) -> str | None:
        """
        Resolve root project id using local project metadata first, with memoized API fallback.
        """
        if project_id in root_id_cache:
            return root_id_cache[project_id]

        traversal_path: list[str] = []
        traversal_seen: set[str] = set()
        current_id = project_id
        while True:
            if current_id in root_id_cache:
                resolved_root_id = root_id_cache[current_id]
                break

            if current_id in traversal_seen:
                logger.warning(f"Detected project hierarchy cycle while resolving root for {project_id}")
                resolved_root_id = current_id
                break

            traversal_path.append(current_id)
            traversal_seen.add(current_id)
            current_project = all_projects.get(current_id)
            if current_project is None:
                fallback_root = fallback_root_cache.get(current_id)
                if current_id not in fallback_root_cache:
                    fallback_root = try_n_times(partial(self.fetch_project_by_id, current_id, True), 3)
                    fallback_root_cache[current_id] = fallback_root
                    if fallback_root is not None:
                        fallback_root_cache[fallback_root.id] = fallback_root

                resolved_root_id = fallback_root.id if fallback_root is not None else None
                break

            parent_id = current_project.project_entry.parent_id
            if parent_id is None:
                resolved_root_id = current_id
                break
            current_id = parent_id

        for seen_project_id in traversal_path:
            root_id_cache[seen_project_id] = resolved_root_id
        return resolved_root_id

    def _fetch_projects_data(self) -> list[ProjectEntry]:
        data_dicts = self._fetch_paginated_results(
            endpoint=TodoistEndpoints.LIST_PROJECTS,
            operation_name="list projects",
        )

        projects: list[ProjectEntry] = []
        for project in data_dicts:
            projects.append(safe_instantiate_entry(ProjectEntry, **project))

        return projects

    def _fetch_paginated_results(
        self,
        *,
        endpoint,
        operation_name: str,
        limit: int = 200,
    ) -> list[dict]:
        cursor: str | None = None
        results: list[dict] = []

        while True:
            params: dict[str, str | int] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            spec = RequestSpec(
                endpoint=endpoint,
                params=params,
                rate_limited=True,
            )
            payload = self._api_client.request_json(spec, operation_name=operation_name)
            page_results, next_cursor = self._extract_results_page(payload, operation_name=operation_name)
            results.extend(page_results)
            if not next_cursor:
                break
            cursor = next_cursor

        return results

    @staticmethod
    def _extract_results_page(payload: object, *, operation_name: str) -> tuple[list[dict], str | None]:
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected payload type returned from {operation_name}: {type(payload).__name__}")

        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise RuntimeError(f"Unexpected results payload returned from {operation_name}")

        page_results = [item for item in raw_results if isinstance(item, dict)]
        if len(page_results) != len(raw_results):
            raise RuntimeError(f"Unexpected non-object project record in {operation_name} response")
        next_cursor = payload.get("next_cursor")
        return page_results, str(next_cursor) if isinstance(next_cursor, str) else None

    def anonymize_sub_db(self, project_mapping: dict[str, str], label_mapping: dict[str, str] | None = None):
        logger.debug("Anonymizing projects in DatabaseProjects")
        if label_mapping is None:
            label_mapping = {}
        if not self.projects_cache:
            logger.debug("Projects not fetched yet. Fetching now.")
            self.fetch_projects(include_tasks=True)

        logger.debug(f"Project cache has {len(self.projects_cache) if self.projects_cache else 0} projects")
        # Ensure the color mapping is initialized

        if not self.mapping_project_name_to_color:
            _ = self.fetch_mapping_project_name_to_color()

        mapping_ref = self.mapping_project_name_to_color
        if mapping_ref is None:
            logger.error("Project name to color mapping not initialized; aborting anonymization.")
            return

        projects_to_rename = list(self.projects_cache or [])
        if self.archived_projects_cache:
            projects_to_rename.extend(self.archived_projects_cache.values())

        for ori_name, anonym_name in tqdm(project_mapping.items(), desc="Anonymizing projects", unit="project"):
            color = mapping_ref.pop(ori_name, None)
            if color is not None:
                mapping_ref[anonym_name] = color
            for project in projects_to_rename:
                if project.project_entry.name == ori_name:
                    project.project_entry.name = anonym_name

        logger.info(f"Anonymized {len(project_mapping)} projects.")
