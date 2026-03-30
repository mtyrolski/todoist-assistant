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

type TrendPoint = {
  label: string;
  completed: number;
  rescheduled: number;
  total: number;
  rate: number;
};

const WINDOW_SIZES = [4, 8, 12] as const;
const CHART_WIDTH = 1000;
const CHART_HEIGHT = 320;
const CHART_MARGIN = { top: 18, right: 18, bottom: 52, left: 58 };

const HELP = `**Habit rates**
This section turns the weekly habit payload into rate-first views.

- The main chart shows week-by-week completion rate with activity volume behind it.
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
  const trendPoints: TrendPoint[] = history.map((week) => {
    const total = week.completed + week.rescheduled;
    return {
      label: week.label,
      completed: week.completed,
      rescheduled: week.rescheduled,
      total,
      rate: total > 0 ? week.completed / total : 0
    };
  });

  const totalCompleted = trendPoints.reduce((sum, point) => sum + point.completed, 0);
  const totalRescheduled = trendPoints.reduce((sum, point) => sum + point.rescheduled, 0);
  const totalEvents = totalCompleted + totalRescheduled;
  const totalRate = totalEvents > 0 ? totalCompleted / totalEvents : 0;
  const latestPoint = trendPoints.at(-1) ?? null;
  const latestRate = latestPoint?.rate ?? 0;
  const recentWindows = WINDOW_SIZES.map((weeks) => sumWindow(history, weeks));
  const ranking = [...habitTracker.items].sort((left, right) => {
    const reliabilityDelta = (right.reliability ?? -1) - (left.reliability ?? -1);
    if (reliabilityDelta !== 0) return reliabilityDelta;
    const leftVolume = left.allTimeCompleted + left.allTimeRescheduled;
    const rightVolume = right.allTimeCompleted + right.allTimeRescheduled;
    return rightVolume - leftVolume;
  });
  const topHabits = ranking.slice(0, 6);

  const innerWidth = CHART_WIDTH - CHART_MARGIN.left - CHART_MARGIN.right;
  const innerHeight = CHART_HEIGHT - CHART_MARGIN.top - CHART_MARGIN.bottom;
  const maxVolume = Math.max(1, ...trendPoints.map((point) => point.total));
  const barStep = trendPoints.length > 0 ? innerWidth / trendPoints.length : innerWidth;
  const barWidth = Math.max(14, Math.min(36, barStep * 0.6));
  const ratePath = trendPoints
    .map((point, index) => {
      const x = CHART_MARGIN.left + index * barStep + barStep / 2;
      const y = CHART_MARGIN.top + innerHeight - point.rate * innerHeight;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  const labelStride = Math.max(1, Math.ceil(trendPoints.length / 8));
  const gridSteps = [0, 0.25, 0.5, 0.75, 1];

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

      <article className="habitTrendCard">
        <header className="habitCardHeader">
          <div>
            <p className="eyebrow">Weekly trend</p>
            <h3>Completion rate with activity volume behind it</h3>
          </div>
          <div className="habitCardHeaderMeta">
            <span className="pill pill-good">Completed</span>
            <span className="pill pill-warn">Rescheduled</span>
            <span className="pill pill-neutral">Rate line</span>
          </div>
        </header>
        <div className="habitTrendChartWrap">
          <svg
            className="habitTrendChart"
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            role="img"
            aria-label="Weekly habit completion rate and activity volume"
          >
            {gridSteps.map((step) => {
              const y = CHART_MARGIN.top + innerHeight - step * innerHeight;
              return (
                <g key={step}>
                  <line
                    x1={CHART_MARGIN.left}
                    x2={CHART_WIDTH - CHART_MARGIN.right}
                    y1={y}
                    y2={y}
                    className="habitTrendGridLine"
                  />
                  <text x={20} y={y + 4} className="habitTrendAxisLabel">
                    {formatPercent(step)}
                  </text>
                </g>
              );
            })}
            {trendPoints.length ? (
              <>
                {trendPoints.map((point, index) => {
                  const x = CHART_MARGIN.left + index * barStep + barStep / 2;
                  const totalHeight = point.total > 0 ? (point.total / maxVolume) * innerHeight : 0;
                  const rescheduledHeight = point.total > 0 ? (point.rescheduled / point.total) * totalHeight : 0;
                  const completedHeight = Math.max(0, totalHeight - rescheduledHeight);
                  const top = CHART_MARGIN.top + innerHeight - totalHeight;
                  const barX = x - barWidth / 2;
                  const rateY = CHART_MARGIN.top + innerHeight - point.rate * innerHeight;
                  const shouldLabel = index % labelStride === 0 || index === trendPoints.length - 1;
                  return (
                    <g key={point.label}>
                      <rect
                        x={barX}
                        y={top + rescheduledHeight}
                        width={barWidth}
                        height={completedHeight}
                        rx={10}
                        className="habitTrendBarGood"
                      />
                      <rect
                        x={barX}
                        y={top}
                        width={barWidth}
                        height={rescheduledHeight}
                        rx={10}
                        className="habitTrendBarWarn"
                      />
                      <rect
                        x={barX}
                        y={top}
                        width={barWidth}
                        height={Math.max(totalHeight, 1)}
                        rx={10}
                        className="habitTrendBarShell"
                      />
                      <circle cx={x} cy={rateY} r={5.5} className="habitTrendPoint" />
                      {shouldLabel ? (
                        <text x={x} y={CHART_HEIGHT - 16} textAnchor="middle" className="habitTrendLabel">
                          {point.label}
                        </text>
                      ) : null}
                      <title>
                        {point.label}: {formatPercent(point.rate)} completion rate, {formatCount(point.completed)} completed,{" "}
                        {formatCount(point.rescheduled)} rescheduled.
                      </title>
                    </g>
                  );
                })}
                <path d={ratePath} className="habitTrendLine" />
              </>
            ) : (
              <text x={CHART_WIDTH / 2} y={CHART_HEIGHT / 2} textAnchor="middle" className="habitTrendEmpty">
                No weekly history yet.
              </text>
            )}
          </svg>
        </div>
        <div className="habitTrendLegend">
          <span className="habitLegendItem">
            <span className="habitLegendSwatch habitLegendSwatchGood" />
            Completed tasks
          </span>
          <span className="habitLegendItem">
            <span className="habitLegendSwatch habitLegendSwatchWarn" />
            Rescheduled tasks
          </span>
          <span className="habitLegendItem">
            <span className="habitLegendSwatch habitLegendSwatchLine" />
            Completion rate
          </span>
        </div>
      </article>

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
