"""Tests for the active project hierarchy sunburst plot."""

from datetime import datetime
from collections.abc import Sequence
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import pytest

from tests.factories import make_project, make_project_entry
from todoist.dashboard._plot_project_hierarchy_sunburst import (
    plot_active_project_hierarchy_sunburst,
)

ProjectSpec = tuple[str, str, str | None]
TaskSpec = tuple[str, str, int, str, str]


def _tasks(
    specs: Sequence[TaskSpec], *, completed: bool = True, indexed: bool = True
) -> pd.DataFrame:
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
            project_entry=make_project_entry(
                project_id=project_id, name=name, parent_id=parent_id
            ),
        )
        for project_id, name, parent_id in specs
    ]


def _plot(df: pd.DataFrame, projects: list[Any]) -> go.Figure:
    return plot_active_project_hierarchy_sunburst(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 31),
        projects,
        {"Root A": "#123456", "Root B": "#654321"},
    )


def _sunburst_node_map(fig: go.Figure) -> dict[str, dict[str, Any]]:
    traces = cast(tuple[Any, ...], fig.data)
    assert len(traces) == 1
    trace = cast(Any, traces[0])
    assert trace.type == "sunburst"
    assert trace.branchvalues == "total"
    return {
        str(node_id): {
            "parent": str(trace.parents[idx]),
            "label": str(trace.labels[idx]),
            "text": str(trace.text[idx]),
            "value": int(trace.values[idx]),
            "color": str(trace.marker.colors[idx]),
            "customdata": trace.customdata[idx],
        }
        for idx, node_id in enumerate(trace.ids)
    }


BASE_PROJECTS: list[ProjectSpec] = [
    ("root-a", "Root A", None),
    ("child-a1", "Child A1", "root-a"),
    ("grand-a", "Grand A", "child-a1"),
    ("root-b", "Root B", None),
]


