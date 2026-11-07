"use client";

import { useEffect, useMemo, useState } from "react";
import { DashboardSettings } from "../components/DashboardSettings";
import { LeaderboardCard } from "../components/LeaderboardCard";
import { LoadingBar } from "../components/LoadingBar";
import { MobileAbout } from "../components/MobileAbout";
import { MobilePlotCard } from "../components/MobilePlotCard";
import { PlotCard } from "../components/PlotCard";
import { StatCard } from "../components/StatCard";
import { DeferredPlot } from "./DeferredPlot";
import { ProjectGrouping } from "./ProjectGrouping";
import { PLOT_HELP } from "../lib/dashboardCopy";
import {
  command,
  completionFigure,
  mobileSettings,
  mobileSettingsRequest,
  mobileForecastAvailable,
  mobileHistoryEnd,
  mobileHistoryStart,
  projectColor,
  weekDate,
} from "../lib/mobile";
import type { MobileState } from "../lib/mobile";
import {
  calendarCompletionFigure,
  eventsFigure,
  heatmapFigure,
  hierarchyFigure,
  lifespanFigure,
  paceWindowAvailable,
  projectTimelineFigure,
  taskCountsFigure,
  weeklyPaceFigure,
} from "../lib/mobilePlots";

const TABS = ["Overview", "Projects", "Activity", "Control Panel"] as const;
type Tab = (typeof TABS)[number];
const INITIAL_UI = {
  tab: "Overview" as Tab,
  query: "",
  priority: 0,
  range: 8,
  week: 7,
  granularity: "week" as "week" | "month" | "quarter",
};

function restoredUi(value: unknown): { ui: typeof INITIAL_UI; valid: boolean } {
  const ui = { ...INITIAL_UI };
  if (value === null) return { ui, valid: true };
  if (typeof value !== "object" || Array.isArray(value)) return { ui, valid: false };
  const saved = value as Record<string, unknown>;
  let valid = true;
  if ("tab" in saved) {
    if (typeof saved.tab === "string" && TABS.some((tab) => tab === saved.tab)) ui.tab = saved.tab as Tab;
    else valid = false;
  }
  if ("query" in saved) {
    if (typeof saved.query === "string") ui.query = saved.query;
    else valid = false;
  }
  if ("priority" in saved) {
    if (typeof saved.priority === "number" && Number.isInteger(saved.priority) && saved.priority >= 0 && saved.priority <= 4) ui.priority = saved.priority;
    else valid = false;
  }
  if ("range" in saved) {
    if (typeof saved.range === "number" && [0, 4, 8, 26, 52].includes(saved.range)) ui.range = saved.range;
    else valid = false;
  }
  if ("week" in saved) {
    if (typeof saved.week === "number" && Number.isSafeInteger(saved.week) && saved.week <= 8) ui.week = saved.week;
    else valid = false;
  }
  if ("granularity" in saved) {
    if (saved.granularity === "week" || saved.granularity === "month" || saved.granularity === "quarter") ui.granularity = saved.granularity;
    else valid = false;
  }
  return { ui, valid };
}

