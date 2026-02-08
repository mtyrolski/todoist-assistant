"""Tests for ``process_rescheduled_tasks`` filtering and aggregation behavior."""

import pandas as pd

from todoist.dashboard.tasks import process_rescheduled_tasks


def _build_task(task_factory, task_id: str, content: str, *, is_recurring: bool = False, due_date: str | None = None):
    due = None
    if is_recurring:
        due = {"date": due_date or "2024-01-15", "is_recurring": True}
    elif due_date is not None:
        due = {"date": due_date, "is_recurring": False}
    return task_factory(task_id, content=content, due=due)


def _rescheduled_df(titles: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "type": ["rescheduled"] * len(titles),
            "title": titles,
            "parent_project_name": ["Project A"] * len(titles),
            "root_project_name": ["Root A"] * len(titles),
        }
    )


def test_filters_out_recurring_tasks(task_factory):
    active_tasks = [
        _build_task(task_factory, "task1", "Daily Standup", is_recurring=True),
        _build_task(task_factory, "task2", "Review PR", due_date="2024-01-15"),
        _build_task(task_factory, "task3", "Weekly Meeting", is_recurring=True),
        _build_task(task_factory, "task4", "Fix Bug", due_date="2024-01-20"),
    ]
    result = process_rescheduled_tasks(
        _rescheduled_df(["Daily Standup", "Review PR", "Weekly Meeting", "Fix Bug"]),
        active_tasks,
    )

    assert set(result["title"].tolist()) == {"Review PR", "Fix Bug"}
    assert len(result) == 2


def test_includes_historical_non_recurring_tasks(task_factory):
    active_tasks = [_build_task(task_factory, "task1", "Current Task", due_date="2024-01-15")]
    result = process_rescheduled_tasks(
        _rescheduled_df(["Current Task", "Old Deleted Task", "Completed Task", "Changed Task"]),
        active_tasks,
    )
    assert set(result["title"].tolist()) == {"Current Task", "Old Deleted Task", "Completed Task", "Changed Task"}
    assert len(result) == 4


def test_all_recurring_tasks_only_historical_tasks_are_kept(task_factory):
    active_tasks = [
        _build_task(task_factory, "task1", "Daily Task", is_recurring=True),
        _build_task(task_factory, "task2", "Weekly Task", is_recurring=True),
    ]
    result = process_rescheduled_tasks(
        _rescheduled_df(["Daily Task", "Weekly Task", "Historical Task 1", "Historical Task 2"]),
        active_tasks,
    )

    assert set(result["title"].tolist()) == {"Historical Task 1", "Historical Task 2"}
    assert len(result) == 2


def test_reschedule_count_aggregation(task_factory):
    active_tasks = [_build_task(task_factory, "task1", "Frequently Rescheduled", due_date="2024-01-15")]
    result = process_rescheduled_tasks(
        _rescheduled_df(["Frequently Rescheduled"] * 5),
        active_tasks,
    )

    assert len(result) == 1
    assert result.iloc[0]["title"] == "Frequently Rescheduled"
    assert result.iloc[0]["reschedule_count"] == 5


def test_empty_activity_dataframe(task_factory):
    active_tasks = [_build_task(task_factory, "task1", "Task A", due_date="2024-01-15")]
    empty_df = pd.DataFrame({"type": [], "title": [], "parent_project_name": [], "root_project_name": []})
    result = process_rescheduled_tasks(empty_df, active_tasks)
    assert result.empty


def test_no_active_tasks_includes_all_historical_rescheduled_titles():
    result = process_rescheduled_tasks(
        _rescheduled_df(["Historical Task 1", "Historical Task 2", "Historical Task 3"]),
        [],
    )
    assert set(result["title"].tolist()) == {"Historical Task 1", "Historical Task 2", "Historical Task 3"}
    assert len(result) == 3


def test_non_rescheduled_events_are_ignored(task_factory):
    active_tasks = [_build_task(task_factory, "task1", "Task A", due_date="2024-01-15")]
    df_activity = pd.DataFrame(
        {
            "type": ["added", "completed", "rescheduled"],
            "title": ["Task A", "Task A", "Task A"],
            "parent_project_name": ["Project A"] * 3,
            "root_project_name": ["Root A"] * 3,
        }
    )
    result = process_rescheduled_tasks(df_activity, active_tasks)
    assert len(result) == 1
    assert result.iloc[0]["reschedule_count"] == 1


def test_same_title_in_multiple_projects_is_grouped_separately(task_factory):
    active_tasks = [_build_task(task_factory, "task1", "Shared title", due_date="2024-01-15")]
    df_activity = pd.DataFrame(
        {
            "type": ["rescheduled", "rescheduled", "rescheduled"],
            "title": ["Shared title", "Shared title", "Shared title"],
            "parent_project_name": ["Project A", "Project B", "Project A"],
            "root_project_name": ["Root A", "Root B", "Root A"],
        }
    )

    result = process_rescheduled_tasks(df_activity, active_tasks)
    by_project = {
        (row["parent_project_name"], row["root_project_name"]): row["reschedule_count"]
        for _, row in result.iterrows()
    }
    assert by_project == {("Project A", "Root A"): 2, ("Project B", "Root B"): 1}
