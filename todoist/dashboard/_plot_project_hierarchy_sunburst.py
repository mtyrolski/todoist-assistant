from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Callable, cast

import pandas as pd
import plotly.graph_objects as go

from todoist.types import Project

_BACKGROUND_COLOR = "#111318"
_BORDER_COLOR = "rgba(17,19,24,0.92)"
_EMPTY_COLOR = "#7f8b99"
_TEXT_COLOR = "#e7edf5"
_MUTED_TEXT_COLOR = "#9fb0c2"
_CENTER_COLOR = "#151a2b"
_PANEL_GLOW = "#71dfff"


@dataclass(frozen=True)
class _HierarchyNode:
    node_id: str
    parent_id: str
    label: str
    total_completed: int
    direct_completed: int
    root_name: str
    depth: int
    kind: str
    color: str
    hidden_projects: int = 0


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


def _direct_completed_counts(
    df_completed: pd.DataFrame,
    *,
    active_projects: list[Project],
) -> dict[str, int]:
    if "parent_project_id" in df_completed.columns:
        project_ids = cast(
            pd.Series, df_completed["parent_project_id"].fillna("").astype(str)
        )
        counts = cast(pd.Series, project_ids.loc[project_ids != ""]).value_counts()
        return {str(project_id): int(count) for project_id, count in counts.items()}

    if "parent_project_name" not in df_completed.columns:
        return {}

    ids_by_name: dict[str, list[str]] = defaultdict(list)
    for project in active_projects:
        ids_by_name[str(project.project_entry.name)].append(str(project.id))

    resolved_ids = [
        project_ids[0]
        for project_name in cast(pd.Series, df_completed["parent_project_name"])
        .fillna("")
        .astype(str)
        .tolist()
        if len(project_ids := ids_by_name.get(project_name, [])) == 1
    ]
    if not resolved_ids:
        return {}

    counts = pd.Series(resolved_ids, dtype="string").value_counts()
    return {str(project_id): int(count) for project_id, count in counts.items()}


def _normalize_activity_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        valid_dates = cast(pd.Series, normalized["date"]).notna()
        normalized = cast(
            pd.DataFrame,
            normalized.loc[valid_dates].set_index("date", drop=False),
        )
        return cast(pd.DataFrame, normalized.sort_index())

    normalized.index = pd.to_datetime(normalized.index, errors="coerce")
    valid_index = ~pd.isna(normalized.index)
    normalized = cast(pd.DataFrame, normalized.loc[valid_index])
    return cast(pd.DataFrame, normalized.sort_index())


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = color.strip()
    if normalized.startswith("#") and len(normalized) == 7:
        try:
            return (
                int(normalized[1:3], 16),
                int(normalized[3:5], 16),
                int(normalized[5:7], 16),
            )
        except ValueError:
            pass
    fallback = _EMPTY_COLOR
    return (
        int(fallback[1:3], 16),
        int(fallback[3:5], 16),
        int(fallback[5:7], 16),
    )


def _mix_color(color: str, target: str, weight: float) -> str:
    base_rgb = _hex_to_rgb(color)
    target_rgb = _hex_to_rgb(target)
    clamped = max(0.0, min(weight, 1.0))
    mixed = tuple(
        round(base * (1.0 - clamped) + blend * clamped)
        for base, blend in zip(base_rgb, target_rgb, strict=False)
    )
    return f"#{mixed[0]:02x}{mixed[1]:02x}{mixed[2]:02x}"


def _rgba(color: str, alpha: float) -> str:
    red, green, blue = _hex_to_rgb(color)
    return f"rgba({red},{green},{blue},{max(0.0, min(alpha, 1.0)):.3f})"


def _wrap_label(label: str, max_line_length: int = 15) -> str:
    words = label.split()
    if not words:
        return label

    lines: list[str] = []
    current = words[0]
    consumed_words = 1
    for word in words[1:]:
        if len(current) + 1 + len(word) <= max_line_length:
            current = f"{current} {word}"
            consumed_words += 1
            continue
        lines.append(current)
        current = word
        consumed_words += 1
        if len(lines) == 2:
            break
    if len(lines) < 2:
        lines.append(current)

    wrapped = "<br>".join(lines[:2])
    if consumed_words < len(words) or len(label.replace(" ", "")) > max_line_length * 2:
        return f"{wrapped}..."
    return wrapped