export default function AndroidDashboard() {
  const [state, setState] = useState<MobileState | null>(null);
  const [ui, setUi] = useState(INITIAL_UI);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  const [storageInvalid, setStorageInvalid] = useState(false);
  const [persist, setPersist] = useState(false);
  const [paceWindow, setPaceWindow] = useState(3);
  const [lifespanAll, setLifespanAll] = useState(true);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [, refreshDate] = useState(0);
  useEffect(() => {
    try {
      const raw = localStorage.getItem("todoist-ui");
      try {
        const saved = restoredUi(JSON.parse(raw ?? "null"));
        setUi(saved.ui);
        setStorageInvalid(!saved.valid);
        setPersist(saved.valid);
      } catch {
        setStorageInvalid(true);
      }
    } catch {
      setStorageUnavailable(true);
    }
    const receive = (event: Event) =>
      setState((previous) => ({
        ...previous,
        ...(event as CustomEvent<MobileState>).detail,
      }));
    const fail = (event: Event) =>
      setError(String((event as CustomEvent<string>).detail));
    window.addEventListener("todoist-state", receive);
    window.addEventListener("todoist-error", fail);
    if (window.Todoist) window.Todoist.ready();
    else setError("Open this dashboard in the Android app.");
    return () => {
      window.removeEventListener("todoist-state", receive);
      window.removeEventListener("todoist-error", fail);
    };
  }, []);
  useEffect(() => {
    if (!persist) return;
    try {
      localStorage.setItem("todoist-ui", JSON.stringify(ui));
    } catch {
      setStorageUnavailable(true);
    }
  }, [ui, persist]);
  useEffect(() => {
    if (state?.message.startsWith("Sync complete.") || state?.message.startsWith("Saved on device.")) {
      setToken("");
    }
  }, [state?.message]);
  useEffect(() => {
    const back = () =>
      ui.tab === "Overview"
        ? command("close")
        : setUi((current) => ({ ...current, tab: "Overview" }));
    window.addEventListener("todoist-back", back);
    return () => window.removeEventListener("todoist-back", back);
  }, [ui.tab]);
  useEffect(() => {
    let timer = 0;
    const schedule = () => {
      window.clearTimeout(timer);
      const now = new Date();
      const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
      timer = window.setTimeout(() => {
        command("refresh-clock");
        refreshDate((value) => value + 1);
        schedule();
      }, Math.max(1, next.getTime() - now.getTime() + 50));
    };
    const resume = () => {
      if (document.visibilityState !== "visible") return;
      command("refresh-clock");
      refreshDate((value) => value + 1);
      schedule();
    };
    schedule();
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("focus", resume);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("focus", resume);
    };
  }, []);
  const patch = (value: Partial<typeof ui>) => {
    setStorageInvalid(false);
    setPersist(true);
    setUi((current) => ({ ...current, ...value }));
  };
  const model = state?.model;
  const settings = state?.preferences
    ? mobileSettings(state.preferences)
    : null;
  const eventsKey = JSON.stringify(settings?.plotEvents ?? []);
  const figures = useMemo(
    () =>
      model
        ? [false, true].map((cumulative) =>
            ui.granularity === "week"
              ? completionFigure(model, ui.range, JSON.parse(eventsKey), cumulative)
              : calendarCompletionFigure(model, ui.range, ui.granularity, cumulative),
          )
        : [],
    [model, ui.range, ui.granularity, eventsKey],
  );
  const analysis = useMemo(() => {
    if (!model?.plotData) return null;
    return {
      pace: weeklyPaceFigure(model, paceWindow),
      lifespan: lifespanFigure(model, ui.range, lifespanAll),
      hierarchy: hierarchyFigure(model, ui.range),
      heatmap: heatmapFigure(model, ui.range),
      events: eventsFigure(model, ui.range),
      taskCounts: taskCountsFigure(model, ui.range),
      timeline: timelineOpen ? projectTimelineFigure(model, ui.range) : null,
    };
  }, [model, ui.range, paceWindow, lifespanAll, timelineOpen]);
  const busy = state?.loading || state?.syncing;
  const matches =
    model?.tasks.filter(
      (task) =>
        (!ui.priority || task.priority === ui.priority) &&
        `${task.content} ${task.project} ${task.labels.join(" ")}`
          .toLowerCase()
          .includes(ui.query.trim().toLowerCase()),
    ) ?? [];
  const counts = model?.weeklyProjects[ui.week + model.weeks.length - 9] ?? {};
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const leaderboard = model
    ? Object.entries(counts)
        .map(([name, completed]) => ({
          name,
          completed,
          percentOfCompleted: total ? (100 * completed) / total : 0,
          color: projectColor(model, name),
        }))
        .sort((a, b) => b.completed - a.completed)
    : [];
  const alert = state?.alert;
  const historyStart = model ? mobileHistoryStart(model) : "";
  const historyAsOf = model ? mobileHistoryEnd(model) : "";
  const localNow = new Date();
  const today = `${localNow.getFullYear()}-${String(localNow.getMonth() + 1).padStart(2, "0")}-${String(localNow.getDate()).padStart(2, "0")}`;
  const monday = new Date(localNow.getFullYear(), localNow.getMonth(), localNow.getDate() - (localNow.getDay() + 6) % 7);
  const currentWeek = `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
  const snapshotTime = model ? Date.parse(model.syncedAt) : NaN;
  const activityTime = model?.activitySyncedAt ? Date.parse(model.activitySyncedAt) : snapshotTime;
  const activityBehindSnapshot = Number.isFinite(activityTime) && Number.isFinite(snapshotTime) && activityTime < snapshotTime;
  const staleActivity = Boolean(model?.historyAvailable && (
    (historyAsOf && historyAsOf < today) ||
    activityBehindSnapshot
  ));
  const activityLabel = model?.activitySyncedAt && Number.isFinite(activityTime)
    ? new Date(activityTime).toLocaleString()
    : historyAsOf;
  const weekStart = model?.weekStart ?? "";
  const weekUnavailable = Boolean(model?.historyAvailable && (
    weekStart !== currentWeek ||
    (historyAsOf && historyAsOf < weekStart) ||
    historyStart === "9999-12-31"
  ));
  const weekPartial = Boolean(!weekUnavailable && model?.historyAvailable && (
    (historyStart && historyStart > weekStart) ||
    (historyAsOf && historyAsOf >= weekStart && historyAsOf < today) ||
    activityBehindSnapshot
  ));
  const selectedWeek = model ? weekDate(model.weekStart, ui.week - 8) : "";
  const selectedWeekEnd = model ? weekDate(model.weekStart, ui.week - 8, 6) : "";
  const selectedUnavailable = Boolean(
    (historyAsOf && selectedWeek > historyAsOf) ||
    (historyStart && selectedWeekEnd < historyStart)
  );
  const selectedPartial = Boolean(!selectedUnavailable && (
    (historyStart && selectedWeek < historyStart) ||
    (historyAsOf && historyAsOf < today && historyAsOf < selectedWeekEnd) ||
    (activityBehindSnapshot && selectedWeek <= historyAsOf && historyAsOf <= selectedWeekEnd)
  ));
  const alertTitle = !alert?.enabled
    ? "Monitoring paused"
    : alert.level === 2
      ? "Urgent attention needed"
      : alert.level === 1
        ? "Attention needed"
        : "All clear";
  const connect = () => {
    if (!token.trim()) {
      setError("Enter your Todoist API token.");
      return;
    }
    setError("");
    command("sync", token.trim());
  };
  const disconnect = () => {
    if (
      window.confirm(
        "Disconnect and remove this account's saved data from the phone?",
      )
    ) {
      command("disconnect");
      try {
        localStorage.removeItem("todoist-ui");
      } catch {
        setStorageUnavailable(true);
      }
      setStorageInvalid(false);
      setPersist(true);
      setUi(INITIAL_UI);
    }
  };

  return (
    <>
      <LoadingBar active={Boolean(busy)} />
      <header className="topbar">
        <div>
          <p className="eyebrow">todometry</p>
          <h1>{ui.tab === "Overview" ? "Dashboard" : ui.tab}</h1>
          <div className="statusPills">
            {state?.demo && <span className="pill pill-neutral">Demo</span>}
            {model && (
              <span className="muted tiny">
                Tasks and projects: {new Date(model.syncedAt).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
          </div>
        </div>
        <div className="controls">
          {state?.demo && (
            <button
              className="button buttonSmall buttonGhost"
              onClick={() => command("account")}
            >
              Back to my data
            </button>
          )}
          {state?.connected && !state.demo && (
            <button
              className="button buttonSmall"
              onClick={() => command("sync")}
              disabled={busy}
            >
              {model ? "Refresh" : "Retry sync"}
            </button>
          )}
          {state?.syncing && (
            <button
              className="button buttonSmall buttonGhost"
              onClick={() => command("cancel")}
            >
              Cancel sync
            </button>
          )}
        </div>
      </header>
      <nav className="segmented mobileNav" aria-label="Dashboard sections">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`seg ${ui.tab === tab ? "segActive" : ""}`}
            aria-current={ui.tab === tab ? "page" : undefined}
            onClick={() => {
              patch({ tab, query: "", priority: 0 });
              setError("");
            }}
          >
            {tab}
          </button>
        ))}
      </nav>
      {error && (
        <p className="pill pill-warn" role="alert">
          {error}
        </p>
      )}
      {storageUnavailable && (
        <p className="tiny mobileNotice" role="status">
          View preferences could not be saved on this device.
        </p>
      )}
      {storageInvalid && (
        <p className="tiny mobileNotice" role="status">
          Some saved view preferences are invalid. Safe defaults are in use until you change a view.
        </p>
      )}
      {state?.syncing ? (
        <div className="mobileSync" role="status" aria-live="polite">
          <strong>Syncing with Todoist</strong>
          <span>{state.message}</span>
          <span className="muted tiny">
            {model
              ? "You can browse your saved data while syncing."
              : "The first sync loads your available history and may take a while."}
          </span>
        </div>
      ) : state?.message && !state.demo ? (
        <p className="tiny mobileNotice" role="status">{state.message}</p>
      ) : null}
      {!state && !error && <p className="muted">Opening dashboard…</p>}

      {state && (!model || ui.tab === "Control Panel") && (
        <section className="card">
          <header className="cardHeader">
            <h2>Todoist account</h2>
            {state.connected && (
              <span className="pill pill-neutral">Account saved</span>
            )}
          </header>
          <p className="muted tiny">Connect directly to Todoist. Your token is encrypted on this device.</p>
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              connect();
            }}
          >
            <label className="control">
              API token
              <input
                type="password"
                className="textInput"
                autoComplete="off"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                disabled={busy}
              />
            </label>
            <div className="controls">
              <button
                className="button buttonSmall"
                type="submit"
                disabled={busy}
              >
                Connect and sync
              </button>
              {!state.demo && (
                <button
                  className="button buttonSmall buttonGhost"
                  type="button"
                  onClick={() => command("demo")}
                  disabled={busy}
                >
                  Explore a demo
                </button>
              )}
              {(state.connected || state.savedHistory) && (
                <button
                  className="button buttonSmall buttonGhost"
                  type="button"
                  onClick={disconnect}
                  disabled={busy}
                >
                  Disconnect
                </button>
              )}
            </div>
          </form>
        </section>
      )}
      {state && ui.tab === "Control Panel" && (
        <>
          <ProjectGrouping model={model ?? null} enabled={Boolean(state.connected && model && !state.demo)} busy={Boolean(busy)} message={state.message} />
          <DashboardSettings
            request={mobileSettingsRequest}
            onAfterMutation={() => setError("")}
          />
          <MobileAbout version={state.version} preview={state.preview} />
        </>
      )}

      {model && ui.tab === "Overview" && (
        <>
          <div className="statsRow mobileStats">
            {model.historyAvailable && !weekUnavailable ? (
              <StatCard
                name={weekPartial ? "This week (partial)" : "This week"}
                value={model.weeks[model.weeks.length - 1]}
                deltaPercent={null}
                inverseDelta={false}
                currentPeriod={model.weekStart}
                previousPeriod={weekDate(model.weekStart, -1)}
                comparison={false}
              />
            ) : (
              <section className="stat">
                <p className="muted">Completed this week</p>
                <p>{model.historyAvailable ? "Current week unavailable" : "History unavailable"}</p>
              </section>
            )}
            <section className="stat mobileUrgency" data-level={alert?.level}>
              <div className="statTop">
                <p className="muted">Urgency</p>
              </div>
              <p className="statValue">{alert ? alert.matches : "Unavailable"}</p>
              <button
                className="mobileRuleLink"
                onClick={() => patch({ tab: "Control Panel" })}
              >
                {alert ? alertTitle : "Attention rules unavailable"}
              </button>
              <p className="muted tiny">
                {model.tasks.length} active tasks · P1 {model.priorities[0]} ·
                P2 {model.priorities[1]}
              </p>
            </section>
          </div>
          {!model.historyAvailable ? (
            <>
              <p className="pill pill-warn">Completion history unavailable. {model.historyWarning}</p>
              {analysis && <><p className="muted tiny">Only the current active-task snapshot is available.</p><DeferredPlot title="Active Tasks by Priority" height={310}><MobilePlotCard title="Active Tasks by Priority" figure={analysis.taskCounts} height={310} help={PLOT_HELP.taskCountTrend} /></DeferredPlot></>}
            </>
          ) : (
            <>
              {staleActivity && (
                <p className="pill pill-warn">Activity is out of date{activityLabel ? `; last refreshed ${activityLabel}` : ""}. Refresh to update it.</p>
              )}
              {!staleActivity && model.activitySyncedAt && activityLabel && <p className="muted tiny">Activity through {activityLabel}; today is still in progress.</p>}
              {model.activity.length === 0 && <p className="muted tiny">No activity found in the history stored on this device.</p>}
              <p className="muted tiny">Totals use activity returned by Todoist; older history may be limited by your plan.</p>
              {model.historyWarning && (
                <p className="pill pill-warn">{model.historyWarning}</p>
              )}
              {model.plotData?.historyComplete === false && <p className="muted tiny">History is incomplete; earlier periods may change or be omitted as sync continues.</p>}
              <div className="controls mobilePlotControls">
                <label className="control">
                  <span className="muted tiny">Range</span>
                  <select
                    className="select"
                    value={ui.range}
                    onChange={(event) =>
                      patch({ range: Number(event.target.value) })
                    }
                  >
                    <option value={4}>Last 4 weeks</option>
                    <option value={8}>Last 8 weeks</option>
                    <option value={26}>Last 26 weeks</option>
                    <option value={52}>Last 52 weeks</option>
                    <option value={0}>All available history</option>
                  </select>
                </label>
                {model.plotData?.dailyActivity.some((day) => day.projects !== undefined) && (
                  <label className="control">
                    <span className="muted tiny">Period</span>
                    <select className="select" value={ui.granularity} onChange={(event) => patch({ granularity: event.target.value as typeof ui.granularity })}>
                      <option value="week">Weekly</option>
                      <option value="month">Monthly</option>
                      <option value="quarter">Quarterly</option>
                    </select>
                  </label>
                )}
                {mobileForecastAvailable(model) && ui.granularity === "week" && (
                  <span className="pill pill-neutral">
                    Forecast: {model.forecast}
                  </span>
                )}
              </div>
              {ui.granularity !== "week" && <p className="muted tiny">Calendar periods show actual completions; the current period is still in progress.</p>}
              {analysis && (
                <>
                  <div className="controls mobilePlotControls">
                    <label className="control"><span className="muted tiny">Weekly pace comparison</span>
                      <select className="select" value={paceWindow} onChange={(event) => setPaceWindow(Number(event.target.value))}>
                        <option value={3}>3-week baseline</option><option value={6} disabled={!paceWindowAvailable(model, 6)}>Add 6-week baseline</option><option value={12} disabled={!paceWindowAvailable(model, 12)}>Add 12-week baseline</option><option value={24} disabled={!paceWindowAvailable(model, 24)}>Add 24-week baseline</option>
                      </select>
                    </label>
                  </div>
                  {paceWindow !== 3 && !paceWindowAvailable(model, paceWindow) && <p className="muted tiny">The selected {paceWindow}-week baseline is unavailable for the current history.</p>}
                  <DeferredPlot title="Weekly Completion Trend" height={310}><MobilePlotCard title="Weekly Completion Trend" figure={analysis.pace} height={310} help={PLOT_HELP.weeklyCompletionTrend} /></DeferredPlot>
                  <DeferredPlot title="Task Lifespans: Time to Completion" height={310}><PlotCard title="Task Lifespans: Time to Completion" figure={analysis.lifespan} height={310} compact help={PLOT_HELP.taskLifespans} actions={
                    <select aria-label="Task lifespan date range" className="select" value={lifespanAll ? "all" : "period"} onChange={(event) => setLifespanAll(event.target.value === "all")}>
                      <option value="all">All time</option><option value="period">Selected period</option>
                    </select>
                  } /></DeferredPlot>
                  <DeferredPlot title="Project Hierarchy" height={380}><PlotCard title="Project Hierarchy" figure={analysis.hierarchy} height={380} compact help={PLOT_HELP.activeProjectHierarchy} /></DeferredPlot>
                </>
              )}
              <MobilePlotCard
                title="Completed tasks"
                figure={figures[0]}
                height={340}
                help={ui.granularity === "week" ? PLOT_HELP.completedTasksPeriodically : "Actual completed tasks per project in each calendar period. The current period is incomplete; forecasts are shown in the weekly view."}
              />
              <section className="card">
                <header className="cardHeader">
                  <h2>Project contributions</h2>
                  <select
                    aria-label="Contribution week"
                    className="select"
                    value={ui.week}
                    onChange={(event) =>
                      patch({ week: Number(event.target.value) })
                    }
                  >
                    {model.weeks.map((_, i) => (
                      <option key={i} value={i - model.weeks.length + 9}>
                        {i === model.weeks.length - 1
                          ? weekStart === currentWeek ? "This week" : "Snapshot week"
                          : i === model.weeks.length - 2 && weekStart === currentWeek
                            ? "Last completed week"
                            : weekDate(model.weekStart, i - model.weeks.length + 1)}
                      </option>
                    ))}
                  </select>
                </header>
                {selectedUnavailable ? (
                  <p className="muted">History is unavailable for this week.</p>
                ) : leaderboard.length ? (
                  <>{selectedPartial && <p className="muted tiny">This week has partial history.</p>}<LeaderboardCard items={leaderboard} /></>
                ) : (
                  <p className="muted">{selectedPartial ? "No completions recorded in the available part of this week." : "No completions in this week."}</p>
                )}
              </section>
              <MobilePlotCard
                title="Cumulative completions"
                figure={figures[1]}
                height={320}
              />
              {analysis && (
                <>
                  <p className="muted tiny">Dates and activity hours use your device time zone.</p>
                  <DeferredPlot title="Heatmap of Events by Day and Hour" height={290}><PlotCard title="Heatmap of Events by Day and Hour" figure={analysis.heatmap} height={290} compact help={PLOT_HELP.heatmapEventsByDayHour} /></DeferredPlot>
                  <DeferredPlot title="Events Over Time" height={310}><MobilePlotCard title="Events Over Time" figure={analysis.events} height={310} help={PLOT_HELP.eventsOverTime} /></DeferredPlot>
                  <p className="muted tiny">Active-task history is estimated from cached activity and current tasks.</p>
                  <DeferredPlot title="Active Tasks by Priority" height={310}><MobilePlotCard title="Active Tasks by Priority" figure={analysis.taskCounts} height={310} help={PLOT_HELP.taskCountTrend} /></DeferredPlot>
                  <div className="card">
                    <div className="cardHeader"><h2>Project Timeline</h2><button type="button" className="button buttonSmall buttonGhost" onClick={() => setTimelineOpen(!timelineOpen)}>{timelineOpen ? "Hide" : "Show"}</button></div>
                    <p className="muted tiny">Starts use the earliest known date. Where an archive date is missing, the timeline ends at the last observed activity.</p>
                    {timelineOpen && analysis.timeline && <div style={{ maxHeight: 620, overflowY: "auto" }}><PlotCard title="Timeline" figure={analysis.timeline.figure} height={Math.max(320, analysis.timeline.rows * 26)} compact /></div>}
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}

      {model && (ui.tab === "Projects" || ui.tab === "Activity") && (
        <div className="controls mobileSearch">
          <label className="control">
            <span className="muted tiny">Search</span>
            <input
              className="textInput"
              type="search"
              aria-label="Search tasks, projects or activity"
              placeholder={
                ui.tab === "Projects"
                  ? "Tasks, projects, labels"
                  : "Recent activity"
              }
              value={ui.query}
              onChange={(event) => patch({ query: event.target.value })}
            />
          </label>
          {ui.tab === "Projects" && (
            <label className="control">
              <span className="muted tiny">Priority</span>
              <select
                className="select"
                aria-label="Filter task priority"
                value={ui.priority}
                onChange={(event) =>
                  patch({ priority: Number(event.target.value) })
                }
              >
                <option value={0}>All</option>
                {[4, 3, 2, 1].map((value) => (
                  <option key={value} value={value}>
                    P{5 - value}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}
      {model && ui.tab === "Projects" && (
        <>
          <p className="muted tiny">
            {matches.length} of {model.tasks.length} active tasks
          </p>
          {model.projects.length === 0 && <p className="muted">No projects are available on this device.</p>}
          {model.projects.map((project) => {
            const tasks = matches.filter(
              (task) => task.projectId === project.id,
            );
            if (!tasks.length && (ui.query || ui.priority)) return null;
            return (
              <details
                key={project.id}
                className="card mobileProject"
                open={Boolean(ui.query || ui.priority)}
              >
                <summary>
                  <span>{project.path}</span>
                  <span className="pill pill-neutral">{tasks.length}</span>
                </summary>
                {tasks.length ? (
                  tasks.map((task) => (
                    <article className="mobileTask" key={task.id}>
                      <div>
                        <strong>{task.content}</strong>
                        <p className="muted tiny">
                          {[
                            task.due,
                            ...task.labels.map((label) => `#${label}`),
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                        {task.deadline && (
                          <p className="muted tiny">
                            Deadline: {task.deadline}
                          </p>
                        )}
                      </div>
                      <span
                        className={`pill pill-${task.priority === 4 ? "warn" : "neutral"}`}
                      >
                        P{5 - task.priority}
                      </span>
                    </article>
                  ))
                ) : (
                  <p className="muted tiny">No active tasks.</p>
                )}
              </details>
            );
          })}
          {!matches.length && (ui.query || ui.priority) && (
            <p className="muted">No tasks match.</p>
          )}
        </>
      )}
      {model && ui.tab === "Activity" && (
        <section className="card">
          <header className="cardHeader">
            <h2>Recent activity</h2>
          </header>
          {model.activity.length === 0 && (
            <p className="muted">{model.historyAvailable ? "No activity in the available history." : "Activity history is unavailable."}</p>
          )}
          {model.activity.length > 0 && ui.query.trim() && !model.activity.some((event) =>
            `${event.kind === "uncompleted" ? "undone" : event.kind} ${event.content} ${event.project}`.toLowerCase().includes(ui.query.trim().toLowerCase()),
          ) && <p className="muted">No activity matches your search.</p>}
          {model.activity
            .filter((event) =>
              `${event.kind === "uncompleted" ? "undone" : event.kind} ${event.content} ${event.project}`
                .toLowerCase()
                .includes(ui.query.trim().toLowerCase()),
            )
            .map((event) => (
              <article className="mobileTask" key={event.id}>
                <div>
                  <strong>{event.content || event.project}</strong>
                  <p className="muted tiny">
                    {event.project} · {new Date(event.date).toLocaleString()}
                  </p>
                </div>
                <span className="pill pill-neutral">
                  {event.kind === "uncompleted" ? "Undone" : event.kind}
                </span>
              </article>
            ))}
        </section>
      )}
    </>
  );
}
