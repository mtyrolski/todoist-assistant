"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PlotCard, type PlotlyFigure } from "./components/PlotCard";
import { StatCard } from "./components/StatCard";
import { LoadingBar } from "./components/LoadingBar";
import { ProgressSteps, type DashboardProgress } from "./components/ProgressSteps";
import { LeaderboardCard, type LeaderboardItem } from "./components/LeaderboardCard";
import { ServiceMonitor, type ServiceStatus } from "./components/ServiceMonitor";
import { InsightCard, type InsightItem } from "./components/InsightCard";
import { AdminPanel } from "./components/AdminPanel";
import { LlmBreakdownStatus, type LlmBreakdownProgress } from "./components/LlmBreakdownStatus";
import { LlmChatPanel } from "./components/LlmChatPanel";
import { InfoTip } from "./components/InfoTip";

type Health = { status: string; version?: string } | null;

type Granularity = "W" | "ME" | "3ME";

type DashboardHome = {
  range: { beg: string; end: string; granularity: Granularity; weeks: number };
  metrics: {
    items: { name: string; value: number; deltaPercent: number | null; inverseDelta: boolean }[];
    currentPeriod: string;
    previousPeriod: string;
  };
  badges: { p1: number; p2: number; p3: number; p4: number };
  insights?: { label?: string; items: InsightItem[] };
  leaderboards?: {
    lastCompletedWeek: {
      label: string;
      beg: string;
      end: string;
      parentProjects: { items: LeaderboardItem[]; totalCompleted: number; figure: PlotlyFigure };
      rootProjects: { items: LeaderboardItem[]; totalCompleted: number; figure: PlotlyFigure };
    };
  };
  figures: Record<string, PlotlyFigure>;
  refreshedAt: string;
  error?: string;
};

type DashboardStatus = {
  services: ServiceStatus[];
  apiCache: { lastRefresh: string | null };
  activityCache: { path: string; mtime: string | null; size: number | null } | null;
  now: string;
};

