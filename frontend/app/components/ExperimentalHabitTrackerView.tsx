"use client";

import { HabitTrackerCard } from "./HabitTrackerCard";
import { HabitTrackerPlots } from "./HabitTrackerPlots";
import { InfoTip } from "./InfoTip";
import { LoadingBar } from "./LoadingBar";
import { PageHeader } from "./PageHeader";
import type { StatusPill } from "./StatusPills";
import { StatusPills } from "./StatusPills";
import { HABIT_TRACKER_LAB_HELP } from "../lib/dashboardCopy";
import { useApiHealth, useDashboardHome } from "../lib/dashboardHooks";

export function ExperimentalHabitTrackerView() {
  const { health, loadingHealth } = useApiHealth();
  const { dashboard, loadingDashboard, dashboardError, retrying, refresh } = useDashboardHome();
  const habitTracker = dashboard?.habitTracker ?? null;

  const statusItems: StatusPill[] = [
    {
      key: "api",
      label: loadingHealth
        ? "API check running"
        : health?.status === "ok"
          ? "API online"
          : "API offline",
      tone: health?.status === "ok" ? "good" : "warn"
    },
    {
      key: "tracked",
      label: habitTracker ? `${habitTracker.trackedCount} habits tracked` : "Waiting for tracker",
      tone: habitTracker?.trackedCount ? "good" : "neutral"
    },
    {
      key: "period",
      label: habitTracker ? `Week ${habitTracker.label}` : "No tracked period yet",
      tone: "neutral" as const
    }
  ];

  return (
    <>
      <LoadingBar active={loadingDashboard} />
      <PageHeader
        eyebrow="Experimental"
        title="Habit Tracker Lab"
        lede="A separate playground for weekly habit stats, custom scorecards, and a few more opinionated dashboard treatments."
      >
        <StatusPills items={statusItems} />
      </PageHeader>

      <section className="card">
        <header className="cardHeader">
          <div className="cardTitleRow">
            <h2>About this lab</h2>
            <InfoTip label="About Habit Tracker Lab" content={HABIT_TRACKER_LAB_HELP} />
          </div>
          <div className="actionRow">
            <button className="button buttonSmall" type="button" onClick={refresh} disabled={loadingDashboard}>
              {loadingDashboard ? "Refreshing..." : retrying ? "Retrying..." : "Refresh lab"}
            </button>
          </div>
        </header>
        <p className="muted" style={{ margin: 0 }}>
          The overview comes first, then a single rate-focused plots section, then a roster and notes that stay readable
          without turning the page into a chart dump.
        </p>
      </section>

      {dashboardError ? (
        <section className="card">
          <p className="muted">{dashboardError}</p>
        </section>
      ) : null}

      <HabitTrackerPlots habitTracker={habitTracker} />

      <section className="grid2">
        <HabitTrackerCard habitTracker={habitTracker} />

        <section className="card">
          <header className="cardHeader">
            <div className="cardTitleRow">
              <h2>Lab notes</h2>
            </div>
          </header>
          <div className="experimentNoteStack">
            <div>
              <p className="eyebrow">What posts back to Todoist</p>
              <p className="muted">
                The weekly automation comments directly on each tracked task with completions, reschedules, all-time
                totals, and a simple reliability score.
              </p>
            </div>
            <div>
              <p className="eyebrow">How to opt in</p>
              <p className="muted">
                Label any task with <code>@track_habit</code>. The next weekly run will include it automatically, and the
                dashboard payload will reflect it here.
              </p>
            </div>
            <div>
              <p className="eyebrow">Why this page is separate</p>
              <p className="muted">
                The overview dashboard stays focused on broad activity. This lab is intentionally narrower and leaves room
                for richer habit-specific components without crowding the home page.
              </p>
            </div>
          </div>
        </section>
      </section>
    </>
  );
}
