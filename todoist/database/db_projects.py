import json
from subprocess import DEVNULL, PIPE, run

from loguru import logger
from tqdm import tqdm

from todoist.types import Project, Task, ProjectEntry, TaskEntry
from todoist.utils import COLOR_NAME_TO_TODOIST_CODE, get_api_key, try_n_times
from joblib import Parallel, delayed


class DatabaseProjects:
    def __init__(self):
        self.archived_projects_cache: dict[str, Project] | None = None    # Not initialized yet
        self.projects_cache: list[Project] | None = None    # Not initialized yet

    def pull(self):
        self.fetch_archived_projects()
        self.fetch_projects(include_tasks=True)

    def reset(self):
        self.archived_projects_cache = None
        self.projects_cache = None
        self.pull()

    def fetch_archived_projects(self) -> list[Project]:
        if self.archived_projects_cache is not None:
            return list(self.archived_projects_cache.values())

        data = run([
            'curl', 'https://api.todoist.com/sync/v9/projects/get_archived', '-H',
            f'Authorization: Bearer {get_api_key()}'
        ],
                   stdout=PIPE,
                   stderr=DEVNULL,
                   check=True)
        data_dicts: list[dict] = json.loads(data.stdout)
        entries = map(lambda raw_dict: ProjectEntry(**raw_dict), data_dicts)
        self.archived_projects_cache = {
            entry.id: Project(id=entry.id, project_entry=entry, tasks=[], is_archived=True) for entry in entries
        }
        return list(self.archived_projects_cache.values())

    def fetch_project_by_id(self, project_id: str, include_archived_in_search: bool = False) -> Project:
        """
        Does not include tasks. Falls back to the archived projects if the project is not found
        """
        data = run([
            'curl', 'https://api.todoist.com/sync/v9/projects/get_data', '-H', f'Authorization: Bearer {get_api_key()}',
            '-d', f'project_id={project_id}'
        ],
                   stdout=PIPE,
                   stderr=DEVNULL,
                   check=True)

        result_dict = json.loads(data.stdout)

        if 'project' not in result_dict:
            logger.error(
                f"Error fetching project with id {project_id}. If it is archived, use include_archived_in_search=True")
            if include_archived_in_search:
                if self.archived_projects_cache is None:
                    logger.info("Fetching archived projects")
                    archived = self.fetch_archived_projects()
                    self.archived_projects_cache = {project.id: project for project in archived}
                return self.archived_projects_cache[project_id]

        project = ProjectEntry(**result_dict['project'])
        return Project(id=project.id, project_entry=project, tasks=[], is_archived=False)

    def fetch_projects(self, include_tasks: bool = True) -> list[Project]:
        if self.projects_cache is not None:
            return self.projects_cache

        result: list[Project] = []
        projects: list[ProjectEntry] = self._fetch_projects_data()

        if not include_tasks:
            return list(
                map(lambda project: Project(id=project.id, project_entry=project, tasks=[], is_archived=False),
                    projects))

        def process_project(project: ProjectEntry) -> Project:
            task_entries: list[TaskEntry] = self.fetch_project_tasks(project.id)
            tasks: list[Task] = list(map(lambda task: Task(id=task.id, task_entry=task), task_entries))
            return Project(id=project.id, project_entry=project, tasks=tasks, is_archived=False)

        result = Parallel(n_jobs=-1)(
            delayed(process_project)(project)
            for project in tqdm(
            projects,
            desc='Querying project data',
            unit='project',
            total=len(projects),
            position=0,
            leave=True
            )
        )

        self.projects_cache = result
        return self.projects_cache

    def fetch_project_tasks(self, project_id: str) -> list[TaskEntry]:
        data = run([
            'curl', 'https://api.todoist.com/sync/v9/projects/get_data', '-H', f'Authorization: Bearer {get_api_key()}',
            '-d', f'project_id={project_id}'
        ],
                   stdout=PIPE,
                   stderr=DEVNULL,
                   check=True)

        tasks = []
        for task in json.loads(data.stdout)['items']:
            tasks.append(TaskEntry(**task))

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

        # Build active project hierarchy in parallel
        active_roots = Parallel(n_jobs=-1)(delayed(self._get_root_project)(project.id) for project in tqdm(
            projects.values(), desc='Building active project hierarchy', unit='project', total=len(projects)))
        for project, root in zip(projects.values(), active_roots):
            mapping_project_id_to_root[project.id] = root

        # Build archived project hierarchy in parallel
        archived_roots = Parallel(n_jobs=-1)(delayed(self._get_root_project)(project.id)
                                             for project in tqdm(archived_projects.values(),
                                                                 desc='Building archived project hierarchy',
                                                                 unit='project',
                                                                 total=len(archived_projects)))
        for project, root in zip(archived_projects.values(), archived_roots):
            mapping_project_id_to_root[project.id] = root

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
            project.id: COLOR_NAME_TO_TODOIST_CODE[project.project_entry.color]
            for project in self.fetch_projects(include_tasks=False)
        })
        mapping.update({
            project.id: COLOR_NAME_TO_TODOIST_CODE[project.project_entry.color]
            for project in self.fetch_archived_projects()
        })
        
        return mapping

    def _get_root_project(self, project_id: int):
        # project = self.fetch_project_by_id(project_id)
        project = try_n_times(lambda: self.fetch_project_by_id(project_id), 3)
        if project.project_entry.parent_id is None:
            return project
        return self._get_root_project(project.project_entry.parent_id)

    def _fetch_projects_data(self) -> list[ProjectEntry]:
        data = run([
            'curl', 'https://api.todoist.com/sync/v9/sync', '-H', f'Authorization: Bearer {get_api_key()}', '-d',
            'sync_token=*', '-d', 'resource_types=[\"projects\"]'
        ],
                   stdout=PIPE,
                   stderr=DEVNULL,
                   check=True)

        projects = []
        for project in json.loads(data.stdout)['projects']:
            projects.append(ProjectEntry(**project))

        return projects
