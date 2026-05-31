"""Tests for the active project hierarchy sunburst plot."""

from datetime import datetime
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go

from tests.factories import make_project, make_project_entry
from todoist.dashboard._plot_project_hierarchy_sunburst import (
    plot_active_project_hierarchy_sunburst,
)


def _sunburst_node_map(fig: go.Figure) -> dict[str, dict[str, Any]]:
    traces = cast(tuple[Any, ...], fig.data)
    assert len(traces) == 1
    trace = cast(Any, traces[0])
    ids = list(getattr(trace, "ids", []))
    parents = list(getattr(trace, "parents", []))
    labels = list(getattr(trace, "labels", []))
    values = list(getattr(trace, "values", []))
    colors = list(getattr(getattr(trace, "marker", None), "colors", []))
    customdata = list(getattr(trace, "customdata", []))

    node_map: dict[str, dict[str, Any]] = {}
    for idx, node_id in enumerate(ids):
        node_map[str(node_id)] = {
            "parent": str(parents[idx]),
            "label": str(labels[idx]),
            "value": int(values[idx]),
            "color": str(colors[idx]),
            "customdata": customdata[idx],
        }
    return node_map


def test_plot_active_project_hierarchy_sunburst_rolls_up_active_subprojects():
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

    fig = plot_active_project_hierarchy_sunburst(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 10),
        active_projects,
        {"Root A": "#123456", "Root B": "#654321"},
    )

    assert isinstance(fig, go.Figure)
    assert len(cast(tuple[Any, ...], fig.data)) == 1
    trace = cast(Any, cast(tuple[Any, ...], fig.data)[0])
    assert trace.type == "sunburst"
    assert trace.branchvalues == "total"
    assert trace.sort is False
    assert trace.textinfo == "label+value"
    assert int(trace.insidetextfont.size) >= 18
    assert str(trace.insidetextfont.color) == "#f8fbff"
    assert int(trace.outsidetextfont.size) >= 16
    assert fig.layout.uirevision == "active-project-hierarchy-sunburst"
    assert fig.layout.margin.l >= 24
    assert fig.layout.margin.r >= 24
    assert fig.layout.margin.t >= 30
    assert fig.layout.margin.b >= 76
    assert fig.layout.annotations
    assert float(fig.layout.annotations[0].y) < 0

    nodes = _sunburst_node_map(fig)
    assert "inactive-project" not in nodes
    assert "active-projects" in nodes
    assert nodes["active-projects"]["value"] == 5
    assert nodes["active-projects"]["parent"] == ""
    assert nodes["root-a"]["parent"] == "active-projects"
    assert nodes["root-a"]["value"] == 4
    assert nodes["root-a"]["label"] == "Root A"
    assert nodes["child-a1"]["parent"] == "root-a"
    assert nodes["child-a1"]["value"] == 3
    assert nodes["grand-a"]["parent"] == "child-a1"
    assert nodes["grand-a"]["value"] == 1
    assert nodes["root-b"]["value"] == 1


def test_plot_active_project_hierarchy_sunburst_folds_small_long_tail_into_other_node():
    rows: list[dict[str, str]] = []
    for idx in range(2):
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
    child_totals = [20, 10, 4, 3, 1, 1]
    for idx, total in enumerate(child_totals):
        for occurrence in range(total):
            rows.append(
                {
                    "date": f"2025-02-{idx + occurrence + 3:02d}",
                    "id": f"e-child-{idx}-{occurrence}",
                    "title": f"Child {idx + 1} task",
                    "type": "completed",
                    "parent_project_id": f"child-a{idx + 1}",
                    "parent_project_name": f"Child A{idx + 1}",
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
        make_project(
            project_id="child-a6",
            project_entry=make_project_entry(
                project_id="child-a6",
                name="Child A6",
                parent_id="root-a",
            ),
        ),
    ]

    fig = plot_active_project_hierarchy_sunburst(
        df,
        datetime(2025, 2, 1),
        datetime(2025, 2, 21),
        active_projects,
        {"Root A": "#22577a"},
    )

    nodes = _sunburst_node_map(fig)
    assert "other:root-a" in nodes
    assert nodes["other:root-a"]["parent"] == "root-a"
    assert nodes["other:root-a"]["value"] == 2
    assert nodes["other:root-a"]["customdata"][6] == 2
    assert nodes["other:root-a"]["customdata"][7] == "aggregate"


def test_plot_active_project_hierarchy_sunburst_folds_small_roots_into_other_roots():
    rows: list[dict[str, str]] = []
    root_totals = [100, 50, 25, 10, 1, 1, 1]
    for idx, total in enumerate(root_totals):
        for occurrence in range(total):
            rows.append(
                {
                    "date": f"2025-03-{(occurrence % 20) + 1:02d}",
                    "id": f"e-root-{idx}-{occurrence}",
                    "title": f"Root {idx + 1} task",
                    "type": "completed",
                    "parent_project_id": f"root-{idx + 1}",
                    "parent_project_name": f"Root {idx + 1}",
                    "root_project_id": f"root-{idx + 1}",
                    "root_project_name": f"Root {idx + 1}",
                }
            )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    active_projects = []
    for idx in range(len(root_totals)):
        active_projects.append(
            make_project(
                project_id=f"root-{idx + 1}",
                project_entry=make_project_entry(
                    project_id=f"root-{idx + 1}",
                    name=f"Root {idx + 1}",
                ),
            )
        )

    fig = plot_active_project_hierarchy_sunburst(
        df,
        datetime(2025, 3, 1),
        datetime(2025, 3, 22),
        active_projects,
        {f"Root {idx + 1}": f"#{idx + 1}{idx + 1}{idx + 1}{idx + 1}{idx + 1}{idx + 1}" for idx in range(len(root_totals))},
    )

    nodes = _sunburst_node_map(fig)
    assert "other-roots" in nodes
    assert nodes["other-roots"]["parent"] == "active-projects"
    assert nodes["other-roots"]["value"] == 3
    assert nodes["other-roots"]["customdata"][6] == 3
    assert nodes["other-roots"]["customdata"][7] == "aggregate"


def test_plot_active_project_hierarchy_sunburst_returns_empty_figure_without_completed_tasks():
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

    fig = plot_active_project_hierarchy_sunburst(
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


def test_plot_active_project_hierarchy_sunburst_normalizes_date_column_input():
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

    fig = plot_active_project_hierarchy_sunburst(
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

    nodes = _sunburst_node_map(fig)
    assert nodes["root-a"]["value"] == 1
    assert nodes["root-a"]["customdata"][2] == 1
