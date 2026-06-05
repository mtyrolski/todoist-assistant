"""Tests for Todoist dashboard plotting helpers."""

from datetime import datetime
from typing import Any, cast

import pandas as pd

from todoist.dashboard._plot_project_hierarchy import plot_active_project_hierarchy
from tests.factories import make_project, make_project_entry


def test_plot_active_project_hierarchy_rolls_up_active_subprojects():
    df = pd.DataFrame(
        [
            {
                "date": "2025-01-02",
                "id": "e1",
                "title": "Root task",
                "type": "completed",
                "parent_project_id": "root-a",
                "parent_project_name": "Root A",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            },
            {
                "date": "2025-01-03",
                "id": "e2",
                "title": "Child task 1",
                "type": "completed",
                "parent_project_id": "child-a1",
                "parent_project_name": "Child A1",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            },
            {
                "date": "2025-01-04",
                "id": "e3",
                "title": "Child task 2",
                "type": "completed",
                "parent_project_id": "child-a1",
                "parent_project_name": "Child A1",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            },
            {
                "date": "2025-01-05",
                "id": "e4",
                "title": "Nested task",
                "type": "completed",
                "parent_project_id": "grand-a",
                "parent_project_name": "Grand A",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            },
            {
                "date": "2025-01-06",
                "id": "e5",
                "title": "Other root task",
                "type": "completed",
                "parent_project_id": "root-b",
                "parent_project_name": "Root B",
                "root_project_id": "root-b",
                "root_project_name": "Root B",
            },
            {
                "date": "2025-01-07",
                "id": "e6",
                "title": "Ignored archived-like task",
                "type": "completed",
                "parent_project_id": "inactive-project",
                "parent_project_name": "Inactive",
                "root_project_id": "inactive-project",
                "root_project_name": "Inactive",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    active_projects = [
        make_project(
            project_id="root-a",
            project_entry=make_project_entry(project_id="root-a", name="Root A"),
        ),
        make_project(
            project_id="child-a1",
            project_entry=make_project_entry(
                project_id="child-a1",
                name="Child A1",
                parent_id="root-a",
            ),
        ),
        make_project(
            project_id="grand-a",
            project_entry=make_project_entry(
                project_id="grand-a",
                name="Grand A",
                parent_id="child-a1",
            ),
        ),
        make_project(
            project_id="root-b",
            project_entry=make_project_entry(project_id="root-b", name="Root B"),
        ),
    ]

    fig = plot_active_project_hierarchy(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 10),
        active_projects,
        {"Root A": "#123456", "Root B": "#654321"},
    )

    traces = cast(tuple[Any, ...], fig.data)
    assert len(traces) == 4
    bubble_traces = [
        cast(Any, trace)
        for trace in traces
        if str(getattr(trace, "hoverinfo", "")) != "skip"
    ]
    assert [trace.type for trace in bubble_traces] == ["scatter", "scatter"]
    assert fig.layout.dragmode == "pan"
    assert fig.layout.xaxis.fixedrange is False
    assert fig.layout.yaxis.fixedrange is False
    assert fig.layout.margin.l >= 24
    assert fig.layout.margin.r >= 24
    assert fig.layout.margin.t >= 30
    assert fig.layout.margin.b >= 72
    assert fig.layout.annotations
    assert int(fig.layout.annotations[0].font.size) <= 9

    by_id: dict[str, dict[str, Any]] = {}
    for trace in bubble_traces:
        x_values = list(getattr(trace, "x", []))
        y_values = list(getattr(trace, "y", []))
        sizes = list(getattr(getattr(trace, "marker", None), "size", []))
        customdata = list(getattr(trace, "customdata", []))
        for idx, point in enumerate(customdata):
            by_id[str(point[0])] = {
                "label": str(point[1]),
                "total": int(point[2]),
                "direct": int(point[3]),
                "root_name": str(point[4]),
                "depth": int(point[5]),
                "hidden_projects": int(point[6]),
                "kind": str(point[7]),
                "size": float(sizes[idx]),
                "x": float(x_values[idx]),
                "y": float(y_values[idx]),
            }

    assert "inactive-project" not in by_id
    assert by_id["root-a"]["label"] == "Root A"
    assert by_id["root-a"]["direct"] == 1
    assert by_id["root-a"]["total"] == 4
    assert by_id["root-a"]["kind"] == "root"
    assert by_id["child-a1"]["total"] == 3
    assert by_id["child-a1"]["root_name"] == "Root A"
    assert by_id["grand-a"]["total"] == 1
    assert by_id["root-b"]["total"] == 1
    child_a1_to_root_a = (
        (by_id["child-a1"]["x"] - by_id["root-a"]["x"]) ** 2
        + (by_id["child-a1"]["y"] - by_id["root-a"]["y"]) ** 2
    ) ** 0.5
    child_a1_to_root_b = (
        (by_id["child-a1"]["x"] - by_id["root-b"]["x"]) ** 2
        + (by_id["child-a1"]["y"] - by_id["root-b"]["y"]) ** 2
    ) ** 0.5
    grand_a_to_root_a = (
        (by_id["grand-a"]["x"] - by_id["root-a"]["x"]) ** 2
        + (by_id["grand-a"]["y"] - by_id["root-a"]["y"]) ** 2
    ) ** 0.5
    grand_a_to_root_b = (
        (by_id["grand-a"]["x"] - by_id["root-b"]["x"]) ** 2
        + (by_id["grand-a"]["y"] - by_id["root-b"]["y"]) ** 2
    ) ** 0.5
    assert child_a1_to_root_a < child_a1_to_root_b
    assert grand_a_to_root_a < grand_a_to_root_b
    assert by_id["child-a1"]["y"] < by_id["root-a"]["y"]
    assert by_id["grand-a"]["y"] < by_id["root-a"]["y"]


def test_plot_active_project_hierarchy_folds_small_long_tail_into_other_bubble():
    rows: list[dict[str, str]] = []
    for idx in range(5):
        rows.append(
            {
                "date": f"2025-02-{idx + 1:02d}",
                "id": f"e-root-{idx}",
                "title": "Root A task",
                "type": "completed",
                "parent_project_id": "root-a",
                "parent_project_name": "Root A",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            }
        )
    for idx in range(6):
        rows.append(
            {
                "date": f"2025-02-{idx + 6:02d}",
                "id": f"e-child-1-{idx}",
                "title": "Child 1 task",
                "type": "completed",
                "parent_project_id": "child-a1",
                "parent_project_name": "Child A1",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            }
        )
    for idx in range(4):
        rows.append(
            {
                "date": f"2025-02-{idx + 12:02d}",
                "id": f"e-child-2-{idx}",
                "title": "Child 2 task",
                "type": "completed",
                "parent_project_id": "child-a2",
                "parent_project_name": "Child A2",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            }
        )
    for idx in range(3):
        rows.append(
            {
                "date": f"2025-02-{idx + 16:02d}",
                "id": f"e-child-3-{idx}",
                "title": "Child 3 task",
                "type": "completed",
                "parent_project_id": "child-a3",
                "parent_project_name": "Child A3",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            }
        )
    rows.append(
        {
            "date": "2025-02-19",
            "id": "e-child-4",
            "title": "Child 4 task",
            "type": "completed",
            "parent_project_id": "child-a4",
            "parent_project_name": "Child A4",
            "root_project_id": "root-a",
            "root_project_name": "Root A",
        }
    )
    rows.append(
        {
            "date": "2025-02-20",
            "id": "e-child-5",
            "title": "Child 5 task",
            "type": "completed",
            "parent_project_id": "child-a5",
            "parent_project_name": "Child A5",
            "root_project_id": "root-a",
            "root_project_name": "Root A",
        }
    )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    active_projects = [
        make_project(
            project_id="root-a",
            project_entry=make_project_entry(project_id="root-a", name="Root A"),
        ),
        make_project(
            project_id="child-a1",
            project_entry=make_project_entry(
                project_id="child-a1",
                name="Child A1",
                parent_id="root-a",
            ),
        ),
        make_project(
            project_id="child-a2",
            project_entry=make_project_entry(
                project_id="child-a2",
                name="Child A2",
                parent_id="root-a",
            ),
        ),
        make_project(
            project_id="child-a3",
            project_entry=make_project_entry(
                project_id="child-a3",
                name="Child A3",
                parent_id="root-a",
            ),
        ),
        make_project(
            project_id="child-a4",
            project_entry=make_project_entry(
                project_id="child-a4",
                name="Child A4",
                parent_id="root-a",
            ),
        ),
        make_project(
            project_id="child-a5",
            project_entry=make_project_entry(
                project_id="child-a5",
                name="Child A5",
                parent_id="root-a",
            ),
        ),
    ]

    fig = plot_active_project_hierarchy(
        df,
        datetime(2025, 2, 1),
        datetime(2025, 2, 21),
        active_projects,
        {"Root A": "#22577a"},
    )

    traces = [
        cast(Any, trace)
        for trace in cast(tuple[Any, ...], fig.data)
        if str(getattr(trace, "hoverinfo", "")) != "skip"
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for trace in traces:
        sizes = list(getattr(getattr(trace, "marker", None), "size", []))
        customdata = list(getattr(trace, "customdata", []))
        for idx, point in enumerate(customdata):
            by_id[str(point[0])] = {
                "label": str(point[1]),
                "total": int(point[2]),
                "hidden_projects": int(point[6]),
                "kind": str(point[7]),
                "size": float(sizes[idx]),
            }

    assert "other:root-a" in by_id
    assert by_id["other:root-a"]["kind"] == "aggregate"
    assert by_id["other:root-a"]["total"] == 2
    assert by_id["other:root-a"]["hidden_projects"] == 2
    assert by_id["other:root-a"]["size"] < by_id["child-a3"]["size"]


def test_plot_active_project_hierarchy_returns_empty_figure_without_completed_tasks():
    df = pd.DataFrame(
        [
            {
                "date": "2025-01-02",
                "id": "e1",
                "title": "Task",
                "type": "added",
                "parent_project_id": "root-a",
                "parent_project_name": "Root A",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            }
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    fig = plot_active_project_hierarchy(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 10),
        [
            make_project(
                project_id="root-a",
                project_entry=make_project_entry(project_id="root-a", name="Root A"),
            )
        ],
        {"Root A": "#123456"},
    )

    assert not fig.data
    assert fig.layout.annotations
    assert "No completed tasks" in str(fig.layout.annotations[0].text)


def test_plot_active_project_hierarchy_normalizes_date_column_input():
    df = pd.DataFrame(
        [
            {
                "date": "2025-01-02",
                "id": "e1",
                "title": "Task",
                "type": "completed",
                "parent_project_id": "root-a",
                "parent_project_name": "Root A",
                "root_project_id": "root-a",
                "root_project_name": "Root A",
            }
        ]
    )

    fig = plot_active_project_hierarchy(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 10),
        [
            make_project(
                project_id="root-a",
                project_entry=make_project_entry(project_id="root-a", name="Root A"),
            )
        ],
        {"Root A": "#123456"},
    )

    traces = [
        cast(Any, trace)
        for trace in cast(tuple[Any, ...], fig.data)
        if str(getattr(trace, "hoverinfo", "")) != "skip"
    ]
    assert traces
    customdata = list(getattr(traces[-1], "customdata", []))
    assert customdata[0][0] == "root-a"
    assert customdata[0][2] == 1
