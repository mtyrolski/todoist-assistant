"use client";

import dynamic from "next/dynamic";
import type { ComponentType } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { PlotParams } from "react-plotly.js";
import { PlotCard } from "./PlotCard";
import type { PlotlyFigure } from "./PlotCard";
import { StatCard } from "./StatCard";
import { LoadingBar } from "./LoadingBar";
import { ProgressSteps } from "./ProgressSteps";
import { LeaderboardCard } from "./LeaderboardCard";
import { ServiceMonitor } from "./ServiceMonitor";
import { InsightCard } from "./InsightCard";
import { AdminPanel } from "./AdminPanel";
import { LlmBreakdownStatus } from "./LlmBreakdownStatus";
import { ObserverControl } from "./ObserverControl";
import { InfoTip } from "./InfoTip";
import { StatusPills } from "./StatusPills";
import {
  BADGES_HELP,
  DEFAULT_INSIGHT_HELP,
  DEFAULT_METRIC_HELP,
  INSIGHT_HELP,
  METRIC_HELP,
  PLOT_HELP,
  SPOTLIGHT_HELP
} from "../lib/dashboardCopy";
import type { DashboardHome } from "../lib/dashboardData";
import {
  useApiHealth,
  useDashboardHome,
  useDashboardStatus,
  useLlmBreakdownProgress,
  useSyncLabel
} from "../lib/dashboardHooks";

const FIRST_SYNC_KEY = "todoist-assistant.firstSyncComplete";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as unknown as ComponentType<PlotParams>;

type UrgencyStatusPayload = {
  state: "good" | "warn" | "danger";
  title: string;
  summary: string;
  todayLabel: string;
  total: number;
  counts: {
    fireTasks: number;
    p1Tasks: number;
    p2Tasks: number;
    dueTasks: number;
    deadlineTasks: number;
  };
  badgeLabel: string;
  helpKey: string;
};

type DashboardHomeWithUrgency = DashboardHome & {
  urgencyStatus?: UrgencyStatusPayload;
};

function buildHierarchyFigureLayout(figure: PlotlyFigure): Record<string, unknown> {
  const { title: _title, height: _height, ...baseLayout } = figure.layout ?? {};
  const layoutRecord = baseLayout as Record<string, unknown>;
  const margin = (layoutRecord.margin ?? {}) as Record<string, unknown>;
  const xaxis = (layoutRecord.xaxis ?? {}) as Record<string, unknown>;
  const yaxis = (layoutRecord.yaxis ?? {}) as Record<string, unknown>;
  const legend = (layoutRecord.legend ?? {}) as Record<string, unknown>;
  const font = (layoutRecord.font ?? {}) as Record<string, unknown>;

  const toNumber = (value: unknown, fallback: number): number =>
    typeof value === "number" && Number.isFinite(value) ? value : fallback;

  const withTitleStandoff = (axis: Record<string, unknown>, standoff: number): Record<string, unknown> => {
    const axisTitle = axis.title;
    if (typeof axisTitle === "string") {
      return { ...axis, automargin: true, title: { text: axisTitle, standoff } };
    }
    if (axisTitle && typeof axisTitle === "object") {
      return {
        ...axis,
        automargin: true,
        title: { ...(axisTitle as Record<string, unknown>), standoff }
      };
    }
    return { ...axis, automargin: true };
  };

  return {
    ...baseLayout,
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {
      ...font,
      color: typeof font.color === "string" ? font.color : "#e8ecf2"
    },
    template: "plotly_dark",
    margin: {
      l: Math.max(22, toNumber(margin.l, 22)),
      r: Math.max(22, toNumber(margin.r, 22)),
      t: Math.max(22, toNumber(margin.t, 22)),
      b: Math.max(50, toNumber(margin.b, 50))
    },
    xaxis: withTitleStandoff(xaxis, 16),
    yaxis: withTitleStandoff(yaxis, 14),
    legend: {
      ...legend,
      tracegroupgap: Math.max(10, toNumber(legend.tracegroupgap, 10))
    },
    hoverlabel: {
      bgcolor: "rgba(13,16,27,0.96)",
      bordercolor: "rgba(146,225,255,0.24)",
      font: { color: "#eff4ff", size: 13 }
    }
  };
}

function toDateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function DashboardView({
  setupActive = false,
  tokenReady = false,
  setupComplete = false
}: {
  setupActive?: boolean;
  tokenReady?: boolean;
  setupComplete?: boolean;
}) {
  const { health, loadingHealth, error } = useApiHealth();
  const {
    dashboard,
    loadingDashboard,
    dashboardError,
    progressDisplay,
    retrying,
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
  } = useDashboardHome({ enabled: !setupActive });
  const { status, loadingStatus, refreshStatus } = useDashboardStatus();
  const { progress: llmProgress, loading: loadingLlmProgress, refresh: refreshLlmProgress } = useLlmBreakdownProgress();
  const { label: syncLabel, title: syncTitle } = useSyncLabel(status);
  const [firstSyncPending, setFirstSyncPending] = useState(false);
  const [firstSyncTriggered, setFirstSyncTriggered] = useState(false);
  const [activityRecoveryAttempted, setActivityRecoveryAttempted] = useState(false);
  const [focusMetricsHeight, setFocusMetricsHeight] = useState<number | null>(null);
  const focusMetricsRef = useRef<HTMLDivElement | null>(null);
  const activityReady = Boolean(status?.activityCache);
  const mappingReady = setupComplete;
  const setupSteps = useMemo(() => {
    return [
      {
        label: "Token connected",
        hint: tokenReady ? "Validated and saved" : "Add your API token",
        done: tokenReady
      },
      {
        label: "Activity cache loaded",
        hint: activityReady ? "Activity history ready" : "Fetching activity history",
        done: activityReady
      },
      {
        label: "Project mapping confirmed",
        hint: mappingReady ? "Mappings saved" : "Confirm project adjustments",
        done: mappingReady
      }
    ];
  }, [tokenReady, activityReady, mappingReady]);
  const firstIncompleteSetup = useMemo(() => setupSteps.findIndex((step) => !step.done), [setupSteps]);
  const setupChecklistActive = setupSteps.some((step) => !step.done);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const done = window.localStorage.getItem(FIRST_SYNC_KEY) === "1";
    setFirstSyncPending(!done);
  }, []);

  const periodLabel = useMemo(() => {
    if (!dashboard) return null;
    return `${dashboard.range.beg} -> ${dashboard.range.end}`;
  }, [dashboard]);
  const customRangeInvalid = Boolean(customBeg && customEnd && customBeg > customEnd);
  const customRangeSummary = useMemo(() => {
    if (!customBeg && !customEnd) return "Pick a start and end date.";
    if (!customBeg || !customEnd) return "Select both dates to apply custom range.";
    if (customRangeInvalid) return "Start date should be before end date.";
    const start = new Date(`${customBeg}T00:00:00`);
    const end = new Date(`${customEnd}T00:00:00`);
    const msInDay = 24 * 60 * 60 * 1000;
    const days = Math.round((end.getTime() - start.getTime()) / msInDay) + 1;
    return `${days} day${days === 1 ? "" : "s"} selected.`;
  }, [customBeg, customEnd, customRangeInvalid]);
  const refreshDisabled = loadingDashboard || (rangeMode === "custom" && customRangeInvalid);

  const applyCustomPreset = (days: number) => {
    const end = new Date();
    const beg = new Date(end);
    beg.setDate(end.getDate() - (days - 1));
    setRangeMode("custom");
    setCustomBeg(toDateInputValue(beg));
    setCustomEnd(toDateInputValue(end));
  };

  const clearCustomRange = () => {
    setCustomBeg("");
    setCustomEnd("");
  };

  useEffect(() => {
    if (!status || activityRecoveryAttempted) return;
    if (!activityReady) {
      setActivityRecoveryAttempted(true);
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(FIRST_SYNC_KEY);
      }
      if (!firstSyncPending) {
        setFirstSyncPending(true);
        setFirstSyncTriggered(false);
      }
    }
  }, [status, activityRecoveryAttempted, activityReady, firstSyncPending]);

  useEffect(() => {
    if (!firstSyncPending || firstSyncTriggered) return;
    setFirstSyncTriggered(true);
    refresh();
  }, [firstSyncPending, firstSyncTriggered, refresh]);

  useEffect(() => {
    if (!firstSyncPending) return;
    if (!activityReady) return;
    if (loadingDashboard || progressDisplay?.active) return;
    if (!dashboard && !dashboardError) return;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(FIRST_SYNC_KEY, "1");
    }
    setFirstSyncPending(false);
  }, [firstSyncPending, activityReady, loadingDashboard, progressDisplay, dashboard, dashboardError]);

  const noData = Boolean(dashboard?.noData);
  const dashboardWithUrgency = dashboard as DashboardHomeWithUrgency | null;
  const figures = dashboard?.figures ?? {};
  const lastWeek = dashboard?.leaderboards?.lastCompletedWeek ?? null;
  const parentBoard = lastWeek?.parentProjects?.items ?? null;
  const rootBoard = lastWeek?.rootProjects?.items ?? null;
  const metricsCurrentPeriod = dashboard?.metrics.currentPeriod ?? "";
  const metricsPreviousPeriod = dashboard?.metrics.previousPeriod ?? "";
  const healthLabel = loadingHealth ? "Checking API..." : health?.status === "ok" ? "API online" : "API offline";
  const healthTone = health?.status === "ok" ? "good" : "warn";
  const jumpTargets = [
    { id: "insights", label: "Insights" },
    { id: "weekly-trend-lifespans", label: "Trend + Lifespans" },
    { id: "stats", label: "Focus" },
    { id: "badges", label: "Badges" },
    { id: "completed-tasks", label: "Completions" },
    { id: "events", label: "Events" },
    { id: "projects", label: "Projects" },
    { id: "ops", label: "Activity & Ops" }
  ];
  const insightItems = dashboard?.insights?.items ?? Array.from({ length: 4 }).map(() => null);
  const metricItems = dashboard?.metrics.items ?? Array.from({ length: 4 }).map(() => null);
  const urgencyStatus = dashboardWithUrgency?.urgencyStatus ?? null;
  const urgencyConfigItem = dashboard?.configurableItems?.find((item) => item.key === "urgency") ?? null;
  const focusMetricItems = metricItems.filter(
    (item) => item && (item.name === "Completed Tasks" || item.name === "Rescheduled Tasks")
  );
  const secondaryMetricItems = metricItems.filter(
    (item) => item && !focusMetricItems.some((focus) => focus?.name === item.name) && item.name !== "Events" && item.name !== "Added Tasks"
  );
  const activeProjectHierarchyFigure = figures.activeProjectHierarchy ?? null;
  useEffect(() => {
    const metricsNode = focusMetricsRef.current;
    if (!metricsNode) return;

    const updateHeight = () => {
      const nextHeight = Math.ceil(metricsNode.getBoundingClientRect().height);
      setFocusMetricsHeight((currentHeight) => (currentHeight === nextHeight ? currentHeight : nextHeight));
    };

    updateHeight();
    if (typeof ResizeObserver === "undefined") return undefined;

    const observer = new ResizeObserver(() => {
      updateHeight();
    });
    observer.observe(metricsNode);
    return () => observer.disconnect();
  }, [urgencyStatus, focusMetricItems.length, metricsCurrentPeriod, metricsPreviousPeriod]);
  const urgencyTheme = {
    good: {
      background: "linear-gradient(180deg, rgba(39, 77, 66, 0.82), rgba(18, 22, 28, 0.94))",
      borderColor: "rgba(119, 212, 161, 0.35)",
      shadow: "0 16px 36px rgba(31, 108, 77, 0.15)",
      accent: "#a6f5c4",
      pillBackground: "rgba(119, 212, 161, 0.15)",
      pillBorder: "rgba(119, 212, 161, 0.45)",
      pillText: "#c7ffe0",
      chipBackground: "rgba(119, 212, 161, 0.12)",
      chipBorder: "rgba(119, 212, 161, 0.18)",
      chipText: "#e8fff1"
    },
    warn: {
      background: "linear-gradient(180deg, rgba(79, 63, 22, 0.82), rgba(21, 20, 22, 0.94))",
      borderColor: "rgba(255, 203, 107, 0.38)",
      shadow: "0 16px 36px rgba(154, 109, 18, 0.16)",
      accent: "#ffd89a",
      pillBackground: "rgba(255, 203, 107, 0.16)",
      pillBorder: "rgba(255, 203, 107, 0.52)",
      pillText: "#fff0c9",
      chipBackground: "rgba(255, 203, 107, 0.12)",
      chipBorder: "rgba(255, 203, 107, 0.18)",
      chipText: "#fff4d5"
    },
    danger: {
      background: "linear-gradient(180deg, rgba(84, 34, 31, 0.84), rgba(23, 20, 22, 0.96))",
      borderColor: "rgba(255, 133, 124, 0.4)",
      shadow: "0 16px 36px rgba(168, 64, 56, 0.16)",
      accent: "#ffb4ae",
      pillBackground: "rgba(255, 133, 124, 0.18)",
      pillBorder: "rgba(255, 133, 124, 0.52)",
      pillText: "#ffd3d0",
      chipBackground: "rgba(255, 133, 124, 0.12)",
      chipBorder: "rgba(255, 133, 124, 0.18)",
      chipText: "#ffe6e4"
    }
  } as const;
  const urgencyStatusTheme = urgencyStatus ? urgencyTheme[urgencyStatus.state] : urgencyTheme.good;
  const urgencyChips = urgencyStatus
    ? [
        { key: "fireTasks", label: "Fire", value: urgencyStatus.counts.fireTasks },
        { key: "p1Tasks", label: "P1", value: urgencyStatus.counts.p1Tasks },
        { key: "p2Tasks", label: "P2", value: urgencyStatus.counts.p2Tasks },
        { key: "dueTasks", label: "Due today", value: urgencyStatus.counts.dueTasks },
        { key: "deadlineTasks", label: "Deadline", value: urgencyStatus.counts.deadlineTasks }
      ]
    : [];
  const labelPlots = [
    {
      title: "Weekly Completion Trend",
      figure: figures.weeklyCompletionTrend,
      height: 420,
      help: PLOT_HELP.weeklyCompletionTrend
    },
    {
      title: "Task Lifespans: Time to Completion",
      figure: figures.taskLifespans,
      height: 420,
      help: PLOT_HELP.taskLifespans
    }
  ];
  const completionPlots = [
    {
      title: "Periodically Completed Tasks Per Project",
      figure: figures.completedTasksPeriodically,
      height: 520,
      help: PLOT_HELP.completedTasksPeriodically
    },
    {
      title: "Cumulative Periodically Completed Tasks Per Project",
      figure: figures.cumsumCompletedTasksPeriodically,
      height: 520,
      help: PLOT_HELP.cumsumCompletedTasksPeriodically
    }
  ];
  const eventPlots = [
    {
      title: "Heatmap of Events by Day and Hour",
      figure: figures.heatmapEventsByDayHour,
      height: 520,
      help: PLOT_HELP.heatmapEventsByDayHour
    },
    {
      title: "Events Over Time",
      figure: figures.eventsOverTime,
      height: 520,
      help: PLOT_HELP.eventsOverTime
    }
  ];
  const onAfterMutation = () => {
    refresh();
    refreshStatus();
  };
  const badgeItems = [
    { key: "p1", label: "P1", className: "badge badge-p1", value: dashboard?.badges.p1 },
    { key: "p2", label: "P2", className: "badge badge-p2", value: dashboard?.badges.p2 },
    { key: "p3", label: "P3", className: "badge badge-p3", value: dashboard?.badges.p3 },
    { key: "p4", label: "P4", className: "badge badge-p4", value: dashboard?.badges.p4 }
  ];

  const showFirstSyncOverlay =
    !setupActive && (setupChecklistActive || loadingDashboard || progressDisplay?.active || retrying);

  return (
    <div>
      <LoadingBar active={loadingDashboard || loadingStatus} />
      {showFirstSyncOverlay ? (
        <div className="firstSyncOverlay" role="status" aria-live="polite">
          <div className="firstSyncPanel">
            <p className="eyebrow">First-time sync</p>
            <h2>Preparing your dashboard</h2>
            <p className="muted">
              We are fetching your Todoist data and building the first set of charts. This can take a few minutes on
              large accounts.
            </p>
            {setupSteps.length ? (
              <div className="setupChecklist">
                <p className="eyebrow">Setup status</p>
                <div className="progressSteps">
                  {setupSteps.map((step, idx) => {
                    const state = step.done
                      ? "done"
                      : idx === firstIncompleteSetup
                        ? "active"
                        : "pending";
                    return (
                      <div key={step.label} className={`progressStep progressStep-${state}`}>
                        <span className="progressDot" />
                        <div>
                          <p className="progressLabel">{step.label}</p>
                          <p className="progressHint">{step.hint}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
            <ProgressSteps progress={progressDisplay} />
          </div>
        </div>
      ) : null}
      <header className="topbar">
        <div>
          <p className="eyebrow">Todoist Assistant</p>
          <h1>Dashboard</h1>
          <p className="lede">A fast, local dashboard for your Todoist data and automations.</p>
          <StatusPills
            items={[
              { label: healthLabel, tone: healthTone },
              { label: health?.version ? `v${health.version}` : "", tone: "neutral" },
              { label: syncLabel, tone: "neutral", title: syncTitle },
              { label: periodLabel ?? "" },
              { label: dashboardError ?? "", tone: "warn" },
              { label: error ?? "", tone: "warn" }
            ]}
          />
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
            <div className="control controlCustomRange">
              <label className="muted tiny" htmlFor="beg-input">
                Custom range
              </label>
              <div className={`customRangePanel ${customRangeInvalid ? "customRangePanelInvalid" : ""}`}>
                <div className="customRangeQuick">
                  {[7, 14, 30, 90].map((days) => (
                    <button
                      key={days}
                      type="button"
                      className="customRangeChip"
                      onClick={() => applyCustomPreset(days)}
                    >
                      Last {days}d
                    </button>
                  ))}
                  <button type="button" className="customRangeChip customRangeChipGhost" onClick={clearCustomRange}>
                    Clear
                  </button>
                </div>
                <div className="customRangeFields">
                  <label className="customRangeField" htmlFor="beg-input">
                    <span className="customRangeFieldLabel">From</span>
                    <input
                      id="beg-input"
                      className="dateInput"
                      type="date"
                      value={customBeg}
                      onChange={(e) => setCustomBeg(e.target.value)}
                    />
                  </label>
                  <span className="customRangeDivider" aria-hidden>
                    →
                  </span>
                  <label className="customRangeField" htmlFor="end-input">
                    <span className="customRangeFieldLabel">To</span>
                    <input
                      id="end-input"
                      className="dateInput"
                      type="date"
                      value={customEnd}
                      onChange={(e) => setCustomEnd(e.target.value)}
                    />
                  </label>
                </div>
                <p className={`customRangeMeta ${customRangeInvalid ? "customRangeMetaWarn" : ""}`}>
                  {customRangeSummary}
                </p>
              </div>
            </div>
          )}
          <button className="button" onClick={refresh} disabled={refreshDisabled}>
            {loadingDashboard ? "Loading..." : "Refresh"}
          </button>
          {dashboard?.refreshedAt && <p className="muted tiny">Updated {dashboard.refreshedAt}</p>}
        </div>
      </header>

      {showFirstSyncOverlay ? null : <ProgressSteps progress={progressDisplay} />}

      {!noData ? (
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
      ) : null}

      {noData ? (
        <section className="card emptyState">
          <div className="cardHeader">
            <div className="cardTitleRow">
              <h2>No activity yet</h2>
            </div>
          </div>
          <p className="muted">
            Once Todoist events start syncing, charts and insights will appear here. You can still manage automations and
            configuration in the Control Panel below.
          </p>
          <div className="emptyStateActions">
            <button className="button buttonSmall" type="button" onClick={refresh} disabled={loadingDashboard}>
              {loadingDashboard ? "Loading..." : "Retry sync"}
            </button>
          </div>
        </section>
      ) : null}

      {!noData ? (
        <section id="insights" className="insightsRow jumpTarget" aria-label="Insights">
          {insightItems.map((it, idx) =>
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
      ) : null}

      {!noData ? (
        <section id="weekly-trend-lifespans" className="grid2 jumpTarget" aria-label="Weekly trend and task lifespans">
          {labelPlots.map((plot) => (
            <PlotCard key={plot.title} {...plot} />
          ))}
        </section>
      ) : null}

      {!noData ? (
        <section id="stats" className="overviewSplit jumpTarget" aria-label="Focused metrics and project hierarchy">
          <div ref={focusMetricsRef} className="overviewMetricColumn">
            {urgencyStatus ? (
              <section
                className="card"
                style={{
                  background: urgencyStatusTheme.background,
                  borderColor: urgencyStatusTheme.borderColor,
                  boxShadow: urgencyStatusTheme.shadow,
                  minHeight: "172px"
                }}
              >
                <header className="cardHeader">
                  <div className="cardTitleRow" style={{ alignItems: "flex-start" }}>
                    <div>
                      <h2>Urgency status</h2>
                      <p className="muted tiny" style={{ margin: "6px 0 0" }}>
                        Active tasks only · as of {urgencyStatus.todayLabel}
                      </p>
                    </div>
                    <InfoTip label="About urgency status" content={METRIC_HELP["Urgency Status"] ?? DEFAULT_METRIC_HELP} />
                  </div>
                  {urgencyConfigItem?.anchor ? (
                    <a className="button buttonSmall buttonGhost" href={`/control-panel#${urgencyConfigItem.anchor}`}>
                      🔧 Configure
                    </a>
                  ) : null}
                </header>
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "16px" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      <div
                        style={{
                          fontSize: "clamp(2.75rem, 6vw, 4rem)",
                          fontWeight: 700,
                          lineHeight: 0.95,
                          color: urgencyStatusTheme.accent,
                          letterSpacing: "-0.03em"
                        }}
                      >
                        {urgencyStatus.total}
                      </div>
                      <div style={{ color: urgencyStatusTheme.accent, fontSize: "1rem", fontWeight: 600 }}>
                        {urgencyStatus.title}
                      </div>
                    </div>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: "0.55rem 0.95rem",
                        borderRadius: "999px",
                        background: urgencyStatusTheme.pillBackground,
                        color: urgencyStatusTheme.pillText,
                        border: `1px solid ${urgencyStatusTheme.pillBorder}`,
                        fontSize: "0.95rem",
                        fontWeight: 700,
                        letterSpacing: "0.04em",
                        textTransform: "uppercase",
                        whiteSpace: "nowrap"
                      }}
                    >
                      {urgencyStatus.badgeLabel}
                    </span>
                  </div>
                  <p className="muted" style={{ margin: 0, lineHeight: 1.55 }}>
                    {urgencyStatus.summary}
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                    {urgencyChips.map((chip) => {
                      const tone = chip.value > 0 ? "1" : "0.7";
                      return (
                        <span
                          key={chip.key}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px",
                            padding: "0.45rem 0.7rem",
                            borderRadius: "999px",
                            background: urgencyStatusTheme.chipBackground,
                            color: urgencyStatusTheme.chipText,
                            border: `1px solid ${urgencyStatusTheme.chipBorder}`,
                            fontSize: "0.86rem",
                            fontWeight: 600,
                            opacity: tone
                          }}
                        >
                          <span>{chip.label}</span>
                          <span style={{ fontVariantNumeric: "tabular-nums" }}>{chip.value}</span>
                        </span>
                      );
                    })}
                  </div>
                </div>
              </section>
            ) : (
              <div className="stat skeleton" style={{ minHeight: "172px" }} />
            )}
            {focusMetricItems.length ? (
              focusMetricItems.map((m) =>
                m ? (
                  <StatCard
                    key={m.name}
                    name={m.name}
                    value={m.value}
                    deltaPercent={m.deltaPercent}
                    inverseDelta={m.inverseDelta}
                    currentPeriod={m.currentPeriod ?? metricsCurrentPeriod}
                    previousPeriod={m.previousPeriod ?? metricsPreviousPeriod}
                    currentLabel={m.currentLabel}
                    previousLabel={m.previousLabel}
                    help={METRIC_HELP[m.name] ?? DEFAULT_METRIC_HELP}
                  />
                ) : null
              )
            ) : (
              <>
                <div className="stat skeleton" />
                <div className="stat skeleton" />
              </>
            )}
          </div>
          <div
            id="projects"
            className="overviewPlotColumn jumpTarget"
            style={focusMetricsHeight ? { height: `${focusMetricsHeight}px` } : undefined}
          >
            <section className="card cardFillHeight hierarchyCard">
              <header className="cardHeader hierarchyCardHeader">
                <div className="hierarchyCardHeaderTop">
                  <div className="cardTitleRow">
                    <h2>Active Project Hierarchy</h2>
                    <InfoTip label="About active project hierarchy" content={PLOT_HELP.activeProjectHierarchy} />
                  </div>
                </div>
                <p className="muted hierarchyCardLead">
                  Sunburst view of active roots and subprojects, tuned to match the dashboard palette.
                </p>
              </header>
              <div className="cardBody cardBodyFill hierarchyCardBody">
                <div className="hierarchyPlotStage">
                  {!activeProjectHierarchyFigure ? (
                    <div className="skeleton hierarchyPlotSkeleton" />
                  ) : (
                    <Plot
                      data={activeProjectHierarchyFigure.data as PlotParams["data"]}
                      layout={buildHierarchyFigureLayout(activeProjectHierarchyFigure)}
                      config={{
                        displayModeBar: true,
                        responsive: true,
                        scrollZoom: true,
                        doubleClick: "reset+autosize"
                      }}
                      useResizeHandler
                      style={{ width: "100%", height: "100%" }}
                    />
                  )}
                </div>
              </div>
            </section>
          </div>
        </section>
      ) : null}

      {!noData ? (
        <section id="badges" className="jumpTarget" aria-label="Priority badges">
          <div className="sectionHeader">
            <h2>Priority badges</h2>
            <InfoTip label="About priority badges" content={BADGES_HELP} />
          </div>
          <div className="badges">
            {badgeItems.map((item) => (
              <span key={item.key} className={item.className}>
                {item.label} {item.value ?? "-"}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {!noData ? (
        <section id="completed-tasks" className="stack jumpTarget" aria-label="Completed tasks per project">
          {completionPlots.map((plot) => (
            <PlotCard key={plot.title} {...plot} />
          ))}
        </section>
      ) : null}

      {!noData ? (
        <section id="events" className="stack jumpTarget" aria-label="Event trends">
          {eventPlots.map((plot) => (
            <PlotCard key={plot.title} {...plot} />
          ))}
        </section>
      ) : null}

      {!noData && secondaryMetricItems.length ? (
        <section className="statsRow jumpTarget" aria-label="Additional stats">
          {secondaryMetricItems.map((m) =>
            m ? (
              <StatCard
                key={m.name}
                name={m.name}
                value={m.value}
                deltaPercent={m.deltaPercent}
                inverseDelta={m.inverseDelta}
                currentPeriod={m.currentPeriod ?? metricsCurrentPeriod}
                previousPeriod={m.previousPeriod ?? metricsPreviousPeriod}
                currentLabel={m.currentLabel}
                previousLabel={m.previousLabel}
                help={METRIC_HELP[m.name] ?? DEFAULT_METRIC_HELP}
              />
            ) : null
          )}
        </section>
      ) : null}

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
          <AdminPanel onAfterMutation={onAfterMutation} />

          <LlmBreakdownStatus
            progress={llmProgress}
            loading={loadingLlmProgress}
            onRefresh={refreshLlmProgress}
          />

          <ObserverControl onAfterMutation={onAfterMutation} />

          <ServiceMonitor
            services={status?.services ?? null}
            configurableItems={status?.configurableItems}
            onRefresh={refreshStatus}
          />
        </section>
      </section>
    </div>
  );
}
