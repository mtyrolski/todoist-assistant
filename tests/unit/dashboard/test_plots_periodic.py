"""Tests for Todoist dashboard plotting helpers."""

from datetime import datetime, timedelta
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import pytest
from todoist.dashboard._plot_periodic import _prepare_completed_periodic_frame

from todoist.dashboard.plots import (
    cumsum_completed_tasks_periodically,
    plot_completed_tasks_periodically,
    plot_weekly_completion_trend,
)


def _weekly_completion_df() -> pd.DataFrame:
    return _completed_df(
        [
            ("2024-06-01", "Project A", "task1", "Task 1"),
            ("2024-06-03", "Project A", "task2", "Task 2"),
            ("2024-06-04", "Project A", "task3", "Task 3"),
        ]
    )


def test_periodic_frame_buckets_utc_events_in_configured_timezone(monkeypatch: Any):
    monkeypatch.setenv("TODOIST_TIMEZONE", "Europe/Warsaw")
    df = pd.DataFrame(
        {
            "root_project_name": ["Academy", "Academy"],
            "type": ["completed", "completed"],
            "title": ["Sunday local", "Monday local"],
        },
        index=pd.to_datetime(
            ["2026-06-21T20:00:00Z", "2026-06-21T23:30:00Z"], utc=True
        ),
    )

    _, periodic = _prepare_completed_periodic_frame(
        df,
        beg_date=datetime(2026, 6, 15),
        end_date=datetime(2026, 6, 28),
        granularity="W-SUN",
    )

    assert int(periodic.loc[pd.Timestamp("2026-06-21"), "Academy"]) == 1
    assert int(periodic.loc[pd.Timestamp("2026-06-28"), "Academy"]) == 1


def _monthly_completion_df() -> pd.DataFrame:
    return _completed_df(
        [
            ("2024-04-10", "Project A", "task1", "Task 1"),
            ("2024-04-20", "Project A", "task2", "Task 2"),
            ("2024-05-03", "Project A", "task3", "Task 3"),
            ("2024-05-10", "Project A", "task4", "Task 4"),
        ]
    )


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


def _completed_df(rows: list[tuple[Any, ...]]) -> pd.DataFrame:
    records = []
    for row in rows:
        date, root_name, item_id, title, *parent = row
        record = {
            "root_project_name": root_name,
            "root_project_id": str(root_name).lower(),
            "type": "completed",
            "parent_item_id": item_id,
            "title": title,
            "date": date,
        }
        if parent:
            record["parent_project_name"] = parent[0]
            record["parent_project_id"] = parent[1]
        records.append(record)
    df = pd.DataFrame(records).set_index("date")
    df.index = pd.DatetimeIndex(df.index)
    return df


def _archived_visibility_df() -> pd.DataFrame:
    return _completed_df(
        [
            ("2023-03-15", "Deepflare", "deepflare-old", "Deepflare old task"),
            (
                "2024-06-02",
                "Deepflare",
                "deepflare-selected",
                "Deepflare selected task",
            ),
            ("2023-05-10", "OldOnly", "old-only-task", "Old only task"),
        ]
    )


def _root_project_visibility_df() -> pd.DataFrame:
    return _completed_df(
        [
            (
                "2024-06-02",
                "Academy",
                "deep-mhc-flare-task",
                "DeepMhcFlare task",
                "DeepMhcFlare",
                "deep-mhc-flare",
            ),
            ("2024-06-03", "skynet", "msft-task", "MSFT task", "MSFT", "msft"),
        ]
    )


def _sparse_cumulative_df() -> pd.DataFrame:
    rows = [
        (
            datetime(2024, 1, 1, 12, 0, 0) + timedelta(seconds=idx),
            "Large",
            f"large-{idx}",
            f"Large {idx}",
        )
        for idx in range(100)
    ]
    rows.append((datetime(2024, 1, 8, 12, 0, 0), "Small", "small-1", "Small 1"))
    return _completed_df(rows)


def _archived_current_period_sparse_df() -> pd.DataFrame:
    return _completed_df(
        [
            ("2024-05-20", "Archived", "archived-old", "Archived old"),
            ("2024-05-27", "Active", "active-gap", "Active gap"),
            ("2024-06-03", "Archived", "archived-current", "Archived current"),
        ]
    )


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


PLOT_FUNCTIONS = [
    pytest.param(
        plot_completed_tasks_periodically,
        "all projects (total)",
        id="periodic",
    ),
    pytest.param(
        cumsum_completed_tasks_periodically,
        "all projects (total cumulative)",
        id="cumulative",
    ),
]


def _fig_traces(fig: go.Figure) -> tuple[Any, ...]:
    return cast(tuple[Any, ...], fig.data)


def _trace_name(trace: Any) -> str:
    return str(getattr(trace, "name", ""))


