from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, NotRequired, TypedDict, cast

import pandas as pd

from todometry.core.completions import effective_completion_mask

from todometry.core.types import Project


class ProjectLifecycleChild(TypedDict):
    id: str
    name: str
    status: Literal["completed", "ongoing", "unresolved", "inactive"]
    startDate: str
    endDate: str | None
    visualStart: str
    visualEnd: str
    completionDate: str | None
    archiveDate: str | None
    archived: bool
    durationDays: int
    completions: int
    completionWeeks: list[str]
    openTasks: int


class ProjectLifecycleParent(TypedDict):
    id: str
    name: str
    children: list[ProjectLifecycleChild]
    standalone: NotRequired[bool]


class ProjectLifecycleRange(TypedDict):
    start: str
    end: str


class ProjectLifecycleHistory(TypedDict):
    activityStart: str | None
    activityEnd: str | None
    activeProjects: int
    archivedProjects: int
    archivedProjectsInView: int


class ProjectLifecycleData(TypedDict):
    range: ProjectLifecycleRange | None
    parents: list[ProjectLifecycleParent]
    history: ProjectLifecycleHistory
    refreshedAt: NotRequired[str]


@dataclass(frozen=True)
class _Span:
    parent_id: str
    project_id: str
    parent: str
    project: str
    start: pd.Timestamp
    end: pd.Timestamp
    actual_start: pd.Timestamp
    actual_end: pd.Timestamp
    status: Literal["completed", "ongoing", "stalled", "inactive"]
    completions: int
    completion_weeks: tuple[pd.Timestamp, ...]
    open_tasks: int
    archived: bool


_ARCHIVED_ROOTS_ID = "archived-root-projects"
_ARCHIVED_ROOTS_NAME = "Archived root projects"




def build_project_lifecycle_data(
    activity: pd.DataFrame,
    beg: datetime,
    end: datetime,
    projects: list[Project],
) -> ProjectLifecycleData:
    """Return semantic lifecycle rows for the native project-timeline UI."""

    window_start, window_end = _timestamp(beg), _timestamp(end)
    if window_start is None or window_end is None or window_start >= window_end:
        return {
            "range": None,
            "parents": [],
            "history": _history_payload(activity, projects, []),
        }

    spans = _lifecycle_spans(activity, projects, window_start, window_end)
    grouped: defaultdict[str, list[_Span]] = defaultdict(list)
    for span in spans:
        grouped[span.parent_id].append(span)

    parents: list[ProjectLifecycleParent] = []
    archived_roots = grouped.pop(_ARCHIVED_ROOTS_ID, [])
    for parent_id, children in sorted(
        grouped.items(),
        key=lambda item: (
            -sum(child.completions for child in item[1]),
            item[1][0].parent.casefold(),
            item[0],
        ),
    ):
        first = children[0]
        parents.append(
            {
                "id": parent_id,
                "name": first.parent,
                "children": [_span_payload(span) for span in children],
            }
        )

    for span in sorted(
        archived_roots,
        key=lambda item: (item.actual_end, item.project.casefold()),
        reverse=True,
    ):
        parents.append(
            {
                "id": f"archived-root:{span.project_id}",
                "name": span.project,
                "children": [_span_payload(span)],
                "standalone": True,
            }
        )

    return {
        "range": {
            "start": window_start.date().isoformat(),
            "end": (window_end - timedelta(microseconds=1)).date().isoformat(),
        },
        "parents": parents,
        "history": _history_payload(activity, projects, spans),
    }


