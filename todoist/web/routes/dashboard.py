# pyright: reportUndefinedVariable=false
"""Dashboard FastAPI routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement

from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter

from todoist.dashboard._plot_task_counts import plot_task_count_trend
from todoist.dashboard._plot_activity import (
    plot_events_over_time,
    plot_heatmap_of_events_by_day_and_hour,
)
from todoist.dashboard._plot_lifespans import plot_task_lifespans
from todoist.dashboard._plot_periodic import (
    cumsum_completed_tasks_periodically,
    plot_completed_tasks_periodically,
)
from todoist.dashboard._plot_project_hierarchy import (
    plot_active_project_hierarchy_sunburst as plot_active_project_hierarchy,
)
from todoist.dashboard._plot_weekly_trend import plot_weekly_completion_trend
from todoist.dashboard._plot_project_lifecycle import build_project_lifecycle_data
from todoist.database.dataframe import (
    get_adjusting_archived_parent_projects,
    get_adjusting_mapping,
)
from todoist.features.activity import load_activity_cache
from todoist.features.habit_tracker import extract_tracked_habit_tasks
from todoist.features.stats import p1_tasks, p2_tasks, p3_tasks, p4_tasks
from todoist.web.dashboard_payload import (
    add_plot_event_markers as _add_plot_event_markers,
    apply_date_axis_viewport as _apply_date_axis_viewport,
    build_habit_tracker_payload as _build_habit_tracker_payload,
    completed_share_leaderboard as _completed_share_leaderboard,
    compute_insights as _compute_insights,
    compute_plot_history_beg as _compute_plot_history_beg,
    extract_metrics_dict as _extract_metrics_dict,
    fig_to_dict as _fig_to_dict,
    last_completed_week_bounds as _last_completed_week_bounds,
    period_bounds as _period_bounds,
    safe_activity_anchor as _safe_activity_anchor,
)

from todoist.web.routes.common import _sync_api_globals

Granularity = Literal["W", "ME", "3ME"]


router = APIRouter()


@router.get("/api/dashboard/hierarchy-playback", tags=["dashboard"])
async def hierarchy_playback(
    weeks: int = 12,
    beg: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Build cumulative hierarchy snapshots on demand for the selected period."""
    _sync_api_globals(globals())
    await _ensure_state(refresh=False)
    activity = _state.df_activity
    active_projects = _state.active_projects
    project_colors = _state.project_colors
    if activity is None or active_projects is None or project_colors is None:
        return {"error": "Dashboard data unavailable.", "frames": []}

    activity = _normalize_activity_df(activity)
    range_beg, range_end = _compute_plot_range(activity, weeks=weeks, beg=beg, end=end)
    mappings = get_adjusting_mapping()
    archived_parents = get_adjusting_archived_parent_projects()
    cache_key = (
        "hierarchy-playback",
        range_beg.isoformat(),
        range_end.isoformat(),
        tuple(sorted(mappings.items())),
        tuple(sorted(archived_parents)),
    )
    cached = _state.home_payload_cache.get(cache_key)
    if cached is not None:
        return cached

    frame_count = min(16, max(1, (range_end.date() - range_beg.date()).days))
    span = range_end - range_beg
    projects = [*active_projects, *(_state.archived_projects or [])]
    frames = []
    for index in range(1, frame_count + 1):
        frame_end = range_beg + span * index / frame_count
        figure = plot_active_project_hierarchy(
            activity,
            range_beg,
            frame_end,
            projects,
            project_colors,
            project_mappings=mappings,
            archived_parent_projects=archived_parents,
        )
        frames.append(
            {
                "date": (frame_end - timedelta(microseconds=1)).date().isoformat(),
                "figure": _fig_to_dict(figure),
            }
        )
    payload = {"frames": frames}
    _state.home_payload_cache[cache_key] = payload
    return payload


