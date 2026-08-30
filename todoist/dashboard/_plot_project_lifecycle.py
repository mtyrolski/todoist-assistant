from collections import defaultdict
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
    actual_end: pd.Timestamp
    status: str
    completions: int
    open_tasks: int
    archived: bool


_STATUS = {
    "completed": ("Completed / archived", "#61f4b3"),
    "ongoing": ("Ongoing", "#6ae3ff"),
    "stalled": ("No completion in period", "#ffb86c"),
}
_HOVER = (
    "<b>%{customdata[1]}</b><br>Parent: %{customdata[0]}<br>"
    "Status: %{customdata[2]}<br>Start: %{customdata[3]}<br>"
    "End: %{customdata[4]}<br>Duration: %{customdata[5]}<br>"
    "Completions: %{customdata[6]}<br>Open tasks: %{customdata[7]}<br>"
    "Archived: %{customdata[8]}<extra></extra>"
)


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

    grouped: defaultdict[str, list[_Span]] = defaultdict(list)
    for span in spans:
        grouped[span.parent].append(span)
    groups = sorted(
        grouped.items(),
        key=lambda item: (-sum(s.completions for s in item[1]), item[0].casefold()),
    )
    positioned, ticks, tick_labels = _positions(groups)
    figure = go.Figure()
    for status, (label, color) in _STATUS.items():
        matching = [(span, y) for span, y in positioned if span.status == status]
        if matching:
            figure.add_trace(_trace(matching, label, color))

    figure.update_layout(
        template="plotly_dark",
        height=max(340, 86 * len(groups) + 32 * len(spans) + 105),
        margin={"l": 210, "r": 28, "t": 62, "b": 48},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel={"bgcolor": "#151922", "bordercolor": "rgba(255,255,255,.16)"},
        legend={"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"},
        xaxis={
            "type": "date",
            "range": [window_start.isoformat(), window_end.isoformat()],
            "gridcolor": "rgba(255,255,255,0.08)",
            "tickformat": "%b %-d",
            "nticks": 9,
            "zeroline": False,
        },
        yaxis={
            "tickmode": "array",
            "tickvals": ticks,
            "ticktext": tick_labels,
            "range": [max(ticks) + 0.7, min(ticks) - 0.7],
            "automargin": True,
            "showgrid": False,
            "zeroline": False,
        },
    )
    return figure


def _trace(matching: list[tuple[_Span, float]], label: str, color: str) -> go.Bar:
    return go.Bar(
        x=[
            max((span.end - span.start).total_seconds(), 21_600) * 1000
            for span, _ in matching
        ],
        base=[span.start for span, _ in matching],
        y=[y for _, y in matching],
        customdata=[_details(span) for span, _ in matching],
        name=label,
        orientation="h",
        width=0.42,
        marker={"color": color},
        hovertemplate=_HOVER,
    )


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
    activity_by_project: dict[str, pd.DataFrame] = {}
    if "parent_project_id" in frame:
        for project_id, group in frame.groupby(
            frame["parent_project_id"].fillna("").astype(str), sort=False
        ):
            activity_by_project[str(project_id)] = group
    candidates: list[tuple[int, _Span]] = []
    for project in projects:
        root_id = _root_id(project, by_id)
        if root_id not in active_roots or str(project.id) == root_id:
            continue
        project_frame = activity_by_project.get(str(project.id))
        if project_frame is None:
            project_frame = frame.head(0)
        recent = project_frame.loc[
            (project_frame.index >= window_start) & (project_frame.index < window_end)
        ]
        created = _timestamp(project.project_entry.created_at)
        if created is None and not project_frame.empty:
            created = _timestamp(str(project_frame.index.min()))
        if created is None:
            continue
        updated = _timestamp(project.project_entry.updated_at)
        last_event = (
            None if project_frame.empty else _timestamp(str(project_frame.index.max()))
        )
        completions = (
            int(recent[event_column].eq("completed").sum())
            if event_column in recent
            else 0
        )
        open_tasks = sum(
            not task.task_entry.checked and not task.task_entry.is_deleted
            for task in project.tasks
        )
        if (
            recent.empty
            and not open_tasks
            and not (updated is not None and window_start <= updated < window_end)
        ):
            continue
        if project.is_archived:
            endpoint = max(
                created,
                updated if updated is not None else created,
                last_event if last_event is not None else created,
            )
            status = "completed"
        else:
            endpoint = window_end - timedelta(microseconds=1)
            status = "ongoing" if completions else "stalled"
        if endpoint < window_start or created >= window_end:
            continue
        candidates.append(
            (
                len(recent) * 3 + completions * 2 + open_tasks,
                _Span(
                    active_roots[root_id],
                    project.project_entry.name,
                    max(created, window_start),
                    min(endpoint, window_end),
                    created,
                    endpoint,
                    status,
                    completions,
                    open_tasks,
                    project.is_archived,
                ),
            )
        )
    candidates.sort(key=lambda item: (-item[0], item[1].project.casefold()))
    return [span for _, span in candidates]


def _positions(
    groups: list[tuple[str, list[_Span]]],
) -> tuple[list[tuple[_Span, float]], list[float], list[str]]:
    positioned: list[tuple[_Span, float]] = []
    ticks: list[float] = []
    labels: list[str] = []
    cursor = 0.0
    for parent, children in groups:
        ticks.append(cursor)
        labels.append(f"<b>{_short(parent, 32)}</b>")
        for span in children:
            cursor += 1.0
            positioned.append((span, cursor))
            ticks.append(cursor)
            labels.append(f"  {_short(span.project, 34)}")
        cursor += 0.9
    return positioned, ticks, labels


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


def _short(value: str, limit: int = 24) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _details(span: _Span) -> list[str | int]:
    return [
        span.parent,
        span.project,
        _STATUS[span.status][0],
        span.actual_start.strftime("%d %b %Y"),
        span.actual_end.strftime("%d %b %Y"),
        f"{max(1, (span.actual_end - span.actual_start).days)} days",
        span.completions,
        span.open_tasks,
        "Yes" if span.archived else "No",
    ]


def _empty(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False
    )
    figure.update_layout(template="plotly_dark", height=430)
    return figure
