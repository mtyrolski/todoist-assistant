"""
Tests for rescheduled tasks filtering functionality.

This module tests the process_rescheduled_tasks function to ensure that
recurring tasks are properly filtered out from the rescheduled tasks list.
"""
import pytest
import pandas as pd
from loguru import logger

from todoist.types import Task, TaskEntry


def process_rescheduled_tasks(df_activity, active_tasks):
    """
    Process and return rescheduled tasks data - copied from tasks.py for testing.
    """
    rescheduled_tasks = df_activity[df_activity['type'] == 'rescheduled'] \
        .groupby(['title', 'parent_project_name', 'root_project_name']) \
        .size() \
        .sort_values(ascending=False) \
        .reset_index(name='reschedule_count')

    # Get names of currently active recurring tasks (to exclude them)
    active_recurring_tasks = filter(lambda task: task.is_recurring, active_tasks)
    recurring_task_names = set(task.task_entry.content for task in active_recurring_tasks)

    # Filter out rescheduled tasks that correspond to currently recurring tasks
    filtered_tasks = rescheduled_tasks[~rescheduled_tasks['title'].isin(recurring_task_names)]
    logger.debug(f"Found {len(filtered_tasks)} rescheduled tasks")

    return filtered_tasks


@pytest.fixture
def create_task():
    """Factory fixture to create test tasks with specified properties."""
    def _create_task(task_id, content, is_recurring=False, due_date=None):
        due = None
        if is_recurring:
            due = {"date": due_date or "2024-01-15", "is_recurring": True}
        elif due_date:
            due = {"date": due_date, "is_recurring": False}
        
        task_entry = TaskEntry(
            id=task_id,
            is_deleted=False,
            added_at="2024-01-01T00:00:00Z",
            child_order=1,
            responsible_uid=None,
            content=content,
            description="",
            user_id="user123",
            assigned_by_uid="user123",
            project_id="project123",
            section_id="section123",
            sync_id=None,
            collapsed=False,
            due=due,
            parent_id=None,
            labels=[],
            checked=False,
            priority=1,
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
            day_order=None
        )
        
        return Task(id=task_id, task_entry=task_entry)
    
    return _create_task


