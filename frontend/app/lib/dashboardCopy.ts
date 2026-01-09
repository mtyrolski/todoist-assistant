export const METRIC_HELP: Record<string, string> = {
  Events: `**Events**
Total task activity (added, completed, rescheduled) in the selected period.

- Delta compares against the previous period of equal length.`,
  "Completed Tasks": `**Completed tasks**
Total completed tasks in the selected period.

- Delta compares against the previous period of equal length.`,
  "Added Tasks": `**Added tasks**
Total tasks added in the selected period.

- Delta compares against the previous period of equal length.`,
  "Rescheduled Tasks": `**Rescheduled tasks**
Total tasks rescheduled in the selected period.

- Lower is better, so the delta is inverted.`,
};

export const DEFAULT_METRIC_HELP = `**Metric**
Value for the selected period.

- Delta compares against the previous period of equal length.`;

export const INSIGHT_HELP: Record<string, string> = {
  "Most active project": `**Most active project**
Project with the highest number of completed tasks in the last full week.`,
  "Most rescheduled project": `**Most rescheduled project**
Project with the most reschedules in the last full week. High values can indicate churn.`,
  "Busiest day": `**Busiest day**
Day of the week with the most events in the selected range.`,
  "Added vs completed": `**Added vs completed**
Compares added and completed tasks in the last week.

- Ratio shows throughput (completed / added).`,
  "Peak hour": `**Peak hour**
Hour of day with the most events in the selected range.`,
};

export const DEFAULT_INSIGHT_HELP = `**Insight**
Quick highlight computed from recent activity.`;

export const PLOT_HELP = {
  mostPopularLabels: `**Most Popular Labels**
Ranks labels by completed tasks in the selected range.`,
  taskLifespans: `**Task Lifespans**
Distribution of time between task creation and completion.`,
  completedTasksPeriodically: `**Periodically Completed Tasks**
Completed tasks per project for each period in the selected range.`,
  cumsumCompletedTasksPeriodically: `**Cumulative Completed Tasks**
Running total of completions per project across the range.`,
  heatmapEventsByDayHour: `**Event Heatmap**
Activity intensity by day of week and hour. Darker means more events.`,
  eventsOverTime: `**Events Over Time**
Timeline of activity events across the selected range.`,
};

export const BADGES_HELP = `**Priority badges**
Snapshot of current tasks by priority.

- P1 is highest urgency, P4 is lowest.`;

export const SPOTLIGHT_HELP = `**Activity spotlight**
Top projects by completed tasks in the most recent finished week.

- Subprojects includes nested projects.
- Root projects are top-level only.`;