const METRIC_HELP: Record<string, string> = {
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

const DEFAULT_METRIC_HELP = `**Metric**
Value for the selected period.

- Delta compares against the previous period of equal length.`;

const INSIGHT_HELP: Record<string, string> = {
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

const DEFAULT_INSIGHT_HELP = `**Insight**
Quick highlight computed from recent activity.`;

const PLOT_HELP = {
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

const BADGES_HELP = `**Priority badges**
Snapshot of current tasks by priority.

- P1 is highest urgency, P4 is lowest.`;

const SPOTLIGHT_HELP = `**Activity spotlight**
Top projects by completed tasks in the most recent finished week.

- Subprojects includes nested projects.
- Root projects are top-level only.`;

export default function Page() {
  const [health, setHealth] = useState<Health>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  const [granularity, setGranularity] = useState<Granularity>("W");
  const [weeks, setWeeks] = useState<number>(12);
  const [rangeMode, setRangeMode] = useState<"rolling" | "custom">("rolling");
  const [customBeg, setCustomBeg] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [refreshNonce, setRefreshNonce] = useState<number>(0);
  const lastRefreshNonce = useRef<number>(0);
  const [dashboard, setDashboard] = useState<DashboardHome | null>(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [progress, setProgress] = useState<DashboardProgress | null>(null);
  const [status, setStatus] = useState<DashboardStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [statusRefreshNonce, setStatusRefreshNonce] = useState(0);
  const [llmProgress, setLlmProgress] = useState<LlmBreakdownProgress | null>(null);
  const [loadingLlmProgress, setLoadingLlmProgress] = useState(false);
  const [llmRefreshNonce, setLlmRefreshNonce] = useState(0);
  const [syncClock, setSyncClock] = useState(() => Date.now());

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        setLoadingHealth(true);
        setError(null);
        const res = await fetch("/api/health");
        if (!res.ok) throw new Error("API unavailable");
        const data = (await res.json()) as Health;
        setHealth(data);
      } catch (err) {
        setError("Unable to connect to the API server. Please check that the backend is running.");
      } finally {
        setLoadingHealth(false);
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 10_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        setLoadingDashboard(true);
        setDashboardError(null);
        const shouldRefresh = refreshNonce !== lastRefreshNonce.current;
        lastRefreshNonce.current = refreshNonce;
        const qs = new URLSearchParams({ granularity, refresh: shouldRefresh ? "true" : "false" });
        if (rangeMode === "custom" && customBeg && customEnd) {
          qs.set("beg", customBeg);
          qs.set("end", customEnd);
        } else {
          qs.set("weeks", String(weeks));
        }
        const res = await fetch(`/api/dashboard/home?${qs.toString()}`, { signal: controller.signal });
        const payload = (await res.json()) as DashboardHome;
        if (!res.ok || payload.error) {
          throw new Error(payload.error ?? "Failed to load dashboard");
        }
        setDashboard(payload);
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
        setDashboard(null);
        setDashboardError(e instanceof Error ? e.message : "Failed to load dashboard");
      } finally {
        setLoadingDashboard(false);
      }
    };
    load();
    return () => controller.abort();
  }, [granularity, weeks, rangeMode, customBeg, customEnd, refreshNonce]);

  const shouldPollProgress = loadingDashboard || (!dashboard && !dashboardError);

  useEffect(() => {
    if (!shouldPollProgress) {
      setProgress(null);
      return;
    }
    const controller = new AbortController();
    let active = true;

    const loadProgress = async () => {
      try {
        const res = await fetch("/api/dashboard/progress", { signal: controller.signal });
        if (!res.ok) return;
        const payload = (await res.json()) as DashboardProgress;
        if (!active) return;
        setProgress(payload);
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
      }
    };

    loadProgress();
    const interval = setInterval(loadProgress, 700);
    return () => {
      active = false;
      controller.abort();
      clearInterval(interval);
    };
  }, [shouldPollProgress]);

  const progressDisplay = useMemo(() => {
    if (progress?.active) return progress;
    if (!shouldPollProgress) return null;
    return {
      active: true,
      stage: null,
      step: 1,
      totalSteps: 3,
      startedAt: null,
      updatedAt: null,
      detail: "Connecting to the API and preparing the dashboard...",
      error: null
    } satisfies DashboardProgress;
  }, [progress, shouldPollProgress]);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        setLoadingStatus(true);
        const qs = new URLSearchParams({ refresh: statusRefreshNonce ? "true" : "false" });
        const res = await fetch(`/api/dashboard/status?${qs.toString()}`, { signal: controller.signal });
        if (!res.ok) throw new Error("status");
        const payload = (await res.json()) as DashboardStatus;
        setStatus(payload);
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
        setStatus(null);
      } finally {
        setLoadingStatus(false);
      }
    };
    load();
    return () => controller.abort();
  }, [statusRefreshNonce]);

  useEffect(() => {
    const interval = setInterval(() => setSyncClock(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    const load = async () => {
      try {
        setLoadingLlmProgress(true);
        const res = await fetch("/api/dashboard/llm_breakdown", { signal: controller.signal });
        if (!res.ok) throw new Error("llm-progress");
        const payload = (await res.json()) as LlmBreakdownProgress;
        if (!active) return;
        setLlmProgress(payload);
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
        setLlmProgress(null);
      } finally {
        if (active) setLoadingLlmProgress(false);
      }
    };

    load();
    const interval = setInterval(load, 2000);
    return () => {
      active = false;
      controller.abort();
      clearInterval(interval);
    };
  }, [llmRefreshNonce]);

  const syncLabel = useMemo(() => {
    if (!status) return "Sync status unavailable";
    const activityCache = status.activityCache;
    if (!activityCache) return "Activity cache missing";
    const lastRefresh = activityCache.mtime;
    if (!lastRefresh) return "Sync time unknown";
    const lastMs = Date.parse(lastRefresh);
    if (Number.isNaN(lastMs)) return "Sync unknown";
    const diffMs = Math.max(0, syncClock - lastMs);
    if (diffMs < 60_000) return "Synced just now";
    const minutes = Math.floor(diffMs / 60_000);
    if (minutes < 60) return `Synced ${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Synced ${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `Synced ${days}d ago`;
  }, [status, syncClock]);

  const syncTitle = useMemo(() => {
    if (!status) return undefined;
    if (!status.activityCache) return "activity.joblib missing";
    return status.activityCache.mtime ?? "sync time unavailable";
  }, [status]);

  const periodLabel = useMemo(() => {
    if (!dashboard) return null;
    return `${dashboard.range.beg} → ${dashboard.range.end}`;
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
    { id: "llm-chat", label: "LLM Chat" },
    { id: "ops", label: "Activity & Ops" },
  ];

  return (
    <div className="page">
      <LoadingBar active={loadingDashboard || loadingStatus} />
      <header className="topbar">
        <div>
          <p className="eyebrow">Todoist Assistant</p>
          <h1>Dashboard</h1>
          <p className="lede">
            A fast, local dashboard for your Todoist data and automations.
          </p>
          <div className="status-row">
            <span className={`pill ${health?.status === "ok" ? "pill-good" : "pill-warn"}`}>
              {loadingHealth ? "Checking API…" : health?.status === "ok" ? "API online" : "API offline"}
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
              onChange={(e) => setGranularity(e.target.value as Granularity)}
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
          <button
            className="button"
            onClick={() => setRefreshNonce((x) => x + 1)}
            disabled={loadingDashboard}
          >
            {loadingDashboard ? "Loading…" : "Refresh"}
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
          <span className="badge badge-p1">P1 {dashboard?.badges.p1 ?? "—"}</span>
          <span className="badge badge-p2">P2 {dashboard?.badges.p2 ?? "—"}</span>
          <span className="badge badge-p3">P3 {dashboard?.badges.p3 ?? "—"}</span>
          <span className="badge badge-p4">P4 {dashboard?.badges.p4 ?? "—"}</span>
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

      <section id="llm-chat" className="stack jumpTarget" aria-label="LLM chat">
        <LlmChatPanel />
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
            Most active projects by completed tasks ({lastWeek?.label ?? "—"}).
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
              setRefreshNonce((x) => x + 1);
              setStatusRefreshNonce((x) => x + 1);
            }}
          />

          <LlmBreakdownStatus
            progress={llmProgress}
            loading={loadingLlmProgress}
            onRefresh={() => setLlmRefreshNonce((x) => x + 1)}
          />

          <ServiceMonitor services={status?.services ?? null} onRefresh={() => setStatusRefreshNonce((x) => x + 1)} />
        </section>
      </section>
    </div>
  );
}
