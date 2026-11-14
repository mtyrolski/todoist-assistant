import type { PlotlyFigure } from "../components/PlotCard";
import { aggregateProjectIdentity, mobileHistoryEnd, mobileHistoryStart, projectColor, weekDate, type MobileModel } from "./mobile";

export type MobilePlotData = {
  historyComplete?: boolean;
  historyStart?: string;
  historyAsOf?: string;
  dailyActivity: {
    date: string;
    counts: Record<string, number>;
    hours: number[];
    effectiveCompletions: number;
    projects?: Record<string, number>;
  }[];
  lifespans: { completedAt: string; seconds: number }[];
  hierarchy: {
    id: string;
    name: string;
    parentId: string;
    rootName: string;
    color: string;
    archived: boolean;
    previousNames?: string[];
    metadataKnown?: boolean;
    createdAt: string;
    lastEventAt: string;
    updatedAt?: string;
    createdAtSource?: "metadata" | "activity" | "unknown";
    archivedAt: string;
    weeklyCounts: Record<string, number>;
    openTasks?: number;
    dailyCompletions?: { date: string; count: number }[];
    dailyEvents?: { date: string; count: number }[];
  }[];
  taskCounts: { date: string; total: number; p1: number; p2: number; p3: number; p4: number }[];
};

const DAY = 86400000;
const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const eventTypes = [
  ["added", "Added", "#2E8B57"],
  ["completed", "Completion actions", "#4169E1"],
  ["uncompleted", "Undone completions", "#E5A04B"],
  ["updated", "Updated", "#FF8C00"],
  ["deleted", "Deleted", "#DC143C"],
  ["rescheduled", "Rescheduled", "#9370DB"],
] as const;
const time = (day: string) => Date.parse(`${day}T00:00:00Z`);
const dayString = (value: number) => new Date(value).toISOString().slice(0, 10);
const localDay = (value: string) => {
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
};
const historyDay = mobileHistoryEnd;
const confirmedStart = mobileHistoryStart;
const startDate = (model: MobileModel, range: number) =>
  range > 0 ? weekDate(model.weekStart, 1 - range) : "";
const inRange = (day: string, start: string, end: string) =>
  (!start || day >= start) && day <= end;

function empty(message: string): PlotlyFigure {
  return {
    data: [],
    layout: {
      xaxis: { visible: false },
      yaxis: { visible: false },
      annotations: [{ text: message, xref: "paper", yref: "paper", x: 0.5, y: 0.5, showarrow: false }],
    },
  };
}

function line(name: string, color: string, x: unknown[], y: unknown[], extra: Record<string, unknown> = {}) {
  return { name, legendgroup: name, x, y, type: "scatter", mode: "lines+markers", line: { color, width: 2 }, marker: { color }, ...extra };
}

function percentile(values: number[], fraction: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * fraction;
  const lower = Math.floor(index);
  return sorted[lower] + (sorted[Math.ceil(index)] - sorted[lower]) * (index - lower);
}

function paceStats(model: MobileModel, size: number) {
  if (historyDay(model) < model.weekStart) return null;
  const coverage = confirmedStart(model);
  const daily = (model.plotData?.dailyActivity ?? []).filter((day) => !coverage || day.date >= coverage);
  const counts = new Map(daily.map((day) => [day.date, day.effectiveCompletions]));
  const firstRecorded = daily.filter((day) => day.effectiveCompletions > 0).map((day) => day.date).sort()[0];
  if (!firstRecorded) return null;
  const week = (offset: number) => weekdays.map((_, day) => counts.get(weekDate(model.weekStart, offset, day)) ?? 0);
  const recorded = Array.from({ length: size }, (_, i) => -size + i)
    .filter((offset) => weekDate(model.weekStart, offset, coverage ? 0 : 6) >= (coverage || firstRecorded));
  if (size > 3 && recorded.length < size) return null;
  const candidates = recorded.map(week).filter((values) => values.some((value) => value > 0));
  if (!candidates.length) return null;
  const totals = candidates.map((values) => values.reduce((sum, value) => sum + value, 0));
  const curves = candidates.map((values, index) => {
    let sum = 0;
    return values.map((value) => (sum += value) / totals[index] * 100);
  });
  return {
    avgTotal: totals.reduce((sum, value) => sum + value, 0) / totals.length,
    avg: weekdays.map((_, day) => curves.reduce((sum, values) => sum + values[day], 0) / curves.length),
    low: weekdays.map((_, day) => percentile(curves.map((values) => values[day]), 0.25)),
    high: weekdays.map((_, day) => percentile(curves.map((values) => values[day]), 0.75)),
  };
}

