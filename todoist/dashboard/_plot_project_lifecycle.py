from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt

import pandas as pd
import plotly.graph_objects as go

from todoist.core.types import Project


_MAX_PROJECTS = 16


@dataclass(frozen=True)
class _Lifecycle:
    label: str
    full_label: str
    created_at: pd.Timestamp
    display_start: pd.Timestamp
    display_end: pd.Timestamp
    endpoint_at: pd.Timestamp
    last_completion: pd.Timestamp | None
    completions: int
    active_tasks: int
    is_archived: bool
    starts_before_window: bool


def plot_project_lifecycle_timeline(
    activity: pd.DataFrame,
    beg: datetime,
    end: datetime,
    projects: list[Project],
) -> go.Figure:
    window_start = _timestamp(beg)
    window_end = _timestamp(end)
    if window_start is None or window_end is None or window_start >= window_end:
        return _empty_figure("Select a valid period to inspect project lifecycles.")

    frame = activity.copy()
    frame.index = pd.to_datetime(frame.index, errors="coerce", utc=True).tz_localize(None)
    frame = frame.loc[~frame.index.isna()]
    event_column = "event_type" if "event_type" in frame else "type"
    lifecycles = _lifecycles(
        frame,
        event_column=event_column if event_column in frame else None,
        projects=projects,
        window_start=window_start,
        window_end=window_end,
    )
    if not lifecycles:
        return _empty_figure("No project lifecycles overlap this period.")

    lifecycles = sorted(
        lifecycles,
        key=lambda item: (item.is_archived, item.display_end, item.full_label.lower()),
        reverse=True,
    )
    figure = go.Figure()
    _add_span_trace(figure, lifecycles, archived=False)
    _add_span_trace(figure, lifecycles, archived=True)
    _add_start_trace(figure, lifecycles)
    _add_completion_trace(figure, lifecycles)
    _add_endpoint_trace(figure, lifecycles, archived=False)
    _add_endpoint_trace(figure, lifecycles, archived=True)
    figure.update_layout(
        template="plotly_dark",
        height=max(430, 42 * len(lifecycles) + 150),
        margin={"l": 24, "r": 28, "t": 28, "b": 56},
        paper_bgcolor="#111318",
        plot_bgcolor="#111318",
        barmode="overlay",
        hovermode="closest",
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.04,
            "xanchor": "left",
            "yanchor": "bottom",
        },
        xaxis={
            "title": "Project lifecycle within the selected period",
            "type": "date",
            "range": [window_start.isoformat(), window_end.isoformat()],
            "showgrid": True,
            "gridcolor": "rgba(255,255,255,0.08)",
            "zeroline": False,
        },
        yaxis={
            "title": None,
            "autorange": "reversed",
            "automargin": True,
            "categoryorder": "array",
            "categoryarray": [item.label for item in lifecycles],
            "showgrid": False,
        },
    )
    return figure


def _lifecycles(
    frame: pd.DataFrame,
    *,
    event_column: str | None,
    projects: list[Project],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[_Lifecycle]:
    project_names = {
        str(project.id): project.project_entry.name for project in projects
    }
    project_by_id = {str(project.id): project for project in projects}
    candidates: list[tuple[int, pd.Timestamp, _Lifecycle]] = []

    for project in projects:
        project_id = str(project.id)
        project_activity = _project_activity(frame, project_id)
        recent_activity = project_activity.loc[
            (project_activity.index >= window_start)
            & (project_activity.index < window_end)
        ]
        created_at = _timestamp(project.project_entry.created_at)
        if created_at is None:
            created_at = _index_edge(project_activity, last=False)
        if created_at is None:
            continue

        updated_at = _timestamp(project.project_entry.updated_at)
        last_activity = _index_edge(project_activity, last=True)
        active_tasks = sum(
            not task.task_entry.checked and not task.task_entry.is_deleted
            for task in project.tasks
        )
        relevant = (
            not recent_activity.empty
            or window_start <= created_at < window_end
            or (
                updated_at is not None
                and window_start <= updated_at < window_end
            )
            or (not project.is_archived and active_tasks > 0)
        )
        if not relevant:
            continue

        completed = (
            project_activity.loc[project_activity[event_column] == "completed"]
            if event_column and not project_activity.empty
            else project_activity.iloc[0:0]
        )
        recent_completed = completed.loc[
            (completed.index >= window_start) & (completed.index < window_end)
        ]
        last_completion = _index_edge(recent_completed, last=True)
        if project.is_archived:
            endpoint_candidates: list[pd.Timestamp] = [created_at]
            if updated_at is not None:
                endpoint_candidates.append(updated_at)
            if last_activity is not None:
                endpoint_candidates.append(last_activity)
            endpoint_at = max(endpoint_candidates)
        else:
            endpoint_at = window_end - timedelta(microseconds=1)

        if endpoint_at < window_start or created_at >= window_end:
            continue
        display_start = max(created_at, window_start)
        display_end = min(max(endpoint_at, display_start), window_end)
        full_label = _project_label(project, project_by_id, project_names)
        lifecycle = _Lifecycle(
            label=_shorten(full_label),
            full_label=full_label,
            created_at=created_at,
            display_start=display_start,
            display_end=display_end,
            endpoint_at=endpoint_at,
            last_completion=last_completion,
            completions=int(len(recent_completed)),
            active_tasks=active_tasks,
            is_archived=project.is_archived,
            starts_before_window=created_at < window_start,
        )
        score = len(recent_activity) * 4 + len(recent_completed) * 3 + active_tasks
        freshness_candidates: list[pd.Timestamp] = [created_at]
        if updated_at is not None:
            freshness_candidates.append(updated_at)
        if last_activity is not None:
            freshness_candidates.append(last_activity)
        freshness = max(freshness_candidates)
        candidates.append((score, freshness, lifecycle))

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in candidates[:_MAX_PROJECTS]]


