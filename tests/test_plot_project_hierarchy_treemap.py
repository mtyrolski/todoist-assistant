from datetime import datetime
from typing import Sequence, cast

import pandas as pd
import plotly.graph_objects as go

from tests.factories import make_project, make_project_entry
from todoist.types import Project
from todoist.dashboard._plot_project_hierarchy_treemap import (
    plot_active_project_hierarchy_treemap,
)


def _completed_row(date: str, project_id: str, title: str) -> dict[str, str]:
    return {
        "date": date,
        "id": f"event-{project_id}-{date}",
        "title": title,
        "type": "completed",
        "parent_project_id": project_id,
    }


def _active_project(
    *,
    project_id: str,
    name: str,
    parent_id: str | None = None,
) -> Project:
    return make_project(
        project_id=project_id,
        project_entry=make_project_entry(
            project_id=project_id,
            name=name,
            parent_id=parent_id,
        ),
    )


def test_plot_active_project_hierarchy_treemap_preserves_tree_structure():
    df = pd.DataFrame(
        [
            _completed_row("2025-01-02", "root-a", "Root task"),
            _completed_row("2025-01-03", "child-a1", "Child A1 task"),
            _completed_row("2025-01-04", "grand-a1", "Grandchild task"),
            _completed_row("2025-01-05", "child-a2", "Child A2 task"),
            _completed_row("2025-01-06", "root-b", "Root B task"),
        ]
    )

    active_projects = [
        _active_project(project_id="root-a", name="Root A"),
        _active_project(project_id="child-a1", name="Child A1", parent_id="root-a"),
        _active_project(project_id="grand-a1", name="Grand A1", parent_id="child-a1"),
        _active_project(project_id="child-a2", name="Child A2", parent_id="root-a"),
        _active_project(project_id="root-b", name="Root B"),
    ]

    fig = plot_active_project_hierarchy_treemap(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 10),
        active_projects,
        {"Root A": "#226677", "Root B": "#774422"},
    )

    trace = cast(go.Treemap, fig.data[0])
    trace_ids = tuple(cast(Sequence[str] | None, trace.ids) or ())
    trace_parents = tuple(cast(Sequence[str] | None, trace.parents) or ())
    trace_values = tuple(cast(Sequence[int | float] | None, trace.values) or ())
    assert isinstance(trace, go.Treemap)
    assert trace.branchvalues == "total"

    by_id = {
        str(node_id): str(parent_id)
        for node_id, parent_id in zip(trace_ids, trace_parents, strict=False)
    }
    values = {
        str(node_id): int(value)
        for node_id, value in zip(trace_ids, trace_values, strict=False)
    }

    assert by_id["root-a"] == ""
    assert by_id["child-a1"] == "root-a"
    assert by_id["grand-a1"] == "child-a1"
    assert by_id["child-a2"] == "root-a"
    assert by_id["root-b"] == ""

    assert values["grand-a1"] == 1
    assert values["child-a1"] == 2
    assert values["child-a2"] == 1
    assert values["root-a"] == 4
    assert values["root-b"] == 1

    assert fig.layout.annotations
    assert "Treemap area tracks completed tasks" in str(fig.layout.annotations[0].text)


