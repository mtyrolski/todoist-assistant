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
};

const HELP = `**Habit tracker**
Weekly summary for tasks labeled \`@track_habit\`.

- Weekly counts use the most recent completed week.
- Reschedules are shown separately so you can spot churn.
- Reliability is completions divided by completions plus reschedules.`;

export function HabitTrackerCard({
  habitTracker
}: {
  habitTracker: HabitTrackerPayload | null | undefined;
}) {
  if (!habitTracker) {
    return <div className="skeleton" style={{ minHeight: 320 }} />;
  }

  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Habit tracker</h2>
          <InfoTip label="About habit tracker" content={HELP} />
        </div>
      </header>

      <div className="habitTrackerMeta">
        <span className="pill pill-neutral">{habitTracker.trackedCount} tracked</span>
        <span className="pill pill-good">
          {habitTracker.totals.weeklyCompleted} completed
        </span>
        <span className="pill pill-warn">
          {habitTracker.totals.weeklyRescheduled} rescheduled
        </span>
      </div>

      <p className="muted tiny" style={{ margin: "0 0 14px" }}>
        Weekly check-in for {habitTracker.label}.
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
              <div className="habitStats">
                <span className="pill pill-good">W {item.weeklyCompleted}</span>
                <span className="pill pill-warn">R {item.weeklyRescheduled}</span>
                <span className="pill pill-neutral">All {item.allTimeCompleted}</span>
                <span className="pill pill-neutral">
                  {item.reliability === null ? "N/A" : `${item.reliability.toFixed(2)}%`}
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
