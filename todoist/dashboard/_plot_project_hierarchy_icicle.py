from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Callable, cast

import pandas as pd
import plotly.graph_objects as go

from todoist.types import Project

_BACKGROUND_COLOR = "#111318"
_EMPTY_COLOR = "#7f8b99"
_TEXT_COLOR = "#e7edf5"
_MUTED_TEXT_COLOR = "#9fb0c2"


@dataclass(frozen=True)
class _IcicleNode:
    node_id: str
    label: str
    parent_id: str
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
        font=dict(size=16, color="#cfd8e3"),
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=620,
        margin=dict(l=24, r=24, t=18, b=24),
        paper_bgcolor=_BACKGROUND_COLOR,
        plot_bgcolor=_BACKGROUND_COLOR,
    )
    return fig


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


def _wrap_label(label: str, max_line_length: int = 16) -> str:
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
    nodes: list[_IcicleNode],
    *,
    preferred_visible: int,
    max_visible: int,
) -> tuple[list[_IcicleNode], list[_IcicleNode]]:
    if len(nodes) <= preferred_visible:
        return nodes, []

    remaining_total = sum(node.total_completed for node in nodes)
    visible: list[_IcicleNode] = []
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


def _root_color_for(project: Project, project_colors: dict[str, str]) -> str:
    label = str(project.project_entry.name)
    color = project_colors.get(label) or project_colors.get(str(project.id))
    if color:
        return color
    return _EMPTY_COLOR


def _build_node(
    *,
    project_id: str,
    parent_id: str,
    depth: int,
    root_name: str,
    root_color: str,
    projects_by_id: dict[str, Project],
    children_by_parent: dict[str, list[str]],
    subtree_total: Callable[[str], int],
    direct_counts: dict[str, int],
) -> list[_IcicleNode]:
    project = projects_by_id[project_id]
    project_name = str(project.project_entry.name)
    nodes = [
        _IcicleNode(
            node_id=project_id,
            label=project_name,
            parent_id=parent_id,
            total_completed=subtree_total(project_id),
            direct_completed=int(direct_counts.get(project_id, 0)),
            root_name=root_name,
            depth=depth,
            kind="root" if depth == 0 else "project",
            color=_mix_color(
                root_color,
                "#ffffff",
                0.12 if depth == 0 else min(0.22 + depth * 0.08, 0.58),
            ),
        )
    ]

    child_ids = [
        child_id
        for child_id in children_by_parent.get(project_id, [])
        if subtree_total(child_id) > 0
    ]
    if not child_ids:
        return nodes

    child_ids.sort(
        key=lambda child_id: (
            -subtree_total(child_id),
            projects_by_id[child_id].project_entry.name.lower(),
        )
    )
    child_nodes = [
        _IcicleNode(
            node_id=child_id,
            label=str(projects_by_id[child_id].project_entry.name),
            parent_id=project_id,
            total_completed=subtree_total(child_id),
            direct_completed=int(direct_counts.get(child_id, 0)),
            root_name=root_name,
            depth=depth + 1,
            kind="project",
            color=_mix_color(
                root_color,
                "#ffffff",
                min(0.28 + (depth + 1) * 0.08, 0.72),
            ),
        )
        for child_id in child_ids
    ]
    visible_children, hidden_children = _select_visible_nodes(
        child_nodes, preferred_visible=4, max_visible=7
    )
    if hidden_children:
        hidden_total = sum(node.total_completed for node in hidden_children)
        smallest_visible = min(node.total_completed for node in visible_children)
        if hidden_total < smallest_visible:
            visible_children = [
                *visible_children,
                _IcicleNode(
                    node_id=f"other:{project_id}",
                    label="Other",
                    parent_id=project_id,
                    total_completed=hidden_total,
                    direct_completed=sum(node.direct_completed for node in hidden_children),
                    root_name=root_name,
                    depth=depth + 1,
                    kind="aggregate",
                    color=_mix_color(root_color, "#dbe7f5", 0.42),
                    hidden_projects=len(hidden_children),
                ),
            ]

    for child_node in visible_children:
        if child_node.kind == "aggregate":
            nodes.append(child_node)
            continue
        nodes.extend(
            _build_node(
                project_id=child_node.node_id,
                parent_id=project_id,
                depth=depth + 1,
                root_name=root_name,
                root_color=root_color,
                projects_by_id=projects_by_id,
                children_by_parent=children_by_parent,
                subtree_total=subtree_total,
                direct_counts=direct_counts,
            )
        )

    return nodes


