"""Shared fixtures for test object factories."""

from collections.abc import Callable
from typing import Any

import pytest

from tests.factories import make_project, make_project_entry, make_task, make_task_entry
from todoist.types import Project, ProjectEntry, Task, TaskEntry


@pytest.fixture
def project_entry_factory() -> Callable[..., ProjectEntry]:
    return make_project_entry


@pytest.fixture
def project_entry(project_entry_factory: Callable[..., ProjectEntry]) -> ProjectEntry:
    return project_entry_factory()


@pytest.fixture
def task_entry_factory() -> Callable[..., TaskEntry]:
    def _build(task_id: str, **overrides: Any) -> TaskEntry:
        return make_task_entry(task_id=task_id, **overrides)

    return _build


@pytest.fixture
def task_factory(task_entry_factory: Callable[..., TaskEntry]) -> Callable[..., Task]:
    def _build(task_id: str, **overrides: Any) -> Task:
        entry_override = overrides.pop("task_entry", None)
        entry = entry_override or task_entry_factory(task_id, **overrides)
        return make_task(task_id=task_id, task_entry=entry)

    return _build


@pytest.fixture
def project_factory(project_entry_factory: Callable[..., ProjectEntry]) -> Callable[..., Project]:
    def _build(
        *,
        project_id: str = "project123",
        project_entry: ProjectEntry | None = None,
        tasks: list[Task] | None = None,
        is_archived: bool = False,
        **project_entry_overrides: Any,
    ) -> Project:
        entry = project_entry or project_entry_factory(project_id=project_id, **project_entry_overrides)
        return make_project(
            project_id=project_id,
            project_entry=entry,
            tasks=tasks,
            is_archived=is_archived,
        )

    return _build