export function paceWindowAvailable(model: MobileModel, window: number): boolean {
  return paceStats(model, window) !== null;
}

export function weeklyPaceFigure(model: MobileModel, window: number): PlotlyFigure {
  if (historyDay(model) < model.weekStart) return empty("Activity has not been refreshed for the current week.");
  const coverage = confirmedStart(model);
  const daily = (model.plotData?.dailyActivity ?? []).filter((day) => !coverage || day.date >= coverage);
  const counts = new Map(daily.map((day) => [day.date, day.effectiveCompletions]));
  if (!daily.some((day) => day.effectiveCompletions > 0)) return empty("No completed tasks available yet.");
  const week = (offset: number) => weekdays.map((_, day) => counts.get(weekDate(model.weekStart, offset, day)) ?? 0);
  const baseline = paceStats(model, 3);
  if (!baseline) return empty("Not enough completed-week data for a baseline.");
  const data: unknown[] = [
    line("3-week baseline", "#6CCFF6", weekdays, baseline.low, { mode: "lines", showlegend: false, line: { width: 0 }, hoverinfo: "skip" }),
    line("3-week baseline", "#6CCFF6", weekdays, baseline.high, { mode: "lines", showlegend: false, line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(108,207,246,0.15)", hoverinfo: "skip" }),
    line("3-week baseline", "#6CCFF6", weekdays, baseline.avg, { hovertemplate: "%{x}: %{y:.1f}%<extra></extra>" }),
  ];
  if (window !== 3) {
    const optional = paceStats(model, window);
    if (optional) data.push(line(`${window}-week baseline`, "#A868FF", weekdays, optional.avg, { hovertemplate: "%{x}: %{y:.1f}%<extra></extra>" }));
  }
  const today = historyDay(model);
  let sum = 0;
  const raw = week(0).map((value, day) => {
    sum += value;
    return weekDate(model.weekStart, 0, day) <= today ? sum : null;
  });
  data.push(line("This week", "#FFB703", weekdays, raw.map((value) => value === null ? null : value / baseline.avgTotal * 100), {
    customdata: raw,
    line: { color: "#FFB703", width: 3, dash: "dash" },
    hovertemplate: "%{x}: %{customdata} completed<br>%{y:.1f}% of 3-week average<extra></extra>",
  }));
  return { data, layout: { showlegend: false, yaxis: { ticksuffix: "%", rangemode: "tozero" }, xaxis: { categoryorder: "array", categoryarray: weekdays } } };
}

export function lifespanFigure(model: MobileModel, range: number, all: boolean): PlotlyFigure {
  const start = all ? "" : startDate(model, range);
  const end = historyDay(model);
  // Explicit, non-overlapping durations keep a seconds-to-years distribution readable on a phone.
  const buckets = [
    { label: "Under 1 min", limit: 60 },
    { label: "1–59 min", limit: 3600 },
    { label: "1–23 hours", limit: 86400 },
    { label: "1–6 days", limit: 7 * 86400 },
    { label: "1–<4 weeks", limit: 28 * 86400 },
    { label: "4 weeks–<1 year", limit: 365 * 86400 },
    { label: "1+ year", limit: Infinity },
  ];
  const counts = buckets.map(() => 0);
  for (const item of model.plotData?.lifespans ?? []) {
    if (!inRange(item.completedAt, start, end) || !Number.isFinite(item.seconds) || item.seconds <= 0) continue;
    counts[buckets.findIndex(({ limit }) => item.seconds < limit)]++;
  }
  if (!counts.some(Boolean)) return empty("No tasks with a recorded creation and completion in this range.");
  const maxCount = Math.max(...counts);
  return {
    data: [{ type: "bar", orientation: "h", x: counts, y: buckets.map(({ label }) => label), marker: { color: "#1ABC9C" }, hovertemplate: "%{y}<br>%{x} tasks<extra></extra>" }],
    layout: { showlegend: false, xaxis: { title: "Completed tasks", rangemode: "tozero", tickformat: ",d", ...(maxCount <= 5 ? { dtick: 1 } : {}) }, yaxis: { autorange: "reversed", automargin: true } },
  };
}

export function heatmapFigure(model: MobileModel, range: number): PlotlyFigure {
  const start = startDate(model, range), end = historyDay(model), coverage = confirmedStart(model);
  const z = Array.from({ length: 7 }, () => Array(24).fill(0));
  let total = 0;
  for (const day of model.plotData?.dailyActivity ?? []) {
    if (!inRange(day.date, start, end) || (coverage && day.date < coverage)) continue;
    const weekday = (new Date(time(day.date)).getUTCDay() + 6) % 7;
    for (let hour = 0; hour < 24; hour++) {
      z[weekday][hour] += day.hours[hour] ?? 0;
      total += day.hours[hour] ?? 0;
    }
  }
  if (!total) return empty("No activity in this range.");
  return {
    data: [{ type: "heatmap", z, x: Array.from({ length: 24 }, (_, i) => i), y: weekdays, colorscale: [[0, "#0d1b2a"], [0.35, "#415a77"], [0.7, "#ffeaa7"], [1, "#d63031"]], showscale: false, hovertemplate: "%{y} %{x}:00<br>%{z} events<extra></extra>" }],
    layout: { showlegend: false, xaxis: { title: "Hour", dtick: 4 }, yaxis: { autorange: "reversed" }, margin: { l: 48, r: 12, t: 20, b: 42 } },
  };
}

export function eventsFigure(model: MobileModel, range: number): PlotlyFigure {
  const coverage = confirmedStart(model);
  const daily = (model.plotData?.dailyActivity ?? []).filter((day) => !coverage || day.date >= coverage).sort((a, b) => a.date.localeCompare(b.date));
  if (!daily.length) return empty("No activity recorded yet.");
  const end = historyDay(model), requestedStart = startDate(model, range);
  const start = requestedStart && requestedStart > daily[0].date ? requestedStart : daily[0].date;
  const byDate = new Map(daily.map((day) => [day.date, day.counts]));
  const x: string[] = [];
  const values = eventTypes.map(() => [] as number[]);
  const buffers = eventTypes.map(() => [] as number[]);
  for (let cursor = Math.max(time(daily[0].date), time(start) - 6 * DAY); cursor <= time(end); cursor += DAY) {
    const date = dayString(cursor), counts = byDate.get(date);
    eventTypes.forEach(([type], i) => {
      buffers[i].push(counts?.[type] ?? 0);
      if (buffers[i].length > 7) buffers[i].shift();
      if (date >= start) values[i].push(buffers[i].reduce((sum, value) => sum + value, 0) / buffers[i].length);
    });
    if (date >= start) x.push(date);
  }
  if (!x.length) return empty("No activity in this range.");
  return {
    data: eventTypes.map(([, label, color], i) => line(label, color, x, values[i], { mode: "lines", stackgroup: "activity", hovertemplate: `${label}<br>%{x}: %{y:.1f} events/day<extra></extra>` })),
    layout: { showlegend: false, xaxis: { type: "date" }, yaxis: { title: "Events per day", rangemode: "tozero" } },
  };
}

export function taskCountsFigure(model: MobileModel, range: number): PlotlyFigure {
  const start = startDate(model, range), end = localDay(model.syncedAt);
  const rows = (model.plotData?.taskCounts ?? []).filter((row) => inRange(row.date, start, end));
  if (!rows.length) return empty("No task-count history is available.");
  const series = [["total", "All tasks", "#E8ECF2"], ["p1", "P1", "#FF7777"], ["p2", "P2", "#FFBD69"], ["p3", "P3", "#8BD0FF"], ["p4", "P4", "#A7E3A1"]] as const;
  const maximum = rows.reduce((largest, row) => Math.max(largest, row.total), 0);
  const ticks = [0, 10, 50, 100, 250, 500, 1000, 1500, 2000, 2500, 3000].filter((value) => value <= maximum * 1.2);
  return {
    data: series.map(([key, name, color]) => line(name, color, rows.map((row) => row.date), rows.map((row) => Math.sqrt(Math.max(0, row[key]))), {
      mode: "lines", customdata: rows.map((row) => row[key]), hovertemplate: `${name}<br>%{x}: %{customdata} tasks<extra></extra>`,
    })),
    layout: { showlegend: false, xaxis: { type: "date" }, yaxis: { title: "Active tasks (softened scale)", rangemode: "tozero", tickvals: ticks.map(Math.sqrt), ticktext: ticks.map(String) } },
  };
}

export function hierarchyFigure(model: MobileModel, range: number): PlotlyFigure {
  const projects = model.plotData?.hierarchy ?? [];
  const byId = new Map(projects.map((project) => [project.id, project]));
  const first = range > 0 ? Math.max(0, model.weeks.length - range) : 0;
  const coverage = confirmedStart(model), current = model.weeks.length - 1, end = historyDay(model);
  const own = new Map(projects.map((project) => [project.id, Object.entries(project.weeklyCounts).reduce((sum, [index, value]) => {
    const position = Number(index);
    if (!Number.isSafeInteger(position) || position < 0 || position > current || !Number.isSafeInteger(value) || value <= 0) return sum;
    const start = weekDate(model.weekStart, position - current);
    const lastDay = position === current ? start : weekDate(model.weekStart, position - current, 6);
    return sum + (position >= first && (!coverage || start >= coverage) && lastDay <= end ? value : 0);
  }, 0)]));
  const included = new Set<string>();
  for (const project of projects) {
    if (!(own.get(project.id) ?? 0)) continue;
    const visited = new Set<string>();
    let current: typeof project | undefined = project;
    while (current && current.rootName === project.rootName && !visited.has(current.id)) {
      visited.add(current.id);
      included.add(current.id);
      current = byId.get(current.parentId);
    }
  }
  if (!included.size) return empty("No project completions in this range.");
  const roots = [...new Set(projects.filter((project) => included.has(project.id)).map((project) => project.rootName))];
  const ids = roots.map((name) => `root:${name}`), labels = [...roots], parents = roots.map(() => ""), values = roots.map(() => 0);
  const colors = roots.map((name) => projectColor(model, name));
  const rootProjects = new Set(projects.filter((project) => {
    const parent = byId.get(project.parentId);
    return included.has(project.id) && project.name === project.rootName && (!parent || parent.rootName !== project.rootName);
  }).map((project) => project.id));
  for (const project of projects) {
    if (!included.has(project.id)) continue;
    const root = `root:${project.rootName}`;
    if (rootProjects.has(project.id)) {
      values[roots.indexOf(project.rootName)] += own.get(project.id) ?? 0;
      continue;
    }
    let parent = byId.get(project.parentId);
    const visited = new Set([project.id]);
    while (parent && parent.rootName === project.rootName && !visited.has(parent.id)) {
      visited.add(parent.id);
      parent = byId.get(parent.parentId);
    }
    const cyclic = parent && visited.has(parent.id);
    const candidate = byId.get(project.parentId);
    ids.push(`project:${project.id}`);
    labels.push(project.name);
    parents.push(!cyclic && candidate && included.has(candidate.id) && !rootProjects.has(candidate.id) && candidate.rootName === project.rootName ? `project:${candidate.id}` : root);
    values.push(own.get(project.id) ?? 0);
    colors.push(projectColor(model, project.rootName));
  }
  return { data: [{ type: "sunburst", ids, labels, parents, values, branchvalues: "remainder", maxdepth: 2, textinfo: "label", insidetextorientation: "horizontal", marker: { colors }, hovertemplate: "%{label}<br>%{value} completions<extra></extra>" }], layout: { showlegend: false, uniformtext: { minsize: 10, mode: "hide" }, margin: { l: 8, r: 8, t: 12, b: 12 } } };
}

export function calendarCompletionFigure(
  model: MobileModel,
  range: number,
  granularity: "month" | "quarter",
  cumulative: boolean,
): PlotlyFigure {
  const coverage = confirmedStart(model);
  const days = (model.plotData?.dailyActivity ?? []).filter((day) => day.effectiveCompletions > 0 && (!coverage || day.date >= coverage)).sort((a, b) => a.date.localeCompare(b.date));
  if (!days.length) return empty("No completed tasks available yet.");
  const start = startDate(model, range);
  const end = historyDay(model);
  if (start && start > end) return empty("No completed tasks in this range.");
  const period = (date: string) => {
    const month = Number(date.slice(5, 7));
    const firstMonth = granularity === "month" ? month : Math.floor((month - 1) / 3) * 3 + 1;
    return `${date.slice(0, 4)}-${String(firstMonth).padStart(2, "0")}-01`;
  };
  const byPeriod = new Map<string, Record<string, number>>();
  const totals = new Map<string, number>(), unattributed = new Map<string, number>();
  for (const day of days) {
    if (day.date > end) continue;
    const key = period(day.date), counts = byPeriod.get(key) ?? Object.create(null) as Record<string, number>;
    const projects = Object.entries(day.projects ?? {}).filter(([, count]) => Number.isSafeInteger(count) && count >= 0);
    const attributed = projects.reduce((sum, [, count]) => sum + count, 0);
    totals.set(key, (totals.get(key) ?? 0) + day.effectiveCompletions);
    if (attributed <= day.effectiveCompletions) {
      for (const [name, count] of projects) counts[name] = (counts[name] ?? 0) + count;
      unattributed.set(key, (unattributed.get(key) ?? 0) + day.effectiveCompletions - attributed);
    } else {
      // Inconsistent project metadata must not invent more completions than the actual total.
      unattributed.set(key, (unattributed.get(key) ?? 0) + day.effectiveCompletions);
    }
    byPeriod.set(key, counts);
  }
  const firstDay = days[0]?.date;
  if (!firstDay || firstDay > end) return empty("No completed tasks available yet.");
  const cursor = new Date(time(period(firstDay)));
  const finalPeriod = period(end);
  const periods: string[] = [];
  while (dayString(cursor.getTime()) <= finalPeriod) {
    periods.push(dayString(cursor.getTime()));
    cursor.setUTCMonth(cursor.getUTCMonth() + (granularity === "month" ? 1 : 3));
  }
  const visibleFrom = start ? period(start) : periods[0];
  const from = periods.findIndex((value) => value >= visibleFrom);
  if (from < 0) return empty("No completed tasks in this range.");
  const currentPeriod = period(localDay(new Date().toISOString()));
  const coveredPeriod = (key: string) => {
    const next = new Date(time(key));
    next.setUTCMonth(next.getUTCMonth() + (granularity === "month" ? 1 : 3));
    const lastDay = dayString(next.getTime() - DAY);
    return (!coverage || key >= coverage) && (key === currentPeriod || lastDay <= end);
  };
  const projects = [...new Set(periods.slice(from).flatMap((key) => Object.keys(byPeriod.get(key) ?? {})))].sort();
  const aggregateProject = aggregateProjectIdentity(projects);
  let missingLabel = "Unattributed";
  while (projects.includes(missingLabel)) missingLabel += " (missing project)";
  const data: unknown[] = [];
  const series = [{ name: "All projects", total: true, missing: false }, ...projects.map((name) => ({ name, total: false, missing: false }))];
  if (periods.slice(from).some((key) => (unattributed.get(key) ?? 0) > 0)) series.push({ name: missingLabel, total: false, missing: true });
  for (const { name, total, missing } of series) {
    const label = !total && name === "All projects" ? aggregateProject.label : name;
    const color = total ? "#F4D35E" : projectColor(model, name);
    let sum = 0;
    const values = periods.map((key) => {
      if (!coveredPeriod(key)) return null;
      const counts = byPeriod.get(key) ?? Object.create(null) as Record<string, number>;
      const value = total ? totals.get(key) ?? 0 : missing ? unattributed.get(key) ?? 0 : counts[name] ?? 0;
      sum += value;
      return cumulative ? sum : value;
    });
    data.push(line(label, color, periods.slice(from), values.slice(from), {
      legendgroup: !total && name === "All projects" ? aggregateProject.group : name,
      line: { color, width: total ? 3 : 2 },
      hovertemplate: `${label}<br>%{x|%b %Y}: %{y} tasks<extra></extra>`,
    }));
  }
  return { data, layout: { showlegend: false, xaxis: { type: "date", tickformat: "%b %Y" }, yaxis: { rangemode: "tozero" } } };
}
