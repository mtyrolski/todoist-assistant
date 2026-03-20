"""Tests for the active project hierarchy icicle plot."""

from datetime import datetime, timedelta
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go

from tests.factories import make_project
from todoist.dashboard._plot_project_hierarchy_icicle import (
    plot_active_project_hierarchy_icicle,
)


def _activity_frame(rows: list[dict[str, Any]], dates: list[datetime]) -> pd.DataFrame:
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
    df.index.name = "date"
    return df


def test_plot_active_project_hierarchy_icicle_builds_a_tree() -> None:
    root_academy = make_project(project_id="academy-root", name="Academy", color="blue")
    academy_phd = make_project(
        project_id="academy-phd",
        name="PhD",
        color="blue",
        parent_id="academy-root",
    )
    academy_notes = make_project(
        project_id="academy-notes",
        name="Notes",
        color="blue",
        parent_id="academy-root",
    )
    root_ey = make_project(project_id="ey-root", name="EY", color="purple")
    ey_delivery = make_project(
        project_id="ey-delivery",
        name="Delivery",
        color="purple",
        parent_id="ey-root",
    )

    active_projects = [root_academy, academy_phd, academy_notes, root_ey, ey_delivery]
    project_colors = {
        "Academy": "#7dcfb6",
        "EY": "#be6cff",
    }
    base_date = datetime(2024, 1, 1, 12, 0, 0)
    df = _activity_frame(
        [
            {"type": "completed", "parent_project_id": "academy-root"},
            {"type": "completed", "parent_project_id": "academy-root"},
            {"type": "completed", "parent_project_id": "academy-root"},
            {"type": "completed", "parent_project_id": "academy-phd"},
            {"type": "completed", "parent_project_id": "academy-phd"},
            {"type": "completed", "parent_project_id": "academy-notes"},
            {"type": "completed", "parent_project_id": "ey-root"},
            {"type": "completed", "parent_project_id": "ey-delivery"},
            {"type": "completed", "parent_project_id": "ey-delivery"},
        ],
        [base_date + timedelta(hours=idx) for idx in range(9)],
    )

    fig = plot_active_project_hierarchy_icicle(
        df,
        base_date - timedelta(days=1),
        base_date + timedelta(days=1),
        active_projects,
        project_colors,
    )

    assert isinstance(fig, go.Figure)
    trace = cast(go.Icicle, fig.data[0])
    assert trace.type == "icicle"
    assert trace.branchvalues == "total"

    labels = list(cast(tuple[str, ...], trace.labels))
    ids = list(cast(tuple[str, ...], trace.ids))
    parents = list(cast(tuple[str, ...], trace.parents))
    values = list(cast(tuple[int, ...], trace.values))
    value_by_id = dict(zip(ids, values, strict=False))

    assert "Academy" in labels
    assert "EY" in labels
    assert "PhD" in labels
    assert "Notes" in labels
    assert "Delivery" in labels

    assert value_by_id["academy-root"] == 6
    assert value_by_id["academy-phd"] == 2
    assert value_by_id["academy-notes"] == 1
    assert value_by_id["ey-root"] == 3
    assert value_by_id["ey-delivery"] == 2

    assert parents[ids.index("academy-root")] == ""
    assert parents[ids.index("ey-root")] == ""
    assert parents[ids.index("academy-phd")] == "academy-root"
    assert parents[ids.index("academy-notes")] == "academy-root"
    assert parents[ids.index("ey-delivery")] == "ey-root"


def test_plot_active_project_hierarchy_icicle_folds_small_tail_into_other() -> None:
    root = make_project(project_id="root-a", name="Academy", color="blue")
    alpha = make_project(project_id="alpha", name="Alpha", parent_id="root-a")
    beta = make_project(project_id="beta", name="Beta", parent_id="root-a")
    gamma = make_project(project_id="gamma", name="Gamma", parent_id="root-a")
    delta = make_project(project_id="delta", name="Delta", parent_id="root-a")
    epsilon = make_project(project_id="epsilon", name="Epsilon", parent_id="root-a")

    active_projects = [root, alpha, beta, gamma, delta, epsilon]
    project_colors = {"Academy": "#7dcfb6"}
    base_date = datetime(2024, 1, 1, 12, 0, 0)
    df = _activity_frame(
        [
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "alpha"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "beta"},
            {"type": "completed", "parent_project_id": "gamma"},
            {"type": "completed", "parent_project_id": "gamma"},
            {"type": "completed", "parent_project_id": "gamma"},
            {"type": "completed", "parent_project_id": "gamma"},
            {"type": "completed", "parent_project_id": "gamma"},
            {"type": "completed", "parent_project_id": "gamma"},
            {"type": "completed", "parent_project_id": "delta"},
            {"type": "completed", "parent_project_id": "delta"},
            {"type": "completed", "parent_project_id": "delta"},
            {"type": "completed", "parent_project_id": "delta"},
            {"type": "completed", "parent_project_id": "epsilon"},
        ],
        [base_date + timedelta(minutes=idx) for idx in range(33)],
    )

    fig = plot_active_project_hierarchy_icicle(
        df,
        base_date - timedelta(days=1),
        base_date + timedelta(days=1),
        active_projects,
        project_colors,
    )

    trace = cast(go.Icicle, fig.data[0])
    labels = list(cast(tuple[str, ...], trace.labels))
    ids = list(cast(tuple[str, ...], trace.ids))
    parents = list(cast(tuple[str, ...], trace.parents))
    values = list(cast(tuple[int, ...], trace.values))
    value_by_id = dict(zip(ids, values, strict=False))

    assert "Other" in labels
    other_index = labels.index("Other")
    assert parents[other_index] == "root-a"
    assert value_by_id["other:root-a"] == 1
    assert "Epsilon" not in labels


def test_plot_active_project_hierarchy_icicle_accepts_date_column() -> None:
    root = make_project(project_id="root-date", name="Root")
    child = make_project(project_id="child-date", name="Child", parent_id="root-date")
    project_colors = {"Root": "#88a8ff"}
    base_date = datetime(2024, 1, 1, 12, 0, 0)
    df = pd.DataFrame(
        [
            {"date": base_date, "type": "completed", "parent_project_id": "child-date"},
            {
                "date": base_date + timedelta(hours=1),
                "type": "completed",
                "parent_project_id": "root-date",
            },
        ]
    )

    fig = plot_active_project_hierarchy_icicle(
        df,
        base_date - timedelta(days=1),
        base_date + timedelta(days=1),
        [root, child],
        project_colors,
    )

    trace = cast(go.Icicle, fig.data[0])
    labels = list(cast(tuple[str, ...], trace.labels))
    assert "Root" in labels
    assert "Child" in labels


def test_plot_active_project_hierarchy_icicle_handles_no_completed_tasks() -> None:
    root = make_project(project_id="root-empty", name="Empty Root")
    base_date = datetime(2024, 1, 1, 12, 0, 0)
    df = _activity_frame(
        [{"type": "added", "parent_project_id": "root-empty"}],
        [base_date],
    )

    fig = plot_active_project_hierarchy_icicle(
        df,
        base_date - timedelta(days=1),
        base_date + timedelta(days=1),
        [root],
        {"Empty Root": "#8cbf88"},
    )

    assert isinstance(fig, go.Figure)
    assert fig.layout.annotations is not None
    annotation = fig.layout.annotations[0]
    assert "No completed tasks" in cast(str, annotation.text)
