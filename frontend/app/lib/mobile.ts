import type { DashboardSettings, PlotEventSetting } from "./dashboardSettings";
import type { PlotlyFigure } from "../components/PlotCard";
import type { requestJson } from "./adminApi";

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
  weekStart: string;
  weeks: number[];
  priorities: number[];
  forecast: number;
  forecastAvailable: boolean;
  historyAvailable: boolean;
  historyWarning: string;
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
  if (preferences.settings) return preferences.settings;
  const rules = preferences.rules;
  const labels = String(rules.fireLabels ?? "fire")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
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
  const color = model.projectColors[name];
  return (
    COLORS[color] ?? (/^#[\da-f]{6}$/i.test(color ?? "") ? color : "#808080")
  );
}
export function weekDate(start: string, offset: number, days = 0): string {
  const date = new Date(`${start}T12:00:00`);
  date.setDate(date.getDate() + offset * 7 + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function completionFigure(
  model: MobileModel,
  range: number,
  events: PlotEventSetting[],
  cumulative = false,
): PlotlyFigure {
  const dates = model.weeks.map((_, i) => weekDate(model.weekStart, i - 8, 6));
  const names = [
    ...new Set(model.weeklyProjects.flatMap((counts) => Object.keys(counts))),
  ].sort();
  const data: unknown[] = [];
  for (const name of ["All projects", ...names]) {
    const total = name === "All projects";
    const color = total ? "#F4D35E" : projectColor(model, name);
    let values = total
      ? model.weeks
      : model.weeklyProjects.map((counts) => counts[name] ?? 0);
    const actual = values[8];
    let forecast = total
      ? model.forecast
      : (model.projectForecasts[name] ?? actual);
    if (cumulative) {
      let sum = 0;
      values = values.map((value) => (sum += value));
      forecast += values[7];
    }
    const group = {
      name,
      legendgroup: name,
      line: { color, width: total ? 3 : 2 },
      marker: { color },
      hovertemplate: `${name}<br>%{x}: %{y} tasks<extra></extra>`,
    };
    data.push({
      ...group,
      x: dates.slice(9 - range, 8),
      y: values.slice(9 - range, 8),
      mode: "lines+markers",
      type: "scatter",
    });
    if (model.forecastAvailable)
      data.push({
        ...group,
        x: dates.slice(7),
        y: [values[7], forecast],
        showlegend: false,
        mode: "lines+markers",
        type: "scatter",
        line: { color, width: total ? 3 : 2, dash: "dash" },
        hovertemplate: `${name}<br>Forecast: %{y} tasks<extra></extra>`,
      });
    data.push({
      ...group,
      x: [dates[8]],
      y: [values[8]],
      showlegend: false,
      type: "scatter",
      mode: "markers",
      marker: {
        color,
        size: 10,
        symbol: "circle-open",
        line: { color, width: 2 },
      },
      hovertemplate: `${name}<br>So far: %{y} tasks<extra></extra>`,
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
