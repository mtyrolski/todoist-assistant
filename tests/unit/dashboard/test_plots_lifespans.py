"""Tests for Todoist dashboard lifespan plots."""

from datetime import datetime, timedelta
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import pytest

from todoist.dashboard.plots import plot_task_lifespans

BASE_DATE = datetime(2024, 1, 1, 12, 0, 0)


def _events_df(events: list[tuple[str, str, datetime, object | None]]) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "parent_item_id": task_id,
                "type": event_type,
                "title": title,
                "root_project_name": "Project A",
                "root_project_id": "proj_a",
            }
            for task_id, event_type, _, title in events
        ],
        index=pd.DatetimeIndex([date for _, _, date, _ in events]),
    )
    df.index.name = "date"
    return df


def _task_pair(
    task_id: str,
    duration: timedelta,
    *,
    start: datetime = BASE_DATE,
    title: object | None = None,
) -> list[tuple[str, str, datetime, object | None]]:
    name = task_id if title is None else title
    return [
        (task_id, "added", start, name),
        (task_id, "completed", start + duration, name),
    ]


@pytest.fixture
def sample_task_events_df() -> pd.DataFrame:
    return _events_df(
        [
            *_task_pair("task1", timedelta(hours=1), title="Task 1"),
            *_task_pair("task2", timedelta(days=1), title="Task 2"),
            *_task_pair("task3", timedelta(days=7), title="Task 3"),
            ("task4", "added", BASE_DATE, "Task 4"),
            ("task5", "completed", BASE_DATE, "Task 5"),
            *_task_pair("task6", timedelta(minutes=5), title="Task 6"),
        ]
    )


def _empty_events_df() -> pd.DataFrame:
    df = pd.DataFrame(
        columns=[
            "parent_item_id",
            "type",
            "title",
            "root_project_name",
            "root_project_id",
        ],
        index=pd.DatetimeIndex([]),
    )
    df.index.name = "date"
    return df


def _traces(fig: go.Figure) -> tuple[Any, ...]:
    return cast(tuple[Any, ...], fig.data)


def test_plot_task_lifespans_with_valid_data(
    sample_task_events_df: pd.DataFrame,
) -> None:
    fig = plot_task_lifespans(sample_task_events_df)

    assert isinstance(fig, go.Figure)
    assert _traces(fig)
    assert "Task Lifespans" in fig.layout.title.text
    assert fig.layout.xaxis.type == "log"
    assert fig.layout.xaxis.title.text == ""
    assert "Frequency" in fig.layout.yaxis.title.text
    assert fig.layout.plot_bgcolor == "#111318"
    assert fig.layout.paper_bgcolor == "#111318"
    assert fig.layout.template is not None
    assert fig.layout.autosize is True
    assert fig.layout.xaxis.showgrid is False
    assert fig.layout.yaxis.showgrid is False
    assert fig.layout.legend is not None


@pytest.mark.parametrize(
    ("df", "title_fragment"),
    [
        pytest.param(_empty_events_df(), "No Task Events", id="empty"),
        pytest.param(
            _events_df(
                [
                    ("task1", "added", BASE_DATE, "Task 1"),
                    ("task2", "added", BASE_DATE + timedelta(days=1), "Task 2"),
                ]
            ),
            "No Tasks with Both Added and Completed Events",
            id="only-added",
        ),
        pytest.param(
            _events_df(
                [
                    ("task1", "completed", BASE_DATE, "Task 1"),
                    ("task2", "completed", BASE_DATE + timedelta(days=1), "Task 2"),
                ]
            ),
            "No Tasks with Both Added and Completed Events",
            id="only-completed",
        ),
    ],
)
def test_plot_task_lifespans_handles_missing_duration_inputs(
    df: pd.DataFrame, title_fragment: str
) -> None:
    fig = plot_task_lifespans(df)

    assert isinstance(fig, go.Figure)
    assert "Task Lifespans" in fig.layout.title.text
    assert title_fragment in fig.layout.title.text


@pytest.mark.parametrize(
    "df",
    [
        pytest.param(
            _events_df(
                [
                    ("task1", "added", BASE_DATE + timedelta(hours=1), "Task 1"),
                    ("task1", "completed", BASE_DATE, "Task 1"),
                ]
            ),
            id="negative-duration",
        ),
        pytest.param(
            _events_df(_task_pair("task1", timedelta(hours=1), title=None)),
            id="missing-title",
        ),
    ],
)
def test_plot_task_lifespans_tolerates_edge_rows(df: pd.DataFrame) -> None:
    assert isinstance(plot_task_lifespans(df), go.Figure)


@pytest.mark.parametrize(
    ("durations", "expected_units"),
    [
        pytest.param(
            [timedelta(minutes=10), timedelta(minutes=30)], ("m", "h"), id="minutes"
        ),
        pytest.param([timedelta(days=5), timedelta(days=10)], ("d", "w"), id="days"),
    ],
)
def test_plot_task_lifespans_time_unit_selection(
    durations: list[timedelta], expected_units: tuple[str, ...]
) -> None:
    fig = plot_task_lifespans(
        _events_df(
            [
                event
                for index, duration in enumerate(durations, start=1)
                for event in _task_pair(f"task{index}", duration)
            ]
        )
    )

    tick_labels = " ".join(str(item) for item in (fig.layout.xaxis.ticktext or []))
    assert any(unit in tick_labels for unit in expected_units)


def test_plot_task_lifespans_weights_recent_completions_more() -> None:
    old_events = [
        event
        for index in range(100)
        for event in _task_pair(
            f"old-{index}", timedelta(days=1), start=datetime(2020, 1, 1)
        )
    ]
    recent_events = [
        event
        for index in range(5)
        for event in _task_pair(
            f"recent-{index}", timedelta(days=30), start=datetime(2025, 1, 1)
        )
    ]

    fig = plot_task_lifespans(_events_df([*old_events, *recent_events]))

    assert sorted(float(shape.x0) for shape in fig.layout.shapes)[-1] == pytest.approx(
        30.0
    )
    assert "Recency-weighted frequency" in [str(trace.name) for trace in _traces(fig)]
