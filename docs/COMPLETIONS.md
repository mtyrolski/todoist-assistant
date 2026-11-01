# Completion history

All desktop completion views consume the same DataFrame built from the cached activity log. Counts are never replaced by Todoist Productivity counters or adjusted to force a particular number.

The cache keeps original events, including `completed` and `uncompleted`, and merges by event ID. `todoist/core/completions.py` makes a derived projection before DataFrame creation:

- Events are processed chronologically in UTC, with event ID as a deterministic tie breaker.
- For an ordinary task, each `completed` event enters that task's outstanding completion stack. An `uncompleted` event cancels the latest outstanding completion. An unmatched undo never creates a negative count.
- A cancelled completion disappears from its original day/week/month. If the task is completed again, the later completion counts on its own date.
- Recurring tasks retain each occurrence. A subsequent reset/undo does not remove prior occurrences. Recurrence is recognized from cached `is_recurring`, `due.is_recurring`, or `sub_tasks_reset` metadata.
- Undo events remain in the derived activity data and have their own metric and activity trace, including undo events for recurring tasks.
- The task identity is the event's `object_id`, never its parent task ID. Tasks in missing/deleted projects remain under `(unknown)` instead of disappearing from totals.

The original cache is not rewritten by this projection. Re-running it with the same events produces the same result. A newer undo can revise an older period; that is expected. Counts depend on available history and recurrence metadata. Missing API history cannot be reconstructed from aggregate counters.

Periodic plots use local calendar weeks (Monday–Sunday), months and calendar quarters. UTC timestamps are converted using `TODOIST_TIMEZONE`, falling back to the system zone. Automatic exclusive ranges include the newest cached event. Current-day and final-day markers remain visible until the actual period ends, even when the period's axis label is at midnight.

Forecasts blend an exponentially weighted baseline from up to eight preceding periods with observed pace. Empty periods, including recent idle weeks for individual projects, are included. Early-period pace uses a quarter-period floor; estimates never go below observed completions. A project with no baseline uses its observed pace. Completed periods return their actual count. The total forecast sums project forecasts; archived projects contribute actual current-period completions without extrapolation.

The metric cards currently compare rolling windows of 1/4/12 weeks ending at the latest cached activity; their displayed dates describe that window. The periodic plots use calendar periods, and cumulative plots start at the available chart history. These ranges can legitimately differ; the underlying completion history is shared.
