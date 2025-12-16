"""
Tests for helper functions in todoist.dashboard.utils and todoist.automations.multiplicate modules.
"""

import pytest
import pandas as pd

from todoist.automations.multiplicate import extract_multiplication_factor, is_multiplication_label
from todoist.dashboard.utils import extract_metrics, get_badges
from todoist.types import Project, ProjectEntry, Task, TaskEntry


@pytest.fixture
def activity_df_two_weeks() -> pd.DataFrame:
    """Craft a two-week slice so we can assert concrete metric deltas."""
    records = [
        # Current week (end date is 2024-03-14)
        {"date": "2024-03-14", "id": "e1", "title": "t1", "type": "completed"},
        {"date": "2024-03-13", "id": "e2", "title": "t2", "type": "completed"},
        {"date": "2024-03-12", "id": "e3", "title": "t3", "type": "added"},
        {"date": "2024-03-11", "id": "e4", "title": "t4", "type": "added"},
        {"date": "2024-03-08", "id": "e5", "title": "t5", "type": "rescheduled"},
        {"date": "2024-03-07", "id": "e6", "title": "t6", "type": "added"},
        # Previous week window
        {"date": "2024-03-06", "id": "e7", "title": "t7", "type": "completed"},
        {"date": "2024-03-05", "id": "e8", "title": "t8", "type": "completed"},
        {"date": "2024-03-04", "id": "e9", "title": "t9", "type": "rescheduled"},
        {"date": "2024-03-03", "id": "e10", "title": "t10", "type": "added"},
        {"date": "2024-03-02", "id": "e11", "title": "t11", "type": "added"},
        {"date": "2024-03-01", "id": "e12", "title": "t12", "type": "completed"},
    ]
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df["parent_project_id"] = "proj"
    df["parent_project_name"] = "Project"
    return df.set_index("date").sort_index()


@pytest.fixture
def project_entry() -> ProjectEntry:
    return ProjectEntry(
        id="project123",
        name="Test Project",
        color="blue",
        parent_id=None,
        child_order=1,
        view_style="list",
        is_favorite=False,
        is_archived=False,
        is_deleted=False,
        is_frozen=False,
        can_assign_tasks=True,
        shared=False,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_project123",
        v2_parent_id=None,
        sync_id=None,
        collapsed=False,
    )


@pytest.fixture
def task_entry_factory():
    def _build(task_id: str, priority: int) -> TaskEntry:
        return TaskEntry(
            id=task_id,
            is_deleted=False,
            added_at="2024-01-01T00:00:00Z",
            child_order=1,
            responsible_uid=None,
            content=f"Task {task_id}",
            description="",
            user_id="user123",
            assigned_by_uid="user123",
            project_id="project123",
            section_id="section123",
            sync_id=None,
            collapsed=False,
            due=None,
            parent_id=None,
            labels=[],
            checked=False,
            priority=priority,
            note_count=0,
            added_by_uid="user123",
            completed_at=None,
            deadline=None,
            duration=None,
            updated_at="2024-01-01T00:00:00Z",
            v2_id=f"v2_{task_id}",
            v2_parent_id=None,
            v2_project_id="v2_project123",
            v2_section_id="v2_section123",
            day_order=None,
        )

    return _build


def test_extract_metrics_reports_counts_and_deltas(activity_df_two_weeks: pd.DataFrame):
    """Ensure the dashboard shows real counts and meaningful deltas."""
    metrics, current_period, previous_period = extract_metrics(activity_df_two_weeks, "W")

    metrics_by_name = {name: (value, delta, inverse) for name, value, delta, inverse in metrics}
    # Window uses inclusive bounds, so the boundary day (2024-03-07) is counted in both periods
    assert metrics_by_name == {
        "Events": ("6", "-14.29%", False),
        "Completed Tasks": ("2", "-33.33%", False),
        "Added Tasks": ("3", "0.0%", False),
        "Rescheduled Tasks": ("1", "0.0%", True),
    }
    assert current_period.startswith("2024-03-07")
    assert current_period.endswith("2024-03-14")
    assert previous_period.startswith("2024-02-29")
    assert previous_period.endswith("2024-03-07")


def test_extract_metrics_rejects_unknown_granularity(activity_df_two_weeks: pd.DataFrame):
    with pytest.raises(ValueError):
        extract_metrics(activity_df_two_weeks, "quarterly")


def test_get_badges_aggregates_priorities(project_entry, task_entry_factory):
    """Badge counts should reflect totals across projects, not per-project fragments."""
    another_project_entry = ProjectEntry(
        id="project456",
        name="Project 2",
        color="red",
        parent_id=None,
        child_order=2,
        view_style="list",
        is_favorite=False,
        is_archived=False,
        is_deleted=False,
        is_frozen=False,
        can_assign_tasks=True,
        shared=False,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        v2_id="v2_project456",
        v2_parent_id=None,
        sync_id=None,
        collapsed=False,
    )

    projects = [
        Project(
            id="proj1",
            project_entry=project_entry,
            tasks=[
                Task(id="t1", task_entry=task_entry_factory("t1", priority=4)),
                Task(id="t2", task_entry=task_entry_factory("t2", priority=3)),
            ],
            is_archived=False,
        ),
        Project(
            id="proj2",
            project_entry=another_project_entry,
            tasks=[
                Task(id="t3", task_entry=task_entry_factory("t3", priority=4)),
                Task(id="t4", task_entry=task_entry_factory("t4", priority=2)),
                Task(id="t5", task_entry=task_entry_factory("t5", priority=1)),
            ],
            is_archived=False,
        ),
    ]

    badge = get_badges(projects)

    assert "P1 tasks 2" in badge  # priority 4
    assert "P2 tasks 1" in badge  # priority 3
    assert "P3 tasks 1" in badge  # priority 2
    assert "P4 tasks 1" in badge  # priority 1


def test_get_badges_handles_empty_projects():
    badge = get_badges([])
    assert "P1 tasks 0" in badge
    assert "P2 tasks 0" in badge
    assert "P3 tasks 0" in badge
    assert "P4 tasks 0" in badge


def test_multiplication_labels_are_uppercase_only():
    assert is_multiplication_label("X3")
    assert not is_multiplication_label("x3")
    with pytest.raises(ValueError):
        extract_multiplication_factor("x3")
    with pytest.raises(ValueError):
        extract_multiplication_factor("X")


def test_multiplication_label_pipeline_filters_and_extracts():
    labels = ["X2", "ship", "X10", "X07"]
    factors = [extract_multiplication_factor(label) for label in labels if is_multiplication_label(label)]
    assert factors == [2, 10, 7]
