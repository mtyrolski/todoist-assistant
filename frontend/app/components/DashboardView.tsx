"use client";

import { useMemo } from "react";
import { PlotCard } from "./PlotCard";
import { StatCard } from "./StatCard";
import { LoadingBar } from "./LoadingBar";
import { ProgressSteps } from "./ProgressSteps";
import { LeaderboardCard } from "./LeaderboardCard";
import { ServiceMonitor } from "./ServiceMonitor";
import { InsightCard } from "./InsightCard";
import { AdminPanel } from "./AdminPanel";
import { LlmBreakdownStatus } from "./LlmBreakdownStatus";
import { InfoTip } from "./InfoTip";
import {
  BADGES_HELP,
  DEFAULT_INSIGHT_HELP,
  DEFAULT_METRIC_HELP,
  INSIGHT_HELP,
  METRIC_HELP,
  PLOT_HELP,
  SPOTLIGHT_HELP
} from "../lib/dashboardCopy";
import {
  useApiHealth,
  useDashboardHome,
  useDashboardStatus,
  useLlmBreakdownProgress,
  useSyncLabel
} from "../lib/dashboardHooks";

export function DashboardView() {
  const { health, loadingHealth, error } = useApiHealth();
  const {
    dashboard,
    loadingDashboard,
    dashboardError,
    progressDisplay,
    granularity,
    setGranularity,
    weeks,
    setWeeks,
    rangeMode,
    setRangeMode,
    customBeg,
    setCustomBeg,
    customEnd,
    setCustomEnd,
    refresh
  } = useDashboardHome();
  const { status, loadingStatus, refreshStatus } = useDashboardStatus();
  const { progress: llmProgress, loading: loadingLlmProgress, refresh: refreshLlmProgress } = useLlmBreakdownProgress();
  const { label: syncLabel, title: syncTitle } = useSyncLabel(status);

  const periodLabel = useMemo(() => {
    if (!dashboard) return null;
    return `${dashboard.range.beg} -> ${dashboard.range.end}`;
  }, [dashboard]);

  const figures = dashboard?.figures ?? {};
  const lastWeek = dashboard?.leaderboards?.lastCompletedWeek ?? null;
  const parentBoard = lastWeek?.parentProjects?.items ?? null;
  const rootBoard = lastWeek?.rootProjects?.items ?? null;
  const metricsCurrentPeriod = dashboard?.metrics.currentPeriod ?? "";
  const metricsPreviousPeriod = dashboard?.metrics.previousPeriod ?? "";
  const jumpTargets = [
    { id: "insights", label: "Insights" },
    { id: "labels-lifespans", label: "Labels + Lifespans" },
    { id: "stats", label: "Stats" },
    { id: "badges", label: "Badges" },
    { id: "completed-tasks", label: "Completions" },
    { id: "events", label: "Events" },
    { id: "ops", label: "Activity & Ops" }
  ];

  return (
    <div>
      <LoadingBar active={loadingDashboard || loadingStatus} />
      <header className="topbar">
        <div>
          <p className="eyebrow">Todoist Assistant</p>
          <h1>Dashboard</h1>
          <p className="lede">A fast, local dashboard for your Todoist data and automations.</p>
          <div className="status-row">
            <span className={`pill ${health?.status === "ok" ? "pill-good" : "pill-warn"}`}>
              {loadingHealth ? "Checking API..." : health?.status === "ok" ? "API online" : "API offline"}
            </span>
            {health?.version ? <span className="pill pill-neutral">v{health.version}</span> : null}
            <span className="pill pill-neutral" title={syncTitle}>
              {syncLabel}
            </span>
            {periodLabel && <span className="pill">{periodLabel}</span>}
            {dashboardError && <span className="pill pill-warn">{dashboardError}</span>}
            {error && <span className="pill pill-warn">{error}</span>}
          </div>
        </div>
        <div className="controls">
          <div className="control">
            <label className="muted tiny" htmlFor="granularity-select">
              Granularity
            </label>
            <select
              id="granularity-select"
              value={granularity}
              onChange={(e) => setGranularity(e.target.value as "W" | "ME" | "3ME")}
              className="select"
            >
              <option value="W">Week</option>
              <option value="ME">Month</option>
              <option value="3ME">Three Months</option>
            </select>
          </div>

          <div className="control">
            <div className="muted tiny">Time range</div>
            <div className="segmented">
              <button
                type="button"
                className={`seg ${rangeMode === "rolling" ? "segActive" : ""}`}
                onClick={() => setRangeMode("rolling")}
              >
                Rolling
              </button>
              <button
                type="button"
                className={`seg ${rangeMode === "custom" ? "segActive" : ""}`}
                onClick={() => setRangeMode("custom")}
              >
                Custom
              </button>
            </div>
          </div>

          {rangeMode === "rolling" ? (
            <div className="control">
              <label className="muted tiny" htmlFor="range-select">
                Range
              </label>
              <select
                id="range-select"
                value={weeks}
                onChange={(e) => setWeeks(Number(e.target.value))}
                className="select"
              >
                <option value={4}>Last 4 weeks</option>
                <option value={12}>Last 12 weeks</option>
                <option value={26}>Last 26 weeks</option>
                <option value={52}>Last 52 weeks</option>
              </select>
            </div>
          ) : (
            <div className="control">
              <label className="muted tiny" htmlFor="beg-input">
                Beg / End
              </label>
              <div className="dateRow">
                <input
                  id="beg-input"
                  className="dateInput"
                  type="date"
                  value={customBeg}
                  onChange={(e) => setCustomBeg(e.target.value)}
                />
                <input
                  id="end-input"
                  className="dateInput"
                  type="date"
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                />
              </div>
            </div>
          )}
          <button className="button" onClick={refresh} disabled={loadingDashboard}>
            {loadingDashboard ? "Loading..." : "Refresh"}
          </button>
          {dashboard?.refreshedAt && <p className="muted tiny">Updated {dashboard.refreshedAt}</p>}
        </div>
      </header>

      <ProgressSteps progress={progressDisplay} />

      <nav className="jumpNav" aria-label="Jump to sections">
        <span className="muted tiny">Jump to</span>
        <div className="jumpLinks">
          {jumpTargets.map((target) => (
            <a key={target.id} className="jumpLink" href={`#${target.id}`}>
              {target.label}
            </a>
          ))}
        </div>
      </nav>

      <section id="insights" className="insightsRow jumpTarget" aria-label="Insights">
        {(dashboard?.insights?.items ?? Array.from({ length: 4 }).map(() => null)).map((it, idx) =>
          it ? (
            <InsightCard
              key={`${it.title}-${idx}`}
              item={it}
              help={INSIGHT_HELP[it.title] ?? DEFAULT_INSIGHT_HELP}
            />
          ) : (
            <div key={idx} className="stat skeleton" />
          )
        )}
        {dashboard?.insights?.label ? (
          <p className="muted tiny" style={{ gridColumn: "1 / -1", marginTop: "-6px" }}>
            Insights for {dashboard.insights.label}.
          </p>
        ) : null}
      </section>

      <section id="labels-lifespans" className="grid2 jumpTarget" aria-label="Labels and task lifespans">
        <PlotCard
          title="Most Popular Labels"
          figure={figures.mostPopularLabels}
          height={420}
          help={PLOT_HELP.mostPopularLabels}
        />
        <PlotCard
          title="Task Lifespans: Time to Completion"
          figure={figures.taskLifespans}
          height={420}
          help={PLOT_HELP.taskLifespans}
        />
      </section>

      <section id="stats" className="statsRow jumpTarget" aria-label="Key stats">
        {(dashboard?.metrics.items ?? Array.from({ length: 4 }).map(() => null)).map((m, idx) =>
          m ? (
            <StatCard
              key={m.name}
              name={m.name}
              value={m.value}
              deltaPercent={m.deltaPercent}
              inverseDelta={m.inverseDelta}
              currentPeriod={metricsCurrentPeriod}
              previousPeriod={metricsPreviousPeriod}
              help={METRIC_HELP[m.name] ?? DEFAULT_METRIC_HELP}
            />
          ) : (
            <div key={idx} className="stat skeleton" />
          )
        )}
      </section>

      <section id="badges" className="jumpTarget" aria-label="Priority badges">
        <div className="sectionHeader">
          <h2>Priority badges</h2>
          <InfoTip label="About priority badges" content={BADGES_HELP} />
        </div>
        <div className="badges">
          <span className="badge badge-p1">P1 {dashboard?.badges.p1 ?? "-"}</span>
          <span className="badge badge-p2">P2 {dashboard?.badges.p2 ?? "-"}</span>
          <span className="badge badge-p3">P3 {dashboard?.badges.p3 ?? "-"}</span>
          <span className="badge badge-p4">P4 {dashboard?.badges.p4 ?? "-"}</span>
        </div>
      </section>

      <section id="completed-tasks" className="stack jumpTarget" aria-label="Completed tasks per project">
        <PlotCard
          title="Periodically Completed Tasks Per Project"
          figure={figures.completedTasksPeriodically}
          height={520}
          help={PLOT_HELP.completedTasksPeriodically}
        />
        <PlotCard
          title="Cumulative Periodically Completed Tasks Per Project"
          figure={figures.cumsumCompletedTasksPeriodically}
          height={520}
          help={PLOT_HELP.cumsumCompletedTasksPeriodically}
        />
      </section>

      <section id="events" className="stack jumpTarget" aria-label="Event trends">
        <PlotCard
          title="Heatmap of Events by Day and Hour"
          figure={figures.heatmapEventsByDayHour}
          height={520}
          help={PLOT_HELP.heatmapEventsByDayHour}
        />
        <PlotCard
          title="Events Over Time"
          figure={figures.eventsOverTime}
          height={520}
          help={PLOT_HELP.eventsOverTime}
        />
      </section>

      <section id="ops" className="grid2 jumpTarget" aria-label="Activity and operations">
        <section className="card">
          <header className="cardHeader">
            <div className="cardTitleRow">
              <h2>Activity Spotlight</h2>
              <InfoTip label="About activity spotlight" content={SPOTLIGHT_HELP} />
            </div>
          </header>
          <div className="muted tiny" style={{ padding: "0 2px 10px" }}>
            Most active projects by completed tasks ({lastWeek?.label ?? "-"}).
          </div>
          <div className="spotlightGrid">
            <div>
              <p className="muted tiny" style={{ margin: "0 0 10px" }}>
                Subprojects
              </p>
              <LeaderboardCard items={parentBoard} />
            </div>
            <div>
              <p className="muted tiny" style={{ margin: "0 0 10px" }}>
                Root projects
              </p>
              <LeaderboardCard items={rootBoard} />
            </div>
          </div>
        </section>

        <section className="stack">
          <AdminPanel
            onAfterMutation={() => {
              refresh();
              refreshStatus();
            }}
          />

          <LlmBreakdownStatus
            progress={llmProgress}
            loading={loadingLlmProgress}
            onRefresh={refreshLlmProgress}
          />

          <ServiceMonitor services={status?.services ?? null} onRefresh={refreshStatus} />
        </section>
      </section>
    </div>
  );
}