def test_filters_out_recurring_tasks(create_task):
    """Test that recurring tasks are excluded from rescheduled list."""
    # Create active tasks with mix of recurring and non-recurring
    active_tasks = [
        create_task("task1", "Daily Standup", is_recurring=True),
        create_task("task2", "Review PR", is_recurring=False, due_date="2024-01-15"),
        create_task("task3", "Weekly Meeting", is_recurring=True),
        create_task("task4", "Fix Bug", is_recurring=False, due_date="2024-01-20"),
    ]
    
    # Create activity data with rescheduled events for all tasks
    df_activity = pd.DataFrame({
        'type': ['rescheduled'] * 4,
        'title': ['Daily Standup', 'Review PR', 'Weekly Meeting', 'Fix Bug'],
        'parent_project_name': ['Project A'] * 4,
        'root_project_name': ['Root A'] * 4
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    # Verify only non-recurring tasks are included
    actual_tasks = set(result['title'].tolist())
    assert actual_tasks == {'Review PR', 'Fix Bug'}
    assert len(result) == 2
    
    # Verify recurring tasks are excluded
    assert 'Daily Standup' not in actual_tasks
    assert 'Weekly Meeting' not in actual_tasks


def test_includes_historical_non_recurring_tasks(create_task):
    """Test that historical (deleted/completed) non-recurring tasks are included."""
    # Only current active task
    active_tasks = [
        create_task("task1", "Current Task", is_recurring=False, due_date="2024-01-15"),
    ]
    
    # Historical rescheduled tasks that no longer exist as active tasks
    df_activity = pd.DataFrame({
        'type': ['rescheduled'] * 4,
        'title': ['Current Task', 'Old Deleted Task', 'Completed Task', 'Changed Task'],
        'parent_project_name': ['Project A'] * 4,
        'root_project_name': ['Root A'] * 4
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    # All tasks should be included since none are currently recurring
    actual_tasks = set(result['title'].tolist())
    assert actual_tasks == {'Current Task', 'Old Deleted Task', 'Completed Task', 'Changed Task'}
    assert len(result) == 4


def test_mixed_scenario_with_recurring_and_historical(create_task):
    """Test realistic scenario with active recurring, active non-recurring, and historical tasks."""
    active_tasks = [
        # Recurring tasks that should be excluded
        create_task("task1", "Daily Standup", is_recurring=True),
        create_task("task2", "Weekly Planning", is_recurring=True),
        
        # Non-recurring active tasks that should be included
        create_task("task3", "Review Pull Request", is_recurring=False, due_date="2024-01-15"),
        create_task("task4", "Update Documentation", is_recurring=False, due_date="2024-01-20"),
    ]
    
    df_activity = pd.DataFrame({
        'type': ['rescheduled'] * 8,
        'title': [
            'Daily Standup',        # Currently recurring - EXCLUDE
            'Weekly Planning',      # Currently recurring - EXCLUDE  
            'Review Pull Request',  # Currently non-recurring - INCLUDE
            'Update Documentation', # Currently non-recurring - INCLUDE
            'Old Task 1',          # Historical - INCLUDE
            'Old Task 2',          # Historical - INCLUDE
            'Completed Project',   # Historical - INCLUDE
            'Legacy Task'          # Historical - INCLUDE
        ],
        'parent_project_name': ['Project A'] * 8,
        'root_project_name': ['Root A'] * 8
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    # Verify correct tasks are included
    actual_tasks = set(result['title'].tolist())
    expected_tasks = {
        'Review Pull Request', 'Update Documentation', 
        'Old Task 1', 'Old Task 2', 'Completed Project', 'Legacy Task'
    }
    assert actual_tasks == expected_tasks
    assert len(result) == 6
    
    # Verify recurring tasks are excluded
    excluded_tasks = {'Daily Standup', 'Weekly Planning'}
    all_rescheduled = set(df_activity['title'].tolist())
    actual_excluded = all_rescheduled - actual_tasks
    assert actual_excluded == excluded_tasks


def test_no_recurring_tasks_all_included(create_task):
    """Test when there are no recurring tasks - all rescheduled tasks should be included."""
    active_tasks = [
        create_task("task1", "Task A", is_recurring=False, due_date="2024-01-15"),
        create_task("task2", "Task B", is_recurring=False, due_date="2024-01-20"),
    ]
    
    df_activity = pd.DataFrame({
        'type': ['rescheduled'] * 4,
        'title': ['Task A', 'Task B', 'Historical Task 1', 'Historical Task 2'],
        'parent_project_name': ['Project A'] * 4,
        'root_project_name': ['Root A'] * 4
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    # All tasks should be included
    actual_tasks = set(result['title'].tolist())
    assert actual_tasks == {'Task A', 'Task B', 'Historical Task 1', 'Historical Task 2'}
    assert len(result) == 4


def test_all_recurring_tasks_only_historical_included(create_task):
    """Test when all active tasks are recurring - only historical tasks should be included."""
    active_tasks = [
        create_task("task1", "Daily Task", is_recurring=True),
        create_task("task2", "Weekly Task", is_recurring=True),
    ]
    
    df_activity = pd.DataFrame({
        'type': ['rescheduled'] * 4,
        'title': ['Daily Task', 'Weekly Task', 'Historical Task 1', 'Historical Task 2'],
        'parent_project_name': ['Project A'] * 4,
        'root_project_name': ['Root A'] * 4
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    # Only historical tasks should be included
    actual_tasks = set(result['title'].tolist())
    assert actual_tasks == {'Historical Task 1', 'Historical Task 2'}
    assert len(result) == 2
    
    # Verify recurring active tasks are excluded
    assert 'Daily Task' not in actual_tasks
    assert 'Weekly Task' not in actual_tasks


def test_reschedule_count_aggregation(create_task):
    """Test that reschedule counts are properly aggregated."""
    active_tasks = [
        create_task("task1", "Frequently Rescheduled", is_recurring=False, due_date="2024-01-15"),
    ]
    
    # Same task rescheduled multiple times
    df_activity = pd.DataFrame({
        'type': ['rescheduled'] * 5,
        'title': ['Frequently Rescheduled'] * 5,
        'parent_project_name': ['Project A'] * 5,
        'root_project_name': ['Root A'] * 5
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    assert len(result) == 1
    assert result.iloc[0]['title'] == 'Frequently Rescheduled'
    assert result.iloc[0]['reschedule_count'] == 5


def test_empty_activity_dataframe(create_task):
    """Test handling of empty activity dataframe."""
    active_tasks = [
        create_task("task1", "Task A", is_recurring=False, due_date="2024-01-15"),
    ]
    
    df_activity = pd.DataFrame({
        'type': [],
        'title': [],
        'parent_project_name': [],
        'root_project_name': []
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    assert len(result) == 0
    assert result.empty


def test_no_active_tasks_all_historical_included(create_task):
    """Test when there are no active tasks - all historical rescheduled tasks should be included."""
    active_tasks = []
    
    df_activity = pd.DataFrame({
        'type': ['rescheduled'] * 3,
        'title': ['Historical Task 1', 'Historical Task 2', 'Historical Task 3'],
        'parent_project_name': ['Project A'] * 3,
        'root_project_name': ['Root A'] * 3
    })
    
    result = process_rescheduled_tasks(df_activity, active_tasks)
    
    # All historical tasks should be included since there are no recurring tasks to exclude
    actual_tasks = set(result['title'].tolist())
    assert actual_tasks == {'Historical Task 1', 'Historical Task 2', 'Historical Task 3'}
    assert len(result) == 3