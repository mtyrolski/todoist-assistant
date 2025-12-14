"""
Tests for statistics and helper functions in todoist.stats module.
"""
import pytest
from datetime import datetime

from todoist.stats import (
    all_tasks,
    priority_tasks,
    p1_tasks,
    p2_tasks,
    p3_tasks,
    p4_tasks,
    any_labels,
    try_parse_date,
    extract_task_due_date
)
from todoist.types import Project, ProjectEntry, Task, TaskEntry


# Fixtures for creating test data
@pytest.fixture
def project_entry():
    """Create a sample ProjectEntry."""
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
        collapsed=False
    )


@pytest.fixture
def task_entry_factory():
    """Factory for creating TaskEntry instances with different priorities and labels."""
    def _create_task_entry(task_id: str, priority: int = 1, labels: list[str] = None):
        if labels is None:
            labels = []
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
            labels=labels,
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
            day_order=None
        )
    return _create_task_entry


@pytest.fixture
def project_with_tasks(project_entry, task_entry_factory):
    """Create a Project with various tasks."""
    tasks = [
        Task(id="task1", task_entry=task_entry_factory("task1", priority=4, labels=["urgent", "work"])),
        Task(id="task2", task_entry=task_entry_factory("task2", priority=4, labels=["urgent"])),
        Task(id="task3", task_entry=task_entry_factory("task3", priority=3, labels=["important"])),
        Task(id="task4", task_entry=task_entry_factory("task4", priority=2, labels=[])),
        Task(id="task5", task_entry=task_entry_factory("task5", priority=1, labels=["someday"])),
    ]
    return Project(
        id="project123",
        project_entry=project_entry,
        tasks=tasks,
        is_archived=False
    )


# Test all_tasks
def test_all_tasks_with_multiple_tasks(project_with_tasks):
    """Test all_tasks returns correct count for project with tasks."""
    count = all_tasks(project_with_tasks)
    assert count == 5


def test_all_tasks_empty_project(project_entry):
    """Test all_tasks returns 0 for project with no tasks."""
    empty_project = Project(
        id="empty_project",
        project_entry=project_entry,
        tasks=[],
        is_archived=False
    )
    count = all_tasks(empty_project)
    assert count == 0


def test_all_tasks_single_task(project_entry, task_entry_factory):
    """Test all_tasks returns 1 for project with single task."""
    single_task_project = Project(
        id="single_project",
        project_entry=project_entry,
        tasks=[Task(id="task1", task_entry=task_entry_factory("task1"))],
        is_archived=False
    )
    count = all_tasks(single_task_project)
    assert count == 1


# Test priority_tasks
def test_priority_tasks_p1(project_with_tasks):
    """Test priority_tasks for priority 4 (P1) tasks."""
    count = priority_tasks(project_with_tasks, prio=4)
    assert count == 2  # task1 and task2


def test_priority_tasks_p2(project_with_tasks):
    """Test priority_tasks for priority 3 (P2) tasks."""
    count = priority_tasks(project_with_tasks, prio=3)
    assert count == 1  # task3


def test_priority_tasks_p3(project_with_tasks):
    """Test priority_tasks for priority 2 (P3) tasks."""
    count = priority_tasks(project_with_tasks, prio=2)
    assert count == 1  # task4


def test_priority_tasks_p4(project_with_tasks):
    """Test priority_tasks for priority 1 (P4) tasks."""
    count = priority_tasks(project_with_tasks, prio=1)
    assert count == 1  # task5


def test_priority_tasks_no_matching_priority(project_entry, task_entry_factory):
    """Test priority_tasks returns 0 when no tasks match priority."""
    project = Project(
        id="project",
        project_entry=project_entry,
        tasks=[
            Task(id="task1", task_entry=task_entry_factory("task1", priority=2)),
            Task(id="task2", task_entry=task_entry_factory("task2", priority=2)),
        ],
        is_archived=False
    )
    count = priority_tasks(project, prio=4)
    assert count == 0


def test_priority_tasks_empty_project(project_entry):
    """Test priority_tasks returns 0 for empty project."""
    empty_project = Project(
        id="empty",
        project_entry=project_entry,
        tasks=[],
        is_archived=False
    )
    count = priority_tasks(empty_project, prio=4)
    assert count == 0


# Test p1_tasks, p2_tasks, p3_tasks, p4_tasks partials
def test_p1_tasks(project_with_tasks):
    """Test p1_tasks partial function."""
    count = p1_tasks(project_with_tasks)
    assert count == 2  # Priority 4 tasks


def test_p2_tasks(project_with_tasks):
    """Test p2_tasks partial function."""
    count = p2_tasks(project_with_tasks)
    assert count == 1  # Priority 3 tasks


