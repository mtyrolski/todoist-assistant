"""
Tests for plotting functions in todoist.plots module.
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, cast
import plotly.graph_objects as go

from todoist.plots import (
    plot_completed_tasks_periodically,
    plot_cumulative_events_over_time,
    cumsum_completed_tasks_periodically,
    plot_task_lifespans,
)


@pytest.fixture
def sample_task_events_df():
    """Create a sample DataFrame with task events for testing."""
    # Create tasks with various lifespans
    base_date = datetime(2024, 1, 1, 12, 0, 0)

    data = {
        'parent_item_id': [
            # Task 1: completed in 1 hour
            'task1', 'task1',
            # Task 2: completed in 1 day
            'task2', 'task2',
            # Task 3: completed in 7 days
            'task3', 'task3',
            # Task 4: only added (no completion)
            'task4',
            # Task 5: only completed (no added event)
            'task5',
            # Task 6: completed in 5 minutes
            'task6', 'task6',
        ],
        'type': [
            'added', 'completed',
            'added', 'completed',
            'added', 'completed',
            'added',
            'completed',
            'added', 'completed',
        ],
        'title': [
            'Task 1', 'Task 1',
            'Task 2', 'Task 2',
            'Task 3', 'Task 3',
            'Task 4',
            'Task 5',
            'Task 6', 'Task 6',
        ],
        'root_project_name': ['Project A'] * 10,
        'root_project_id': ['proj_a'] * 10,
    }

    dates = [
        base_date, base_date + timedelta(hours=1),
        base_date, base_date + timedelta(days=1),
        base_date, base_date + timedelta(days=7),
        base_date,
        base_date,
        base_date, base_date + timedelta(minutes=5),
    ]

    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'
    return df


@pytest.fixture
def empty_events_df():
    """Create an empty DataFrame with correct structure."""
    df = pd.DataFrame({
        'parent_item_id': [],
        'type': [],
        'title': [],
        'root_project_name': [],
        'root_project_id': [],
    })
    df.index = pd.DatetimeIndex([])
    df.index.name = 'date'
    return df


def test_plot_task_lifespans_returns_figure(sample_task_events_df):
    """Test that plot_task_lifespans returns a Plotly Figure object."""
    fig = plot_task_lifespans(sample_task_events_df)

    assert isinstance(fig, go.Figure)
    assert fig.data is not None
    traces = cast(tuple[Any, ...], fig.data)
    assert len(traces) > 0


def test_plot_task_lifespans_with_valid_data(sample_task_events_df):
    """Test plot_task_lifespans with valid task data."""
    fig = plot_task_lifespans(sample_task_events_df)

    # Should have data traces (histogram and scatter)
    traces = cast(tuple[Any, ...], fig.data)
    assert len(traces) >= 1

    # Check layout properties
    assert fig.layout.title is not None
    assert 'Task Lifespans' in fig.layout.title.text

    # Check x-axis is logarithmic
    assert fig.layout.xaxis.type == 'log'

    # Check axis labels exist
    assert fig.layout.xaxis.title is not None
    assert fig.layout.yaxis.title is not None
    assert fig.layout.xaxis.title.text == ''
    assert 'Frequency' in fig.layout.yaxis.title.text


def test_plot_task_lifespans_empty_data(empty_events_df):
    """Test plot_task_lifespans handles empty data gracefully."""
    fig = plot_task_lifespans(empty_events_df)

    assert isinstance(fig, go.Figure)
    # Changed to check for the specific error message
    assert 'Task Lifespans' in fig.layout.title.text
    assert ('No Data' in fig.layout.title.text or 'No Task Events' in fig.layout.title.text)


def test_plot_task_lifespans_only_added_events():
    """Test plot_task_lifespans with only 'added' events (no completions)."""
    base_date = datetime(2024, 1, 1, 12, 0, 0)

    data = {
        'parent_item_id': ['task1', 'task2', 'task3'],
        'type': ['added', 'added', 'added'],
        'title': ['Task 1', 'Task 2', 'Task 3'],
        'root_project_name': ['Project A'] * 3,
        'root_project_id': ['proj_a'] * 3,
    }

    dates = [base_date, base_date + timedelta(days=1), base_date + timedelta(days=2)]

    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'

    fig = plot_task_lifespans(df)

    # Should handle this gracefully with specific error message
    assert isinstance(fig, go.Figure)
    assert 'Task Lifespans' in fig.layout.title.text
    assert 'No Tasks with Both Added and Completed Events' in fig.layout.title.text


def test_plot_task_lifespans_only_completed_events():
    """Test plot_task_lifespans with only 'completed' events (no added events)."""
    base_date = datetime(2024, 1, 1, 12, 0, 0)

    data = {
        'parent_item_id': ['task1', 'task2', 'task3'],
        'type': ['completed', 'completed', 'completed'],
        'title': ['Task 1', 'Task 2', 'Task 3'],
        'root_project_name': ['Project A'] * 3,
        'root_project_id': ['proj_a'] * 3,
    }

    dates = [base_date, base_date + timedelta(days=1), base_date + timedelta(days=2)]

    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'

    fig = plot_task_lifespans(df)

    # Should handle this gracefully with specific error message
    assert isinstance(fig, go.Figure)
    assert 'Task Lifespans' in fig.layout.title.text
    assert 'No Tasks with Both Added and Completed Events' in fig.layout.title.text


def test_plot_task_lifespans_negative_duration():
    """Test plot_task_lifespans handles negative durations (completed before added)."""
    base_date = datetime(2024, 1, 1, 12, 0, 0)

    data = {
        'parent_item_id': ['task1', 'task1'],
        'type': ['added', 'completed'],
        'title': ['Task 1', 'Task 1'],
        'root_project_name': ['Project A'] * 2,
        'root_project_id': ['proj_a'] * 2,
    }

    # Completed before added (invalid)
    dates = [base_date + timedelta(hours=1), base_date]

    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'

    fig = plot_task_lifespans(df)

    # Should skip invalid duration and show no data
    assert isinstance(fig, go.Figure)


def test_plot_task_lifespans_dark_mode_styling(sample_task_events_df):
    """Test plot_task_lifespans has dark mode styling."""
    fig = plot_task_lifespans(sample_task_events_df)

    # Check for dark theme properties by verifying dark background colors
    assert fig.layout.plot_bgcolor == '#111318'
    assert fig.layout.paper_bgcolor == '#111318'
    # Check that template is set (it's a Template object, not a simple string)
    assert fig.layout.template is not None


def test_plot_task_lifespans_responsive_layout(sample_task_events_df):
    """Test plot_task_lifespans has responsive layout properties."""
    fig = plot_task_lifespans(sample_task_events_df)

    # Check autosize is enabled for responsiveness
    assert fig.layout.autosize is True


def test_plot_task_lifespans_has_gridlines(sample_task_events_df):
    """Task lifespans plot should keep the dashboard gridlines subtle/disabled."""
    fig = plot_task_lifespans(sample_task_events_df)

    assert fig.layout.xaxis.showgrid is False
    assert fig.layout.yaxis.showgrid is False


def test_plot_task_lifespans_has_legend(sample_task_events_df):
    """Test plot_task_lifespans includes a legend."""
    fig = plot_task_lifespans(sample_task_events_df)

    # Check legend configuration
    assert fig.layout.legend is not None


def test_plot_task_lifespans_time_unit_selection():
    """Test plot_task_lifespans selects appropriate time units."""
    base_date = datetime(2024, 1, 1, 12, 0, 0)

    # Test with very short durations (minutes)
    data_minutes = {
        'parent_item_id': ['task1', 'task1', 'task2', 'task2'],
        'type': ['added', 'completed', 'added', 'completed'],
        'title': ['Task 1', 'Task 1', 'Task 2', 'Task 2'],
        'root_project_name': ['Project A'] * 4,
        'root_project_id': ['proj_a'] * 4,
    }
    dates_minutes = [
        base_date, base_date + timedelta(minutes=10),
        base_date, base_date + timedelta(minutes=30),
    ]
    df_minutes = pd.DataFrame(data_minutes, index=pd.DatetimeIndex(dates_minutes))
    df_minutes.index.name = 'date'

    fig = plot_task_lifespans(df_minutes)
    assert isinstance(fig, go.Figure)
    # Should show minute or hour units in the tick labels
    ticktext_minutes = fig.layout.xaxis.ticktext or []
    joined_minutes = " ".join(str(item) for item in ticktext_minutes)
    assert any(unit in joined_minutes for unit in ("m", "h"))

    # Test with longer durations (days)
    data_days = {
        'parent_item_id': ['task3', 'task3', 'task4', 'task4'],
        'type': ['added', 'completed', 'added', 'completed'],
        'title': ['Task 3', 'Task 3', 'Task 4', 'Task 4'],
        'root_project_name': ['Project A'] * 4,
        'root_project_id': ['proj_a'] * 4,
    }
    dates_days = [
        base_date, base_date + timedelta(days=5),
        base_date, base_date + timedelta(days=10),
    ]
    df_days = pd.DataFrame(data_days, index=pd.DatetimeIndex(dates_days))
    df_days.index.name = 'date'

    fig = plot_task_lifespans(df_days)
    assert isinstance(fig, go.Figure)
    # Should show day/week units in the tick labels
    ticktext_days = fig.layout.xaxis.ticktext or []
    joined_days = " ".join(str(item) for item in ticktext_days)
    assert any(unit in joined_days for unit in ("d", "w"))


def test_plot_task_lifespans_handles_missing_task_names():
    """Test plot_task_lifespans handles missing task names gracefully."""
    base_date = datetime(2024, 1, 1, 12, 0, 0)

    data = {
        'parent_item_id': ['task1', 'task1'],
        'type': ['added', 'completed'],
        'title': [None, None],  # Missing task names
        'root_project_name': ['Project A'] * 2,
        'root_project_id': ['proj_a'] * 2,
    }

    dates = [base_date, base_date + timedelta(hours=1)]

    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'

    fig = plot_task_lifespans(df)

    # Should handle missing names and still create the figure
    assert isinstance(fig, go.Figure)


def _weekly_completion_df() -> pd.DataFrame:
    base_date = datetime(2024, 6, 3, 12, 0, 0)  # Monday
    data = {
        'root_project_name': ['Project A', 'Project A', 'Project A'],
        'root_project_id': ['proj_a'] * 3,
        'type': ['completed', 'completed', 'completed'],
        'parent_item_id': ['task1', 'task2', 'task3'],
        'title': ['Task 1', 'Task 2', 'Task 3'],
    }
    dates = [
        base_date - timedelta(days=2),  # previous Saturday (prior week)
        base_date + timedelta(days=0),  # Monday current week
        base_date + timedelta(days=1),  # Tuesday current week
    ]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = 'date'
    return df


def test_plot_completed_tasks_periodically_keeps_current_week():
    """Current partial period should surface as 'so far' + forecast markers (no dotted connector)."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = plot_completed_tasks_periodically(
        df, beg_date, end_date, granularity='W-SUN', project_colors={'Project A': '#123456'}
    )

    traces = cast(tuple[Any, ...], fig.data)
    dotted_traces = [trace for trace in traces if getattr(getattr(trace, "line", None), "dash", None) == "dot"]
    assert not dotted_traces

    forecast_traces = [trace for trace in traces if "(forecast)" in str(getattr(trace, "name", "")).lower()]
    assert forecast_traces
    assert any(pd.to_datetime(x) > end_date for x in cast(Any, forecast_traces[0]).x)