def _project_activity(frame: pd.DataFrame, project_id: str) -> pd.DataFrame:
    if "parent_project_id" not in frame:
        return frame.iloc[0:0]
    return frame.loc[frame["parent_project_id"].fillna("").astype(str) == project_id]


def _project_label(
    project: Project,
    project_by_id: dict[str, Project],
    project_names: dict[str, str],
) -> str:
    parent_id = project.project_entry.parent_id or project.project_entry.v2_parent_id
    if not parent_id:
        return project.project_entry.name
    root_id = str(parent_id)
    visited = {str(project.id)}
    while root_id in project_by_id and root_id not in visited:
        visited.add(root_id)
        parent = project_by_id[root_id]
        next_parent = parent.project_entry.parent_id or parent.project_entry.v2_parent_id
        if not next_parent:
            break
        root_id = str(next_parent)
    root_name = project_names.get(root_id)
    if not root_name or root_name == project.project_entry.name:
        return project.project_entry.name
    return f"{root_name} → {project.project_entry.name}"


def _add_span_trace(
    figure: go.Figure, lifecycles: list[_Lifecycle], *, archived: bool
) -> None:
    matching = [item for item in lifecycles if item.is_archived is archived]
    if not matching:
        return
    figure.add_trace(
        go.Scatter(
            x=[value for item in matching for value in (item.display_start, item.display_end, None)],
            y=[value for item in matching for value in (item.label, item.label, None)],
            mode="lines",
            name="Archived span" if archived else "Open span",
            line={
                "color": "rgba(174,181,195,0.62)" if archived else "rgba(93,205,255,0.74)",
                "width": 9,
            },
            hoverinfo="skip",
        )
    )


def _add_start_trace(figure: go.Figure, lifecycles: list[_Lifecycle]) -> None:
    figure.add_trace(
        go.Scatter(
            x=[item.display_start for item in lifecycles],
            y=[item.label for item in lifecycles],
            mode="markers",
            name="Project start",
            marker={
                "color": "#f0b45c",
                "size": 11,
                "symbol": [
                    "triangle-left" if item.starts_before_window else "diamond"
                    for item in lifecycles
                ],
            },
            customdata=[
                [
                    item.full_label,
                    item.created_at.strftime("%d %b %Y"),
                    "Started before this period" if item.starts_before_window else "Created",
                ]
                for item in lifecycles
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[2]}: "
                "%{customdata[1]}<extra></extra>"
            ),
        )
    )


def _add_completion_trace(figure: go.Figure, lifecycles: list[_Lifecycle]) -> None:
    matching = [item for item in lifecycles if item.last_completion is not None]
    if not matching:
        return
    figure.add_trace(
        go.Scatter(
            x=[item.last_completion for item in matching],
            y=[item.label for item in matching],
            mode="markers",
            name="Last completion",
            marker={
                "color": "#8ce6a7",
                "size": [8 + min(8, sqrt(item.completions) * 1.8) for item in matching],
                "symbol": "circle",
                "line": {"color": "rgba(17,19,24,0.9)", "width": 2},
            },
            customdata=[
                [item.full_label, item.completions, item.active_tasks] for item in matching
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Last completion: %{x|%d %b %Y}<br>"
                "Completed in period: %{customdata[1]}<br>"
                "Open tasks: %{customdata[2]}<extra></extra>"
            ),
        )
    )


def _add_endpoint_trace(
    figure: go.Figure, lifecycles: list[_Lifecycle], *, archived: bool
) -> None:
    matching = [item for item in lifecycles if item.is_archived is archived]
    if not matching:
        return
    figure.add_trace(
        go.Scatter(
            x=[item.display_end for item in matching],
            y=[item.label for item in matching],
            mode="markers",
            name="Archived / last update" if archived else "Open at period end",
            marker={
                "color": "#c2c8d2" if archived else "#5dcdff",
                "size": 12,
                "symbol": "x" if archived else "circle-open",
                "line": {"width": 2},
            },
            customdata=[
                [item.full_label, item.endpoint_at.strftime("%d %b %Y"), item.active_tasks]
                for item in matching
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                + (
                    "Archived; last Todoist update: %{customdata[1]}"
                    if archived
                    else "Open at period end<br>Open tasks: %{customdata[2]}"
                )
                + "<extra></extra>"
            ),
        )
    )


def _timestamp(value: str | datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, pd.Timestamp):
        return None
    if parsed.tzinfo is not None:
        return parsed.tz_convert(None)
    return parsed


def _index_edge(frame: pd.DataFrame, *, last: bool) -> pd.Timestamp | None:
    timestamps = [
        parsed
        for value in frame.index
        if (parsed := _timestamp(str(value))) is not None
    ]
    if not timestamps:
        return None
    return max(timestamps) if last else min(timestamps)


def _shorten(value: str, limit: int = 52) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
    )
    figure.update_layout(
        template="plotly_dark",
        height=430,
        paper_bgcolor="#111318",
        plot_bgcolor="#111318",
    )
    return figure