def test_p3_tasks(project_with_tasks):
    """Test p3_tasks partial function."""
    count = p3_tasks(project_with_tasks)
    assert count == 1  # Priority 2 tasks


def test_p4_tasks(project_with_tasks):
    """Test p4_tasks partial function."""
    count = p4_tasks(project_with_tasks)
    assert count == 1  # Priority 1 tasks


def test_all_priority_partials_on_empty_project(project_entry):
    """Test all priority partial functions on empty project."""
    empty_project = Project(
        id="empty",
        project_entry=project_entry,
        tasks=[],
        is_archived=False
    )
    assert p1_tasks(empty_project) == 0
    assert p2_tasks(empty_project) == 0
    assert p3_tasks(empty_project) == 0
    assert p4_tasks(empty_project) == 0


def test_priority_partials_with_mixed_priorities(project_entry, task_entry_factory):
    """Test priority partials with all different priorities."""
    project = Project(
        id="mixed",
        project_entry=project_entry,
        tasks=[
            Task(id="t1", task_entry=task_entry_factory("t1", priority=4)),
            Task(id="t2", task_entry=task_entry_factory("t2", priority=4)),
            Task(id="t3", task_entry=task_entry_factory("t3", priority=4)),
            Task(id="t4", task_entry=task_entry_factory("t4", priority=3)),
            Task(id="t5", task_entry=task_entry_factory("t5", priority=3)),
            Task(id="t6", task_entry=task_entry_factory("t6", priority=2)),
            Task(id="t7", task_entry=task_entry_factory("t7", priority=1)),
        ],
        is_archived=False
    )
    assert p1_tasks(project) == 3
    assert p2_tasks(project) == 2
    assert p3_tasks(project) == 1
    assert p4_tasks(project) == 1


# Test any_labels
def test_any_labels_with_labeled_tasks(project_with_tasks):
    """Test any_labels returns count of tasks with labels."""
    count = any_labels(project_with_tasks)
    assert count == 4  # task1, task2, task3, task5 have labels


def test_any_labels_no_labels(project_entry, task_entry_factory):
    """Test any_labels returns 0 when no tasks have labels."""
    project = Project(
        id="no_labels",
        project_entry=project_entry,
        tasks=[
            Task(id="task1", task_entry=task_entry_factory("task1", labels=[])),
            Task(id="task2", task_entry=task_entry_factory("task2", labels=[])),
        ],
        is_archived=False
    )
    count = any_labels(project)
    assert count == 0


def test_any_labels_all_tasks_labeled(project_entry, task_entry_factory):
    """Test any_labels when all tasks have labels."""
    project = Project(
        id="all_labeled",
        project_entry=project_entry,
        tasks=[
            Task(id="task1", task_entry=task_entry_factory("task1", labels=["label1"])),
            Task(id="task2", task_entry=task_entry_factory("task2", labels=["label2", "label3"])),
            Task(id="task3", task_entry=task_entry_factory("task3", labels=["label4"])),
        ],
        is_archived=False
    )
    count = any_labels(project)
    assert count == 3


def test_any_labels_empty_project(project_entry):
    """Test any_labels returns 0 for empty project."""
    empty_project = Project(
        id="empty",
        project_entry=project_entry,
        tasks=[],
        is_archived=False
    )
    count = any_labels(empty_project)
    assert count == 0


def test_any_labels_multiple_labels_per_task(project_entry, task_entry_factory):
    """Test any_labels counts tasks with multiple labels correctly."""
    project = Project(
        id="multi_label",
        project_entry=project_entry,
        tasks=[
            Task(id="task1", task_entry=task_entry_factory("task1", labels=["a", "b", "c"])),
            Task(id="task2", task_entry=task_entry_factory("task2", labels=[])),
            Task(id="task3", task_entry=task_entry_factory("task3", labels=["d"])),
        ],
        is_archived=False
    )
    count = any_labels(project)
    assert count == 2  # task1 and task3


# Test try_parse_date
def test_try_parse_date_basic_format():
    """Test try_parse_date with basic YYYY-MM-DD format."""
    result = try_parse_date("2024-01-15")
    assert result == datetime(2024, 1, 15)


def test_try_parse_date_with_time_z():
    """Test try_parse_date with datetime and Z timezone."""
    result = try_parse_date("2024-01-15T14:30:00Z")
    assert result == datetime(2024, 1, 15, 14, 30, 0)


def test_try_parse_date_with_time_no_z():
    """Test try_parse_date with datetime without timezone."""
    result = try_parse_date("2024-01-15T14:30:00")
    assert result == datetime(2024, 1, 15, 14, 30, 0)