def plot_active_project_hierarchy_icicle(
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
        child_ids.sort(key=lambda child_id: projects_by_id[child_id].project_entry.name.lower())
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
        _IcicleNode(
            node_id=project_id,
            label=str(projects_by_id[project_id].project_entry.name),
            parent_id="",
            total_completed=subtree_total(project_id),
            direct_completed=int(direct_counts.get(project_id, 0)),
            root_name=str(projects_by_id[project_id].project_entry.name),
            depth=0,
            kind="root",
            color=_mix_color(_root_color_for(projects_by_id[project_id], project_colors), "#ffffff", 0.1),
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
        root_nodes, preferred_visible=5, max_visible=8
    )
    if hidden_roots:
        hidden_total = sum(node.total_completed for node in hidden_roots)
        smallest_visible = min(node.total_completed for node in visible_roots)
        if hidden_total < smallest_visible:
            visible_roots.append(
                _IcicleNode(
                    node_id="other-roots",
                    label="Other Roots",
                    parent_id="",
                    total_completed=hidden_total,
                    direct_completed=sum(node.direct_completed for node in hidden_roots),
                    root_name="Other active roots",
                    depth=0,
                    kind="aggregate",
                    color=_mix_color(_EMPTY_COLOR, "#dbe7f5", 0.22),
                    hidden_projects=len(hidden_roots),
                )
            )
        else:
            visible_roots = root_nodes

    all_nodes: list[_IcicleNode] = []
    for root_node in visible_roots:
        if root_node.kind == "aggregate":
            all_nodes.append(root_node)
            continue
        all_nodes.extend(
            _build_node(
                project_id=root_node.node_id,
                parent_id="",
                depth=0,
                root_name=root_node.label,
                root_color=_root_color_for(projects_by_id[root_node.node_id], project_colors),
                projects_by_id=projects_by_id,
                children_by_parent=children_by_parent,
                subtree_total=subtree_total,
                direct_counts=direct_counts,
            )
        )

    labels = [_wrap_label(node.label) for node in all_nodes]
    ids = [node.node_id for node in all_nodes]
    parents = [node.parent_id for node in all_nodes]
    values = [node.total_completed for node in all_nodes]
    colors = [node.color for node in all_nodes]
    customdata = [
        [
            node.root_name,
            node.direct_completed,
            node.depth,
            node.hidden_projects,
            node.kind,
        ]
        for node in all_nodes
    ]

    fig = go.Figure(
        data=[
            go.Icicle(
                ids=ids,
                labels=labels,
                parents=parents,
                values=values,
                branchvalues="total",
                sort=False,
                marker=dict(colors=colors, line=dict(color=_BACKGROUND_COLOR, width=1.2)),
                textinfo="label+value",
                textfont=dict(color=_TEXT_COLOR, size=12),
                hovertemplate=(
                    "<b>%{label}</b>"
                    "<br>Root project: %{customdata[0]}"
                    "<br>Total completed in range: %{value}"
                    "<br>Completed directly here: %{customdata[1]}"
                    "<br>Hierarchy depth: %{customdata[2]}"
                    "<br>Hidden projects folded in: %{customdata[3]}"
                    "<extra></extra>"
                ),
                customdata=customdata,
                tiling=dict(orientation="v", pad=2),
                root_color=_mix_color(_BACKGROUND_COLOR, "#1b2332", 0.1),
                pathbar=dict(visible=False),
                maxdepth=-1,
            )
        ]
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=620,
        margin=dict(l=18, r=18, t=30, b=58),
        paper_bgcolor=_BACKGROUND_COLOR,
        plot_bgcolor=_BACKGROUND_COLOR,
        showlegend=False,
        uniformtext=dict(minsize=10, mode="hide"),
        annotations=[
            dict(
                x=0.99,
                y=0.0,
                xref="paper",
                yref="paper",
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                align="right",
                text=(
                    "Strip area tracks completed tasks. "
                    "Roots and active subprojects are folded into Other only when the "
                    "folded tail stays smaller than the smallest visible sibling."
                ),
                font=dict(size=9, color=_MUTED_TEXT_COLOR),
            )
        ],
        uirevision="active-project-hierarchy-icicle",
    )
    return fig