def _trace_names(fig: go.Figure) -> list[str]:
    return [_trace_name(trace) for trace in _fig_traces(fig)]


def _trace_by_name(fig: go.Figure, name: str) -> Any:
    return next(trace for trace in _fig_traces(fig) if _trace_name(trace) == name)


def _trace_by_lower_name(fig: go.Figure, name: str) -> Any:
    return next(
        trace for trace in _fig_traces(fig) if _trace_name(trace).lower() == name
    )


def _weekly_plot(plot_func: Any, **kwargs: Any) -> go.Figure:
    return plot_func(
        _weekly_completion_df(),
        datetime(2024, 5, 27),
        datetime(2024, 6, 5),
        granularity="W-SUN",
        project_colors={"Project A": "#123456"},
        **kwargs,
    )


@pytest.mark.parametrize(("plot_func", "_total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_keeps_current_week(
    plot_func: Any, _total_name: str
):
    """Current partial period should surface as 'so far' + forecast markers."""

    end_date = datetime(2024, 6, 5)

    fig = _weekly_plot(plot_func)

    dotted_traces = [
        trace
        for trace in _fig_traces(fig)
        if getattr(getattr(trace, "line", None), "dash", None) == "dot"
    ]
    assert not dotted_traces

    forecast_traces = [
        trace
        for trace in _fig_traces(fig)
        if "(forecast)" in _trace_name(trace).lower()
    ]
    assert forecast_traces
    assert any(pd.to_datetime(x) > end_date for x in cast(Any, forecast_traces[0]).x)


@pytest.mark.parametrize(("plot_func", "total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_dashes_current_month_when_range_extends_past_today(
    monkeypatch: Any, plot_func: Any, total_name: str
):
    _freeze_periodic_now(monkeypatch, datetime(2024, 5, 13, 12, 0, 0))
    df = _monthly_completion_df()
    beg_date = datetime(2024, 4, 1)
    end_date = datetime(2024, 7, 15)
    current_month_label = pd.Timestamp("2024-05-31")

    fig = plot_func(
        df,
        beg_date,
        end_date,
        granularity="ME",
        project_colors={"Project A": "#123456"},
    )

    total_trace = _trace_by_lower_name(fig, total_name)
    assert current_month_label not in _normalized_trace_x(total_trace)

    forecast_line = _trace_by_lower_name(fig, "all projects (forecast line)")
    assert getattr(getattr(forecast_line, "line", None), "dash", None) == "dash"
    assert _normalized_trace_x(forecast_line)[-1] == current_month_label


@pytest.mark.parametrize(("plot_func", "_total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_uses_matching_forecast_marker_colors(
    monkeypatch: Any, plot_func: Any, _total_name: str
):
    _freeze_periodic_now(monkeypatch, datetime(2024, 5, 13, 12, 0, 0))
    df = _monthly_completion_df()
    fig = plot_func(
        df,
        datetime(2024, 4, 1),
        datetime(2024, 7, 15),
        granularity="ME",
        project_colors={"Project A": "#123456"},
    )

    project_so_far = _trace_by_name(fig, "Project A (so far)")
    project_forecast = _trace_by_name(fig, "Project A (forecast)")
    total_so_far = _trace_by_name(fig, "All Projects (so far)")
    total_forecast = _trace_by_name(fig, "All Projects (forecast)")

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


@pytest.mark.parametrize(
    ("plot_func", "expected_y"),
    [
        pytest.param(plot_completed_tasks_periodically, None, id="periodic"),
        pytest.param(cumsum_completed_tasks_periodically, [1.0, 2.0], id="cumulative"),
    ],
)
def test_completed_tasks_periodically_keeps_archived_points_sparse_without_forecast(
    monkeypatch: Any, plot_func: Any, expected_y: list[float] | None
) -> None:
    _freeze_periodic_now(monkeypatch, datetime(2024, 6, 5, 12, 0, 0))

    fig = plot_func(
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
    if expected_y is not None:
        assert [float(value) for value in cast(Any, archived_trace).y] == expected_y
    assert not any(
        str(getattr(trace, "name", "")).startswith("Archived (") for trace in traces
    )


@pytest.mark.parametrize(("plot_func", "_total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_hides_inactive_projects_in_range(
    plot_func: Any, _total_name: str
):
    fig = plot_func(
        _completed_df(
            [
                ("2024-05-24", "Project B", "task3", "Task 3"),
                ("2024-06-03", "Project A", "task1", "Task 1"),
                ("2024-06-04", "Project A", "task2", "Task 2"),
            ]
        ),
        datetime(2024, 6, 1),
        datetime(2024, 6, 5),
        granularity="W-SUN",
        project_colors={"Project A": "#123456", "Project B": "#654321"},
    )

    trace_names = _trace_names(fig)
    assert any(name.startswith("Project A") for name in trace_names)
    assert not any(name.startswith("Project B") for name in trace_names)


@pytest.mark.parametrize(
    ("plot_func", "check_color"),
    [
        pytest.param(plot_completed_tasks_periodically, True, id="periodic"),
        pytest.param(cumsum_completed_tasks_periodically, False, id="cumulative"),
    ],
)
def test_completed_tasks_periodically_keeps_projects_from_full_history_range(
    plot_func: Any, check_color: bool
):
    fig = plot_func(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
    )

    trace_names = _trace_names(fig)

    assert "Deepflare" in trace_names
    assert "OldOnly" in trace_names
    if check_color:
        deepflare_trace = _trace_by_name(fig, "Deepflare")
        assert (
            getattr(getattr(deepflare_trace, "line", None), "color", None) == "#ff8800"
        )


@pytest.mark.parametrize(("plot_func", "_total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_uses_selected_range_for_root_visibility(
    plot_func: Any, _total_name: str
):
    fig = plot_func(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
        visibility_beg_date=datetime(2024, 6, 1),
        visibility_end_date=datetime(2024, 6, 10),
    )

    trace_names = _trace_names(fig)
    assert "Deepflare" in trace_names
    assert "OldOnly" not in trace_names


@pytest.mark.parametrize(("plot_func", "_total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_keeps_archived_parent_history_outside_viewport(
    plot_func: Any, _total_name: str
):
    fig = plot_func(
        _archived_visibility_df(),
        datetime(2023, 1, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Deepflare": "#ff8800", "OldOnly": "#111111"},
        visibility_beg_date=datetime(2024, 6, 3),
        visibility_end_date=datetime(2024, 6, 10),
        always_visible_projects={"Deepflare"},
    )

    trace_names = _trace_names(fig)
    deepflare_trace = _trace_by_name(fig, "Deepflare")

    assert "Deepflare" in trace_names
    assert "OldOnly" not in trace_names
    assert pd.Timestamp("2023-03-19") in _normalized_trace_x(deepflare_trace)


@pytest.mark.parametrize(("plot_func", "_total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_groups_by_root_project_when_parent_exists(
    plot_func: Any, _total_name: str
):
    fig = plot_func(
        _root_project_visibility_df(),
        datetime(2024, 6, 1),
        datetime(2024, 6, 10),
        granularity="W-SUN",
        project_colors={"Academy": "#123456", "skynet": "#654321"},
    )

    trace_names = _trace_names(fig)
    assert "Academy" in trace_names
    assert "skynet" in trace_names
    assert "DeepMhcFlare" not in trace_names
    assert "MSFT" not in trace_names


def test_cumsum_completed_tasks_periodically_keeps_sparse_project_totals_compact():
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
        if str(getattr(trace, "name", "")).lower() == "all projects (total cumulative)"
    )
    values = [float(value) for value in cast(Any, total_trace).y]

    assert values == sorted(values)
    assert values[-1] == 101.0
    small_trace = _trace_by_name(fig, "Small")
    large_trace = _trace_by_name(fig, "Large")
    assert _normalized_trace_x(small_trace) == [pd.Timestamp("2024-01-14")]
    assert _normalized_trace_x(large_trace) == [pd.Timestamp("2024-01-07")]


@pytest.mark.parametrize(("plot_func", "total_name"), PLOT_FUNCTIONS)
def test_completed_tasks_periodically_adds_total_overlay_on_primary_axis(
    plot_func: Any, total_name: str
):
    fig = _weekly_plot(plot_func)

    total_traces = [
        trace for trace in _fig_traces(fig) if total_name in _trace_name(trace).lower()
    ]
    assert total_traces
    assert getattr(cast(Any, total_traces[0]), "yaxis", None) in (None, "y")
    assert getattr(cast(Any, fig.layout), "yaxis2", None) is None


def test_cumsum_completed_tasks_periodically_keeps_cumulative_lines_linear():
    """Cumulative lines should not use smoothing that can imply decreases."""

    fig = _weekly_plot(cumsum_completed_tasks_periodically)

    traces = cast(tuple[Any, ...], fig.data)
    project_lines = [
        trace for trace in traces if str(getattr(trace, "name", "")) == "Project A"
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

    fig = _weekly_plot(plot_completed_tasks_periodically, include_total_overlay=False)

    trace_names = [
        str(getattr(trace, "name", "")) for trace in cast(tuple[Any, ...], fig.data)
    ]
    assert not any("all projects" in name.lower() for name in trace_names)


def test_plot_weekly_completion_trend_uses_legend_toggles_for_optional_windows():
    """Weekly trend should keep 3w/current fixed and expose 6w/12w/24w as legend toggles."""

    df = _weekly_completion_trend_df()
    fig = plot_weekly_completion_trend(df, end_date=datetime(2024, 7, 24))

    assert isinstance(fig, go.Figure)
    assert not cast(Any, fig.layout).updatemenus

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
