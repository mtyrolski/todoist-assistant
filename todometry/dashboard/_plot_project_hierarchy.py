from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Callable, cast

import pandas as pd
import plotly.graph_objects as go

from todometry.core.completions import effective_completion_mask
from todometry.core.types import Project
from todometry.dashboard._project_colors import resolve_project_color

_BACKGROUND_COLOR = "#111318"
_TEXT_COLOR = "#e7edf5"
_MUTED_TEXT_COLOR = "#9fb0c2"
_COLOR_FALLBACK = "#7f8b99"


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
    parent_id: str = ""
    is_archived: bool = False
    parent_assignment: str = "Root project"


def _empty_project_hierarchy_figure(
    message: str, *, height: int = 520, font_color: str = "#cfd8e3"
) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16, color=font_color),
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=height,
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


def _project_parent_id(project: Project) -> str | None:
    return project.project_entry.parent_id or project.project_entry.v2_parent_id


def _preferred_project_id_for_name(
    project_name: str, projects_by_id: dict[str, Project]
) -> str | None:
    matches = [
        project
        for project in projects_by_id.values()
        if str(project.project_entry.name) == project_name
    ]
    active_matches = [project for project in matches if not project.is_archived]
    preferred = active_matches or matches
    if len(preferred) != 1:
        return None
    return str(preferred[0].id)


def _would_create_parent_cycle(
    project_id: str,
    parent_id: str,
    effective_parent_by_id: dict[str, str | None],
) -> bool:
    current_id: str | None = parent_id
    visited: set[str] = set()
    while current_id is not None and current_id not in visited:
        if current_id == project_id:
            return True
        visited.add(current_id)
        current_id = effective_parent_by_id.get(current_id)
    return False


