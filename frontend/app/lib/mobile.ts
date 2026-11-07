import type { DashboardSettings, PlotEventSetting } from "./dashboardSettings";
import type { PlotlyFigure } from "../components/PlotCard";
import type { requestJson } from "./adminApi";
import type { MobilePlotData } from "./mobilePlots";

export type MobileTask = {
  id: string;
  projectId: string;
  content: string;
  project: string;
  priority: number;
  due: string;
  deadline: string;
  labels: string[];
};
export type MobileModel = {
  syncedAt: string;
  activitySyncedAt?: string;
  weekStart: string;
  weeks: number[];
  priorities: number[];
  forecast: number;
  forecastAvailable: boolean;
  historyAvailable: boolean;
  historyWarning: string;
  plotData?: MobilePlotData;
  adjustments?: { mappings: Record<string, string>; archivedParents: string[] };
  weeklyProjects: Record<string, number>[];
  projectForecasts: Record<string, number>;
  projectColors: Record<string, string>;
  tasks: MobileTask[];
  projects: { id: string; path: string }[];
  activity: {
    id: string;
    kind: string;
    content: string;
    project: string;
    date: string;
  }[];
};
export type MobileState = {
  version?: string;
  preview?: boolean;
  loading: boolean;
  syncing: boolean;
  connected: boolean;
  savedHistory?: boolean;
  demo: boolean;
  message: string;
  model: MobileModel | null;
  preferences: {
    rules: Record<string, unknown>;
    settings: DashboardSettings | null;
    labels: string[];
  };
  alert?: {
    enabled: boolean;
    level: number;
    matches: number;
    fire: number;
    priority: number;
    due: number;
    deadline: number;
  };
};
declare global {
  interface Window {
    Todoist?: {
      ready(): void;
      command(name: string, argument: string): void;
      getSettings(): string;
      saveSettings(json: string): string;
    };
  }
}
export function command(name: string, argument = "") {
  window.Todoist?.command(name, argument);
}

export function mobileSettings(
  preferences: MobileState["preferences"],
): DashboardSettings {
  const rules = preferences.rules;
  const labels = String(rules.fireLabels ?? "fire")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const fallback: DashboardSettings = {
    enabled: Boolean(rules.enabled),
    dangerOnFireLabel: Boolean(rules.fire),
    warnOnPriority: Boolean(rules.priority),
    warnOnDue: Boolean(rules.due),
    warnOnDeadline: Boolean(rules.deadline),
    fireLabel: labels[0] ?? "",
    fireLabels: labels,
    warnPriorityThresholds: rules.priorities as number[],
    warnPriorityMinCount: Number(rules.priorityMin),
    warnDueWithinDays: Number(rules.dueDays),
    warnDueMinCount: Number(rules.dueMin),
    warnDeadlineWithinDays: Number(rules.deadlineDays),
    warnDeadlineMinCount: Number(rules.deadlineMin),
    plotEvents: [],
  };
  const saved = preferences.settings;
  if (!saved || typeof saved !== "object" || Array.isArray(saved)) return fallback;
  const events = saved.plotEvents;
  return {
    // Android evaluates alerts using these native rules, even if the saved UI copy differs.
    ...fallback,
    plotEvents: Array.isArray(events)
      ? events.filter((item) => item && typeof item.date === "string" && typeof item.label === "string" && typeof item.color === "string")
      : fallback.plotEvents,
    ...(typeof saved.configPath === "string" ? { configPath: saved.configPath } : {}),
  };
}
export const mobileSettingsRequest: typeof requestJson = async <T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> => {
  if (!window.Todoist) throw new Error("Android connection unavailable");
  let response = JSON.parse(window.Todoist.getSettings());
  if (String(input).endsWith("/labels"))
    return { labels: response.labels.map((name: string) => ({ name })) } as T;
  if (init?.method === "PUT") {
    const settings = JSON.parse(String(init.body)) as DashboardSettings;
    const rules = {
      enabled: settings.enabled,
      fire: settings.dangerOnFireLabel,
      priority: settings.warnOnPriority,
      due: settings.warnOnDue,
      deadline: settings.warnOnDeadline,
      fireLabels: settings.fireLabels.join(", "),
      priorities: settings.warnPriorityThresholds,
      priorityMin: settings.warnPriorityMinCount,
      dueDays: settings.warnDueWithinDays,
      dueMin: settings.warnDueMinCount,
      deadlineDays: settings.warnDeadlineWithinDays,
      deadlineMin: settings.warnDeadlineMinCount,
    };
    response = JSON.parse(
      window.Todoist.saveSettings(JSON.stringify({ settings, rules })),
    );
  }
  if (response.error) throw new Error(response.error);
  return { settings: mobileSettings(response) } as T;
};

