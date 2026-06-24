from datetime import datetime
from typing import Callable, cast

import pandas as pd
import plotly.graph_objects as go

from todoist.core.types import Project
from todoist.dashboard._plot_project_hierarchy import (
    _HierarchyNode,
    _active_project_tree,
    _mix_color,
    _normalize_activity_frame,
    _rgba,
    _select_visible_nodes,
    _wrap_label,
)

_BACKGROUND_COLOR = "#111318"
_BORDER_COLOR = "rgba(17,19,24,0.92)"
_EMPTY_COLOR = "#8ea3ff"
_TEXT_COLOR = "#e7edf5"
_MUTED_TEXT_COLOR = "#9fb0c2"
_CENTER_COLOR = "#151a2b"
_PANEL_GLOW = "#71dfff"


def _empty_project_hierarchy_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16, color=_TEXT_COLOR),
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=560,
        margin=dict(l=24, r=24, t=18, b=24),
        paper_bgcolor=_BACKGROUND_COLOR,
        plot_bgcolor=_BACKGROUND_COLOR,
    )
    return fig


def _build_nodes_for_parent(
    *,
    parent_id: str,
    root_name: str,
    root_color: str,
    depth: int,
    projects_by_id: dict[str, Project],
    children_by_parent: dict[str, list[str]],
    subtree_total: Callable[[str], int],
    direct_counts: dict[str, int],
) -> list[_HierarchyNode]:
    candidates: list[_HierarchyNode] = []
    for child_id in children_by_parent.get(parent_id, []):
        total_completed = subtree_total(child_id)
        if total_completed <= 0:
            continue

        child_project = projects_by_id[child_id]
        child_name = str(child_project.project_entry.name)
        candidates.append(
            _HierarchyNode(
                node_id=child_id,
                parent_id=parent_id,
                label=child_name,
                total_completed=total_completed,
                direct_completed=int(direct_counts.get(child_id, 0)),
                root_name=root_name,
                depth=depth,
                kind="project",
                color=_rgba(
                    _mix_color(root_color, "#ffffff", min(0.34, 0.1 + depth * 0.11)),
                    max(0.84, 1.0 - depth * 0.06),
                ),
            )
        )

    candidates.sort(key=lambda node: (-node.total_completed, node.label.lower()))
    preferred_visible = 4 if depth <= 1 else 3
    max_visible = 6 if depth <= 1 else 5
    visible_children, hidden_children = _select_visible_nodes(
        candidates,
        preferred_visible=preferred_visible,
        max_visible=max_visible,
    )
    if hidden_children:
        visible_children.append(
            _HierarchyNode(
                node_id=f"other:{parent_id}",
                parent_id=parent_id,
                label="Other",
                total_completed=sum(node.total_completed for node in hidden_children),
                direct_completed=sum(node.direct_completed for node in hidden_children),
                root_name=root_name,
                depth=depth,
                kind="aggregate",
                color=_rgba(
                    _mix_color(root_color, "#fff3dc", 0.18 + min(depth, 4) * 0.05),
                    0.82,
                ),
                hidden_projects=len(hidden_children),
            )
        )

    nodes: list[_HierarchyNode] = []
    for child_node in visible_children:
        nodes.append(child_node)
        if child_node.kind == "project":
            nodes.extend(
                _build_nodes_for_parent(
                    parent_id=child_node.node_id,
                    root_name=root_name,
                    root_color=root_color,
                    depth=depth + 1,
                    projects_by_id=projects_by_id,
                    children_by_parent=children_by_parent,
                    subtree_total=subtree_total,
                    direct_counts=direct_counts,
                )
            )
    return nodes


def _sunburst_display_label(node: _HierarchyNode) -> str:
    if node.kind == "center":
        return f"{node.label}<br>{node.total_completed}"
    if node.kind == "aggregate":
        return "Other" if node.label == "Other" else _wrap_label(node.label)
    return _wrap_label(node.label)


