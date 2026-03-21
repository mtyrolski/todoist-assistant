"""Compatibility facade for dashboard plotting helpers."""

from todoist.dashboard._plot_activity import (
    plot_events_over_time,
    plot_heatmap_of_events_by_day_and_hour,
)
from todoist.dashboard._plot_lifespans import plot_task_lifespans
from todoist.dashboard._plot_periodic import (
    cumsum_completed_tasks_periodically,
    plot_completed_tasks_periodically,
)
from todoist.dashboard._plot_project_hierarchy_sunburst import (
    plot_active_project_hierarchy_sunburst,
)
from todoist.dashboard._plot_weekly_trend import plot_weekly_completion_trend

plot_active_project_hierarchy = plot_active_project_hierarchy_sunburst

__all__ = [
    "plot_active_project_hierarchy",
    "plot_active_project_hierarchy_sunburst",
    "cumsum_completed_tasks_periodically",
    "plot_completed_tasks_periodically",
    "plot_events_over_time",
    "plot_heatmap_of_events_by_day_and_hour",
    "plot_task_lifespans",
    "plot_weekly_completion_trend",
]
