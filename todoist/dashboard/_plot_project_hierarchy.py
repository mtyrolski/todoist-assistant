from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import math
from typing import Callable, cast

import pandas as pd
import plotly.graph_objects as go

from todoist.types import Project

_BACKGROUND_COLOR = "#111318"
_BORDER_COLOR = "rgba(17,19,24,0.92)"
_EMPTY_COLOR = "#7f8b99"
_TEXT_COLOR = "#e7edf5"
_MUTED_TEXT_COLOR = "#9fb0c2"


@dataclass(frozen=True)
class _HierarchyNode:
    node_id: str
    label: str
    total_completed: int
    direct_completed: int
    root_name: str
    depth: int
    kind: str
    color: str
    hidden_projects: int = 0


@dataclass(frozen=True)
class _BubblePoint:
    node: _HierarchyNode
    x: float
    y: float
    size: float


def _empty_project_hierarchy_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16, color="#cfd8e3"),
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=520,
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


def _wrap_label(label: str, max_line_length: int = 13) -> str:
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


def _bubble_size(
    value: int,
    *,
    max_value: int,
    min_diameter: float,
    max_diameter: float,
) -> float:
    if max_value <= 0:
        return min_diameter
    scale = math.sqrt(max(value, 0)) / math.sqrt(max_value)
    return min_diameter + scale * (max_diameter - min_diameter)


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


