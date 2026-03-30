"use client";

import { InfoTip } from "./InfoTip";

export type HabitTrackerItem = {
  taskId: string;
  name: string;
  projectId: string;
  projectName: string;
  color: string;
  weeklyCompleted: number;
  weeklyRescheduled: number;
  allTimeCompleted: number;
  allTimeRescheduled: number;
  reliability: number | null;
};

export type HabitTrackerPayload = {
  label: string;
  weekBeg: string;
  weekEnd: string;
  trackedCount: number;
  totals: {
    weeklyCompleted: number;
    weeklyRescheduled: number;
    allTimeCompleted: number;
    allTimeRescheduled: number;
  };
  items: HabitTrackerItem[];
  history: { label: string; completed: number; rescheduled: number }[];
};

const HELP = `**Habit tracker**
Weekly summary for tasks labeled \`@track_habit\`.

- Weekly counts use the most recent completed week.
- Rates are shown alongside raw counts so you can spot churn at a glance.
- Reliability is completions divided by completions plus reschedules.`;

function formatRate(completed: number, rescheduled: number): string {
  const total = completed + rescheduled;
  return total ? `${((completed / total) * 100).toFixed(1)}%` : "N/A";
}

function toPercent(completed: number, rescheduled: number): number {
  const total = completed + rescheduled;
  return total ? Math.round((completed / total) * 100) : 0;
}

export function HabitTrackerCard({
  habitTracker
}: {
  habitTracker: HabitTrackerPayload | null | undefined;
}) {
  if (!habitTracker) {
    return <div className="card skeleton" style={{ minHeight: 420 }} />;
  }

  const weeklyTotal = habitTracker.totals.weeklyCompleted + habitTracker.totals.weeklyRescheduled;
  const allTimeTotal = habitTracker.totals.allTimeCompleted + habitTracker.totals.allTimeRescheduled;
  const weeklyRate = formatRate(habitTracker.totals.weeklyCompleted, habitTracker.totals.weeklyRescheduled);
  const allTimeRate = formatRate(habitTracker.totals.allTimeCompleted, habitTracker.totals.allTimeRescheduled);

  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Tracked habits</h2>
          <InfoTip label="About habit tracker" content={HELP} />
        </div>
      </header>

      <div className="habitTrackerMeta">
        <span className="pill pill-neutral">{habitTracker.trackedCount} tracked</span>
        <span className="pill pill-good">Weekly rate {weeklyRate}</span>
        <span className="pill pill-warn">All-time rate {allTimeRate}</span>
        <span className="pill pill-neutral">{weeklyTotal} weekly events</span>
        <span className="pill pill-neutral">{allTimeTotal} all-time events</span>
      </div>

      <p className="muted tiny" style={{ margin: "0 0 14px" }}>
        Weekly check-in for {habitTracker.label} covering {habitTracker.weekBeg} to {habitTracker.weekEnd}.
      </p>

      {habitTracker.items.length ? (
        <div className="habitTable">
          {habitTracker.items.map((item) => (
            <div key={item.taskId} className="habitRow">
              <div className="habitRowMain">
                <div className="habitTitle">
                  <span className="swatch" style={{ background: item.color }} />
                  <span className="truncate">{item.name}</span>
                </div>
                <span className="pill pill-neutral truncate">{item.projectName}</span>
              </div>
              <div className="progressTrack" style={{ marginTop: 0 }}>
                <div className="progressFill" style={{ width: `${toPercent(item.weeklyCompleted, item.weeklyRescheduled)}%` }} />
              </div>
              <div className="habitStats">
                <span className="pill pill-good">W {item.weeklyCompleted}</span>
                <span className="pill pill-warn">R {item.weeklyRescheduled}</span>
                <span className="pill pill-neutral">All {item.allTimeCompleted}</span>
                <span className="pill pill-neutral">All R {item.allTimeRescheduled}</span>
                <span className="pill pill-neutral">
                  {item.reliability === null ? "N/A" : `${item.reliability.toFixed(1)}%`} reliability
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">
          Add the <code>@track_habit</code> label to recurring tasks and the weekly tracker will start posting progress
          comments plus dashboard stats.
        </p>
      )}
    </section>
  );
}
