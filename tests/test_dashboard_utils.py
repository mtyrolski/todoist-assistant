"""Practical tests for dashboard utilities and multiplication-label helpers."""

import pandas as pd
import pytest

from todoist.automations.multiplicate import extract_multiplication_factor, is_multiplication_label
from todoist.dashboard.utils import extract_metrics, get_badges


@pytest.fixture
def activity_df_two_weeks() -> pd.DataFrame:
    """Craft a two-week slice so metric deltas can be asserted precisely."""
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


def test_extract_metrics_reports_counts_and_deltas(activity_df_two_weeks: pd.DataFrame):
    metrics, current_period, previous_period = extract_metrics(activity_df_two_weeks, "W")
    metrics_by_name = {name: (value, delta, inverse) for name, value, delta, inverse in metrics}

    # The boundary day (2024-03-07) is included in both windows by design.
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


def test_extract_metrics_uses_inf_delta_when_previous_period_has_zero_events():
    df = pd.DataFrame(
        [
            {"date": "2024-03-14", "id": "e1", "title": "t1", "type": "completed"},
            {"date": "2024-03-13", "id": "e2", "title": "t2", "type": "added"},
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    metrics, *_ = extract_metrics(df, "W")
    metrics_by_name = {name: delta for name, _value, delta, _inverse in metrics}
    assert metrics_by_name["Events"] == "inf%"
    assert metrics_by_name["Completed Tasks"] == "inf%"


def test_get_badges_aggregates_priorities(project_factory, project_entry_factory, task_factory):
    projects = [
        project_factory(
            project_id="proj1",
            project_entry=project_entry_factory(project_id="project123", name="Project 1"),
            tasks=[
                task_factory("t1", priority=4),
                task_factory("t2", priority=3),
            ],
        ),
        project_factory(
            project_id="proj2",
            project_entry=project_entry_factory(project_id="project456", name="Project 2", color="red"),
            tasks=[
                task_factory("t3", priority=4),
                task_factory("t4", priority=2),
                task_factory("t5", priority=1),
            ],
        ),
    ]

    badge = get_badges(projects)
    assert "P1 tasks 2" in badge
    assert "P2 tasks 1" in badge
    assert "P3 tasks 1" in badge
    assert "P4 tasks 1" in badge


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