def _effective_project_parents(
    projects_by_id: dict[str, Project],
    *,
    project_mappings: dict[str, str] | None = None,
    archived_parent_projects: set[str] | None = None,
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Resolve physical parents, then apply explicit dashboard adjustments."""

    effective_parent_by_id: dict[str, str | None] = {}
    assignment_by_id: dict[str, str] = {}
    for project_id, project in projects_by_id.items():
        parent_id = _project_parent_id(project)
        known_parent_id = (
            str(parent_id)
            if parent_id is not None and str(parent_id) in projects_by_id
            else None
        )
        effective_parent_by_id[project_id] = known_parent_id
        if known_parent_id is None:
            assignment_by_id[project_id] = (
                "Archived root" if project.is_archived else "Root project"
            )
        elif project.is_archived:
            assignment_by_id[project_id] = "Automatic (Todoist hierarchy)"
        else:
            assignment_by_id[project_id] = "Todoist hierarchy"

    archived_parent_projects = archived_parent_projects or set()
    for project_id, project in projects_by_id.items():
        if (
            project.is_archived
            and str(project.project_entry.name) in archived_parent_projects
        ):
            effective_parent_by_id[project_id] = None
            assignment_by_id[project_id] = "Manual parent bucket"

    for source_name, target_name in (project_mappings or {}).items():
        if source_name == target_name or source_name in archived_parent_projects:
            continue
        target_id = _preferred_project_id_for_name(target_name, projects_by_id)
        if target_id is None:
            continue
        for project_id, project in projects_by_id.items():
            if str(project.project_entry.name) != source_name:
                continue
            if project_id == target_id or _would_create_parent_cycle(
                project_id, target_id, effective_parent_by_id
            ):
                continue
            effective_parent_by_id[project_id] = target_id
            assignment_by_id[project_id] = "Manual mapping"

    return effective_parent_by_id, assignment_by_id


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
    if normalized.startswith("rgba(") and normalized.endswith(")"):
        channels = [part.strip() for part in normalized[5:-1].split(",")]
        if len(channels) == 4:
            try:
                return (
                    int(float(channels[0])),
                    int(float(channels[1])),
                    int(float(channels[2])),
                )
            except ValueError:
                pass
    if normalized.startswith("rgb(") and normalized.endswith(")"):
        channels = [part.strip() for part in normalized[4:-1].split(",")]
        if len(channels) == 3:
            try:
                return (
                    int(float(channels[0])),
                    int(float(channels[1])),
                    int(float(channels[2])),
                )
            except ValueError:
                pass
    fallback = _COLOR_FALLBACK
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


def _active_project_tree(
    df_completed: pd.DataFrame,
    active_projects: list[Project],
    *,
    project_mappings: dict[str, str] | None = None,
    archived_parent_projects: set[str] | None = None,
) -> tuple[
    dict[str, Project],
    dict[str, list[str]],
    list[str],
    dict[str, int],
    Callable[[str], int],
    dict[str, str],
]:
    projects_by_id = {str(project.id): project for project in active_projects}
    effective_parent_by_id, assignment_by_id = _effective_project_parents(
        projects_by_id,
        project_mappings=project_mappings,
        archived_parent_projects=archived_parent_projects,
    )
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    root_ids: list[str] = []
    for project in active_projects:
        project_id = str(project.id)
        parent_id = effective_parent_by_id[project_id]
        if parent_id is None:
            root_ids.append(project_id)
            continue
        children_by_parent[parent_id].append(project_id)

    for child_ids in children_by_parent.values():
        child_ids.sort(
            key=lambda project_id: projects_by_id[project_id].project_entry.name.lower()
        )
    root_ids.sort(
        key=lambda project_id: projects_by_id[project_id].project_entry.name.lower()
    )

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
            subtree_total(child_id)
            for child_id in children_by_parent.get(project_id, [])
        )

    return (
        projects_by_id,
        children_by_parent,
        root_ids,
        direct_counts,
        subtree_total,
        assignment_by_id,
    )


_EMPTY_COLOR = "#8ea3ff"
_CENTER_COLOR = "#151a2b"
_PANEL_GLOW = "#71dfff"


def _empty_sunburst_figure(message: str) -> go.Figure:
    return _empty_project_hierarchy_figure(message, height=560, font_color=_TEXT_COLOR)


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
    assignment_by_id: dict[str, str],
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
                is_archived=child_project.is_archived,
                parent_assignment=assignment_by_id[child_id],
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
                    assignment_by_id=assignment_by_id,
                )
            )
    return nodes


def _sunburst_display_label(node: _HierarchyNode) -> str:
    if node.kind == "aggregate":
        return "Other" if node.label == "Other" else _wrap_label(node.label)
    return _wrap_label(node.label)


def _sunburst_display_text(node: _HierarchyNode, project_total: int) -> str:
    label = _sunburst_display_label(node)
    if node.kind == "center":
        return f"{label}<br>{node.total_completed}"
    if node.depth == 1:
        percentage = 100.0 * node.total_completed / max(project_total, 1)
        return f"{label}<br><b>{percentage:.1f}%</b>"
    return f"{label}<br>{node.total_completed}"


def plot_active_project_hierarchy_sunburst(
    df: pd.DataFrame,
    beg_date: datetime,
    end_date: datetime,
    active_projects: list[Project],
    project_colors: dict[str, str],
    *,
    project_mappings: dict[str, str] | None = None,
    archived_parent_projects: set[str] | None = None,
) -> go.Figure:
    empty_message: str | None = None
    if df.empty:
        empty_message = "No activity in the selected range"
    elif not active_projects:
        empty_message = "No projects available"
    elif "type" not in df.columns:
        empty_message = "Activity data is missing project event types"
    if empty_message is not None:
        return _empty_sunburst_figure(empty_message)

    df = _normalize_activity_frame(df)
    df_period = cast(pd.DataFrame, df[(df.index >= beg_date) & (df.index < end_date)])
    df_completed = cast(pd.DataFrame, df_period[effective_completion_mask(df_period)])
    if df_completed.empty:
        return _empty_sunburst_figure("No completed tasks in the selected range")

    (
        projects_by_id,
        children_by_parent,
        root_ids,
        direct_counts,
        subtree_total,
        assignment_by_id,
    ) = _active_project_tree(
        df_completed,
        active_projects,
        project_mappings=project_mappings,
        archived_parent_projects=archived_parent_projects,
    )

    active_root_ids = [
        project_id for project_id in root_ids if subtree_total(project_id) > 0
    ]
    if not active_root_ids:
        return _empty_sunburst_figure("No project completions in the selected range")

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
            color=resolve_project_color(
                projects_by_id[project_id].project_entry.name,
                project_colors,
            ),
            is_archived=projects_by_id[project_id].is_archived,
            parent_assignment=assignment_by_id[project_id],
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
                root_name="Projects",
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
            label="Projects",
            total_completed=sum(node.total_completed for node in visible_roots),
            direct_completed=sum(node.direct_completed for node in visible_roots),
            root_name="Projects",
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
                    assignment_by_id=assignment_by_id,
                )
            )

    ids = [node.node_id for node in all_nodes]
    parents = [node.parent_id for node in all_nodes]
    labels = [_sunburst_display_label(node) for node in all_nodes]
    project_total = all_nodes[0].total_completed
    texts = [_sunburst_display_text(node, project_total) for node in all_nodes]
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
            "Archived" if node.is_archived else "Active",
            node.parent_assignment,
        ]
        for node in all_nodes
    ]

    fig = go.Figure(
        data=[
            go.Sunburst(
                ids=ids,
                labels=labels,
                text=texts,
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
                textinfo="text",
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
                    "<br>Project status: %{customdata[8]}"
                    "<br>Parent assignment: %{customdata[9]}"
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
