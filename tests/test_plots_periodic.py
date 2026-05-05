"""Tests for Todoist dashboard plotting helpers."""

from datetime import datetime, timedelta
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go

from todoist.dashboard.plots import (
    cumsum_completed_tasks_periodically,
    plot_completed_tasks_periodically,
    plot_weekly_completion_trend,
)

def _weekly_completion_df() -> pd.DataFrame:
    base_date = datetime(2024, 6, 3, 12, 0, 0)  # Monday
    data = {
        "root_project_name": ["Project A", "Project A", "Project A"],
        "root_project_id": ["proj_a"] * 3,
        "type": ["completed", "completed", "completed"],
        "parent_item_id": ["task1", "task2", "task3"],
        "title": ["Task 1", "Task 2", "Task 3"],
    }
    dates = [
        base_date - timedelta(days=2),  # previous Saturday (prior week)
        base_date + timedelta(days=0),  # Monday current week
        base_date + timedelta(days=1),  # Tuesday current week
    ]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = "date"
    return df


def _weekly_completion_with_inactive_project_df() -> pd.DataFrame:
    """Create data where one project has no completions in the selected window."""

    base_date = datetime(2024, 6, 3, 12, 0, 0)  # Monday
    data = {
        "root_project_name": ["Project B", "Project A", "Project A"],
        "root_project_id": ["proj_b", "proj_a", "proj_a"],
        "type": ["completed", "completed", "completed"],
        "parent_item_id": ["task3", "task1", "task2"],
        "title": ["Task 3", "Task 1", "Task 2"],
    }
    dates = [
        base_date - timedelta(days=10),  # B outside period
        base_date + timedelta(days=0),  # A in period
        base_date + timedelta(days=1),  # A in period
    ]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = "date"
    return df


def _weekly_completion_trend_df(*, total_weeks: int = 30) -> pd.DataFrame:
    base_monday = datetime(2024, 1, 1, 9, 0, 0)  # Monday
    rows: list[dict[str, str]] = []
    dates: list[datetime] = []

    for week in range(total_weeks):
        week_start = base_monday + timedelta(weeks=week)
        daily_pattern = [
            1 + (week % 3),  # Monday
            week % 2,  # Tuesday
            2 + ((week + 1) % 2),  # Wednesday
            1,  # Thursday
            (week + 1) % 2,  # Friday
            0,  # Saturday
            1,  # Sunday
        ]
        for day, task_count in enumerate(daily_pattern):
            for task_idx in range(task_count):
                dates.append(week_start + timedelta(days=day, hours=task_idx))
                rows.append(
                    {
                        "root_project_name": "Project A",
                        "root_project_id": "proj_a",
                        "type": "completed",
                        "parent_item_id": f"w{week}-d{day}-t{task_idx}",
                        "title": f"Task {week}-{day}-{task_idx}",
                    }
                )

    df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
    df.index.name = "date"
    return df


def test_plot_completed_tasks_periodically_keeps_current_week():
    """Current partial period should surface as 'so far' + forecast markers (no dotted connector)."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = plot_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    dotted_traces = [
        trace
        for trace in traces
        if getattr(getattr(trace, "line", None), "dash", None) == "dot"
    ]
    assert not dotted_traces

    forecast_traces = [
        trace
        for trace in traces
        if "(forecast)" in str(getattr(trace, "name", "")).lower()
    ]
    assert forecast_traces
    assert any(pd.to_datetime(x) > end_date for x in cast(Any, forecast_traces[0]).x)


def test_cumsum_completed_tasks_periodically_keeps_current_week():
    """Cumulative plot should surface the partial period as 'so far' + forecast markers."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = cumsum_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    dotted_traces = [
        trace
        for trace in traces
        if getattr(getattr(trace, "line", None), "dash", None) == "dot"
    ]
    assert not dotted_traces

    forecast_traces = [
        trace
        for trace in traces
        if "(forecast)" in str(getattr(trace, "name", "")).lower()
    ]
    assert forecast_traces
    assert any(pd.to_datetime(x) > end_date for x in cast(Any, forecast_traces[0]).x)


def test_plot_completed_tasks_periodically_hides_inactive_projects_in_range():
    """Projects with zero completions in selected period should not produce zero lines."""

    df = _weekly_completion_with_inactive_project_df()
    beg_date = datetime(2024, 6, 1)
    end_date = datetime(2024, 6, 5)

    fig = plot_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456", "Project B": "#654321"},
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert any(name.startswith("Project A") for name in trace_names)
    assert not any(name.startswith("Project B") for name in trace_names)


def test_cumsum_completed_tasks_periodically_hides_inactive_projects_in_range():
    """Cumulative plot should also hide projects with no completions in selected period."""

    df = _weekly_completion_with_inactive_project_df()
    beg_date = datetime(2024, 6, 1)
    end_date = datetime(2024, 6, 5)

    fig = cumsum_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456", "Project B": "#654321"},
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert any(name.startswith("Project A") for name in trace_names)
    assert not any(name.startswith("Project B") for name in trace_names)


