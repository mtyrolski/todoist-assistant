"""Tests for Todoist dashboard plotting helpers."""

from datetime import datetime
from collections.abc import Sequence
from typing import Any, cast

import pandas as pd

from tests.factories import make_project, make_project_entry
from todoist.dashboard._plot_project_hierarchy import plot_active_project_hierarchy

ProjectSpec = tuple[str, str, str | None]
TaskSpec = tuple[str, str, int, str, str]


def _tasks(specs: Sequence[TaskSpec], *, completed: bool = True, indexed: bool = True) -> pd.DataFrame:
    rows = [
        {
            "date": f"2025-01-{day % 28 + 1:02d}",
            "id": f"e-{project_id}-{n}",
            "title": f"{name} task",
            "type": "completed" if completed else "added",
            "parent_project_id": project_id,
            "parent_project_name": name,
            "root_project_id": root_id,
            "root_project_name": root_name,
        }
        for day, (project_id, name, total, root_id, root_name) in enumerate(specs)
        for n in range(total)
    ]
    df = pd.DataFrame(rows)
    if indexed:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
    return df


def _projects(specs: Sequence[ProjectSpec]) -> list[Any]:
    return [
        make_project(
            project_id=project_id,
            project_entry=make_project_entry(project_id=project_id, name=name, parent_id=parent_id),
        )
        for project_id, name, parent_id in specs
    ]


def _plot(df: pd.DataFrame, projects: list[Any]) -> Any:
    return plot_active_project_hierarchy(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 31),
        projects,
        {"Root A": "#123456", "Root B": "#654321"},
    )


def _bubble_map(fig: Any) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for trace in cast(tuple[Any, ...], fig.data):
        trace = cast(Any, trace)
        if str(getattr(trace, "hoverinfo", "")) == "skip":
            continue
        customdata = list(getattr(trace, "customdata", []) or [])
        if not customdata:
            continue
        sizes = list(getattr(getattr(trace, "marker", None), "size", []))
        for idx, point in enumerate(customdata):
            nodes[str(point[0])] = {
                "label": str(point[1]),
                "total": int(point[2]),
                "direct": int(point[3]),
                "root_name": str(point[4]),
                "depth": int(point[5]),
                "hidden_projects": int(point[6]),
                "kind": str(point[7]),
                "size": float(sizes[idx]),
                "x": float(trace.x[idx]),
                "y": float(trace.y[idx]),
            }
    return nodes


BASE_PROJECTS: list[ProjectSpec] = [
    ("root-a", "Root A", None),
    ("child-a1", "Child A1", "root-a"),
    ("grand-a", "Grand A", "child-a1"),
    ("root-b", "Root B", None),
]


def test_plot_active_project_hierarchy_rolls_up_active_subprojects():
    fig = _plot(
        _tasks(
            [
                ("root-a", "Root A", 1, "root-a", "Root A"),
                ("child-a1", "Child A1", 2, "root-a", "Root A"),
                ("grand-a", "Grand A", 1, "root-a", "Root A"),
                ("root-b", "Root B", 1, "root-b", "Root B"),
                ("inactive-project", "Inactive", 1, "inactive-project", "Inactive"),
            ]
        ),
        _projects(BASE_PROJECTS),
    )

    assert [cast(Any, trace).type for trace in fig.data if getattr(trace, "hoverinfo", "") != "skip"] == [
        "scatter",
        "scatter",
    ]
    nodes = _bubble_map(fig)
    assert "inactive-project" not in nodes
    assert nodes["root-a"]["label"] == "Root A"
    assert nodes["root-a"]["direct"] == 1
    assert nodes["root-a"]["total"] == 4
    assert nodes["root-a"]["kind"] == "root"
    assert nodes["child-a1"]["total"] == 3
    assert nodes["child-a1"]["root_name"] == "Root A"
    assert nodes["grand-a"]["total"] == nodes["root-b"]["total"] == 1
    for child_id in ("child-a1", "grand-a"):
        child = nodes[child_id]
        assert abs(child["x"] - nodes["root-a"]["x"]) < abs(child["x"] - nodes["root-b"]["x"])
        assert child["y"] < nodes["root-a"]["y"]


def test_plot_active_project_hierarchy_folds_small_long_tail_into_other_bubble():
    child_totals = [6, 4, 3, 1, 1]
    fig = _plot(
        _tasks(
            [("root-a", "Root A", 5, "root-a", "Root A")]
            + [(f"child-a{i}", f"Child A{i}", total, "root-a", "Root A") for i, total in enumerate(child_totals, 1)]
        ),
        _projects([("root-a", "Root A", None)] + [(f"child-a{i}", f"Child A{i}", "root-a") for i in range(1, 6)]),
    )

    nodes = _bubble_map(fig)
    assert nodes["other:root-a"]["kind"] == "aggregate"
    assert nodes["other:root-a"]["total"] == 2
    assert nodes["other:root-a"]["hidden_projects"] == 2
    assert nodes["other:root-a"]["size"] < nodes["child-a3"]["size"]


def test_plot_active_project_hierarchy_returns_empty_figure_without_completed_tasks():
    fig = _plot(
        _tasks([("root-a", "Root A", 1, "root-a", "Root A")], completed=False),
        _projects([("root-a", "Root A", None)]),
    )

    assert not fig.data
    assert "No completed tasks" in str(fig.layout.annotations[0].text)


def test_plot_active_project_hierarchy_normalizes_date_column_input():
    fig = _plot(
        _tasks([("root-a", "Root A", 1, "root-a", "Root A")], indexed=False),
        _projects([("root-a", "Root A", None)]),
    )

    assert _bubble_map(fig)["root-a"]["total"] == 1