def test_cumsum_completed_tasks_periodically_keeps_current_week():
    """Cumulative plot should surface the partial period as 'so far' + forecast markers."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = cumsum_completed_tasks_periodically(
        df, beg_date, end_date, granularity='W-SUN', project_colors={'Project A': '#123456'}
    )

    traces = cast(tuple[Any, ...], fig.data)
    dotted_traces = [trace for trace in traces if getattr(getattr(trace, "line", None), "dash", None) == "dot"]
    assert not dotted_traces

    forecast_traces = [trace for trace in traces if "(forecast)" in str(getattr(trace, "name", "")).lower()]
    assert forecast_traces
    assert any(pd.to_datetime(x) > end_date for x in cast(Any, forecast_traces[0]).x)


def test_plot_cumulative_events_over_time_includes_partial_period():
    """Cumulative events plot should surface the in-progress period."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 10)

    fig = plot_cumulative_events_over_time(df, beg_date, end_date, granularity='W-SUN')

    traces = cast(tuple[Any, ...], fig.data)
    dotted_traces = [trace for trace in traces if 'current period' in str(getattr(trace, "name", "")).lower()]
    assert dotted_traces, 'Partial period cumulative trace should be present'
    dotted_trace = dotted_traces[0]
    assert cast(Any, dotted_trace).line.dash == 'dot'
    assert any(pd.to_datetime(x) > end_date for x in cast(Any, dotted_trace).x)