@router.get("/api/dashboard/project-timeline", tags=["dashboard"])
async def project_timeline(
    weeks: int = 0,
    beg: str | None = None,
    end: str | None = None,
    refresh: bool = False,
) -> dict[str, object]:
    """Return structured project lifecycle data for the dedicated timeline view."""

    _sync_api_globals(globals())
    await _ensure_state(refresh=refresh)
    activity = _state.df_activity
    active_projects = _state.active_projects
    if activity is None or active_projects is None:
        return {"error": "Dashboard data unavailable.", "range": None, "parents": []}
    activity = _normalize_activity_df(activity)
    if weeks == 0 and beg is None and end is None:
        anchor = _safe_activity_anchor(activity)
        range_end = datetime.combine(
            anchor.date() + timedelta(days=1), datetime.min.time()
        )
        first_event = (
            activity.index.min().to_pydatetime() if not activity.empty else anchor
        )
        range_beg = datetime.combine(first_event.date(), datetime.min.time())
    else:
        range_beg, range_end = _compute_plot_range(
            activity, weeks=weeks, beg=beg, end=end
        )
    payload = build_project_lifecycle_data(
        activity,
        range_beg,
        range_end,
        [*active_projects, *(_state.archived_projects or [])],
    )
    payload["refreshedAt"] = datetime.now().isoformat(timespec="seconds")
    return dict(payload)


@router.get("/api/dashboard/status", tags=["dashboard"])
async def dashboard_status(refresh: bool = False) -> dict[str, Any]:
    _sync_api_globals(globals())
    """
    Lightweight status endpoint for UI badges (does not generate plots).
    """
    # Intentionally ignore refresh: this endpoint must stay non-blocking and avoid Todoist API calls.
    _ = refresh
    return {
        "services": _service_statuses(),
        "configurableItems": [],
        "apiCache": {
            "lastRefresh": datetime.fromtimestamp(_state.last_refresh_s).isoformat(
                timespec="seconds"
            )
            if _state.last_refresh_s
            else None
        },
        "activityCache": _stat_file(_cache_runtime_path("activity.joblib")),
        "now": datetime.now().isoformat(timespec="seconds"),
    }


@router.get("/api/dashboard/progress", tags=["dashboard"])
async def dashboard_progress() -> dict[str, Any]:
    _sync_api_globals(globals())
    """Return current data refresh progress for the dashboard."""

    return await _progress_snapshot()


