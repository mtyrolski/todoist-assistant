# pyright: reportUndefinedVariable=false
"""Dashboard FastAPI routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter

from todoist.dashboard.plots import (
    cumsum_completed_tasks_periodically,
    plot_active_project_hierarchy,
    plot_completed_tasks_periodically,
    plot_events_over_time,
    plot_heatmap_of_events_by_day_and_hour,
    plot_task_lifespans,
    plot_weekly_completion_trend,
)
from todoist.database.dataframe import get_adjusting_archived_parent_projects
from todoist.habit_tracker import extract_tracked_habit_tasks
from todoist.stats import p1_tasks, p2_tasks, p3_tasks, p4_tasks
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

@router.get("/api/dashboard/status", tags=["dashboard"])
async def dashboard_status(refresh: bool = False) -> dict[str, Any]:
    _sync_api_globals(globals())
    """
    Lightweight status endpoint for UI badges (does not generate plots).
    """
    # Intentionally ignore refresh: this endpoint must stay non-blocking and avoid Todoist API calls.
    _ = refresh
    dashboard_config = load_dashboard_config(_DASHBOARD_CONFIG_PATH)
    observer_settings = observer_settings_payload(dashboard_config, path=_DASHBOARD_CONFIG_PATH)
    return {
        "services": _service_statuses(),
        "configurableItems": [
            {
                "key": "observer",
                "label": "Dashboard observer",
                "icon": "wrench",
                "configPath": observer_settings["configPath"],
                "anchor": "observer-control",
            }
        ],
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

@router.get("/api/dashboard/llm_breakdown", tags=["dashboard"])
async def dashboard_llm_breakdown() -> dict[str, Any]:
    _sync_api_globals(globals())
    """Return AI breakdown queue progress."""

    return _llm_breakdown_snapshot()


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
        settings=dashboard_settings_cfg.get("urgency") if hasattr(dashboard_settings_cfg, "get") else None,
    )
    plot_events = _normalize_plot_events(dashboard_settings_cfg)
    always_visible_projects = get_adjusting_archived_parent_projects()

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
        return cached

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
        parent_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
        root_completed_share = {"items": [], "totalCompleted": 0, "figure": {}}
    else:
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
                ),
                plot_events,
                beg=history_beg_range,
                end=end_range,
            ),
            beg=beg_range,
            end=end_range,
        )
        events_over_time_fig = _apply_date_axis_viewport(
            plot_events_over_time(df_activity, history_beg_range, end_range, granularity),
            beg=beg_range,
            end=end_range,
        )
        figures = {
            "weeklyCompletionTrend": _fig_to_dict(weekly_completion_fig),
            "taskLifespans": _fig_to_dict(plot_task_lifespans(df_activity)),
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
                    active_projects,
                    project_colors,
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
        "refreshedAt": datetime.now().isoformat(timespec="seconds"),
    }
    _state.home_payload_cache[cache_key] = payload
    return payload
