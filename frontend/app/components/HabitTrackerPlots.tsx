"use client";

import { InfoTip } from "./InfoTip";
import type { HabitTrackerPayload } from "./HabitTrackerCard";

type WindowSummary = {
  label: string;
  availableWeeks: number;
  completed: number;
  rescheduled: number;
  total: number;
  rate: number;
};

const WINDOW_SIZES = [4, 8, 12] as const;

const HELP = `**Habit rates**
This section turns the weekly habit payload into rate-first views.

- The window cards compare all-time history against recent N-week slices.
- The habit leaderboard ranks tasks by all-time reliability.`;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatPercent(rate: number): string {
  return `${Math.round(clamp(rate, 0, 1) * 100)}%`;
}

function formatStoredPercent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "N/A";
  return `${clamp(rate, 0, 100).toFixed(1)}%`;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function sumWindow(history: HabitTrackerPayload["history"], weeks: number): WindowSummary {
  const slice = history.slice(Math.max(0, history.length - weeks));
  const completed = slice.reduce((total, week) => total + week.completed, 0);
  const rescheduled = slice.reduce((total, week) => total + week.rescheduled, 0);
  const total = completed + rescheduled;
  return {
    label: `Last ${weeks} weeks`,
    availableWeeks: slice.length,
    completed,
    rescheduled,
    total,
    rate: total > 0 ? completed / total : 0
  };
}

function buildRateGradient(rate: number): string {
  const fill = formatPercent(rate);
  return `conic-gradient(rgba(97, 244, 179, 0.95) 0 ${fill}, rgba(255, 184, 108, 0.9) ${fill} 100%)`;
}

export function HabitTrackerPlots({
  habitTracker
}: {
  habitTracker: HabitTrackerPayload | null | undefined;
}) {
  if (!habitTracker) {
    return (
      <section className="card habitPlotsSection">
        <div className="skeleton" style={{ minHeight: 420 }} />
      </section>
    );
  }

  const history = habitTracker.history ?? [];
  const totalCompleted = history.reduce((sum, week) => sum + week.completed, 0);
  const totalRescheduled = history.reduce((sum, week) => sum + week.rescheduled, 0);
  const totalEvents = totalCompleted + totalRescheduled;
  const totalRate = totalEvents > 0 ? totalCompleted / totalEvents : 0;
  const latestWeek = history.at(-1) ?? null;
  const latestTotal = latestWeek ? latestWeek.completed + latestWeek.rescheduled : 0;
  const latestRate = latestTotal > 0 ? (latestWeek?.completed ?? 0) / latestTotal : 0;
  const recentWindows = WINDOW_SIZES.map((weeks) => sumWindow(history, weeks));
  const ranking = [...habitTracker.items].sort((left, right) => {
    const reliabilityDelta = (right.reliability ?? -1) - (left.reliability ?? -1);
    if (reliabilityDelta !== 0) return reliabilityDelta;
    const leftVolume = left.allTimeCompleted + left.allTimeRescheduled;
    const rightVolume = right.allTimeCompleted + right.allTimeRescheduled;
    return rightVolume - leftVolume;
  });
  const topHabits = ranking.slice(0, 6);

  return (
    <section className="card habitPlotsSection">
      <header className="cardHeader habitPlotsHeader">
        <div>
          <div className="cardTitleRow">
            <h2>Rate plots</h2>
            <InfoTip label="About habit rates" content={HELP} />
          </div>
          <p className="muted tiny" style={{ margin: "6px 0 0" }}>
            Completion rate is shown against reschedule pressure, so the lab stays focused on signal instead of raw volume.
          </p>
        </div>
        <div className="habitPlotsHeaderMeta">
          <span className="pill pill-good">{formatPercent(totalRate)} all-time completion rate</span>
          <span className="pill pill-warn">{formatPercent(latestRate)} latest week</span>
          <span className="pill pill-neutral">{formatCount(habitTracker.trackedCount)} tracked habits</span>
        </div>
      </header>

      <div className="habitRateSummary">
        <article className="habitRateStatCard">
          <p className="eyebrow">All history</p>
          <h3>{formatPercent(totalRate)}</h3>
          <p className="muted tiny">
            {formatCount(totalCompleted)} completed and {formatCount(totalRescheduled)} rescheduled across {formatCount(totalEvents)} events.
          </p>
        </article>
        <article className="habitRateStatCard">
          <p className="eyebrow">Latest week</p>
          <h3>{formatPercent(latestRate)}</h3>
          <p className="muted tiny">
            {latestPoint ? `${formatCount(latestPoint.completed)} completed / ${formatCount(latestPoint.total)} total events` : "No weekly history yet."}
          </p>
        </article>
        {recentWindows.map((window) => (
          <article key={window.label} className="habitRateStatCard">
            <p className="eyebrow">{window.label}</p>
            <h3>{formatPercent(window.rate)}</h3>
            <p className="muted tiny">
              {window.availableWeeks} week{window.availableWeeks === 1 ? "" : "s"} available.
            </p>
          </article>
        ))}
      </div>

      <div className="habitWindowGrid">
        {recentWindows.map((window) => (
          <article key={window.label} className="habitWindowCard">
            <div className="habitGauge" style={{ background: buildRateGradient(window.rate) }} aria-hidden="true">
              <div className="habitGaugeInner">
                <span className="habitGaugeValue">{formatPercent(window.rate)}</span>
                <span className="habitGaugeLabel">{window.label}</span>
              </div>
            </div>
            <div className="habitWindowMeta">
              <span>{formatCount(window.completed)} completed</span>
              <span>{formatCount(window.rescheduled)} rescheduled</span>
              <span>{formatCount(window.total)} total events</span>
            </div>
          </article>
        ))}
      </div>

      <article className="habitReliabilityCard">
        <header className="habitCardHeader">
          <div>
            <p className="eyebrow">Reliability spread</p>
            <h3>Highest quality habits by all-time reliability</h3>
          </div>
          <p className="muted tiny" style={{ margin: 0 }}>
            Reliability is completions divided by completions plus reschedules.
          </p>
        </header>
        <div className="habitReliabilityList">
          {topHabits.length ? (
            topHabits.map((item) => {
              const activity = item.allTimeCompleted + item.allTimeRescheduled;
              const reliabilityPercent = item.reliability ?? 0;
              return (
                <div key={item.taskId} className="habitReliabilityRow">
                  <div className="habitReliabilityMain">
                    <div className="habitTitle">
                      <span className="swatch" style={{ background: item.color }} />
                      <span className="truncate">{item.name}</span>
                    </div>
                    <span className="pill pill-neutral">{formatStoredPercent(item.reliability)}</span>
                  </div>
                  <div className="habitReliabilityBar" aria-hidden="true">
                    <div className="habitReliabilityFill" style={{ width: `${clamp(reliabilityPercent, 0, 100)}%` }} />
                  </div>
                  <div className="habitReliabilityMeta">
                    <span className="pill pill-good">{formatCount(item.allTimeCompleted)} completed</span>
                    <span className="pill pill-warn">{formatCount(item.allTimeRescheduled)} rescheduled</span>
                    <span className="pill pill-neutral">{formatCount(activity)} total events</span>
                  </div>
                </div>
              );
            })
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              Add the <code>@track_habit</code> label to recurring tasks and the reliability leaderboard will populate
              automatically.
            </p>
          )}
        </div>
      </article>
    </section>
  );
}