@router.get("/api/dashboard/home", tags=["dashboard"])
async def dashboard_home(
    granularity: Granularity = "W",
    weeks: int = 12,
    beg: str | None = None,
    end: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    _sync_api_globals(globals())
    """
    Home dashboard payload: metrics, badges, and Plotly figures.

    Notes:
    - `weeks` controls the date range used for time-series plots (default ~12 weeks).
    - `beg`/`end` (YYYY-MM-DD) override `weeks` when provided.
    - `granularity` controls periodic aggregation where applicable.
    - `refresh=true` forces a Todoist API pull + activity reload (otherwise cached state is reused).
    """
    await _ensure_state(refresh=refresh)

    df_activity = _state.df_activity
    active_projects = _state.active_projects
    archived_projects = _state.archived_projects or []
    project_colors = _state.project_colors

    if df_activity is None or active_projects is None or project_colors is None:
        return {
            "error": "Dashboard data unavailable. Please ensure the database is configured and accessible."
        }

    df_activity = _normalize_activity_df(df_activity)
    dashboard_settings_cfg = _read_yaml_config(_DASHBOARD_CONFIG_PATH, required=False)
    dashboard_settings = _dashboard_settings_payload(dashboard_settings_cfg)

    no_data = df_activity.empty
    beg_range, end_range = _compute_plot_range(
        df_activity, weeks=weeks, beg=beg, end=end
    )
    history_beg_range = _compute_plot_history_beg(df_activity, end=end_range)
    beg_label = beg if beg is not None else beg_range.strftime("%Y-%m-%d")
    end_label = end if end is not None else end_range.strftime("%Y-%m-%d")

    periods = _period_bounds(df_activity, granularity)
    metrics = _extract_metrics_dict(df_activity, periods)
    today = datetime.now().date()
    urgency_status = _evaluate_urgency_status(
        active_projects,
        today=today,
        settings=dashboard_settings_cfg.get("urgency")
        if hasattr(dashboard_settings_cfg, "get")
        else None,
    )
    plot_events = _normalize_plot_events(dashboard_settings_cfg)
    always_visible_projects = get_adjusting_archived_parent_projects()
    project_mappings = get_adjusting_mapping()
    archived_plot_projects = {
        project.project_entry.name for project in archived_projects
    } - {project.project_entry.name for project in active_projects}

    p1 = sum(map(p1_tasks, active_projects))
    p2 = sum(map(p2_tasks, active_projects))
    p3 = sum(map(p3_tasks, active_projects))
    p4 = sum(map(p4_tasks, active_projects))

    cache_key = (
        "home",
        f"g={granularity}",
        f"beg={beg_label}",
        f"end={end_label}",
        f"no_data={int(no_data)}",
        f"today={today.isoformat()}",
        f"always_visible_projects={','.join(sorted(always_visible_projects))}",
        f"plot_events={len(plot_events)}:{','.join(item['date'] + '=' + item['label'] + '=' + item['color'] for item in plot_events)}",
    )
    cached = _state.home_payload_cache.get(cache_key)
    if cached and not refresh:
        return {
            **cached,
            "refreshWarning": _state.last_refresh_error,
            "refreshing": _state.refresh_task is not None
            and not _state.refresh_task.done(),
        }

    anchor_dt = _safe_activity_anchor(df_activity)
    last_week_beg, last_week_end, last_week_label = _last_completed_week_bounds(
        anchor_dt
    )
    tracked_habit_tasks = extract_tracked_habit_tasks(active_projects)
    habit_tracker = _build_habit_tracker_payload(
        df_activity,
        tracked_habit_tasks,
        anchor=anchor_dt,
        project_colors=project_colors,
    )

    if no_data:
        figures = {}
        project_timeline_summary = {"parentCount": 0, "subprojectCount": 0}
        parent_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
        root_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
    else:
        lifecycle_data = build_project_lifecycle_data(
            df_activity,
            beg_range,
            end_range,
            [*active_projects, *archived_projects],
        )
        lifecycle_parents = lifecycle_data["parents"]
        project_timeline_summary = {
            "parentCount": len(lifecycle_parents),
            "subprojectCount": sum(
                len(parent["children"]) for parent in lifecycle_parents
            ),
        }
        weekly_completion_fig = plot_weekly_completion_trend(df_activity, end_range)
        completed_periodic_fig = _apply_date_axis_viewport(
            _add_plot_event_markers(
                plot_completed_tasks_periodically(
                    df_activity,
                    history_beg_range,
                    end_range,
                    granularity,
                    project_colors,
                    visibility_beg_date=beg_range,
                    visibility_end_date=end_range,
                    always_visible_projects=always_visible_projects,
                    bounds_are_utc=beg is None,
                    archived_project_names=archived_plot_projects,
                ),
                plot_events,
                beg=history_beg_range,
                end=end_range,
            ),
            beg=beg_range,
            end=end_range,
        )
        cumsum_completed_fig = _apply_date_axis_viewport(
            _add_plot_event_markers(
                cumsum_completed_tasks_periodically(
                    df_activity,
                    history_beg_range,
                    end_range,
                    granularity,
                    project_colors,
                    visibility_beg_date=beg_range,
                    visibility_end_date=end_range,
                    always_visible_projects=always_visible_projects,
                    bounds_are_utc=beg is None,
                    archived_project_names=archived_plot_projects,
                ),
                plot_events,
                beg=history_beg_range,
                end=end_range,
            ),
            beg=beg_range,
            end=end_range,
        )
        events_over_time_fig = _apply_date_axis_viewport(
            plot_events_over_time(
                df_activity, history_beg_range, end_range, granularity
            ),
            beg=beg_range,
            end=end_range,
        )
        task_count_trend_fig = _apply_date_axis_viewport(
            plot_task_count_trend(
                active_projects,
                load_activity_cache(),
                today=today,
            ),
            beg=beg_range,
            end=end_range,
        )
        figures = {
            "weeklyCompletionTrend": _fig_to_dict(weekly_completion_fig),
            "taskCountTrend": _fig_to_dict(task_count_trend_fig),
            "taskLifespans": _fig_to_dict(plot_task_lifespans(df_activity)),
            "taskLifespansPeriod": _fig_to_dict(
                plot_task_lifespans(df_activity, beg_range, end_range)
            ),
            "completedTasksPeriodically": _fig_to_dict(completed_periodic_fig),
            "cumsumCompletedTasksPeriodically": _fig_to_dict(cumsum_completed_fig),
            "heatmapEventsByDayHour": _fig_to_dict(
                plot_heatmap_of_events_by_day_and_hour(
                    df_activity, beg_range, end_range
                )
            ),
            "eventsOverTime": _fig_to_dict(events_over_time_fig),
            "activeProjectHierarchy": _fig_to_dict(
                plot_active_project_hierarchy(
                    df_activity,
                    beg_range,
                    end_range,
                    [*active_projects, *archived_projects],
                    project_colors,
                    project_mappings=project_mappings,
                    archived_parent_projects=always_visible_projects,
                )
            ),
        }
        parent_completed_share = _completed_share_leaderboard(
            df_activity,
            beg=last_week_beg,
            end=last_week_end,
            column="parent_project_name",
            project_colors=project_colors,
        )
        root_completed_share = _completed_share_leaderboard(
            df_activity,
            beg=last_week_beg,
            end=last_week_end,
            column="root_project_name",
            project_colors=project_colors,
        )

    payload = {
        "noData": no_data,
        "range": {
            "beg": beg_label,
            "end": end_label,
            "granularity": granularity,
            "weeks": weeks,
        },
        "metrics": {
            "items": metrics,
            "currentPeriod": periods["currentLabel"],
            "previousPeriod": periods["previousLabel"],
        },
        "urgencyStatus": urgency_status,
        "refreshWarning": _state.last_refresh_error,
        "refreshing": _state.refresh_task is not None
        and not _state.refresh_task.done(),
        "configurableItems": [
            {
                "key": "urgency",
                "label": "Urgency watch badge",
                "icon": "wrench",
                "configPath": dashboard_settings["configPath"],
                "anchor": "dashboard-settings",
                "summary": (
                    f"Priority thresholds {dashboard_settings['warnPriorityThresholds']}; "
                    f"due within {dashboard_settings['warnDueWithinDays']} days; "
                    f"deadline within {dashboard_settings['warnDeadlineWithinDays']} days."
                ),
            },
            {
                "key": "plot-events",
                "label": "Plot event markers",
                "icon": "wrench",
                "configPath": dashboard_settings["configPath"],
                "anchor": "dashboard-settings",
                "summary": f"{len(plot_events)} annotated event markers configured.",
            },
        ],
        "badges": {"p1": p1, "p2": p2, "p3": p3, "p4": p4},
        "habitTracker": habit_tracker,
        "insights": {
            "label": last_week_label,
            "items": []
            if no_data
            else _compute_insights(
                df_activity,
                beg=last_week_beg,
                end=last_week_end,
                project_colors=project_colors,
            ),
        },
        "leaderboards": {
            "lastCompletedWeek": {
                "label": last_week_label,
                "beg": last_week_beg.strftime("%Y-%m-%d"),
                "end": (last_week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
                "parentProjects": parent_completed_share,
                "rootProjects": root_completed_share,
            }
        },
        "figures": figures,
        "projectTimelineSummary": project_timeline_summary,
        "refreshedAt": datetime.now().isoformat(timespec="seconds"),
    }
    _state.home_payload_cache[cache_key] = payload
    return payload
