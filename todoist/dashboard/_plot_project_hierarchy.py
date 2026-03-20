from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go

from todoist.types import Project

_BACKGROUND_COLOR = "#111318"
_BORDER_COLOR = "rgba(17,19,24,0.9)"
_EMPTY_COLOR = "#7f8b99"


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

    ids: list[str] = []
    labels: list[str] = []
    parents: list[str] = []
    values: list[int] = []
    colors: list[str] = []
    customdata: list[list[Any]] = []

    def add_subtree(project_id: str, *, root_id: str, depth: int) -> None:
        total_completed = subtree_total(project_id)
        if total_completed <= 0:
            return

        project = projects_by_id[project_id]
        project_name = str(project.project_entry.name)
        root_name = str(projects_by_id[root_id].project_entry.name)
        parent_id = project.project_entry.parent_id

        ids.append(project_id)
        labels.append(project_name)
        parents.append("" if project_id == root_id else str(parent_id))
        values.append(total_completed)
        colors.append(project_colors.get(project_name, project_colors.get(root_name, _EMPTY_COLOR)))
        customdata.append(
            [
                int(direct_counts.get(project_id, 0)),
                total_completed,
                depth,
                root_name,
            ]
        )

        for child_id in children_by_parent.get(project_id, []):
            add_subtree(child_id, root_id=root_id, depth=depth + 1)

    for root_id in sorted(
        active_root_ids,
        key=lambda project_id: (-subtree_total(project_id), projects_by_id[project_id].project_entry.name.lower()),
    ):
        add_subtree(root_id, root_id=root_id, depth=0)

    fig = go.Figure(
        data=[
            go.Treemap(
                ids=ids,
                labels=labels,
                parents=parents,
                values=values,
                branchvalues="total",
                marker=dict(
                    colors=colors,
                    line=dict(color=_BORDER_COLOR, width=2),
                ),
                customdata=customdata,
                texttemplate="%{label}<br>%{customdata[1]} completed",
                hovertemplate=(
                    "<b>%{label}</b>"
                    "<br>Root project: %{customdata[3]}"
                    "<br>Total completed in range: %{customdata[1]}"
                    "<br>Completed directly in project: %{customdata[0]}"
                    "<extra></extra>"
                ),
                tiling=dict(pad=5),
                root_color=_BACKGROUND_COLOR,
                pathbar=dict(visible=False),
            )
        ]
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        height=560,
        margin=dict(l=12, r=12, t=12, b=12),
        paper_bgcolor=_BACKGROUND_COLOR,
        plot_bgcolor=_BACKGROUND_COLOR,
    )
    return fig
