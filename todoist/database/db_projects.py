from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import cast, Optional

from loguru import logger
from tqdm import tqdm
from functools import partial
from todoist.types import Project, Task, ProjectEntry, TaskEntry
from todoist.utils import TODOIST_COLOR_NAME_TO_RGB, safe_instantiate_entry, try_n_times, with_retry, RETRY_MAX_ATTEMPTS
from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.api.client import EndpointCallResult


class DatabaseProjects:
    def __init__(self):
        super().__init__()
        self._api_client = TodoistAPIClient()
        self.archived_projects_cache: dict[str, Project] | None = None    # Not initialized yet
        self.projects_cache: list[Project] | None = None    # Not initialized yet
        self.mapping_project_name_to_color: dict[str, str] | None = None    # Not initialized yet

    def pull(self):
        self.fetch_archived_projects()
        self.fetch_projects(include_tasks=True)

    def reset(self):
        self.archived_projects_cache = None
        self.projects_cache = None
        self.pull()

    @property
    def last_call_details(self) -> EndpointCallResult | None:
        """Expose metadata about the most recent API call."""

        return self._api_client.last_call_result

    def fetch_archived_projects(self) -> list[Project]:
        if self.archived_projects_cache is not None:
            return list(self.archived_projects_cache.values())

        spec = RequestSpec(endpoint=TodoistEndpoints.LIST_ARCHIVED_PROJECTS)
        data_dicts = self._api_client.request_json(spec, operation_name="list archived projects")
        if not isinstance(data_dicts, list):
            logger.error("Unexpected payload returned when fetching archived projects")
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
            endpoint=TodoistEndpoints.GET_PROJECT_DATA,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"project_id": project_id},
        )

        result_dict = self._api_client.request_json(
            spec, operation_name=f"get project {project_id}"
        )
        if not isinstance(result_dict, dict):
            logger.error("Unexpected payload returned when fetching project", project_id=project_id)
            raise RuntimeError(f"Todoist API returned invalid data for project {project_id}")

        if 'project' not in result_dict:
            logger.error(
                f"Error fetching project with id {project_id}. If it is archived, use include_archived_in_search=True")
            if include_archived_in_search:
                if self.archived_projects_cache is None:
                    logger.info("Fetching archived projects")
                    archived = self.fetch_archived_projects()
                    self.archived_projects_cache = {project.id: project for project in archived}
                return self.archived_projects_cache[project_id]

        project = safe_instantiate_entry(ProjectEntry, **result_dict['project'])
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
        max_workers = min(8, len(projects))
        ordered_results: list[Optional[Project]] = [None] * len(projects)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {executor.submit(process_project_with_retry, proj): idx for idx, proj in enumerate(projects)}
            for future in tqdm(as_completed(future_to_index), total=len(projects), desc='Querying project data', unit='project', position=0, leave=True):
                idx = future_to_index[future]
                try:
                    proj_result = future.result(timeout=60)
                except (RuntimeError, ValueError, OSError) as e:  # pragma: no cover - defensive narrow
                    logger.error(f"Failed fetching project index {idx}: {e.__class__.__name__}: {e}")
                    proj_result = Project(id=projects[idx].id, project_entry=projects[idx], tasks=[], is_archived=False)
                ordered_results[idx] = proj_result
                logger.debug(f"Fetched tasks for project {proj_result.project_entry.name} ({idx+1}/{len(projects)})")

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
            endpoint=TodoistEndpoints.GET_PROJECT_DATA,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"project_id": project_id},
        )

        result_dict = self._api_client.request_json(
            spec, operation_name=f"get project tasks {project_id}"
        )
        if not isinstance(result_dict, dict):
            logger.error("Unexpected payload returned when fetching project tasks", project_id=project_id)
            return []

        tasks = []
        for task in result_dict['items']:
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
        archived_projects = {project.id: project for project in self.fetch_archived_projects()}
        projects = {project.id: project for project in self.fetch_projects(include_tasks=False)}
        mapping_project_id_to_root: dict[str, "Project"] = {}

        def get_root_project_with_retry(project_id: str) -> Optional[Project]:
            """Get root project with built-in retry logic."""
            return with_retry(
                partial(self._get_root_project, project_id),
                operation_name=f"resolve hierarchy for project {project_id}",
                max_attempts=RETRY_MAX_ATTEMPTS
            )

        logger.info("Building project hierarchy (active + archived) with thread pool")
        all_projects_seq: list[Project] = list(projects.values()) + list(archived_projects.values())
        if not all_projects_seq:
            return mapping_project_id_to_root

        max_workers = min(8, len(all_projects_seq))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pid = {executor.submit(get_root_project_with_retry, p.id): p.id for p in all_projects_seq}
            for future in tqdm(as_completed(future_to_pid), total=len(future_to_pid), desc='Building project hierarchy', unit='project'):
                pid = future_to_pid[future]
                try:
                    root = future.result(timeout=60)
                except (RuntimeError, ValueError, OSError) as e:  # pragma: no cover
                    logger.error(f"Hierarchy resolution failed for project {pid}: {e.__class__.__name__}: {e}")
                    continue
                if root is not None:
                    mapping_project_id_to_root[pid] = root

        return mapping_project_id_to_root

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

    def _fetch_projects_data(self) -> list[ProjectEntry]:
        spec = RequestSpec(
            endpoint=TodoistEndpoints.SYNC_PROJECTS,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                'sync_token': '*',
                'resource_types': '["projects"]',
            },
        )

        result_dict = self._api_client.request_json(spec, operation_name="sync projects")
        if not isinstance(result_dict, dict):
            logger.error("Unexpected payload returned when syncing projects")
            return []

        projects = []
        for project in result_dict['projects']:
            projects.append(safe_instantiate_entry(ProjectEntry, **project))

        return projects

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
        for ori_name, anonym_name in tqdm(project_mapping.items(), desc="Anonymizing projects", unit="project"):
            logger.info(f"Anonymizing project '{ori_name}' to '{anonym_name}'")
            if ori_name in mapping_ref:
                mapping_ref[anonym_name] = mapping_ref[ori_name]