def _cluster_x_positions(count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [50.0]
    start = 18.0 if count > 2 else 30.0
    end = 82.0 if count > 2 else 70.0
    step = (end - start) / (count - 1)
    return [start + step * idx for idx in range(count)]


def _cluster_centers(cluster_count: int) -> list[tuple[float, float]]:
    if cluster_count <= 0:
        return []
    if cluster_count <= 3:
        xs = _cluster_x_positions(cluster_count)
        return [(x_value, 66.0 + 4.0 * math.sin((idx - (cluster_count - 1) / 2.0) * 0.8)) for idx, x_value in enumerate(xs)]

    first_row = math.ceil(cluster_count / 2)
    second_row = cluster_count - first_row
    centers: list[tuple[float, float]] = []
    for idx, x_value in enumerate(_cluster_x_positions(first_row)):
        centers.append((x_value, 73.0 + 2.5 * math.sin((idx - (first_row - 1) / 2.0) * 0.8)))
    for idx, x_value in enumerate(_cluster_x_positions(second_row)):
        centers.append((x_value, 39.0 + 2.0 * math.sin((idx - (second_row - 1) / 2.0) * 0.6)))
    return centers


def _orbit_angles(count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [math.radians(270)]
    start = math.radians(206)
    end = math.radians(334)
    step = (end - start) / (count - 1)
    return [start + step * idx for idx in range(count)]


def _bubble_text(node: _HierarchyNode, size: float) -> str:
    wrapped_label = _wrap_label(node.label if node.kind != "aggregate" else "Other")
    if node.kind == "root":
        return f"{wrapped_label}<br>{node.total_completed}"
    if size >= 34.0 or node.kind == "aggregate":
        return f"{wrapped_label}<br>{node.total_completed}"
    if size >= 26.0:
        return str(node.total_completed)
    return ""


def _build_trace(
    points: list[_BubblePoint],
    *,
    name: str,
    line_width: float,
    border_mix: float,
    glow_scale: float,
    text_size: int,
    hovertemplate: str,
) -> tuple[go.Scatter, go.Scatter]:
    if not points:
        empty_trace = go.Scatter(x=[], y=[])
        return empty_trace, empty_trace

    x_values = [point.x for point in points]
    y_values = [point.y for point in points]
    sizes = [point.size for point in points]
    colors = [point.node.color for point in points]
    text_values = [_bubble_text(point.node, point.size) for point in points]
    line_colors = [_mix_color(point.node.color, "#ffffff", border_mix) for point in points]
    customdata = [
        [
            point.node.node_id,
            point.node.label,
            point.node.total_completed,
            point.node.direct_completed,
            point.node.root_name,
            point.node.depth,
            point.node.hidden_projects,
            point.node.kind,
        ]
        for point in points
    ]

    glow_trace = go.Scatter(
        x=x_values,
        y=y_values,
        mode="markers",
        showlegend=False,
        hoverinfo="skip",
        marker=dict(
            size=[size * glow_scale for size in sizes],
            color=[_rgba(color, 0.18) for color in colors],
            line=dict(width=0),
        ),
    )
    bubble_trace = go.Scatter(
        x=x_values,
        y=y_values,
        mode="markers+text",
        name=name,
        text=text_values,
        textposition="middle center",
        textfont=dict(size=text_size, color=_TEXT_COLOR),
        cliponaxis=False,
        customdata=customdata,
        hovertemplate=hovertemplate,
        marker=dict(
            size=sizes,
            color=colors,
            line=dict(color=line_colors, width=line_width),
            opacity=0.97,
        ),
    )
    return glow_trace, bubble_trace


def _collect_active_descendants(
    *,
    root_id: str,
    root_label: str,
    root_color: str,
    projects_by_id: dict[str, Project],
    children_by_parent: dict[str, list[str]],
    subtree_total: Callable[[str], int],
    direct_counts: dict[str, int],
) -> list[_HierarchyNode]:
    descendants: list[_HierarchyNode] = []

    def collect(project_id: str, *, depth: int) -> None:
        for child_id in children_by_parent.get(project_id, []):
            total_completed = subtree_total(child_id)
            if total_completed <= 0:
                continue
            child_project = projects_by_id[child_id]
            child_name = str(child_project.project_entry.name)
            descendants.append(
                _HierarchyNode(
                    node_id=child_id,
                    label=child_name,
                    total_completed=total_completed,
                    direct_completed=int(direct_counts.get(child_id, 0)),
                    root_name=root_label,
                    depth=depth,
                    kind="project",
                    color=_mix_color(root_color, "#ffffff", 0.22 + depth * 0.09),
                )
            )
            collect(child_id, depth=depth + 1)

    collect(root_id, depth=1)
    descendants.sort(key=lambda node: (-node.total_completed, node.depth, node.label.lower()))
    return descendants


def plot_active_project_hierarchy(
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
        return _empty_project_hierarchy_figure("No active project completions in the selected range")

    root_nodes = [
        _HierarchyNode(
            node_id=project_id,
            label=str(projects_by_id[project_id].project_entry.name),
            total_completed=subtree_total(project_id),
            direct_completed=int(direct_counts.get(project_id, 0)),
            root_name=str(projects_by_id[project_id].project_entry.name),
            depth=0,
            kind="root",
            color=_mix_color(
                project_colors.get(
                    str(projects_by_id[project_id].project_entry.name), _EMPTY_COLOR
                ),
                "#ffffff",
                0.1,
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
        root_nodes, preferred_visible=4, max_visible=7
    )

    descendant_points_by_root: dict[str, list[_HierarchyNode]] = {}
    if hidden_roots:
        hidden_total = sum(node.total_completed for node in hidden_roots)
        visible_roots.append(
            _HierarchyNode(
                node_id="other-roots",
                label="Other Roots",
                total_completed=hidden_total,
                direct_completed=sum(node.direct_completed for node in hidden_roots),
                root_name="Other active roots",
                depth=0,
                kind="aggregate",
                color=_mix_color(_EMPTY_COLOR, "#dbe7f5", 0.18),
                hidden_projects=len(hidden_roots),
            )
        )

    for root_node in visible_roots:
        if root_node.node_id == "other-roots":
            descendant_points_by_root[root_node.node_id] = []
            continue

        descendants = _collect_active_descendants(
            root_id=root_node.node_id,
            root_label=root_node.label,
            root_color=root_node.color,
            projects_by_id=projects_by_id,
            children_by_parent=children_by_parent,
            subtree_total=subtree_total,
            direct_counts=direct_counts,
        )
        visible_descendants, hidden_descendants = _select_visible_nodes(
            descendants, preferred_visible=3, max_visible=6
        )
        if hidden_descendants:
            visible_descendants.append(
                _HierarchyNode(
                    node_id=f"other:{root_node.node_id}",
                    label="Other",
                    total_completed=sum(
                        node.total_completed for node in hidden_descendants
                    ),
                    direct_completed=sum(
                        node.direct_completed for node in hidden_descendants
                    ),
                    root_name=root_node.label,
                    depth=1,
                    kind="aggregate",
                    color=_mix_color(root_node.color, "#dbe7f5", 0.34),
                    hidden_projects=len(hidden_descendants),
                )
            )
        descendant_points_by_root[root_node.node_id] = visible_descendants

    all_nodes = visible_roots + [
        node
        for _, descendants in descendant_points_by_root.items()
        for node in descendants
    ]
    max_value = max(node.total_completed for node in all_nodes)

    root_points: list[_BubblePoint] = []
    child_points: list[_BubblePoint] = []
    cluster_centers = _cluster_centers(len(visible_roots))
    for idx, root_node in enumerate(visible_roots):
        center_x, center_y = cluster_centers[idx]
        root_size = _bubble_size(
            root_node.total_completed,
            max_value=max_value,
            min_diameter=44.0,
            max_diameter=74.0,
        )
        root_points.append(
            _BubblePoint(node=root_node, x=center_x, y=center_y, size=root_size)
        )

        descendants = descendant_points_by_root[root_node.node_id]
        if not descendants:
            continue
        child_sizes = [
            _bubble_size(
                descendant.total_completed,
                max_value=max_value,
                min_diameter=20.0,
                max_diameter=46.0,
            )
            for descendant in descendants
        ]
        orbit_radius = 11.5 + root_size * 0.23 + max(child_sizes, default=0.0) * 0.15
        vertical_shift = 7.5 if len(visible_roots) <= 3 else 6.0
        for descendant, child_size, angle in zip(
            descendants, child_sizes, _orbit_angles(len(descendants)), strict=False
        ):
            child_points.append(
                _BubblePoint(
                    node=descendant,
                    x=center_x + orbit_radius * math.cos(angle),
                    y=center_y - vertical_shift + orbit_radius * 0.55 * math.sin(angle),
                    size=child_size,
                )
            )

    child_glow, child_trace = _build_trace(
        child_points,
        name="Active subprojects",
        line_width=1.6,
        border_mix=0.42,
        glow_scale=1.55,
        text_size=11,
        hovertemplate=(
            "<b>%{customdata[1]}</b>"
            "<br>Root project: %{customdata[4]}"
            "<br>Total completed in range: %{customdata[2]}"
            "<br>Completed directly in project: %{customdata[3]}"
            "<br>Hierarchy depth: %{customdata[5]}"
            "<br>Hidden projects folded in: %{customdata[6]}"
            "<extra></extra>"
        ),
    )
    root_glow, root_trace = _build_trace(
        root_points,
        name="Root projects",
        line_width=2.2,
        border_mix=0.28,
        glow_scale=1.65,
        text_size=12,
        hovertemplate=(
            "<b>%{customdata[1]}</b>"
            "<br>Total completed in range: %{customdata[2]}"
            "<br>Completed directly in root: %{customdata[3]}"
            "<br>Hidden roots folded in: %{customdata[6]}"
            "<extra></extra>"
        ),
    )

    fig = go.Figure(data=[child_glow, root_glow, child_trace, root_trace])
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=620,
        margin=dict(l=18, r=18, t=14, b=30),
        paper_bgcolor=_BACKGROUND_COLOR,
        plot_bgcolor=_BACKGROUND_COLOR,
        showlegend=False,
        xaxis=dict(
            visible=False,
            range=[0, 100],
            fixedrange=True,
        ),
        yaxis=dict(
            visible=False,
            range=[0, 100],
            fixedrange=True,
            scaleanchor="x",
            scaleratio=1,
        ),
        annotations=[
            dict(
                x=0.99,
                y=0.01,
                xref="paper",
                yref="paper",
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                align="right",
                text=(
                    "Bubble area tracks completed tasks. "
                    "Long tails are folded into Other only when they stay smaller "
                    "than the smallest visible bubble."
                ),
                font=dict(size=11, color=_MUTED_TEXT_COLOR),
            )
        ],
    )
    return fig