def test_plot_active_project_hierarchy_sunburst_rolls_up_active_subprojects():
    nodes = _sunburst_node_map(
        _plot(
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
    )

    assert "inactive-project" not in nodes
    assert nodes["active-projects"]["parent"] == ""
    assert nodes["active-projects"]["value"] == 5
    assert nodes["root-a"]["parent"] == "active-projects"
    assert nodes["root-a"]["label"] == "Root A"
    assert nodes["root-a"]["text"] == "Root A<br><b>80.0%</b>"
    assert nodes["root-a"]["value"] == 4
    assert nodes["root-a"]["color"] == "#123456"
    assert nodes["root-b"]["text"] == "Root B<br><b>20.0%</b>"
    assert nodes["active-projects"]["text"] == "Projects<br>5"
    assert nodes["child-a1"]["parent"] == "root-a"
    assert nodes["child-a1"]["value"] == 3
    assert nodes["grand-a"]["parent"] == "child-a1"
    assert nodes["grand-a"]["value"] == nodes["root-b"]["value"] == 1


@pytest.mark.parametrize(
    ("task_specs", "project_specs", "node_id", "parent", "value", "hidden"),
    [
        (
            [("root-a", "Root A", 2, "root-a", "Root A")]
            + [
                (f"child-a{i}", f"Child A{i}", total, "root-a", "Root A")
                for i, total in enumerate([20, 10, 4, 3, 1, 1], 1)
            ],
            [("root-a", "Root A", None)]
            + [(f"child-a{i}", f"Child A{i}", "root-a") for i in range(1, 7)],
            "other:root-a",
            "root-a",
            2,
            2,
        ),
        (
            [
                (f"root-{i}", f"Root {i}", total, f"root-{i}", f"Root {i}")
                for i, total in enumerate([100, 50, 25, 10, 1, 1, 1], 1)
            ],
            [(f"root-{i}", f"Root {i}", None) for i in range(1, 8)],
            "other-roots",
            "active-projects",
            3,
            3,
        ),
    ],
)
def test_plot_active_project_hierarchy_sunburst_folds_small_nodes(
    task_specs: list[TaskSpec],
    project_specs: list[ProjectSpec],
    node_id: str,
    parent: str,
    value: int,
    hidden: int,
):
    nodes = _sunburst_node_map(_plot(_tasks(task_specs), _projects(project_specs)))

    assert nodes[node_id]["parent"] == parent
    assert nodes[node_id]["value"] == value
    assert nodes[node_id]["customdata"][6] == hidden
    assert nodes[node_id]["customdata"][7] == "aggregate"


def test_plot_active_project_hierarchy_sunburst_returns_empty_figure_without_completed_tasks():
    fig = _plot(
        _tasks([("root-a", "Root A", 1, "root-a", "Root A")], completed=False),
        _projects([("root-a", "Root A", None)]),
    )

    assert not fig.data
    assert "No completed tasks" in str(fig.layout.annotations[0].text)


def test_plot_active_project_hierarchy_sunburst_normalizes_date_column_input():
    nodes = _sunburst_node_map(
        _plot(
            _tasks([("root-a", "Root A", 1, "root-a", "Root A")], indexed=False),
            _projects([("root-a", "Root A", None)]),
        )
    )

    assert nodes["root-a"]["value"] == 1
    assert nodes["root-a"]["customdata"][2] == 1


def test_plot_project_hierarchy_sunburst_resolves_root_colors_case_insensitively():
    fig = plot_active_project_hierarchy_sunburst(
        _tasks(
            [
                ("root-a", "Root A", 1, "root-a", "Root A"),
                ("root-b", "Root B", 1, "root-b", "Root B"),
            ]
        ),
        datetime(2025, 1, 1),
        datetime(2025, 1, 31),
        _projects([("root-a", "Root A", None), ("root-b", "Root B", None)]),
        {"root a": "#abcdef"},
    )

    nodes = _sunburst_node_map(fig)
    assert nodes["root-a"]["color"] == "#abcdef"
    assert nodes["root-b"]["color"] == "#808080"


def test_plot_project_hierarchy_sunburst_includes_archived_projects_and_rolls_up_counts():
    root = make_project(
        project_id="root-a",
        project_entry=make_project_entry(
            project_id="root-a", name="Root A", parent_id=None
        ),
    )
    archived_parent = make_project(
        project_id="archived-parent",
        project_entry=make_project_entry(
            project_id="archived-parent",
            name="Archived Parent",
            parent_id="root-a",
        ),
        is_archived=True,
    )
    archived_child = make_project(
        project_id="archived-child",
        project_entry=make_project_entry(
            project_id="archived-child",
            name="Archived Child",
            parent_id="archived-parent",
        ),
        is_archived=True,
    )

    nodes = _sunburst_node_map(
        _plot(
            _tasks(
                [
                    ("root-a", "Root A", 1, "root-a", "Root A"),
                    (
                        "archived-parent",
                        "Archived Parent",
                        2,
                        "root-a",
                        "Root A",
                    ),
                    (
                        "archived-child",
                        "Archived Child",
                        3,
                        "root-a",
                        "Root A",
                    ),
                ]
            ),
            [root, archived_parent, archived_child],
        )
    )

    assert nodes["active-projects"]["value"] == 6
    assert nodes["root-a"]["value"] == 6
    assert nodes["archived-parent"]["parent"] == "root-a"
    assert nodes["archived-parent"]["value"] == 5
    assert nodes["archived-child"]["parent"] == "archived-parent"
    assert nodes["archived-child"]["value"] == 3
    assert nodes["archived-child"]["customdata"][8] == "Archived"
    assert nodes["archived-child"]["customdata"][9] == "Automatic (Todoist hierarchy)"


def test_plot_project_hierarchy_sunburst_manual_mapping_overrides_archived_root():
    root = make_project(
        project_id="root-a",
        project_entry=make_project_entry(
            project_id="root-a", name="Root A", parent_id=None
        ),
    )
    archived_root = make_project(
        project_id="old-root",
        project_entry=make_project_entry(
            project_id="old-root", name="Old Root", parent_id=None
        ),
        is_archived=True,
    )
    fig = plot_active_project_hierarchy_sunburst(
        _tasks(
            [
                ("root-a", "Root A", 1, "root-a", "Root A"),
                ("old-root", "Old Root", 2, "root-a", "Root A"),
            ]
        ),
        datetime(2025, 1, 1),
        datetime(2025, 1, 31),
        [root, archived_root],
        {"Root A": "#123456"},
        project_mappings={"Old Root": "Root A"},
    )

    nodes = _sunburst_node_map(fig)
    assert nodes["root-a"]["value"] == 3
    assert nodes["old-root"]["parent"] == "root-a"
    assert nodes["old-root"]["customdata"][8] == "Archived"
    assert nodes["old-root"]["customdata"][9] == "Manual mapping"
