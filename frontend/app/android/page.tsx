"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
import type { MobileModel, MobileState } from "../lib/mobile";
import {
  calendarCompletionFigure,
  eventsFigure,
  heatmapFigure,
  hierarchyFigure,
  lifespanFigure,
  paceWindowAvailable,
  taskCountsFigure,
  weeklyPaceFigure,
} from "../lib/mobilePlots";

const TABS = ["Overview", "Projects", "Activity", "Control Panel"] as const;
const SETTINGS_DRAFT_KEY = "todometry-android-dashboard-settings-draft";
type Tab = (typeof TABS)[number];
const INITIAL_UI = {
  tab: "Overview" as Tab,
  projectQuery: "",
  activityQuery: "",
  openProjects: [] as string[],
  priority: 0,
  range: 8,
  week: 7,
  granularity: "week" as "week" | "month" | "quarter",
  paceWindow: 3,
  lifespanAll: true,
  timelineOpen: false,
  timelineStart: "",
  timelineEnd: "",
  timelineProject: "",
  groupingDraft: { search: "", source: "", target: "", customSource: "", customTarget: "" },
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
    if (typeof saved.query === "string") {
      if (ui.tab === "Activity") ui.activityQuery = saved.query;
      else ui.projectQuery = saved.query;
    }
    else valid = false;
  }
  for (const key of ["projectQuery", "activityQuery", "timelineProject"] as const) {
    if (key in saved) {
      if (typeof saved[key] === "string") ui[key] = saved[key];
      else valid = false;
    }
  }
  if ("openProjects" in saved) {
    if (Array.isArray(saved.openProjects) && saved.openProjects.every((id) => typeof id === "string")) ui.openProjects = [...new Set(saved.openProjects as string[])];
    else valid = false;
  }
  for (const key of ["timelineStart", "timelineEnd"] as const) {
    if (key in saved) {
      const value = saved[key];
      if (typeof value === "string" && (value === "" || /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value)) ui[key] = value;
      else valid = false;
    }
  }
  if ("paceWindow" in saved) {
    if (typeof saved.paceWindow === "number" && [3, 6, 12, 24].includes(saved.paceWindow)) ui.paceWindow = saved.paceWindow;
    else valid = false;
  }
  for (const key of ["lifespanAll", "timelineOpen"] as const) {
    if (key in saved) {
      if (typeof saved[key] === "boolean") ui[key] = saved[key];
      else valid = false;
    }
  }
  if ("groupingDraft" in saved) {
    const value = saved.groupingDraft;
    if (value && typeof value === "object" && !Array.isArray(value) &&
        Object.keys(ui.groupingDraft).every((key) => typeof (value as Record<string, unknown>)[key] === "string")) {
      const draft = value as typeof ui.groupingDraft;
      ui.groupingDraft = { search: draft.search, source: draft.source, target: draft.target, customSource: draft.customSource, customTarget: draft.customTarget };
    } else valid = false;
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

function ProjectTimeline({ model, ui, patch }: {
  model: MobileModel;
  ui: typeof INITIAL_UI;
  patch: (value: Partial<typeof INITIAL_UI>) => void;
}) {
  const { timelineOpen: open, timelineStart: start, timelineEnd: end, timelineProject: selectedId } = ui;
  const [projectLimit, setProjectLimit] = useState(20);
  const [dayLimit, setDayLimit] = useState(30);
  const [taskLimit, setTaskLimit] = useState(20);
  const invalid = Boolean(start && end && start > end);
  const projects = model.plotData?.hierarchy ?? [];
  const visible = useMemo(() => {
    if (!open || invalid) return [];
    return projects.filter((project) =>
      (!end || !project.createdAt || project.createdAt <= end) &&
      (!start || !project.archived || !project.archivedAt || project.archivedAt >= start),
    ).slice().sort((a, b) => a.rootName.localeCompare(b.rootName) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
  }, [open, invalid, projects, start, end]);
  const nameCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const project of projects) {
      const key = JSON.stringify([project.parentId, project.name]);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return counts;
  }, [projects]);
  const selected = projects.find((project) => project.id === selectedId);
  const detailAvailable = Boolean(selected && Array.isArray(selected.dailyEvents) && Array.isArray(selected.dailyCompletions));
  const historyStart = mobileHistoryStart(model);
  const historyEnd = mobileHistoryEnd(model);
  const activityTime = model.activitySyncedAt ? Date.parse(model.activitySyncedAt) : NaN;
  const snapshotTime = Date.parse(model.syncedAt);
  const incomplete = !model.historyAvailable || !model.plotData?.historyComplete ||
    Boolean((start && historyStart && start < historyStart) || (end && historyEnd && end > historyEnd) ||
      (Number.isFinite(activityTime) && Number.isFinite(snapshotTime) && activityTime < snapshotTime));
  const daily = useMemo(() => {
    if (!open || !selected || invalid) return [];
    const days = new Map<string, { date: string; completions: number; events: number }>();
    for (const [rows, key] of [[selected.dailyCompletions ?? [], "completions"], [selected.dailyEvents ?? [], "events"]] as const) {
      for (const row of rows) {
        if ((start && row.date < start) || (end && row.date > end)) continue;
        const day = days.get(row.date) ?? { date: row.date, completions: 0, events: 0 };
        day[key] += row.count;
        days.set(row.date, day);
      }
    }
    return [...days.values()].sort((a, b) => b.date.localeCompare(a.date));
  }, [open, selected, invalid, start, end]);
  const tasks = useMemo(() => selected ? model.tasks.filter((task) => task.projectId === selected.id) : [], [model.tasks, selected]);
  const taskNames = useMemo(() => new Map(model.tasks.map((task) => [task.id, task.content])), [model.tasks]);
  const totals = daily.reduce((value, row) => ({ completions: value.completions + row.completions, events: value.events + row.events }), { completions: 0, events: 0 });
  const choose = (id: string) => { patch({ timelineProject: id }); setDayLimit(30); setTaskLimit(20); };
  return (
    <section className="card" aria-label="Project Timeline">
      <div className="cardHeader"><h2>Project Timeline</h2><button type="button" className="button buttonSmall buttonGhost" aria-expanded={open} onClick={() => patch({ timelineOpen: !open })}>{open ? "Hide" : "Show"}</button></div>
      {open && <>
        <p className="muted tiny">Select a project to inspect recorded activity. Dates are inclusive and use your device time zone. Project names and parents reflect the latest available metadata.</p>
        <div className="controls mobilePlotControls">
          <label className="control"><span className="muted tiny">From</span><input className="select" type="date" aria-label="Timeline start date" value={start} onChange={(event) => { patch({ timelineStart: event.target.value }); setProjectLimit(20); setDayLimit(30); }} /></label>
          <label className="control"><span className="muted tiny">Through</span><input className="select" type="date" aria-label="Timeline end date" value={end} onChange={(event) => { patch({ timelineEnd: event.target.value }); setProjectLimit(20); setDayLimit(30); }} /></label>
        </div>
        {invalid ? <p role="alert">The start date must not be after the end date.</p> : <>
          {!model.historyAvailable ? <p className="pill pill-warn">Activity history is unavailable; project metadata may still be shown.</p> : incomplete ? <p className="pill pill-warn">Only available history is shown; missing dates are not confirmed as inactive.</p> : <p className="muted tiny">History is limited to the activity available from Todoist and cached on this device.</p>}
          {model.historyAvailable && historyEnd && <p className="muted tiny">Activity available through {historyEnd}{historyStart && historyStart !== "9999-12-31" ? `; complete days from ${historyStart}` : ""}.</p>}
          {!visible.length ? <p>No projects match this date range. Projects with unknown dates remain visible.</p> : <>
            <p className="muted tiny">{visible.length} project{visible.length === 1 ? "" : "s"}. Select one for its timeline.</p>
            <div aria-label="Timeline projects" style={{ display: "grid", gap: 6 }}>
              {visible.slice(0, projectLimit).map((project) => <button type="button" className="button buttonGhost" style={{ textAlign: "left", whiteSpace: "normal", overflowWrap: "anywhere" }} aria-pressed={selectedId === project.id} data-project-id={project.id} key={project.id} onClick={() => choose(project.id)}>
                {project.name}{project.parentId ? ` · ${project.rootName}` : ""}{(nameCounts.get(JSON.stringify([project.parentId, project.name])) ?? 0) > 1 ? ` · ID ${project.id}` : ""} {project.metadataKnown === false ? "· Status unavailable" : project.archived ? "· Archived" : "· Active"}
              </button>)}
            </div>
            {visible.length > projectLimit && <button type="button" className="button buttonSmall" onClick={() => setProjectLimit((value) => value + 20)}>Show more projects</button>}
          </>}
          {selected && <section aria-label="Selected project timeline" style={{ marginTop: 16 }}>
            <h3 style={{ overflowWrap: "anywhere" }}>{selected.name}</h3>
            {selected.parentId && <p className="muted tiny">Parent project: {projects.find((project) => project.id === selected.parentId)?.name ?? "Unknown project"}</p>}
            {!visible.some((project) => project.id === selected.id) && <p>Selected project is outside the current date range.</p>}
            <p>{selected.metadataKnown === false ? "Status unavailable" : selected.archived ? "Archived" : "Active"} · {selected.openTasks ?? tasks.length} open tasks</p>
            <p className="muted tiny">{selected.createdAt ? `Earliest known start: ${selected.createdAt}${selected.createdAtSource === "activity" ? " (first recorded activity)" : ""}.` : "Start date unavailable."} {selected.metadataKnown === false ? "Project status is unknown." : selected.archived ? selected.archivedAt ? `Archived: ${selected.archivedAt}.` : "Archive date unavailable; the last observed activity is not necessarily the archive date." : "Project is ongoing."}</p>
            {!model.historyAvailable || !detailAvailable ? <p>Activity details are unavailable.</p> : <>
              <p><strong>{totals.completions}</strong> recorded completions · <strong>{totals.events}</strong> recorded activity events</p>
              {!daily.length ? <p>No recorded activity in this range{incomplete ? "; history is incomplete" : ""}.</p> : <>
                <ol aria-label="Project activity by day" style={{ paddingLeft: 20 }}>
                  {daily.slice(0, dayLimit).map((day) => <li key={day.date}><time dateTime={day.date}>{day.date}</time> · {day.completions} completed · {day.events} events</li>)}
                </ol>
                {daily.length > dayLimit && <button type="button" className="button buttonSmall" onClick={() => setDayLimit((value) => value + 30)}>Show more activity</button>}
              </>}
            </>}
            {tasks.length > 0 && <><h4>Open tasks</h4><ul>{tasks.slice(0, taskLimit).map((task) => <li key={task.id} style={{ overflowWrap: "anywhere" }}>{task.content}{task.parentId && <span className="muted tiny"> · {taskNames.has(task.parentId) ? `Subtask of ${taskNames.get(task.parentId)}` : "Subtask (parent unavailable)"}</span>}</li>)}</ul>{tasks.length > taskLimit && <button type="button" className="button buttonSmall" onClick={() => setTaskLimit((value) => value + 20)}>Show more tasks</button>}</>}
          </section>}
        </>}
      </>}
    </section>
  );
}