def test_plot_completed_tasks_periodically_adds_total_overlay_on_primary_axis():
    """Periodic plot should include all-project totals on the primary y-axis."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = plot_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    total_traces = [
        trace
        for trace in traces
        if "all projects (total)" in str(getattr(trace, "name", "")).lower()
    ]
    assert total_traces
    assert getattr(cast(Any, total_traces[0]), "yaxis", None) in (None, "y")
    assert getattr(cast(Any, fig.layout), "yaxis2", None) is None


def test_cumsum_completed_tasks_periodically_adds_total_overlay_on_primary_axis():
    """Cumulative plot should include all-project totals on the primary y-axis."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = cumsum_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    total_traces = [
        trace
        for trace in traces
        if "all projects (total cumulative)" in str(getattr(trace, "name", "")).lower()
    ]
    assert total_traces
    assert getattr(cast(Any, total_traces[0]), "yaxis", None) in (None, "y")
    assert getattr(cast(Any, fig.layout), "yaxis2", None) is None


def test_cumsum_completed_tasks_periodically_curves_projects_but_keeps_total_linear():
    """Project cumulative lines can curve, but the total overlay stays linear."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = cumsum_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    project_lines = [
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "Project A"
    ]
    total_lines = [
        trace
        for trace in traces
        if "all projects (total cumulative)" in str(getattr(trace, "name", "")).lower()
    ]
    assert project_lines
    assert total_lines
    assert all(
        getattr(getattr(trace, "line", None), "shape", None) == "spline"
        for trace in project_lines
    )
    assert all(
        getattr(getattr(trace, "line", None), "shape", None) in (None, "linear")
        for trace in total_lines
    )


def test_plot_completed_tasks_periodically_can_disable_total_overlay():
    """Secondary-axis total line should be optional and hideable via function flag."""

    df = _weekly_completion_df()
    beg_date = datetime(2024, 5, 27)
    end_date = datetime(2024, 6, 5)

    fig = plot_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="W-SUN",
        project_colors={"Project A": "#123456"},
        include_total_overlay=False,
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert not any("all projects" in name.lower() for name in trace_names)

def test_plot_weekly_completion_trend_uses_legend_toggles_for_optional_windows():
    """Weekly trend should keep 3w/current fixed and expose 6w/12w/24w as legend toggles."""

    df = _weekly_completion_trend_df()
    fig = plot_weekly_completion_trend(df, end_date=datetime(2024, 7, 24))

    assert isinstance(fig, go.Figure)
    assert not fig.layout.updatemenus

    traces = cast(tuple[Any, ...], fig.data)
    legend_traces = [trace for trace in traces if getattr(trace, "showlegend", False)]
    legend_labels = [str(getattr(trace, "name", "")) for trace in legend_traces]

    assert any("6w baseline" in label for label in legend_labels)
    assert any("12w baseline" in label for label in legend_labels)
    assert any("24w baseline" in label for label in legend_labels)

    # Optional windows should be hidden by default but available via legend.
    assert all(
        getattr(trace, "visible", None) == "legendonly" for trace in legend_traces
    )

    # Fixed traces (current week + 3w baseline) stay visible and non-legend.
    fixed_traces = [
        trace
        for trace in traces
        if not getattr(trace, "showlegend", False)
        and (
            "current week" in str(getattr(trace, "name", "")).lower()
            or "3w baseline" in str(getattr(trace, "name", "")).lower()
        )
    ]
    assert fixed_traces
    assert all(
        getattr(trace, "visible", None) in (None, True) for trace in fixed_traces
    )


def test_plot_weekly_completion_trend_hides_future_days_for_current_week():
    """Current week line must stop at end_date (no projected points)."""

    df = _weekly_completion_trend_df()
    end_date = datetime(2024, 4, 17)  # Wednesday
    fig = plot_weekly_completion_trend(df, end_date=end_date)

    traces = cast(tuple[Any, ...], fig.data)
    current_traces = [
        trace
        for trace in traces
        if "current week" in str(getattr(trace, "name", "")).lower()
        and getattr(trace, "visible", None) in (None, True)
    ]
    assert current_traces, "Expected a visible current-week trace."

    y_values = list(cast(Any, current_traces[0]).y)
    assert len(y_values) == 7
    assert pd.isna(y_values[3])  # Thursday
    assert pd.isna(y_values[6])  # Sunday


def test_plot_weekly_completion_trend_skips_unavailable_long_window():
    """24w optional baseline should be omitted when fewer than 24 historical weeks exist."""

    df = _weekly_completion_trend_df(total_weeks=14)
    fig = plot_weekly_completion_trend(df, end_date=datetime(2024, 4, 17))

    legend_labels = [
        str(getattr(trace, "name", ""))
        for trace in cast(tuple[Any, ...], fig.data)
        if getattr(trace, "showlegend", False)
    ]
    assert any("6w baseline" in label for label in legend_labels)
    assert any("12w baseline" in label for label in legend_labels)
    assert not any("24w baseline" in label for label in legend_labels)