def test_try_parse_date_with_microseconds():
    """Test try_parse_date with microseconds."""
    result = try_parse_date("2024-01-15T14:30:00.123456Z")
    assert result == datetime(2024, 1, 15, 14, 30, 0, 123456)


def test_try_parse_date_invalid_format():
    """Test try_parse_date returns None for invalid format."""
    result = try_parse_date("invalid-date-format")
    assert result is None


def test_try_parse_date_wrong_date_format():
    """Test try_parse_date returns None for wrong date format."""
    result = try_parse_date("15-01-2024")  # DD-MM-YYYY not supported
    assert result is None


def test_try_parse_date_incomplete_date():
    """Test try_parse_date returns None for incomplete date."""
    result = try_parse_date("2024-01")
    assert result is None


def test_try_parse_date_empty_string():
    """Test try_parse_date returns None for empty string."""
    result = try_parse_date("")
    assert result is None


def test_try_parse_date_various_valid_formats():
    """Test try_parse_date with all supported formats."""
    test_cases = [
        ("2024-03-15", datetime(2024, 3, 15)),
        ("2024-03-15T10:30:45Z", datetime(2024, 3, 15, 10, 30, 45)),
        ("2024-03-15T10:30:45", datetime(2024, 3, 15, 10, 30, 45)),
        ("2024-03-15T10:30:45.999999Z", datetime(2024, 3, 15, 10, 30, 45, 999999)),
    ]
    
    for date_str, expected in test_cases:
        result = try_parse_date(date_str)
        assert result == expected, f"Failed for {date_str}"


# Test extract_task_due_date
def test_extract_task_due_date_none():
    """Test extract_task_due_date returns None when due is None."""
    result = extract_task_due_date(None)
    assert result is None


def test_extract_task_due_date_string():
    """Test extract_task_due_date with string due date."""
    result = extract_task_due_date("2024-01-15")
    assert result == datetime(2024, 1, 15)


def test_extract_task_due_date_string_with_time():
    """Test extract_task_due_date with string datetime."""
    result = extract_task_due_date("2024-01-15T14:30:00Z")
    assert result == datetime(2024, 1, 15, 14, 30, 0)


def test_extract_task_due_date_dict():
    """Test extract_task_due_date with dictionary due date."""
    due_dict = {"date": "2024-01-15"}
    result = extract_task_due_date(due_dict)
    assert result == datetime(2024, 1, 15)


def test_extract_task_due_date_dict_with_time():
    """Test extract_task_due_date with dictionary containing datetime."""
    due_dict = {"date": "2024-01-15T14:30:00Z", "is_recurring": False}
    result = extract_task_due_date(due_dict)
    assert result == datetime(2024, 1, 15, 14, 30, 0)


def test_extract_task_due_date_invalid_string():
    """Test extract_task_due_date returns None for invalid date string."""
    result = extract_task_due_date("invalid-date")
    assert result is None


def test_extract_task_due_date_invalid_dict():
    """Test extract_task_due_date with dict containing invalid date."""
    due_dict = {"date": "invalid-date"}
    result = extract_task_due_date(due_dict)
    assert result is None


def test_extract_task_due_date_dict_with_extra_fields():
    """Test extract_task_due_date ignores extra fields in dict."""
    due_dict = {
        "date": "2024-01-15T10:00:00Z",
        "is_recurring": True,
        "timezone": "UTC",
        "string": "every day"
    }
    result = extract_task_due_date(due_dict)
    assert result == datetime(2024, 1, 15, 10, 0, 0)


def test_extract_task_due_date_edge_cases():
    """Test extract_task_due_date with various edge cases."""
    # End of year
    result1 = extract_task_due_date("2024-12-31")
    assert result1 == datetime(2024, 12, 31)
    
    # Start of year
    result2 = extract_task_due_date("2025-01-01")
    assert result2 == datetime(2025, 1, 1)
    
    # Leap year date
    result3 = extract_task_due_date("2024-02-29")
    assert result3 == datetime(2024, 2, 29)


def test_extract_task_due_date_with_microseconds():
    """Test extract_task_due_date handles microseconds correctly."""
    result = extract_task_due_date("2024-01-15T14:30:45.123456Z")
    assert result == datetime(2024, 1, 15, 14, 30, 45, 123456)


def test_extract_task_due_date_dict_without_date_key():
    """Test extract_task_due_date with dict missing 'date' key."""
    due_dict = {"is_recurring": False, "timezone": "UTC"}
    # Should raise KeyError or return None depending on implementation
    # Based on the code, it will try to access due['date'] which will raise KeyError
    with pytest.raises(KeyError):
        extract_task_due_date(due_dict)
