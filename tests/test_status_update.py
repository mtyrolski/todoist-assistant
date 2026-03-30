from datetime import datetime
from typing import Any

import pandas as pd

from tests.factories import make_project, make_project_entry
from todoist.database.db_tasks import DatabaseTasks
from todoist.status_update import build_status_update_report


def _status_update_df() -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "date": "2025-02-03T09:00:00",
                "id": "event-1",
                "title": "Ship release",
                "type": "completed",
                "parent_project_id": "child-launch",
                "parent_project_name": "Launches",
                "root_project_id": "root-work",
                "root_project_name": "Work",
                "parent_item_id": None,
                "task_id": "task-1",
            },
            {
                "date": "2025-02-04T09:00:00",
                "id": "event-2",
                "title": "Ship release",
                "type": "completed",
                "parent_project_id": "child-launch",
                "parent_project_name": "Launches",
                "root_project_id": "root-work",
                "root_project_name": "Work",
                "parent_item_id": None,
                "task_id": "task-1",
            },
            {
                "date": "2025-02-05T09:00:00",
                "id": "event-3",
                "title": "Personal win",
                "type": "completed",
                "parent_project_id": "root-personal",
                "parent_project_name": "Personal",
                "root_project_id": "root-personal",
                "root_project_name": "Personal",
                "parent_item_id": None,
                "task_id": "task-2",
            },
            {
                "date": "2025-01-10T09:00:00",
                "id": "event-4",
                "title": "Old release",
                "type": "completed",
                "parent_project_id": "child-launch",
                "parent_project_name": "Launches",
                "root_project_id": "root-work",
                "root_project_name": "Work",
                "parent_item_id": None,
                "task_id": "task-3",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


class _FakeDb:
    def __init__(self) -> None:
        self.project_calls: list[bool] = []
        self.archived_calls = 0

    def fetch_projects(self, include_tasks: bool = False):
        self.project_calls.append(include_tasks)
        root_work = make_project(
            project_id="root-work",
            project_entry=make_project_entry(project_id="root-work", name="Work"),
        )
        child_launch = make_project(
            project_id="child-launch",
            project_entry=make_project_entry(
                project_id="child-launch",
                name="Launches",
                parent_id="root-work",
            ),
        )
        root_personal = make_project(
            project_id="root-personal",
            project_entry=make_project_entry(project_id="root-personal", name="Personal"),
        )
        return [root_work, child_launch, root_personal]

    def fetch_archived_projects(self):
        self.archived_calls += 1
        return []

    def fetch_task_comments(self, task_id: str) -> list[dict[str, Any]]:
        _ = task_id
        return []


def test_build_status_update_report_filters_projects_dates_and_comments(monkeypatch) -> None:
    monkeypatch.setattr("todoist.status_update.load_activity_data", lambda db: _status_update_df())

    comments_seen: list[str] = []

    def _fetch_comments(task_id: str) -> list[dict[str, Any]]:
        comments_seen.append(task_id)
        if task_id == "task-1":
            return [
                {"id": "c1", "content": "Released with the rollout checklist"},
                {"id": "c2", "content": "Also updated the release notes"},
            ]
        return []

    report = build_status_update_report(
        _FakeDb(),
        project_ids=["root-work"],
        beg=datetime(2025, 2, 1, 0, 0, 0),
        end=datetime(2025, 2, 6, 0, 0, 0),
        sync_label="Weekly sync",
        comment_fetcher=_fetch_comments,
    )

    assert report["syncLabel"] == "Weekly sync"
    assert report["selection"]["requestedProjectIds"] == ["root-work"]
    assert report["selection"]["expandedProjectIds"] == ["root-work", "child-launch"]
    assert report["summary"] == {
        "selectedProjectCount": 1,
        "expandedProjectCount": 2,
        "completedEventCount": 2,
        "completedTaskCount": 1,
        "commentedTaskCount": 1,
        "commentCount": 2,
    }
    assert comments_seen == ["task-1"]

    task = report["completedTasks"][0]
    assert task["taskId"] == "task-1"
    assert task["completionCount"] == 2
    assert task["projectLabel"] == "Work / Launches"
    assert task["commentCount"] == 2
    assert task["comments"][0]["snippet"] == "Released with the rollout checklist"
    assert "Released with the rollout checklist" in report["markdown"]
    assert "### Work / Launches" in report["markdown"]
    assert "Weekly sync" in report["markdown"]


def test_build_status_update_report_handles_empty_range(monkeypatch) -> None:
    df = _status_update_df()
    monkeypatch.setattr("todoist.status_update.load_activity_data", lambda db: df)

    calls: list[str] = []

    def _fetch_comments(task_id: str) -> list[dict[str, Any]]:
        calls.append(task_id)
        return []

    report = build_status_update_report(
        _FakeDb(),
        project_ids=["root-work"],
        beg=datetime(2025, 2, 10, 0, 0, 0),
        end=datetime(2025, 2, 11, 0, 0, 0),
        comment_fetcher=_fetch_comments,
    )

    assert report["summary"] == {
        "selectedProjectCount": 1,
        "expandedProjectCount": 2,
        "completedEventCount": 0,
        "completedTaskCount": 0,
        "commentedTaskCount": 0,
        "commentCount": 0,
    }
    assert report["completedTasks"] == []
    assert report["warnings"] == []
    assert calls == []
    assert "No completed tasks were found" in report["markdown"]


def test_build_status_update_report_degrades_when_comment_fetch_fails(monkeypatch) -> None:
    df = _status_update_df().iloc[[0]].copy()
    monkeypatch.setattr("todoist.status_update.load_activity_data", lambda db: df)

    def _fetch_comments(task_id: str) -> list[dict[str, Any]]:
        raise RuntimeError("comment API unavailable")

    report = build_status_update_report(
        _FakeDb(),
        project_ids=["root-work"],
        beg=datetime(2025, 2, 1, 0, 0, 0),
        end=datetime(2025, 2, 6, 0, 0, 0),
        comment_fetcher=_fetch_comments,
    )

    assert report["summary"]["commentCount"] == 0
    assert report["warnings"] == ["Comments unavailable for task task-1: RuntimeError"]
    assert report["completedTasks"][0]["comments"] == []
    assert "Comments: none" in report["markdown"]


def test_fetch_task_comments_paginates_results(monkeypatch) -> None:
    db = DatabaseTasks()
    requests: list[dict[str, Any]] = []
    responses = iter(
        [
            {"results": [{"id": "c1", "content": "First"}], "next_cursor": "cursor-2"},
            {"results": [{"id": "c2", "content": "Second"}]},
        ]
    )

    def _request_json(spec, _operation_name: str | None = None):  # type: ignore[no-untyped-def]
        requests.append(dict(spec.params or {}))
        return next(responses)

    class _FakeClient:
        def request_json(self, spec, operation_name: str | None = None):  # type: ignore[no-untyped-def]
            return _request_json(spec, operation_name)

    monkeypatch.setattr(db, "_api_client", _FakeClient())

    comments = db.fetch_task_comments("task-1")

    assert comments == [
        {"id": "c1", "content": "First"},
        {"id": "c2", "content": "Second"},
    ]
    assert requests == [
        {"task_id": "task-1"},
        {"task_id": "task-1", "cursor": "cursor-2"},
    ]