export default function AndroidDashboard() {
  const [state, setState] = useState<MobileState | null>(null);
  const [ui, setUi] = useState(INITIAL_UI);
  const currentUi = useRef(ui);
  const hiddenPlotSeries = useRef(new Map<string, Set<string>>()).current;
  currentUi.current = ui;
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  const [storageInvalid, setStorageInvalid] = useState(false);
  const [persist, setPersist] = useState(false);
  const [controlVisited, setControlVisited] = useState(false);
  const [habitLimit, setHabitLimit] = useState(20);
  const [projectLimits, setProjectLimits] = useState(() => new Map<string, number>());
  const [, refreshDate] = useState(0);
  useEffect(() => {
    try {
      const raw = localStorage.getItem("todoist-ui");
      try {
        const saved = restoredUi(JSON.parse(raw ?? "null"));
        currentUi.current = saved.ui;
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
    if (ui.tab === "Control Panel") setControlVisited(true);
  }, [ui.tab]);
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
    const back = () => {
      const current = currentUi.current;
      const change = current.tab !== "Overview"
        ? { tab: "Overview" as const }
        : current.timelineOpen && current.timelineProject
          ? { timelineProject: "" }
          : current.timelineOpen
            ? { timelineOpen: false }
            : null;
      if (!change) {
        command("close");
        return;
      }
      setStorageInvalid(false);
      setPersist(true);
      currentUi.current = { ...current, ...change };
      setUi(currentUi.current);
    };
    window.addEventListener("todoist-back", back);
    return () => window.removeEventListener("todoist-back", back);
  }, []);
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
    currentUi.current = { ...currentUi.current, ...value };
    setUi(currentUi.current);
  };
  const model = state?.model;
  const settings = state?.preferences
    ? mobileSettings(state.preferences)
    : null;
  const eventsKey = JSON.stringify(settings?.plotEvents ?? []);
  const figures = useMemo(
    () =>
      model && ui.tab === "Overview"
        ? [false, true].map((cumulative) =>
            ui.granularity === "week"
              ? completionFigure(model, ui.range, JSON.parse(eventsKey), cumulative)
              : calendarCompletionFigure(model, ui.range, ui.granularity, cumulative),
          )
        : [],
    [model, ui.tab, ui.range, ui.granularity, eventsKey],
  );
  const analysis = useMemo(() => {
    if (ui.tab !== "Overview" || !model?.plotData) return null;
    return {
      pace: weeklyPaceFigure(model, ui.paceWindow),
      lifespan: lifespanFigure(model, ui.range, ui.lifespanAll),
      hierarchy: hierarchyFigure(model, ui.range),
      heatmap: heatmapFigure(model, ui.range),
      events: eventsFigure(model, ui.range),
      taskCounts: taskCountsFigure(model, ui.range),
    };
  }, [model, ui.tab, ui.range, ui.paceWindow, ui.lifespanAll]);
  const busy = state?.loading || state?.syncing;
  const { matches, tasksByProject } = useMemo(() => {
    const matches: MobileModel["tasks"] = [];
    const tasksByProject = new Map<string, MobileModel["tasks"]>();
    if (ui.tab !== "Projects" || !model) return { matches, tasksByProject };
    const query = ui.projectQuery.trim().toLowerCase();
    for (const task of model.tasks) {
      if (ui.priority && task.priority !== ui.priority) continue;
      if (query && !`${task.content} ${task.project} ${task.labels.join(" ")}`.toLowerCase().includes(query)) continue;
      matches.push(task);
      const tasks = tasksByProject.get(task.projectId);
      if (tasks) tasks.push(task);
      else tasksByProject.set(task.projectId, [task]);
    }
    return { matches, tasksByProject };
  }, [model, ui.tab, ui.priority, ui.projectQuery]);
  const activityQuery = ui.activityQuery.trim().toLowerCase();
  const activityMatches = useMemo(() => ui.tab !== "Activity" ? [] : model?.activity.filter((event) =>
    !activityQuery || `${event.kind} ${event.kind === "uncompleted" ? "undone" : ""} ${event.content} ${event.project}`
      .toLowerCase().includes(activityQuery),
  ) ?? [], [model, ui.tab, activityQuery]);
  const activityTruncated = Boolean(model && Number.isSafeInteger(model.activityTotal) && model.activityTotal! > model.activity.length);
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
        localStorage.removeItem(SETTINGS_DRAFT_KEY);
      } catch {
        setStorageUnavailable(true);
      }
      setStorageInvalid(false);
      setPersist(true);
      setControlVisited(false);
      setProjectLimits(new Map());
      hiddenPlotSeries.clear();
      currentUi.current = INITIAL_UI;
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
              if (tab !== ui.tab) {
                patch({ tab });
                setError("");
              }
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
      {state && (controlVisited || ui.tab === "Control Panel") && (
        <div hidden={ui.tab !== "Control Panel"}>
          <ProjectGrouping model={model ?? null} enabled={Boolean(state.connected && model && !state.demo)} busy={Boolean(busy)} message={state.message} draft={ui.groupingDraft} onDraftChange={(draft) => patch({ groupingDraft: draft })} />
          <DashboardSettings
            request={mobileSettingsRequest}
            draftStorageKey={SETTINGS_DRAFT_KEY}
            onAfterMutation={() => setError("")}
          />
          <MobileAbout version={state.version} preview={state.preview} />
        </div>
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
              {analysis && <><p className="muted tiny">Only the current active-task snapshot is available.</p><DeferredPlot title="Active Tasks by Priority" height={310}><MobilePlotCard title="Active Tasks by Priority" figure={analysis.taskCounts} height={310} help={PLOT_HELP.taskCountTrend} hiddenByTitle={hiddenPlotSeries} /></DeferredPlot></>}
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
                      <select className="select" value={ui.paceWindow} onChange={(event) => patch({ paceWindow: Number(event.target.value) })}>
                        <option value={3}>3-week baseline</option><option value={6} disabled={!paceWindowAvailable(model, 6)}>Add 6-week baseline</option><option value={12} disabled={!paceWindowAvailable(model, 12)}>Add 12-week baseline</option><option value={24} disabled={!paceWindowAvailable(model, 24)}>Add 24-week baseline</option>
                      </select>
                    </label>
                  </div>
                  {ui.paceWindow !== 3 && !paceWindowAvailable(model, ui.paceWindow) && <p className="muted tiny">The selected {ui.paceWindow}-week baseline is unavailable for the current history.</p>}
                  <DeferredPlot title="Weekly Completion Trend" height={310}><MobilePlotCard title="Weekly Completion Trend" figure={analysis.pace} height={310} help={PLOT_HELP.weeklyCompletionTrend} hiddenByTitle={hiddenPlotSeries} /></DeferredPlot>
                  <DeferredPlot title="Task Lifespans: Time to Completion" height={310}><PlotCard title="Task Lifespans: Time to Completion" figure={analysis.lifespan} height={310} compact help={PLOT_HELP.taskLifespans} actions={
                    <select aria-label="Task lifespan date range" className="select" value={ui.lifespanAll ? "all" : "period"} onChange={(event) => patch({ lifespanAll: event.target.value === "all" })}>
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
                hiddenByTitle={hiddenPlotSeries}
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
                hiddenByTitle={hiddenPlotSeries}
              />
              {analysis && (
                <>
                  <p className="muted tiny">Dates and activity hours use your device time zone.</p>
                  <DeferredPlot title="Heatmap of Events by Day and Hour" height={290}><PlotCard title="Heatmap of Events by Day and Hour" figure={analysis.heatmap} height={290} compact help={PLOT_HELP.heatmapEventsByDayHour} /></DeferredPlot>
                  <DeferredPlot title="Events Over Time" height={310}><MobilePlotCard title="Events Over Time" figure={analysis.events} height={310} help={PLOT_HELP.eventsOverTime} hiddenByTitle={hiddenPlotSeries} /></DeferredPlot>
                  <p className="muted tiny">Active-task history is estimated from cached activity and current tasks.</p>
                  <DeferredPlot title="Active Tasks by Priority" height={310}><MobilePlotCard title="Active Tasks by Priority" figure={analysis.taskCounts} height={310} help={PLOT_HELP.taskCountTrend} hiddenByTitle={hiddenPlotSeries} /></DeferredPlot>
                </>
              )}
            </>
          )}
          {model.habitTracker && <section className="card" aria-label="Habit tracker">
            <h2>Habit tracker</h2>
            <p className="muted tiny">Active tasks labelled @track_habit · last full week {model.habitTracker.weekBeg} to {model.habitTracker.weekEnd}.</p>
            {model.habitTracker.trackedCount === 0 ? <p>No active tasks have the @track_habit label.</p> : !model.historyAvailable ? <p>Habit activity is unavailable; saved task labels are still shown.</p> : <>
              {(!model.plotData?.historyComplete || staleActivity || (!state?.demo && (!model.activitySyncedAt || !Number.isFinite(activityTime))) || (historyAsOf && historyAsOf < model.habitTracker.weekEnd)) && <p className="pill pill-warn">Habit history is incomplete or out of date; recorded counts can change after synchronization.</p>}
              <p><strong>{model.habitTracker.totals.weeklyCompleted}</strong> recorded completions · <strong>{model.habitTracker.totals.weeklyRescheduled}</strong> recorded reschedules last week</p>
              <p className="muted tiny">Counts use available Todoist activity. Your plan may limit older history. Reliability is completions divided by recorded completions and reschedules, not a measure of goal adherence.</p>
              {model.habitTracker.items.slice(0, habitLimit).map((habit) => <article className="mobileTask" key={habit.taskId}>
                <div><strong>{habit.name}</strong><p className="muted tiny">{habit.projectName} · {habit.weeklyCompleted} completed and {habit.weeklyRescheduled} rescheduled last week</p><p className="muted tiny">Recorded total: {habit.allTimeCompleted} completed · {habit.allTimeRescheduled} rescheduled{habit.reliability === null ? "" : ` · ${habit.reliability}% reliability`}</p></div>
              </article>)}
              {model.habitTracker.items.length > habitLimit && <button type="button" className="button buttonSmall" onClick={() => setHabitLimit((value) => value + 20)}>Show more habits</button>}
              <details><summary>Recorded weekly history</summary><ul>{model.habitTracker.history.map((week) => <li key={week.label}>{week.label} · {week.completed} completed · {week.rescheduled} rescheduled</li>)}</ul></details>
            </>}
          </section>}
        </>
      )}
      {model?.plotData && <div hidden={ui.tab !== "Overview"}><ProjectTimeline model={model} ui={ui} patch={patch} /></div>}

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
              value={ui.tab === "Projects" ? ui.projectQuery : ui.activityQuery}
              onChange={(event) => patch(ui.tab === "Projects" ? { projectQuery: event.target.value } : { activityQuery: event.target.value })}
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
            const tasks = tasksByProject.get(project.id) ?? [];
            const open = Boolean(ui.projectQuery || ui.priority) || ui.openProjects.includes(project.id);
            const limit = projectLimits.get(project.id) ?? 20;
            if (!tasks.length && (ui.projectQuery || ui.priority)) return null;
            return (
              <details
                key={project.id}
                className="card mobileProject"
                open={open}
                onToggle={(event) => {
                  if (ui.projectQuery || ui.priority) return;
                  const opened = event.currentTarget.open;
                  const previous = currentUi.current.openProjects;
                  if (opened === previous.includes(project.id)) return;
                  patch({ openProjects: opened ? [...previous, project.id] : previous.filter((id) => id !== project.id) });
                }}
              >
                <summary>
                  <span>{project.path}</span>
                  <span className="pill pill-neutral">{tasks.length}</span>
                </summary>
                {open && (tasks.length ? (
                  <>{tasks.slice(0, limit).map((task) => (
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
                  ))}
                  {tasks.length > limit && <button type="button" className="button buttonSmall" onClick={() => setProjectLimits((previous) => new Map(previous).set(project.id, (previous.get(project.id) ?? 20) + 20))}>Show more tasks</button>}
                  </>
                ) : (
                  <p className="muted tiny">No active tasks.</p>
                ))}
              </details>
            );
          })}
          {!matches.length && (ui.projectQuery || ui.priority) && (
            <p className="muted">No tasks match.</p>
          )}
        </>
      )}
      {model && ui.tab === "Activity" && (
        <section className="card">
          <header className="cardHeader">
            <h2>Recent activity</h2>
          </header>
          {state?.demo && <p className="muted tiny">Demo activity; no account data is shown.</p>}
          {model.historyAvailable ? <>
            {!state?.demo && (model.activitySyncedAt && Number.isFinite(activityTime) ? <p className={staleActivity ? "pill pill-warn" : "muted tiny"}>Activity last synchronized {new Date(activityTime).toLocaleString()}{staleActivity ? "; this history is out of date." : "."}</p> : <p className="muted tiny">Activity synchronization time is unavailable for this saved history.</p>)}
            {state?.syncing && <p className="muted tiny">Showing saved activity while synchronization is in progress.</p>}
            {model.plotData?.historyComplete === false && <p className="pill pill-warn">Earlier activity history is incomplete; missing events are not confirmed absent.</p>}
            {model.historyWarning && <p className="pill pill-warn">{model.historyWarning}</p>}
          </> : <p className="pill pill-warn">Activity history is unavailable. {model.historyWarning}</p>}
          {activityTruncated && <p className="muted tiny">Showing the latest {model.activity.length} of {model.activityTotal} saved events. Search covers these recent events only.</p>}
          {model.activity.length === 0 && model.historyAvailable && (
            <p className="muted">No activity in the available history.</p>
          )}
          {model.activity.length > 0 && activityQuery && !activityMatches.length && <p className="muted">{activityTruncated ? "No recent activity matches your search; older saved events are not searched." : "No activity matches your search."}</p>}
          {activityMatches.map((event) => (
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
