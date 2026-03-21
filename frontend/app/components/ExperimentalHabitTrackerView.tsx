"use client";

import { HabitTrackerCard } from "./HabitTrackerCard";
import { LoadingBar } from "./LoadingBar";
import { PageHeader } from "./PageHeader";
import { PlotCard } from "./PlotCard";
import type { StatusPill } from "./StatusPills";
import { StatusPills } from "./StatusPills";
import { useApiHealth, useDashboardHome } from "../lib/dashboardHooks";

function formatReliability(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `${value.toFixed(2)}%`;
}

export function ExperimentalHabitTrackerView() {
  const { health, loadingHealth } = useApiHealth();
  const { dashboard, loadingDashboard, dashboardError, retrying, refresh } =
    useDashboardHome();
  const habitTracker = dashboard?.habitTracker ?? null;
  const topHabits = habitTracker?.items.slice(0, 5) ?? [];

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

      <section className="experimentToolbar card">
        <div>
          <p className="eyebrow">Lab controls</p>
          <p className="muted" style={{ margin: "6px 0 0" }}>
            This page reads the same habit-tracker payload as the main app, but renders it with more exploratory
            components.
          </p>
        </div>
        <div className="actionRow">
          <button className="button buttonSmall" type="button" onClick={refresh} disabled={loadingDashboard}>
            {loadingDashboard ? "Refreshing..." : retrying ? "Retrying..." : "Refresh lab"}
          </button>
        </div>
      </section>

      {dashboardError ? (
        <section className="card">
          <p className="muted">{dashboardError}</p>
        </section>
      ) : null}

      <section className="experimentHero">
        <article className="experimentMetricCard">
          <p className="eyebrow">Tracked habits</p>
          <h2>{habitTracker?.trackedCount ?? 0}</h2>
          <p className="muted">Tasks labeled <code>@track_habit</code> that currently participate in the weekly rollup.</p>
        </article>
        <article className="experimentMetricCard">
          <p className="eyebrow">Weekly completions</p>
          <h2>{habitTracker?.totals.weeklyCompleted ?? 0}</h2>
          <p className="muted">Completions recorded in the most recent finished week.</p>
        </article>
        <article className="experimentMetricCard">
          <p className="eyebrow">Weekly reschedules</p>
          <h2>{habitTracker?.totals.weeklyRescheduled ?? 0}</h2>
          <p className="muted">Reschedules recorded for tracked habits over the same weekly window.</p>
        </article>
      </section>

      <section className="grid2">
        <HabitTrackerCard habitTracker={habitTracker} />
        <PlotCard title="Habit trend" figure={habitTracker?.figure} height={360} />
      </section>

      <section className="grid2">
        <section className="card">
          <header className="cardHeader">
            <div className="cardTitleRow">
              <h2>Top habit signals</h2>
            </div>
          </header>
          {topHabits.length ? (
            <div className="experimentSignalList">
              {topHabits.map((item) => {
                const total = Math.max(1, item.weeklyCompleted + item.weeklyRescheduled);
                const completedWidth = Math.round((item.weeklyCompleted / total) * 100);
                const rescheduledWidth = 100 - completedWidth;
                return (
                  <div key={item.taskId} className="experimentSignalRow">
                    <div className="habitRowMain">
                      <div className="habitTitle">
                        <span className="swatch" style={{ background: item.color }} />
                        <span className="truncate">{item.name}</span>
                      </div>
                      <span className="pill pill-neutral">{formatReliability(item.reliability)}</span>
                    </div>
                    <div className="experimentSignalBar">
                      <div
                        className="experimentSignalBarGood"
                        style={{ width: `${completedWidth}%` }}
                        title={`Completed ${item.weeklyCompleted}`}
                      />
                      <div
                        className="experimentSignalBarWarn"
                        style={{ width: `${rescheduledWidth}%` }}
                        title={`Rescheduled ${item.weeklyRescheduled}`}
                      />
                    </div>
                    <div className="habitStats">
                      <span className="pill pill-good">Completed {item.weeklyCompleted}</span>
                      <span className="pill pill-warn">Rescheduled {item.weeklyRescheduled}</span>
                      <span className="pill pill-neutral">{item.projectName}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="muted">
              Add the <code>@track_habit</code> label to recurring tasks to light up this experimental view.
            </p>
          )}
        </section>

        <section className="card experimentNarrative">
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
                The overview dashboard stays focused on broad activity. This lab is intentionally narrower and gives us a
                place to try richer habit-specific components without crowding the home page.
              </p>
            </div>
          </div>
        </section>
      </section>
    </>
  );
}
