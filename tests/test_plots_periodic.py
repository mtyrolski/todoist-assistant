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


def _monthly_completion_df() -> pd.DataFrame:
    data = {
        "root_project_name": ["Project A", "Project A", "Project A", "Project A"],
        "root_project_id": ["proj_a"] * 4,
        "type": ["completed", "completed", "completed", "completed"],
        "parent_item_id": ["task1", "task2", "task3", "task4"],
        "title": ["Task 1", "Task 2", "Task 3", "Task 4"],
    }
    dates = [
        datetime(2024, 4, 10, 12, 0, 0),
        datetime(2024, 4, 20, 12, 0, 0),
        datetime(2024, 5, 3, 12, 0, 0),
        datetime(2024, 5, 10, 12, 0, 0),
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


def _archived_visibility_df() -> pd.DataFrame:
    rows = [
        {
            "root_project_name": "Deepflare",
            "root_project_id": "deepflare",
            "type": "completed",
            "parent_item_id": "deepflare-old",
            "title": "Deepflare old task",
            "date": datetime(2023, 3, 15, 12, 0, 0),
        },
        {
            "root_project_name": "Deepflare",
            "root_project_id": "deepflare",
            "type": "completed",
            "parent_item_id": "deepflare-selected",
            "title": "Deepflare selected task",
            "date": datetime(2024, 6, 2, 12, 0, 0),
        },
        {
            "root_project_name": "OldOnly",
            "root_project_id": "old-only",
            "type": "completed",
            "parent_item_id": "old-only-task",
            "title": "Old only task",
            "date": datetime(2023, 5, 10, 12, 0, 0),
        },
    ]
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.DatetimeIndex(df.index)
    return df


def _root_project_visibility_df() -> pd.DataFrame:
    rows = [
        {
            "root_project_name": "Academy",
            "root_project_id": "academy",
            "parent_project_name": "DeepMhcFlare",
            "parent_project_id": "deep-mhc-flare",
            "type": "completed",
            "parent_item_id": "deep-mhc-flare-task",
            "title": "DeepMhcFlare task",
            "date": datetime(2024, 6, 2, 12, 0, 0),
        },
        {
            "root_project_name": "skynet",
            "root_project_id": "skynet",
            "parent_project_name": "MSFT",
            "parent_project_id": "msft",
            "type": "completed",
            "parent_item_id": "msft-task",
            "title": "MSFT task",
            "date": datetime(2024, 6, 3, 12, 0, 0),
        },
    ]
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.DatetimeIndex(df.index)
    return df


def _sparse_cumulative_df() -> pd.DataFrame:
    rows = [
        {
            "root_project_name": "Large",
            "root_project_id": "large",
            "type": "completed",
            "parent_item_id": f"large-{idx}",
            "title": f"Large {idx}",
            "date": datetime(2024, 1, 1, 12, 0, 0) + timedelta(seconds=idx),
        }
        for idx in range(100)
    ]
    rows.append(
        {
            "root_project_name": "Small",
            "root_project_id": "small",
            "type": "completed",
            "parent_item_id": "small-1",
            "title": "Small 1",
            "date": datetime(2024, 1, 8, 12, 0, 0),
        }
    )
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.DatetimeIndex(df.index)
    return df


def _archived_current_period_sparse_df() -> pd.DataFrame:
    rows = [
        {
            "root_project_name": "Archived",
            "root_project_id": "archived",
            "type": "completed",
            "parent_item_id": "archived-old",
            "title": "Archived old",
            "date": datetime(2024, 5, 20, 12, 0, 0),
        },
        {
            "root_project_name": "Active",
            "root_project_id": "active",
            "type": "completed",
            "parent_item_id": "active-gap",
            "title": "Active gap",
            "date": datetime(2024, 5, 27, 12, 0, 0),
        },
        {
            "root_project_name": "Archived",
            "root_project_id": "archived",
            "type": "completed",
            "parent_item_id": "archived-current",
            "title": "Archived current",
            "date": datetime(2024, 6, 3, 12, 0, 0),
        },
    ]
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.DatetimeIndex(df.index)
    return df


def _freeze_periodic_now(monkeypatch: Any, now: datetime) -> None:
    import todoist.dashboard._plot_periodic as periodic_module

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            if tz is None:
                return now
            return now.replace(tzinfo=tz)

    monkeypatch.setattr(periodic_module, "datetime", FixedDateTime)


def _normalized_trace_x(trace: Any) -> list[pd.Timestamp]:
    return [
        cast(pd.Timestamp, pd.Timestamp(value)).normalize()
        for value in cast(Any, trace).x
    ]


def _trace_marker_color(trace: Any) -> str:
    return str(getattr(getattr(trace, "marker", None), "color", ""))


def _trace_marker_line_color(trace: Any) -> str:
    marker_line = getattr(getattr(trace, "marker", None), "line", None)
    return str(getattr(marker_line, "color", ""))


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


def test_plot_completed_tasks_periodically_dashes_current_month_when_range_extends_past_today(
    monkeypatch: Any,
):
    """Monthly current period should be split out as a dashed forecast segment."""

    _freeze_periodic_now(monkeypatch, datetime(2024, 5, 13, 12, 0, 0))
    df = _monthly_completion_df()
    beg_date = datetime(2024, 4, 1)
    end_date = datetime(2024, 7, 15)
    current_month_label = pd.Timestamp("2024-05-31")

    fig = plot_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="ME",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    total_trace = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")).lower() == "all projects (total)"
    )
    assert current_month_label not in _normalized_trace_x(total_trace)

    forecast_line = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")).lower() == "all projects (forecast line)"
    )
    assert getattr(getattr(forecast_line, "line", None), "dash", None) == "dash"
    assert _normalized_trace_x(forecast_line)[-1] == current_month_label


