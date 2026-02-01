"use client";

import { useEffect, useMemo, useState } from "react";
import { PlotCard } from "./PlotCard";
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
import {
  useApiHealth,
  useDashboardHome,
  useDashboardStatus,
  useLlmBreakdownProgress,
  useSyncLabel
} from "../lib/dashboardHooks";

const FIRST_SYNC_KEY = "todoist-assistant.firstSyncComplete";

export function DashboardView({ setupActive = false }: { setupActive?: boolean }) {
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
  } = useDashboardHome({ enabled: !setupActive });
  const { status, loadingStatus, refreshStatus } = useDashboardStatus();
  const { progress: llmProgress, loading: loadingLlmProgress, refresh: refreshLlmProgress } = useLlmBreakdownProgress();
  const { label: syncLabel, title: syncTitle } = useSyncLabel(status);
  const [firstSyncPending, setFirstSyncPending] = useState(false);
  const [firstSyncTriggered, setFirstSyncTriggered] = useState(false);
  const [activityRecoveryAttempted, setActivityRecoveryAttempted] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const done = window.localStorage.getItem(FIRST_SYNC_KEY) === "1";
    setFirstSyncPending(!done);
  }, []);

  const periodLabel = useMemo(() => {
    if (!dashboard) return null;
    return `${dashboard.range.beg} -> ${dashboard.range.end}`;
  }, [dashboard]);

  useEffect(() => {
    if (!status || activityRecoveryAttempted) return;
    if (!status.activityCache) {
      setActivityRecoveryAttempted(true);
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(FIRST_SYNC_KEY);
      }
      if (!firstSyncPending) {
        setFirstSyncPending(true);
        setFirstSyncTriggered(false);
      }
    }
  }, [status, activityRecoveryAttempted, firstSyncPending]);

  useEffect(() => {
    if (!firstSyncPending || firstSyncTriggered) return;
    setFirstSyncTriggered(true);
    refresh();
  }, [firstSyncPending, firstSyncTriggered, refresh]);

  useEffect(() => {
    if (!firstSyncPending) return;
    if (loadingDashboard || progressDisplay?.active) return;
    if (!dashboard && !dashboardError) return;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(FIRST_SYNC_KEY, "1");
    }
    setFirstSyncPending(false);
  }, [firstSyncPending, loadingDashboard, progressDisplay, dashboard, dashboardError]);

  const noData = Boolean(dashboard?.noData);
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
    { id: "labels-lifespans", label: "Labels + Lifespans" },
    { id: "stats", label: "Stats" },
    { id: "badges", label: "Badges" },
    { id: "completed-tasks", label: "Completions" },
    { id: "events", label: "Events" },
    { id: "ops", label: "Activity & Ops" }
  ];
  const insightItems = dashboard?.insights?.items ?? Array.from({ length: 4 }).map(() => null);
  const metricItems = dashboard?.metrics.items ?? Array.from({ length: 4 }).map(() => null);
  const labelPlots = [
    {
      title: "Most Popular Labels",
      figure: figures.mostPopularLabels,
      height: 420,
      help: PLOT_HELP.mostPopularLabels
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

  const showFirstSyncOverlay = firstSyncPending && (loadingDashboard || progressDisplay?.active);

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
        <section id="labels-lifespans" className="grid2 jumpTarget" aria-label="Labels and task lifespans">
          {labelPlots.map((plot) => (
            <PlotCard key={plot.title} {...plot} />
          ))}
        </section>
      ) : null}

      {!noData ? (
        <section id="stats" className="statsRow jumpTarget" aria-label="Key stats">
          {metricItems.map((m, idx) =>
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

          <ServiceMonitor services={status?.services ?? null} onRefresh={refreshStatus} />
        </section>
      </section>
    </div>
  );
}
