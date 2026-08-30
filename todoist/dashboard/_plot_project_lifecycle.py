from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go

from todoist.core.types import Project


@dataclass(frozen=True)
class _Span:
    parent: str
    project: str
    start: pd.Timestamp
    end: pd.Timestamp
    actual_start: pd.Timestamp
    status: str
    completions: int
    open_tasks: int


_STATUS = {
    "completed": ("Completed / archived", "#6fe3a1"),
    "ongoing": ("Ongoing", "#63b8ea"),
    "stalled": ("No completion in period", "#e7ad58"),
}


def plot_project_lifecycle_timeline(
    activity: pd.DataFrame,
    beg: datetime,
    end: datetime,
    projects: list[Project],
) -> go.Figure:
    window_start, window_end = _timestamp(beg), _timestamp(end)
    if window_start is None or window_end is None or window_start >= window_end:
        return _empty("Select a valid period.")

    frame = activity.copy()
    frame.index = pd.to_datetime(frame.index, errors="coerce", utc=True).tz_localize(
        None
    )
    frame = frame.loc[~frame.index.isna()]
    event_column = "event_type" if "event_type" in frame else "type"
    spans = _spans(frame, event_column, projects, window_start, window_end)
    if not spans:
        return _empty("No subproject spans overlap this period.")

    parents = sorted(
        {span.parent for span in spans},
        key=lambda parent: sum(
            span.completions for span in spans if span.parent == parent
        ),
        reverse=True,
    )
    positioned = _positions(spans, parents)
    figure = go.Figure()
    for status, (label, color) in _STATUS.items():
        matching = [(span, y) for span, y in positioned if span.status == status]
        if not matching:
            continue
        figure.add_trace(
            go.Scatter(
                x=[
                    value
                    for span, _ in matching
                    for value in (span.start, span.end, None)
                ],
                y=[value for _, y in matching for value in (y, y, None)],
                mode="lines+markers",
                name=label,
                line={"color": color, "width": 11},
                marker={"color": color, "size": 8},
                customdata=[
                    value
                    for span, _ in matching
                    for value in (
                        _details(span),
                        _details(span),
                        [None, None, None, None, None],
                    )
                ],
                hovertemplate=(
                    "<b>%{customdata[1]}</b><br>Parent: %{customdata[0]}<br>"
                    "Started: %{customdata[2]}<br>Completed in period: %{customdata[3]}<br>"
                    "Open tasks: %{customdata[4]}<extra></extra>"
                ),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[span.start + (span.end - span.start) / 2 for span, _ in matching],
                y=[y for _, y in matching],
                mode="text",
                text=[_short(span.project) for span, _ in matching],
                textfont={"color": "#091018", "size": 10},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    figure.update_layout(
        template="plotly_dark",
        height=max(430, 100 * len(parents) + 150),
        margin={"l": 26, "r": 26, "t": 28, "b": 54},
        paper_bgcolor="#111318",
        plot_bgcolor="#111318",
        hovermode="closest",
        legend={"orientation": "h", "x": 0, "y": 1.03, "yanchor": "bottom"},
        xaxis={
            "title": "Subproject spans within the selected period",
            "type": "date",
            "range": [window_start.isoformat(), window_end.isoformat()],
            "gridcolor": "rgba(255,255,255,0.08)",
            "zeroline": False,
        },
        yaxis={
            "title": "Active parent project",
            "tickmode": "array",
            "tickvals": list(range(len(parents))),
            "ticktext": parents,
            "range": [len(parents) - 0.4, -0.6],
            "automargin": True,
            "showgrid": True,
            "gridcolor": "rgba(255,255,255,0.06)",
        },
    )
    return figure


def _spans(
    frame: pd.DataFrame,
    event_column: str,
    projects: list[Project],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[_Span]:
    by_id = {str(project.id): project for project in projects}
    active_roots = {
        str(project.id): project.project_entry.name
        for project in projects
        if not project.is_archived and not _parent_id(project)
    }
    candidates: list[tuple[int, _Span]] = []
    for project in projects:
        root_id = _root_id(project, by_id)
        if root_id not in active_roots or str(project.id) == root_id:
            continue
        project_frame = _project_activity(frame, str(project.id))
        recent = project_frame.loc[
            (project_frame.index >= window_start) & (project_frame.index < window_end)
        ]
        created = _timestamp(project.project_entry.created_at) or _edge(
            project_frame, False
        )
        if created is None:
            continue
        updated = _timestamp(project.project_entry.updated_at)
        last_event = _edge(project_frame, True)
        completed = (
            recent.loc[recent[event_column] == "completed"]
            if event_column in recent
            else recent.iloc[0:0]
        )
        open_tasks = sum(
            not task.task_entry.checked and not task.task_entry.is_deleted
            for task in project.tasks
        )
        relevant = (
            not recent.empty
            or open_tasks > 0
            or (updated is not None and window_start <= updated < window_end)
        )
        if not relevant:
            continue
        if project.is_archived:
            known_edges = [
                value for value in (created, updated, last_event) if value is not None
            ]
            endpoint = max(known_edges)
            status = "completed"
        else:
            endpoint = window_end - timedelta(microseconds=1)
            status = "ongoing" if not completed.empty else "stalled"
        if endpoint < window_start or created >= window_end:
            continue
        span = _Span(
            parent=active_roots[root_id],
            project=project.project_entry.name,
            start=max(created, window_start),
            end=min(endpoint, window_end),
            actual_start=created,
            status=status,
            completions=len(completed),
            open_tasks=open_tasks,
        )
        candidates.append((len(recent) * 3 + len(completed) * 2 + open_tasks, span))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [span for _, span in candidates[:28]]


def _positions(spans: list[_Span], parents: list[str]) -> list[tuple[_Span, float]]:
    result: list[tuple[_Span, float]] = []
    for parent_index, parent in enumerate(parents):
        group = [span for span in spans if span.parent == parent][:7]
        middle = (len(group) - 1) / 2
        result.extend(
            (span, parent_index + (index - middle) * 0.1)
            for index, span in enumerate(group)
        )
    return result


def _parent_id(project: Project) -> str | None:
    value = project.project_entry.parent_id or project.project_entry.v2_parent_id
    return str(value) if value else None


def _root_id(project: Project, by_id: dict[str, Project]) -> str:
    current = str(project.id)
    visited: set[str] = set()
    while current in by_id and current not in visited:
        visited.add(current)
        parent = _parent_id(by_id[current])
        if not parent:
            return current
        current = parent
    return current


def _project_activity(frame: pd.DataFrame, project_id: str) -> pd.DataFrame:
    if "parent_project_id" not in frame:
        return frame.iloc[0:0]
    return frame.loc[frame["parent_project_id"].fillna("").astype(str) == project_id]


def _timestamp(value: str | datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, pd.Timestamp):
        return None
    return parsed.tz_convert(None) if parsed.tzinfo else parsed


def _edge(frame: pd.DataFrame, last: bool) -> pd.Timestamp | None:
    values = [
        parsed
        for value in frame.index
        if (parsed := _timestamp(str(value))) is not None
    ]
    return (max(values) if last else min(values)) if values else None


def _short(value: str, limit: int = 24) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _details(span: _Span) -> list[str | int]:
    return [
        span.parent,
        span.project,
        span.actual_start.strftime("%d %b %Y"),
        span.completions,
        span.open_tasks,
    ]


def _empty(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False
    )
    figure.update_layout(template="plotly_dark", height=430)
    return figure
