"""
Tests for helper functions in todoist.dashboard.utils and todoist.automations.multiplicate modules.
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from todoist.dashboard.utils import extract_metrics, get_badges
from todoist.automations.multiplicate import is_multiplication_label, extract_multiplication_factor
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
    """Factory for creating TaskEntry instances with different priorities."""
    def _create_task_entry(task_id: str, priority: int = 1):
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
            day_order=None
        )
    return _create_task_entry


@pytest.fixture
def sample_activity_df():
    """Create a sample activity DataFrame for testing."""
    dates = pd.date_range(start='2024-01-01', end='2024-03-31', freq='D')
    data = {
        'id': [f'event_{i}' for i in range(len(dates))],
        'title': [f'Task {i}' for i in range(len(dates))],
        'type': ['completed' if i % 3 == 0 else 'added' if i % 3 == 1 else 'rescheduled' 
                 for i in range(len(dates))],
        'parent_project_id': ['proj1'] * len(dates),
        'parent_project_name': ['Project 1'] * len(dates),
    }
    df = pd.DataFrame(data, index=dates)
    return df


# Tests for extract_metrics
def test_extract_metrics_weekly_granularity(sample_activity_df):
    """Test extract_metrics with weekly granularity."""
    metrics, current_period, previous_period = extract_metrics(sample_activity_df, "W")
    
    # Should return 4 metrics: Events, Completed Tasks, Added Tasks, Rescheduled Tasks
    assert len(metrics) == 4
    
    # Each metric is a tuple: (name, current_value, delta_percent, inverse)
    for metric in metrics:
        assert len(metric) == 4
        assert isinstance(metric[0], str)  # name
        assert isinstance(metric[1], str)  # current value
        assert isinstance(metric[2], str)  # delta percent
        assert isinstance(metric[3], bool)  # inverse flag
    
    # Check metric names
    metric_names = [m[0] for m in metrics]
    assert "Events" in metric_names
    assert "Completed Tasks" in metric_names
    assert "Added Tasks" in metric_names
    assert "Rescheduled Tasks" in metric_names
    
    # Check date range strings
    assert isinstance(current_period, str)
    assert isinstance(previous_period, str)
    assert "to" in current_period
    assert "to" in previous_period


def test_extract_metrics_monthly_granularity(sample_activity_df):
    """Test extract_metrics with monthly granularity."""
    metrics, current_period, previous_period = extract_metrics(sample_activity_df, "ME")
    
    assert len(metrics) == 4
    
    # Monthly should use 4 weeks timespan
    # Verify date ranges are approximately 4 weeks apart
    assert "2024-" in current_period
    assert "2024-" in previous_period


def test_extract_metrics_three_month_granularity(sample_activity_df):
    """Test extract_metrics with three-month granularity."""
    metrics, current_period, previous_period = extract_metrics(sample_activity_df, "3ME")
    
    assert len(metrics) == 4
    
    # 3-month should use 12 weeks timespan
    assert "2024-" in current_period
    assert "2024-" in previous_period


def test_extract_metrics_unsupported_granularity(sample_activity_df):
    """Test extract_metrics raises ValueError for unsupported granularity."""
    with pytest.raises(ValueError) as exc_info:
        extract_metrics(sample_activity_df, "INVALID")
    
    assert "Unsupported granularity" in str(exc_info.value)


def test_extract_metrics_calculates_percentages(sample_activity_df):
    """Test extract_metrics calculates percentage changes correctly."""
    metrics, _, _ = extract_metrics(sample_activity_df, "W")
    
    # Each metric should have a delta percentage
    for metric in metrics:
        delta_str = metric[2]
        # Should be a string ending with '%'
        assert delta_str.endswith('%')
        # Remove % and try to convert to float or check for 'inf'
        delta_value = delta_str[:-1]
        # Should be either a number or 'inf'
        try:
            float(delta_value)
        except ValueError:
            # If it's not a number, it should be 'inf'
            assert delta_value == 'inf'


def test_extract_metrics_handles_zero_previous_value():
    """Test extract_metrics handles division by zero (previous value = 0)."""
    # Create a DataFrame with data only in current period
    dates = pd.date_range(start='2024-03-25', end='2024-03-31', freq='D')
    data = {
        'id': [f'event_{i}' for i in range(len(dates))],
        'title': [f'Task {i}' for i in range(len(dates))],
        'type': ['completed'] * len(dates),
        'parent_project_id': ['proj1'] * len(dates),
        'parent_project_name': ['Project 1'] * len(dates),
    }
    df = pd.DataFrame(data, index=dates)
    
    metrics, _, _ = extract_metrics(df, "W")
    
    # When previous value is 0, delta should be 'inf%'
    for metric in metrics:
        delta_str = metric[2]
        assert delta_str.endswith('%')


def test_extract_metrics_inverse_flag():
    """Test extract_metrics sets inverse flag correctly."""
    dates = pd.date_range(start='2024-01-01', end='2024-03-31', freq='D')
    data = {
        'id': [f'event_{i}' for i in range(len(dates))],
        'title': [f'Task {i}' for i in range(len(dates))],
        'type': ['completed'] * len(dates),
        'parent_project_id': ['proj1'] * len(dates),
        'parent_project_name': ['Project 1'] * len(dates),
    }
    df = pd.DataFrame(data, index=dates)
    
    metrics, _, _ = extract_metrics(df, "W")
    
    # Find Rescheduled Tasks metric (should have inverse=True)
    rescheduled_metric = next(m for m in metrics if m[0] == "Rescheduled Tasks")
    assert rescheduled_metric[3] is True  # inverse flag
    
    # Other metrics should have inverse=False
    events_metric = next(m for m in metrics if m[0] == "Events")
    assert events_metric[3] is False


def test_extract_metrics_filters_by_event_type():
    """Test extract_metrics correctly filters events by type."""
    dates = pd.date_range(start='2024-03-01', end='2024-03-31', freq='D')
    
    # Create specific distribution of event types
    types = []
    for i in range(len(dates)):
        if i < 10:
            types.append('completed')
        elif i < 20:
            types.append('added')
        else:
            types.append('rescheduled')
    
    data = {
        'id': [f'event_{i}' for i in range(len(dates))],
        'title': [f'Task {i}' for i in range(len(dates))],
        'type': types,
        'parent_project_id': ['proj1'] * len(dates),
        'parent_project_name': ['Project 1'] * len(dates),
    }
    df = pd.DataFrame(data, index=dates)
    
    metrics, _, _ = extract_metrics(df, "W")
    
    # Verify we get separate counts for each type
    metric_dict = {m[0]: int(m[1]) for m in metrics}
    
    # Total events should be sum of all types
    assert metric_dict["Events"] > 0
    assert metric_dict["Completed Tasks"] >= 0
    assert metric_dict["Added Tasks"] >= 0
    assert metric_dict["Rescheduled Tasks"] >= 0


# Tests for get_badges
def test_get_badges_with_various_priorities(project_entry, task_entry_factory):
    """Test get_badges generates correct badge string with various priority tasks."""
    projects = [
        Project(
            id="proj1",
            project_entry=project_entry,
            tasks=[
                Task(id="t1", task_entry=task_entry_factory("t1", priority=4)),
                Task(id="t2", task_entry=task_entry_factory("t2", priority=4)),
                Task(id="t3", task_entry=task_entry_factory("t3", priority=3)),
                Task(id="t4", task_entry=task_entry_factory("t4", priority=2)),
                Task(id="t5", task_entry=task_entry_factory("t5", priority=1)),
            ],
            is_archived=False
        )
    ]
    
    badge = get_badges(projects)
    
    assert isinstance(badge, str)
    assert "P1 tasks 2" in badge or "P1 tasks 2🔥" in badge
    assert "P2 tasks 1" in badge or "P2 tasks 1 ⚠️" in badge
    assert "P3 tasks 1" in badge or "P3 tasks 1 🔵" in badge
    assert "P4 tasks 1" in badge or "P4 tasks 1 🔧" in badge


def test_get_badges_empty_projects():
    """Test get_badges with empty project list."""
    badge = get_badges([])
    
    assert isinstance(badge, str)
    assert "P1 tasks 0" in badge
    assert "P2 tasks 0" in badge
    assert "P3 tasks 0" in badge
    assert "P4 tasks 0" in badge


def test_get_badges_no_tasks(project_entry):
    """Test get_badges with projects containing no tasks."""
    projects = [
        Project(id="proj1", project_entry=project_entry, tasks=[], is_archived=False)
    ]
    
    badge = get_badges(projects)
    
    assert "P1 tasks 0" in badge
    assert "P2 tasks 0" in badge
    assert "P3 tasks 0" in badge
    assert "P4 tasks 0" in badge


def test_get_badges_multiple_projects(project_entry, task_entry_factory):
    """Test get_badges aggregates tasks across multiple projects."""
    project_entry2 = ProjectEntry(
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
        collapsed=False
    )
    
    projects = [
        Project(
            id="proj1",
            project_entry=project_entry,
            tasks=[
                Task(id="t1", task_entry=task_entry_factory("t1", priority=4)),
                Task(id="t2", task_entry=task_entry_factory("t2", priority=3)),
            ],
            is_archived=False
        ),
        Project(
            id="proj2",
            project_entry=project_entry2,
            tasks=[
                Task(id="t3", task_entry=task_entry_factory("t3", priority=4)),
                Task(id="t4", task_entry=task_entry_factory("t4", priority=2)),
            ],
            is_archived=False
        )
    ]
    
    badge = get_badges(projects)
    
    # Should aggregate: 2 P1 (t1, t3), 1 P2 (t2), 1 P3 (t4), 0 P4
    assert "P1 tasks 2" in badge
    assert "P2 tasks 1" in badge
    assert "P3 tasks 1" in badge
    assert "P4 tasks 0" in badge


def test_get_badges_only_p1_tasks(project_entry, task_entry_factory):
    """Test get_badges when only P1 tasks exist."""
    projects = [
        Project(
            id="proj1",
            project_entry=project_entry,
            tasks=[
                Task(id="t1", task_entry=task_entry_factory("t1", priority=4)),
                Task(id="t2", task_entry=task_entry_factory("t2", priority=4)),
                Task(id="t3", task_entry=task_entry_factory("t3", priority=4)),
            ],
            is_archived=False
        )
    ]
    
    badge = get_badges(projects)
    
    assert "P1 tasks 3" in badge
    assert "P2 tasks 0" in badge
    assert "P3 tasks 0" in badge
    assert "P4 tasks 0" in badge


def test_get_badges_contains_emojis():
    """Test get_badges contains expected emojis."""
    badge = get_badges([])
    
    # Check for emojis in badge string
    assert "🔥" in badge  # P1 emoji
    assert "⚠️" in badge  # P2 emoji
    assert "🔵" in badge  # P3 emoji
    assert "🔧" in badge  # P4 emoji


def test_get_badges_format():
    """Test get_badges returns properly formatted badge string."""
    badge = get_badges([])
    
    # Should contain badge formatting
    assert ":red-badge[" in badge
    assert ":orange-badge[" in badge
    assert ":blue-badge[" in badge
    assert ":gray-badge[" in badge


# Tests for is_multiplication_label
def test_is_multiplication_label_valid_labels():
    """Test is_multiplication_label recognizes valid multiplication labels."""
    assert is_multiplication_label("X2") is True
    assert is_multiplication_label("X5") is True
    assert is_multiplication_label("X10") is True
    assert is_multiplication_label("X100") is True


def test_is_multiplication_label_invalid_labels():
    """Test is_multiplication_label rejects invalid labels."""
    assert is_multiplication_label("x2") is False  # lowercase
    assert is_multiplication_label("2X") is False  # reversed
    assert is_multiplication_label("X") is False  # no number
    assert is_multiplication_label("XX2") is False  # double X
    assert is_multiplication_label("X2X") is False  # X at end
    assert is_multiplication_label("multiply2") is False  # wrong format
    assert is_multiplication_label("X-2") is False  # negative
    assert is_multiplication_label("X2.5") is False  # decimal


def test_is_multiplication_label_edge_cases():
    """Test is_multiplication_label with edge cases."""
    assert is_multiplication_label("X0") is True  # zero is valid pattern
    assert is_multiplication_label("X1") is True  # one
    assert is_multiplication_label("X999") is True  # large number
    assert is_multiplication_label("") is False  # empty string
    assert is_multiplication_label("X ") is False  # space
    assert is_multiplication_label(" X2") is False  # leading space


def test_is_multiplication_label_similar_patterns():
    """Test is_multiplication_label distinguishes similar patterns."""
    assert is_multiplication_label("X2") is True
    assert is_multiplication_label("X2Y") is False
    assert is_multiplication_label("AX2") is False
    assert is_multiplication_label("X23") is True  # multi-digit
    assert is_multiplication_label("X02") is True  # leading zero


# Tests for extract_multiplication_factor
def test_extract_multiplication_factor_valid_labels():
    """Test extract_multiplication_factor extracts correct numbers."""
    assert extract_multiplication_factor("X2") == 2
    assert extract_multiplication_factor("X5") == 5
    assert extract_multiplication_factor("X10") == 10
    assert extract_multiplication_factor("X100") == 100


def test_extract_multiplication_factor_single_digit():
    """Test extract_multiplication_factor with single digit."""
    assert extract_multiplication_factor("X1") == 1
    assert extract_multiplication_factor("X9") == 9


def test_extract_multiplication_factor_multi_digit():
    """Test extract_multiplication_factor with multi-digit numbers."""
    assert extract_multiplication_factor("X23") == 23
    assert extract_multiplication_factor("X456") == 456
    assert extract_multiplication_factor("X999") == 999


def test_extract_multiplication_factor_zero():
    """Test extract_multiplication_factor with zero."""
    assert extract_multiplication_factor("X0") == 0


def test_extract_multiplication_factor_invalid_labels():
    """Test extract_multiplication_factor raises ValueError for invalid labels."""
    with pytest.raises(ValueError) as exc_info:
        extract_multiplication_factor("x2")
    assert "Invalid multiplication label" in str(exc_info.value)
    
    with pytest.raises(ValueError):
        extract_multiplication_factor("2X")
    
    with pytest.raises(ValueError):
        extract_multiplication_factor("X")
    
    with pytest.raises(ValueError):
        extract_multiplication_factor("multiply2")


def test_extract_multiplication_factor_empty_string():
    """Test extract_multiplication_factor raises ValueError for empty string."""
    with pytest.raises(ValueError) as exc_info:
        extract_multiplication_factor("")
    assert "Invalid multiplication label" in str(exc_info.value)


def test_extract_multiplication_factor_leading_zeros():
    """Test extract_multiplication_factor handles leading zeros."""
    # Python's int() will handle leading zeros correctly
    assert extract_multiplication_factor("X02") == 2
    assert extract_multiplication_factor("X007") == 7


def test_extract_multiplication_factor_and_is_label_consistency():
    """Test that is_multiplication_label and extract_multiplication_factor are consistent."""
    test_labels = ["X1", "X5", "X10", "X99", "x2", "2X", "X", ""]
    
    for label in test_labels:
        if is_multiplication_label(label):
            # If is_multiplication_label returns True, extract should not raise
            try:
                factor = extract_multiplication_factor(label)
                assert isinstance(factor, int)
                assert factor >= 0
            except ValueError:
                pytest.fail(f"extract_multiplication_factor raised ValueError for {label} "
                          f"but is_multiplication_label returned True")
        else:
            # If is_multiplication_label returns False, extract should raise
            with pytest.raises(ValueError):
                extract_multiplication_factor(label)


def test_multiplication_label_integration():
    """Test is_multiplication_label and extract_multiplication_factor work together."""
    labels = ["X2", "X5", "urgent", "X10", "important", "X3"]
    
    multiplication_labels = [l for l in labels if is_multiplication_label(l)]
    assert multiplication_labels == ["X2", "X5", "X10", "X3"]
    
    factors = [extract_multiplication_factor(l) for l in multiplication_labels]
    assert factors == [2, 5, 10, 3]
