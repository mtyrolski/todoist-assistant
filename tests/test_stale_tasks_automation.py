from datetime import datetime
from typing import cast
from unittest.mock import patch

from tests.factories import make_project, make_project_entry, make_task
from todoist.automations.stale_tasks import StaleTasksAutomation
from todoist.database.base import Database


class _FakeDb:
    def __init__(self, projects):
        self.projects = projects
        self.updates: list[tuple[str, dict[str, object]]] = []

    def fetch_projects(self, include_tasks: bool = True):
        assert include_tasks is True
        return self.projects

    def update_task(self, task_id: str, **kwargs):
        self.updates.append((task_id, kwargs))
        labels = kwargs.get("labels")
        if isinstance(labels, list):
            for project in self.projects:
                for task in project.tasks:
                    if task.id == task_id:
                        task.task_entry.labels = list(labels)
        return {}


def _project_with_tasks():
    return make_project(
        project_id="project-1",
        project_entry=make_project_entry(project_id="project-1", name="Backlog"),
        tasks=[
            make_task(
                "task-old",
                content="Old task",
                labels=["ops"],
                added_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-05T00:00:00Z",
            ),
            make_task(
                "task-very-old",
                content="Very old task",
                labels=["old", "ops"],
                added_at="2024-01-01T00:00:00Z",
                updated_at="2024-11-01T00:00:00Z",
            ),
            make_task(
                "task-fresh",
                content="Fresh task",
                labels=["very-old", "ops"],
                added_at="2025-03-01T00:00:00Z",
                updated_at="2025-03-19T00:00:00Z",
            ),
            make_task(
                "task-due-soon",
                content="Due soon task",
                labels=["ops"],
                due={"date": "2025-03-22", "is_recurring": False},
                added_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
        ],
    )


def test_stale_tasks_automation_dry_run_reports_changes_without_updating(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db = _FakeDb([_project_with_tasks()])
    automation = StaleTasksAutomation(
        frequency_in_minutes=0,
        dry_run=True,
        config={"old_after_days": 30, "very_old_after_days": 90},
        max_updates_per_tick=10,
    )

    with patch(
        "todoist.automations.stale_tasks.automation.datetime",
        type("_FixedDateTime", (), {"now": staticmethod(lambda: datetime(2025, 3, 20, 12, 0, 0))}),
    ):
        result = automation.tick(cast(Database, db))

    assert db.updates == []
    assert [item["taskId"] for item in result] == [
        "task-old",
        "task-very-old",
        "task-fresh",
    ]
    summary = automation.last_run_summary
    assert summary["dryRun"] is True
    assert summary["counts"]["scanned"] == 4
    assert summary["counts"]["old"] == 1
    assert summary["counts"]["very_old"] == 1
    assert summary["counts"]["fresh"] == 1
    assert summary["counts"]["skip_due_soon"] == 1
    assert summary["counts"]["candidateUpdates"] == 3


def test_stale_tasks_automation_updates_labels_and_respects_cap(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db = _FakeDb([_project_with_tasks()])
    automation = StaleTasksAutomation(
        frequency_in_minutes=0,
        dry_run=False,
        config={"old_after_days": 30, "very_old_after_days": 90},
        max_updates_per_tick=2,
    )

    with patch(
        "todoist.automations.stale_tasks.automation.datetime",
        type("_FixedDateTime", (), {"now": staticmethod(lambda: datetime(2025, 3, 20, 12, 0, 0))}),
    ):
        result = automation.tick(cast(Database, db))

    assert [item["taskId"] for item in result] == ["task-old", "task-very-old"]
    assert db.updates == [
        ("task-old", {"labels": ["ops", "old"]}),
        ("task-very-old", {"labels": ["ops", "very-old"]}),
    ]
    assert automation.last_run_summary["counts"]["selectedUpdates"] == 2
    assert automation.last_run_summary["counts"]["skippedByCap"] == 1


def test_stale_tasks_automation_is_idempotent_after_updates(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db = _FakeDb(
        [
            make_project(
                project_id="project-1",
                project_entry=make_project_entry(project_id="project-1", name="Backlog"),
                tasks=[
                    make_task(
                        "task-old",
                        content="Old task",
                        labels=["ops", "old"],
                        added_at="2025-01-01T00:00:00Z",
                        updated_at="2025-01-05T00:00:00Z",
                    ),
                    make_task(
                        "task-fresh",
                        content="Fresh task",
                        labels=["ops"],
                        added_at="2025-03-01T00:00:00Z",
                        updated_at="2025-03-19T00:00:00Z",
                    ),
                ],
            )
        ]
    )
    automation = StaleTasksAutomation(
        frequency_in_minutes=0,
        dry_run=False,
        config={"old_after_days": 30, "very_old_after_days": 90},
    )

    with patch(
        "todoist.automations.stale_tasks.automation.datetime",
        type("_FixedDateTime", (), {"now": staticmethod(lambda: datetime(2025, 3, 20, 12, 0, 0))}),
    ):
        result = automation.tick(cast(Database, db))

    assert result == []
    assert db.updates == []
    assert automation.last_run_summary["counts"]["candidateUpdates"] == 0