def _lifecycle_spans(
    activity: pd.DataFrame,
    projects: list[Project],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[_Span]:
    frame = activity.copy()
    frame.index = pd.to_datetime(frame.index, errors="coerce", utc=True).tz_localize(
        None
    )
    frame = frame.loc[~frame.index.isna()]
    event_column = "event_type" if "event_type" in frame else "type"
    return _spans(frame, event_column, projects, window_start, window_end)




def _spans(
    frame: pd.DataFrame,
    event_column: str,
    projects: list[Project],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[_Span]:
    by_id = {str(project.id): project for project in projects}
    active_roots = {
        str(project.id): project
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
        project_frame = activity_by_project.get(str(project.id))
        if project_frame is None:
            project_frame = frame.head(0)
        root_id = _activity_root_id(project_frame, by_id) or _root_id(project, by_id)
        project_id = str(project.id)
        if root_id in active_roots and project_id == root_id:
            continue
        if root_id in by_id and root_id != project_id:
            parent_id = root_id
            parent_name = by_id[root_id].project_entry.name
        elif project.is_archived:
            parent_id = _ARCHIVED_ROOTS_ID
            parent_name = _ARCHIVED_ROOTS_NAME
        else:
            continue
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
            int(effective_completion_mask(recent, event_column).sum())
            if event_column in recent
            else 0
        )
        completion_weeks: tuple[pd.Timestamp, ...] = ()
        if event_column in recent and completions:
            completed_dates = (
                _timestamp(str(value))
                for value in recent.index[
                    effective_completion_mask(recent, event_column)
                ]
            )
            completion_weeks = tuple(
                sorted(
                    {
                        cast(
                            pd.Timestamp,
                            pd.Timestamp(day.date() - timedelta(days=day.weekday())),
                        )
                        for day in completed_dates
                        if day is not None
                    }
                )
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
            if completions:
                status = "ongoing"
            elif not recent.empty or open_tasks:
                status = "stalled"
            else:
                status = "inactive"
        if endpoint < window_start or created >= window_end:
            continue
        candidates.append(
            (
                len(recent) * 3 + completions * 2 + open_tasks,
                _Span(
                    parent_id,
                    project_id,
                    parent_name,
                    project.project_entry.name,
                    max(created, window_start),
                    min(endpoint, window_end),
                    created,
                    endpoint,
                    status,
                    completions,
                    completion_weeks,
                    open_tasks,
                    project.is_archived,
                ),
            )
        )
    candidates.sort(key=lambda item: (-item[0], item[1].project.casefold()))
    return [span for _, span in candidates]


def _activity_root_id(
    project_frame: pd.DataFrame,
    projects_by_id: dict[str, Project],
) -> str | None:
    """Recover hierarchy flattened by Todoist's archived-project endpoint.

    Archived project records can lose their ``parent_id``. Historical activity still
    carries the original root id/name, so prefer that evidence when it identifies a
    currently active parent project.
    """

    if project_frame.empty:
        return None
    if "root_project_id" in project_frame:
        root_ids = project_frame["root_project_id"].dropna().astype(str)
        if not root_ids.empty:
            for root_id in root_ids.value_counts().index:
                if root_id in projects_by_id:
                    return root_id
    if "root_project_name" not in project_frame:
        return None
    root_names = project_frame["root_project_name"].dropna().astype(str)
    if root_names.empty:
        return None
    roots_by_name: defaultdict[str, list[str]] = defaultdict(list)
    for root_id, root in projects_by_id.items():
        roots_by_name[root.project_entry.name].append(root_id)
    for root_name_value in root_names.value_counts().index:
        root_name = str(root_name_value)
        matching = roots_by_name[root_name]
        if len(matching) == 1:
            return matching[0]
    return None


def _history_payload(
    activity: pd.DataFrame,
    projects: list[Project],
    spans: list[_Span],
) -> ProjectLifecycleHistory:
    timestamps = pd.to_datetime(activity.index, errors="coerce", utc=True)
    timestamps = timestamps[~timestamps.isna()]
    activity_start = _timestamp(str(timestamps.min())) if len(timestamps) else None
    activity_end = _timestamp(str(timestamps.max())) if len(timestamps) else None
    return {
        "activityStart": activity_start.date().isoformat()
        if activity_start is not None
        else None,
        "activityEnd": activity_end.date().isoformat()
        if activity_end is not None
        else None,
        "activeProjects": sum(not project.is_archived for project in projects),
        "archivedProjects": sum(project.is_archived for project in projects),
        "archivedProjectsInView": sum(span.archived for span in spans),
    }


def _span_payload(span: _Span) -> ProjectLifecycleChild:
    duration = max(1, (span.actual_end.date() - span.actual_start.date()).days + 1)
    return {
        "id": span.project_id,
        "name": span.project,
        "status": "unresolved" if span.status == "stalled" else span.status,
        "startDate": span.actual_start.date().isoformat(),
        "endDate": span.actual_end.date().isoformat()
        if span.status == "completed"
        else None,
        "visualStart": span.start.date().isoformat(),
        "visualEnd": span.end.date().isoformat(),
        "completionDate": span.actual_end.date().isoformat()
        if span.status == "completed"
        else None,
        "archiveDate": span.actual_end.date().isoformat() if span.archived else None,
        "archived": span.archived,
        "durationDays": duration,
        "completions": span.completions,
        "completionWeeks": [week.date().isoformat() for week in span.completion_weeks],
        "openTasks": span.open_tasks,
    }




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