def _select_visible_nodes(
    nodes: list[_HierarchyNode],
    *,
    preferred_visible: int,
    max_visible: int,
) -> tuple[list[_HierarchyNode], list[_HierarchyNode]]:
    if len(nodes) <= preferred_visible:
        return nodes, []

    remaining_total = sum(node.total_completed for node in nodes)
    visible: list[_HierarchyNode] = []
    for node in nodes:
        visible.append(node)
        remaining_total -= node.total_completed
        if remaining_total <= 0:
            break
        if len(visible) < preferred_visible:
            continue
        if remaining_total < visible[-1].total_completed:
            break
        if len(visible) >= max_visible:
            return nodes, []

    return visible, nodes[len(visible) :]


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
                    _mix_color(root_color, "#d9e8ff", min(0.24, 0.06 + depth * 0.05)),
                    max(0.58, 0.88 - depth * 0.08),
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
                    _mix_color(root_color, "#b7c8da", 0.2 + min(depth, 4) * 0.03),
                    0.62,
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
        return _empty_project_hierarchy_figure("No completed tasks in the selected range")

    projects_by_id = {str(project.id): project for project in active_projects}
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    root_ids: list[str] = []
    for project in active_projects:
        project_id = str(project.id)
        parent_id = project.project_entry.parent_id
        if parent_id is None or str(parent_id) not in projects_by_id:
            root_ids.append(project_id)
            continue
        children_by_parent[str(parent_id)].append(project_id)

    for child_ids in children_by_parent.values():
        child_ids.sort(key=lambda project_id: projects_by_id[project_id].project_entry.name.lower())
    root_ids.sort(key=lambda project_id: projects_by_id[project_id].project_entry.name.lower())

    direct_counts = {
        project_id: count
        for project_id, count in _direct_completed_counts(
            df_completed, active_projects=active_projects
        ).items()
        if project_id in projects_by_id
    }

    @lru_cache(maxsize=None)
    def subtree_total(project_id: str) -> int:
        return int(direct_counts.get(project_id, 0)) + sum(
            subtree_total(child_id) for child_id in children_by_parent.get(project_id, [])
        )

    active_root_ids = [project_id for project_id in root_ids if subtree_total(project_id) > 0]
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
                    "#d7eeff",
                    0.12,
                ),
                0.9,
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
                color=_rgba(_mix_color(_EMPTY_COLOR, "#b8c7de", 0.22), 0.78),
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
                    line=dict(color="rgba(8,12,24,0.74)", width=2.0),
                ),
                customdata=customdata,
                textinfo="label+value",
                insidetextorientation="radial",
                hoverlabel=dict(
                    bgcolor="rgba(12,16,28,0.96)",
                    bordercolor=_rgba(_PANEL_GLOW, 0.28),
                    font=dict(color=_TEXT_COLOR, size=13),
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
        margin=dict(l=24, r=24, t=30, b=54),
        paper_bgcolor=_BACKGROUND_COLOR,
        plot_bgcolor=_BACKGROUND_COLOR,
        showlegend=False,
        uniformtext=dict(minsize=12, mode="hide"),
        font=dict(color=_TEXT_COLOR, family="Inter, ui-sans-serif, system-ui, sans-serif"),
        uirevision="active-project-hierarchy-sunburst",
        annotations=[
            dict(
                x=0.5,
                y=0.015,
                xref="paper",
                yref="paper",
                showarrow=False,
                xanchor="center",
                yanchor="bottom",
                align="center",
                text=(
                    "Ring area tracks completed tasks. Long tails fold into Other only when they stay smaller than the smallest visible sibling."
                ),
                font=dict(size=9, color=_MUTED_TEXT_COLOR),
            )
        ],
    )
    return fig