def test_plot_active_project_hierarchy_treemap_folds_long_tail_into_other_nodes():
    rows: list[dict[str, str]] = []
    rows.append(_completed_row("2025-02-01", "root-a", "Root A task"))
    child_counts = {
        "child-a1": 8,
        "child-a2": 7,
        "child-a3": 6,
        "child-a4": 5,
        "child-a5": 4,
    }
    for idx, (project_id, count) in enumerate(child_counts.items(), start=1):
        for _ in range(count):
            rows.append(
                _completed_row(
                    f"2025-02-{idx + 1:02d}",
                    project_id,
                    f"{project_id} task",
                )
            )
    root_counts = {
        "root-b": 20,
        "root-c": 15,
        "root-d": 10,
        "root-e": 1,
    }
    for idx, (project_id, count) in enumerate(root_counts.items(), start=7):
        for _ in range(count):
            rows.append(
                _completed_row(
                    f"2025-02-{idx:02d}",
                    project_id,
                    f"{project_id} task",
                )
            )
    df = pd.DataFrame(rows)

    active_projects = [
        _active_project(project_id="root-a", name="Root A"),
        _active_project(project_id="child-a1", name="Child A1", parent_id="root-a"),
        _active_project(project_id="child-a2", name="Child A2", parent_id="root-a"),
        _active_project(project_id="child-a3", name="Child A3", parent_id="root-a"),
        _active_project(project_id="child-a4", name="Child A4", parent_id="root-a"),
        _active_project(project_id="child-a5", name="Child A5", parent_id="root-a"),
        _active_project(project_id="root-b", name="Root B"),
        _active_project(project_id="root-c", name="Root C"),
        _active_project(project_id="root-d", name="Root D"),
        _active_project(project_id="root-e", name="Root E"),
    ]

    fig = plot_active_project_hierarchy_treemap(
        df,
        datetime(2025, 2, 1),
        datetime(2025, 2, 21),
        active_projects,
        {"Root A": "#226677", "Root B": "#663377", "Root C": "#557733"},
    )

    trace = cast(go.Treemap, fig.data[0])
    trace_ids = tuple(cast(Sequence[str] | None, trace.ids) or ())
    trace_labels = tuple(cast(Sequence[str] | None, trace.labels) or ())
    trace_parents = tuple(cast(Sequence[str] | None, trace.parents) or ())
    trace_values = tuple(cast(Sequence[int | float] | None, trace.values) or ())
    trace_customdata = tuple(
        cast(Sequence[Sequence[object]] | None, trace.customdata) or ()
    )

    ids = [str(node_id) for node_id in trace_ids]
    labels = [str(label) for label in trace_labels]
    by_id = {
        str(node_id): str(parent_id)
        for node_id, parent_id in zip(trace_ids, trace_parents, strict=False)
    }
    values = {
        str(node_id): int(value)
        for node_id, value in zip(trace_ids, trace_values, strict=False)
    }
    customdata = {
        str(node_id): cast(Sequence[object], item)
        for node_id, item in zip(trace_ids, trace_customdata, strict=False)
    }

    assert "other-roots" in ids
    assert "other:root-a" in ids
    assert by_id["other-roots"] == ""
    assert by_id["other:root-a"] == "root-a"
    assert "Other Roots" in labels
    assert "Other" in labels
    assert values["other-roots"] == 1
    assert values["other:root-a"] == 4
    assert int(cast(int, customdata["other-roots"][6])) == 1
    assert int(cast(int, customdata["other:root-a"][6])) == 1


def test_plot_active_project_hierarchy_treemap_returns_empty_figure_without_completed_tasks():
    df = pd.DataFrame(
        [
            _completed_row("2025-01-02", "root-a", "Root task"),
        ]
    )
    df["type"] = "added"

    fig = plot_active_project_hierarchy_treemap(
        df,
        datetime(2025, 1, 1),
        datetime(2025, 1, 10),
        [
            _active_project(project_id="root-a", name="Root A"),
        ],
        {"Root A": "#226677"},
    )

    assert not fig.data
    assert fig.layout.annotations
    assert "No completed tasks" in str(fig.layout.annotations[0].text)


def test_plot_active_project_hierarchy_treemap_normalizes_date_column_input():
    df = pd.DataFrame(
        [
            _completed_row("2025-03-02", "root-a", "Root task"),
        ]
    )

    fig = plot_active_project_hierarchy_treemap(
        df,
        datetime(2025, 3, 1),
        datetime(2025, 3, 10),
        [
            _active_project(project_id="root-a", name="Root A"),
        ],
        {"Root A": "#226677"},
    )

    trace = cast(go.Treemap, fig.data[0])
    assert isinstance(trace, go.Treemap)
    assert "root-a" in {str(node_id) for node_id in cast(Sequence[str] | None, trace.ids) or ()}