def plot_active_project_hierarchy_sunburst(
    df: pd.DataFrame,
    beg_date: datetime,
    end_date: datetime,
    active_projects: list[Project],
    project_colors: dict[str, str],
) -> go.Figure:
    empty_message: str | None = None
    if df.empty:
        empty_message = "No activity in the selected range"
    elif not active_projects:
        empty_message = "No active projects available"
    elif "type" not in df.columns:
        empty_message = "Activity data is missing project event types"
    if empty_message is not None:
        return _empty_project_hierarchy_figure(empty_message)

    df = _normalize_activity_frame(df)
    df_period = cast(pd.DataFrame, df[(df.index >= beg_date) & (df.index < end_date)])
    df_completed = cast(pd.DataFrame, df_period[df_period["type"] == "completed"])
    if df_completed.empty:
        return _empty_project_hierarchy_figure(
            "No completed tasks in the selected range"
        )

    projects_by_id, children_by_parent, root_ids, direct_counts, subtree_total = (
        _active_project_tree(df_completed, active_projects)
    )

    active_root_ids = [
        project_id for project_id in root_ids if subtree_total(project_id) > 0
    ]
    if not active_root_ids:
        return _empty_project_hierarchy_figure(
            "No active project completions in the selected range"
        )

    root_nodes = [
        _HierarchyNode(
            node_id=project_id,
            parent_id="active-projects",
            label=str(projects_by_id[project_id].project_entry.name),
            total_completed=subtree_total(project_id),
            direct_completed=int(direct_counts.get(project_id, 0)),
            root_name=str(projects_by_id[project_id].project_entry.name),
            depth=1,
            kind="root",
            color=_rgba(
                _mix_color(
                    project_colors.get(
                        str(projects_by_id[project_id].project_entry.name),
                        _EMPTY_COLOR,
                    ),
                    "#f9fcff",
                    0.02,
                ),
                0.96,
            ),
        )
        for project_id in sorted(
            active_root_ids,
            key=lambda project_id: (
                -subtree_total(project_id),
                projects_by_id[project_id].project_entry.name.lower(),
            ),
        )
    ]
    visible_roots, hidden_roots = _select_visible_nodes(
        root_nodes, preferred_visible=4, max_visible=6
    )
    if hidden_roots:
        visible_roots.append(
            _HierarchyNode(
                node_id="other-roots",
                parent_id="active-projects",
                label="Other Roots",
                total_completed=sum(node.total_completed for node in hidden_roots),
                direct_completed=sum(node.direct_completed for node in hidden_roots),
                root_name="Active projects",
                depth=1,
                kind="aggregate",
                color=_rgba(_mix_color(_EMPTY_COLOR, "#efe1ff", 0.34), 0.88),
                hidden_projects=len(hidden_roots),
            )
        )

    all_nodes: list[_HierarchyNode] = [
        _HierarchyNode(
            node_id="active-projects",
            parent_id="",
            label="Active projects",
            total_completed=sum(node.total_completed for node in visible_roots),
            direct_completed=sum(node.direct_completed for node in visible_roots),
            root_name="Active projects",
            depth=0,
            kind="center",
            color=_rgba(_CENTER_COLOR, 0.98),
        )
    ]
    for root_node in visible_roots:
        all_nodes.append(root_node)
        if root_node.kind != "aggregate":
            all_nodes.extend(
                _build_nodes_for_parent(
                    parent_id=root_node.node_id,
                    root_name=root_node.label,
                    root_color=root_node.color,
                    depth=2,
                    projects_by_id=projects_by_id,
                    children_by_parent=children_by_parent,
                    subtree_total=subtree_total,
                    direct_counts=direct_counts,
                )
            )

    ids = [node.node_id for node in all_nodes]
    parents = [node.parent_id for node in all_nodes]
    labels = [_sunburst_display_label(node) for node in all_nodes]
    values = [node.total_completed for node in all_nodes]
    colors = [node.color for node in all_nodes]
    customdata = [
        [
            node.node_id,
            node.label,
            node.total_completed,
            node.direct_completed,
            node.root_name,
            node.depth,
            node.hidden_projects,
            node.kind,
        ]
        for node in all_nodes
    ]

    fig = go.Figure(
        data=[
            go.Sunburst(
                ids=ids,
                labels=labels,
                parents=parents,
                values=values,
                branchvalues="total",
                sort=False,
                marker=dict(
                    colors=colors,
                    line=dict(color="rgba(241,246,255,0.42)", width=3.2),
                ),
                leaf=dict(opacity=0.98),
                customdata=customdata,
                textinfo="label+value",
                insidetextorientation="auto",
                insidetextfont=dict(
                    family="Space Grotesk, Segoe UI, Inter, ui-sans-serif, system-ui, sans-serif",
                    size=18,
                    color="#f8fbff",
                ),
                outsidetextfont=dict(
                    family="Space Grotesk, Segoe UI, Inter, ui-sans-serif, system-ui, sans-serif",
                    size=16,
                    color="#f8fbff",
                ),
                hoverlabel=dict(
                    bgcolor="rgba(12,16,28,0.96)",
                    bordercolor=_rgba(_PANEL_GLOW, 0.28),
                    font=dict(
                        color=_TEXT_COLOR,
                        size=14,
                        family="Space Grotesk, Segoe UI, Inter, ui-sans-serif, system-ui, sans-serif",
                    ),
                ),
                hovertemplate=(
                    "<b>%{customdata[1]}</b>"
                    "<br>Total completed in range: %{customdata[2]}"
                    "<br>Completed directly in project: %{customdata[3]}"
                    "<br>Root project: %{customdata[4]}"
                    "<br>Hierarchy depth: %{customdata[5]}"
                    "<br>Hidden projects folded in: %{customdata[6]}"
                    "<extra></extra>"
                ),
            )
        ]
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=620,
        margin=dict(l=24, r=24, t=30, b=76),
        paper_bgcolor=_BACKGROUND_COLOR,
        plot_bgcolor=_BACKGROUND_COLOR,
        showlegend=False,
        uniformtext=dict(minsize=13, mode="hide"),
        font=dict(
            color=_TEXT_COLOR,
            family="Space Grotesk, Segoe UI, Inter, ui-sans-serif, system-ui, sans-serif",
        ),
        uirevision="active-project-hierarchy-sunburst",
        annotations=[
            dict(
                x=0.5,
                y=-0.065,
                xref="paper",
                yref="paper",
                showarrow=False,
                xanchor="center",
                yanchor="bottom",
                align="center",
                text=(
                    "Ring area tracks completed tasks. Long tails fold into Other only when they stay smaller than the smallest visible sibling."
                ),
                font=dict(
                    size=10,
                    color=_MUTED_TEXT_COLOR,
                    family="Space Grotesk, Segoe UI, Inter, ui-sans-serif, system-ui, sans-serif",
                ),
            )
        ],
    )
    return fig