def test_plot_completed_tasks_periodically_uses_matching_forecast_marker_colors(
    monkeypatch: Any,
):
    _freeze_periodic_now(monkeypatch, datetime(2024, 5, 13, 12, 0, 0))
    df = _monthly_completion_df()
    fig = plot_completed_tasks_periodically(
        df,
        datetime(2024, 4, 1),
        datetime(2024, 7, 15),
        granularity="ME",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    project_so_far = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "Project A (so far)"
    )
    project_forecast = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "Project A (forecast)"
    )
    total_so_far = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "All Projects (so far)"
    )
    total_forecast = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "All Projects (forecast)"
    )

    assert _trace_marker_line_color(project_so_far) == "#123456"
    assert _trace_marker_color(project_forecast) == "#123456"
    assert _trace_marker_color(total_forecast) == _trace_marker_line_color(total_so_far)


def test_plot_completed_tasks_periodically_does_not_forecast_stale_history(
    monkeypatch: Any,
):
    _freeze_periodic_now(monkeypatch, datetime(2026, 5, 13, 12, 0, 0))
    df = _archived_visibility_df()

    fig = plot_completed_tasks_periodically(
        df,
        datetime(2023, 1, 1),
        datetime(2026, 5, 13),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
    )

    trace_names = [
        str(getattr(trace, "name", "")).lower()
        for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert not any("forecast" in name or "so far" in name for name in trace_names)


def test_plot_completed_tasks_periodically_keeps_archived_points_sparse_without_forecast(
    monkeypatch: Any,
) -> None:
    _freeze_periodic_now(monkeypatch, datetime(2024, 6, 5, 12, 0, 0))

    fig = plot_completed_tasks_periodically(
        _archived_current_period_sparse_df(),
        datetime(2024, 5, 1),
        datetime(2024, 6, 20),
        granularity="W-SUN",
        project_colors={"Archived": "#123456", "Active": "#654321"},
        always_visible_projects={"Archived"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    archived_trace = next(
        trace for trace in traces if str(getattr(trace, "name", "")) == "Archived"
    )

    assert _normalized_trace_x(archived_trace) == [
        pd.Timestamp("2024-05-26"),
        pd.Timestamp("2024-06-09"),
    ]
    assert not any(
        str(getattr(trace, "name", "")).startswith("Archived (")
        for trace in traces
    )


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


def test_cumsum_completed_tasks_periodically_dashes_current_month_when_range_extends_past_today(
    monkeypatch: Any,
):
    """Monthly cumulative plot should not draw the in-progress month as solid history."""

    _freeze_periodic_now(monkeypatch, datetime(2024, 5, 13, 12, 0, 0))
    df = _monthly_completion_df()
    beg_date = datetime(2024, 4, 1)
    end_date = datetime(2024, 7, 15)
    current_month_label = pd.Timestamp("2024-05-31")

    fig = cumsum_completed_tasks_periodically(
        df,
        beg_date,
        end_date,
        granularity="ME",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    total_trace = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")).lower()
        == "all projects (total cumulative)"
    )
    assert current_month_label not in _normalized_trace_x(total_trace)

    forecast_line = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")).lower() == "all projects (forecast line)"
    )
    assert getattr(getattr(forecast_line, "line", None), "dash", None) == "dash"
    assert _normalized_trace_x(forecast_line)[-1] == current_month_label


def test_cumsum_completed_tasks_periodically_uses_matching_forecast_marker_colors(
    monkeypatch: Any,
):
    _freeze_periodic_now(monkeypatch, datetime(2024, 5, 13, 12, 0, 0))
    df = _monthly_completion_df()
    fig = cumsum_completed_tasks_periodically(
        df,
        datetime(2024, 4, 1),
        datetime(2024, 7, 15),
        granularity="ME",
        project_colors={"Project A": "#123456"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    project_so_far = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "Project A (so far)"
    )
    project_forecast = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "Project A (forecast)"
    )
    total_so_far = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "All Projects (so far)"
    )
    total_forecast = next(
        trace
        for trace in traces
        if str(getattr(trace, "name", "")) == "All Projects (forecast)"
    )

    assert _trace_marker_line_color(project_so_far) == "#123456"
    assert _trace_marker_color(project_forecast) == "#123456"
    assert _trace_marker_color(total_forecast) == _trace_marker_line_color(total_so_far)


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


def test_plot_completed_tasks_periodically_keeps_roots_from_full_history_range():
    """Root projects remain visible when the selected range includes their history."""

    fig = plot_completed_tasks_periodically(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    trace_names = [str(getattr(trace, "name", "")) for trace in traces]
    deepflare_trace = next(
        trace for trace in traces if str(getattr(trace, "name", "")) == "Deepflare"
    )

    assert "Deepflare" in trace_names
    assert "OldOnly" in trace_names
    assert getattr(getattr(deepflare_trace, "line", None), "color", None) == "#ff8800"


def test_cumsum_completed_tasks_periodically_keeps_projects_from_full_history_range():
    fig = cumsum_completed_tasks_periodically(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert "Deepflare" in trace_names
    assert "OldOnly" in trace_names


def test_plot_completed_tasks_periodically_uses_selected_range_for_root_visibility():
    fig = plot_completed_tasks_periodically(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
        visibility_beg_date=datetime(2024, 6, 1),
        visibility_end_date=datetime(2024, 6, 10),
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert "Deepflare" in trace_names
    assert "OldOnly" not in trace_names


def test_plot_completed_tasks_periodically_keeps_archived_parent_history_outside_viewport():
    fig = plot_completed_tasks_periodically(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
        visibility_beg_date=datetime(2024, 6, 3),
        visibility_end_date=datetime(2024, 6, 10),
        always_visible_projects={"Deepflare"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    trace_names = [str(getattr(trace, "name", "")) for trace in traces]
    deepflare_trace = next(
        trace for trace in traces if str(getattr(trace, "name", "")) == "Deepflare"
    )

    assert "Deepflare" in trace_names
    assert "OldOnly" not in trace_names
    assert pd.Timestamp("2023-03-19") in _normalized_trace_x(deepflare_trace)


def test_cumsum_completed_tasks_periodically_uses_selected_range_for_root_visibility():
    fig = cumsum_completed_tasks_periodically(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
        visibility_beg_date=datetime(2024, 6, 1),
        visibility_end_date=datetime(2024, 6, 10),
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert "Deepflare" in trace_names
    assert "OldOnly" not in trace_names


def test_cumsum_completed_tasks_periodically_keeps_archived_parent_history_outside_viewport():
    fig = cumsum_completed_tasks_periodically(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
        visibility_beg_date=datetime(2024, 6, 3),
        visibility_end_date=datetime(2024, 6, 10),
        always_visible_projects={"Deepflare"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    trace_names = [str(getattr(trace, "name", "")) for trace in traces]
    deepflare_trace = next(
        trace for trace in traces if str(getattr(trace, "name", "")) == "Deepflare"
    )

    assert "Deepflare" in trace_names
    assert "OldOnly" not in trace_names
    assert pd.Timestamp("2023-03-19") in _normalized_trace_x(deepflare_trace)


def test_plot_completed_tasks_periodically_groups_by_root_project_when_parent_exists():
    fig = plot_completed_tasks_periodically(
        _root_project_visibility_df(),
        datetime(2024, 6, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Academy": "#123456", "skynet": "#654321"},
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert "Academy" in trace_names
    assert "skynet" in trace_names
    assert "DeepMhcFlare" not in trace_names
    assert "MSFT" not in trace_names


def test_cumsum_completed_tasks_periodically_groups_by_root_project_when_parent_exists():
    fig = cumsum_completed_tasks_periodically(
        _root_project_visibility_df(),
        datetime(2024, 6, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Academy": "#123456", "skynet": "#654321"},
    )

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert "Academy" in trace_names
    assert "skynet" in trace_names
    assert "DeepMhcFlare" not in trace_names
    assert "MSFT" not in trace_names


def test_cumsum_completed_tasks_periodically_forward_fills_sparse_project_totals():
    fig = cumsum_completed_tasks_periodically(
        _sparse_cumulative_df(),
        datetime(2024, 1, 1),
        datetime(2024, 1, 20),
        granularity="W-SUN",
        project_colors={"Large": "#123456", "Small": "#654321"},
    )

    total_trace = next(
        trace
        for trace in cast(tuple[Any, ...], fig.data)
        if str(getattr(trace, "name", "")).lower()
        == "all projects (total cumulative)"
    )
    values = [float(value) for value in cast(Any, total_trace).y]
    assert values == sorted(values)
    assert values[-1] == 101.0


def test_cumsum_completed_tasks_periodically_trims_project_lines_to_activity_span():
    fig = cumsum_completed_tasks_periodically(
        _sparse_cumulative_df(),
        datetime(2024, 1, 1),
        datetime(2024, 1, 20),
        granularity="W-SUN",
        project_colors={"Large": "#123456", "Small": "#654321"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    small_trace = next(
        trace for trace in traces if str(getattr(trace, "name", "")) == "Small"
    )
    large_trace = next(
        trace for trace in traces if str(getattr(trace, "name", "")) == "Large"
    )

    assert _normalized_trace_x(small_trace) == [pd.Timestamp("2024-01-14")]
    assert _normalized_trace_x(large_trace) == [pd.Timestamp("2024-01-07")]


def test_cumsum_completed_tasks_periodically_keeps_archived_points_sparse_without_forecast(
    monkeypatch: Any,
) -> None:
    _freeze_periodic_now(monkeypatch, datetime(2024, 6, 5, 12, 0, 0))

    fig = cumsum_completed_tasks_periodically(
        _archived_current_period_sparse_df(),
        datetime(2024, 5, 1),
        datetime(2024, 6, 20),
        granularity="W-SUN",
        project_colors={"Archived": "#123456", "Active": "#654321"},
        always_visible_projects={"Archived"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    archived_trace = next(
        trace for trace in traces if str(getattr(trace, "name", "")) == "Archived"
    )

    assert _normalized_trace_x(archived_trace) == [
        pd.Timestamp("2024-05-26"),
        pd.Timestamp("2024-06-09"),
    ]
    assert [float(value) for value in cast(Any, archived_trace).y] == [1.0, 2.0]
    assert not any(
        str(getattr(trace, "name", "")).startswith("Archived (")
        for trace in traces
    )


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


def test_cumsum_completed_tasks_periodically_keeps_cumulative_lines_linear():
    """Cumulative lines should not use smoothing that can imply decreases."""

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
        getattr(getattr(trace, "line", None), "shape", None) in (None, "linear")
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
