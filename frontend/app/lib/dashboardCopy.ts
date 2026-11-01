export const METRIC_HELP: Record<string, string> = {
  Events: `Events
Total task activity (added, completed, rescheduled) in the selected period.

- Delta compares against the previous period of equal length.`,
  "Completed Tasks": `Completed tasks
Total completed tasks in the selected period.

- Delta compares against the previous period of equal length.`,
  "Added Tasks": `Added tasks
Total tasks added in the selected period.

- Delta compares against the previous period of equal length.`,
  "Rescheduled Tasks": `Rescheduled tasks
Total tasks rescheduled in the selected period.

- Lower is better, so the delta is inverted.`,
  "Urgency Status": `Urgency status
Live health check for active tasks.

- Green means no active fire, P1, P2, due-today, or deadline-today tasks.
- Yellow means urgent work exists, but there are no fire tasks.
- Red means at least one active fire task is present.
- Counts are based on active tasks only and due/deadline are compared with today.`,
};

export const DEFAULT_METRIC_HELP = `Metric
Value for the selected period.

- Delta compares against the previous period of equal length.`;

export const INSIGHT_HELP: Record<string, string> = {
  "Most active project": `Most active project
Project with the highest number of completed tasks in the last full week.`,
  "Most rescheduled project": `Most rescheduled project
Project with the most reschedules in the last full week. High values can indicate churn.`,
  "Busiest day": `Busiest day
Day of the week with the most events in the selected range.`,
  "Added vs completed": `Added vs completed
Compares added and completed tasks in the last week.

- Ratio shows throughput (completed / added).`,
  "Peak hour": `Peak hour
Hour of day with the most events in the selected range.`,
};

export const DEFAULT_INSIGHT_HELP = `Insight
Quick highlight computed from recent activity.`;

export const PLOT_HELP = {
  taskCountTrend: `Active task counts by date
Reconstructed daily from cached Todoist activity and today's active tasks, shown for the selected dashboard range on a softened scale. Older events without priority metadata are counted as normal priority, so historical totals are more exact than the priority split.`,
  weeklyCompletionTrend: `Weekly completion trend
Normalized cumulative completion pace by weekday.

- Fixed view: current week + previous 3-week baseline.
- Optional 6w / 12w / 24w baselines can be toggled in the legend.
- Current week hover shows raw cumulative task counts (no forecast).`,
  taskLifespans: `Task Lifespans
Time between task creation and completion. Each completed task counts equally. Use Selected period to include tasks completed in the dashboard date range; All time includes the full recorded history.`,
  completedTasksPeriodically: `Periodically Completed Tasks
Completed tasks per project for each calendar period. Recent weekly points use Todoist Productivity counters (last four weeks); older weeks and monthly views count cached completion events and may differ from Productivity.\n\nOpen circles show actual counts; filled circles and dashed lines show estimates. Forecasts blend the last eight periods (including empty periods) with current pace and never fall below actuals. All projects forecast is the sum of project forecasts.`,
  cumsumCompletedTasksPeriodically: `Cumulative Completed Tasks
Running total of completions per project across the available chart history. Recent weeks use Todoist Productivity counters; older history uses cached completion events. This is not the account lifetime total.`,
  activeProjectHierarchy: `Project Hierarchy
Sunburst view of the busiest active and archived projects and their subprojects.

- Ring area is proportional to completed tasks in the selected range.
- The inner ring shows roots and outer rings show active or archived subprojects.
- Todoist parent links are applied automatically; saved adjustments take priority.
- Smaller long-tail projects are folded into Other only when they stay smaller than the smallest visible sibling.`,
  heatmapEventsByDayHour: `Event Heatmap
Activity intensity by day of week and hour. Darker means more events.`,
  eventsOverTime: `Events Over Time
Timeline of activity events across the selected range.`,
};

export const BADGES_HELP = `Priority badges
Snapshot of current tasks by priority.

- P1 is highest urgency, P4 is lowest.`;

export const SPOTLIGHT_HELP = `Activity spotlight
Top projects by completed tasks in the most recent finished week.

- Subprojects includes nested projects.
- Root projects are top-level only.`;

export const HABIT_TRACKER_LAB_HELP = `Habit Tracker Lab
A focused view for the weekly habit payload.

- About sits first so the page reads like an overview instead of a chart dump.
- The plots section shows the overall completion rate and recent N-week slices.
- The notes section stays focused on how the tracker works instead of repeating the roster.`;

export const SURFACE_STATUS_SUMMARY = `Dashboard, project adjustments, and local data sync.`;