const COLORS: Record<string, string> = {
  berry_red: "#B8255F",
  red: "#DC4C3E",
  orange: "#C77100",
  yellow: "#B29104",
  olive_green: "#949C31",
  lime_green: "#65A33A",
  green: "#369307",
  mint_green: "#42A393",
  teal: "#148FAD",
  sky_blue: "#319DC0",
  light_blue: "#6988A4",
  blue: "#4180FF",
  grape: "#692EC2",
  violet: "#CA3FEE",
  lavender: "#A4698C",
  magenta: "#E05095",
  salmon: "#C9766F",
  charcoal: "#808080",
  grey: "#999999",
  taupe: "#8F7A69",
};
export function projectColor(model: MobileModel, name: string): string {
  const color = Object.prototype.hasOwnProperty.call(model.projectColors, name) ? model.projectColors[name] : undefined;
  return (
    (color && Object.prototype.hasOwnProperty.call(COLORS, color) ? COLORS[color] : undefined) ??
    (typeof color === "string" && /^#[\da-f]{6}$/i.test(color) ? color : "#808080")
  );
}
export function weekDate(start: string, offset: number, days = 0): string {
  const date = new Date(`${start}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset * 7 + days);
  return date.toISOString().slice(0, 10);
}
function validCalendarDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}
export function mobileHistoryStart(model: MobileModel): string {
  if (model.plotData?.historyComplete !== false) return "";
  return validCalendarDate(model.plotData.historyStart) ? model.plotData.historyStart : "9999-12-31";
}
export function mobileHistoryEnd(model: MobileModel): string {
  if (model.activitySyncedAt) {
    const end = Date.parse(model.activitySyncedAt);
    if (Number.isFinite(end)) {
      const boundary = new Date(end);
      const midnight = new Date(boundary.getFullYear(), boundary.getMonth(), boundary.getDate()).getTime();
      const today = new Date();
      const currentDay = boundary.getFullYear() === today.getFullYear()
        && boundary.getMonth() === today.getMonth() && boundary.getDate() === today.getDate();
      // A past partial day is not complete. Today may be shown as an explicitly timestamped partial day.
      const last = new Date(end === midnight || !currentDay ? midnight - 1 : end - 1);
      return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, "0")}-${String(last.getDate()).padStart(2, "0")}`;
    }
  }
  if (model.plotData?.historyAsOf) return validCalendarDate(model.plotData.historyAsOf) ? model.plotData.historyAsOf : "0000-01-01";
  const last = new Date(model.syncedAt);
  if (!Number.isFinite(last.getTime())) return "0000-01-01";
  return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, "0")}-${String(last.getDate()).padStart(2, "0")}`;
}
export function aggregateProjectIdentity(names: string[]) {
  let label = "All projects (project)", group = "project:All projects";
  while (names.includes(label)) label += " (project)";
  while (names.includes(group)) group += ":";
  return { label, group };
}
export function mobileForecastAvailable(model: MobileModel): boolean {
  if (!model.forecastAvailable || mobileHistoryEnd(model) < model.weekStart) return false;
  if (model.plotData?.historyComplete === false)
    return mobileHistoryStart(model) <= weekDate(model.weekStart, -8);
  return true;
}
export function completionFigure(
  model: MobileModel,
  range: number,
  events: PlotEventSetting[],
  cumulative = false,
): PlotlyFigure {
  const current = model.weeks.length - 1;
  const dates = model.weeks.map((_, i) => weekDate(model.weekStart, i - current, 6));
  const from = range > 0 ? Math.max(0, model.weeks.length - range) : 0;
  const coverage = mobileHistoryStart(model);
  const historyAsOf = mobileHistoryEnd(model);
  const covered = (index: number) => {
    const start = weekDate(model.weekStart, index - current);
    const end = weekDate(model.weekStart, index - current, 6);
    return (!coverage || start >= coverage) && (!historyAsOf || (index === current ? start : end) <= historyAsOf);
  };
  const names = [
    ...new Set(model.weeklyProjects.flatMap((counts, i) => i >= from && covered(i) ? Object.keys(counts) : [])),
  ].sort();
  const aggregateProject = aggregateProjectIdentity(names);
  const data: unknown[] = [];
  for (const series of [{ name: "All projects", total: true }, ...names.map((name) => ({ name, total: false }))]) {
    const { name, total } = series;
    const label = !total && name === "All projects" ? aggregateProject.label : name;
    const color = total ? "#F4D35E" : projectColor(model, name);
    const raw = total
      ? model.weeks
      : model.weeklyProjects.map((counts) => Object.prototype.hasOwnProperty.call(counts, name) ? counts[name] : 0);
    let values: (number | null)[] = raw.map((value, index) => covered(index) ? value : null);
    const actual = raw[current];
    let forecast = total
      ? model.forecast
      : (Object.prototype.hasOwnProperty.call(model.projectForecasts, name) ? model.projectForecasts[name] : actual);
    if (cumulative) {
      let sum = 0;
      values = values.map((value) => value === null ? null : (sum += value));
      forecast += values[current - 1] ?? 0;
    }
    const group = {
      name: label,
      legendgroup: !total && name === "All projects" ? aggregateProject.group : name,
      line: { color, width: total ? 3 : 2 },
      marker: { color },
      hovertemplate: `${label}<br>%{x}: %{y} tasks<extra></extra>`,
    };
    data.push({
      ...group,
      x: dates.slice(from, current),
      y: values.slice(from, current),
      mode: "lines+markers",
      type: "scatter",
    });
    if (mobileForecastAvailable(model))
      data.push({
        ...group,
        x: dates.slice(current - 1),
        y: [values[current - 1], forecast],
        showlegend: false,
        mode: "lines+markers",
        type: "scatter",
        line: { color, width: total ? 3 : 2, dash: "dash" },
        hovertemplate: `${label}<br>Forecast: %{y} tasks<extra></extra>`,
      });
    data.push({
      ...group,
      x: [dates[current]],
      y: [values[current]],
      showlegend: false,
      type: "scatter",
      mode: "markers",
      marker: {
        color,
        size: 10,
        symbol: "circle-open",
        line: { color, width: 2 },
      },
      hovertemplate: `${label}<br>So far: %{y} tasks<extra></extra>`,
    });
  }
  return {
    data,
    layout: {
      font: { family: "Space Grotesk, sans-serif", size: 11 },
      showlegend: false,
      hovermode: "closest",
      dragmode: false,
      xaxis: { type: "date", tickformat: "%b %-d", showgrid: false },
      yaxis: { rangemode: "tozero", showgrid: false },
      shapes: events.map((event) => ({
        type: "line",
        xref: "x",
        yref: "paper",
        x0: event.date,
        x1: event.date,
        y0: 0,
        y1: 1,
        line: { color: event.color, dash: "dot" },
      })),
      annotations: events.map((event) => ({
        x: event.date,
        y: 1,
        yref: "paper",
        text: event.label,
        showarrow: false,
        font: { color: event.color },
      })),
    },
  };
}
