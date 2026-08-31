"use client";

import { useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type WheelEvent } from "react";
import { LoadingBar } from "./LoadingBar";
import { useProjectTimeline } from "../lib/dashboardHooks";
import type { ProjectTimelineChild, ProjectTimelineParent, TimelineStatus } from "../lib/projectTimeline";

const ROW_HEIGHT = 31;
const MAX_VISIBLE_CHILD_ROWS = 6;
const MIN_TIMELINE_WIDTH = 1060;
const DAY_MS = 86_400_000;

type TimelineResolution = "quarter" | "half" | "year" | "twoYears";

const RESOLUTION_META: Record<TimelineResolution, { label: string; visibleDays: number; tickDays: number }> = {
  quarter: { label: "3 months", visibleDays: 92, tickDays: 7 },
  half: { label: "6 months", visibleDays: 183, tickDays: 14 },
  year: { label: "1 year", visibleDays: 365, tickDays: 28 },
  twoYears: { label: "2 years", visibleDays: 730, tickDays: 56 }
};

const STATUS_META: Record<TimelineStatus, { label: string }> = {
  completed: { label: "Archived projects" },
  ongoing: { label: "Active · completions recorded" },
  unresolved: { label: "Active · no completions recorded" },
  inactive: { label: "Active · no cached activity" }
};

const WEEK_META = {
  completed: { label: "Completion that week", className: "isCompletedWeek" },
  ongoing: { label: "Ongoing project", className: "isOngoingWeek" },
  quiet: { label: "Archived · no completion", className: "isQuietWeek" }
};

const sessionState = {
  collapsed: new Set<string>()
};

function parseDay(value: string): number {
  return Date.parse(`${value}T00:00:00Z`);
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(parseDay(value));
}

function buildTicks(start: number, end: number, stepDays: number) {
  const ticks: { date: number; label: string }[] = [];
  const cursor = new Date(start);
  cursor.setUTCDate(cursor.getUTCDate() + ((8 - cursor.getUTCDay()) % 7));
  while (cursor.getTime() <= end) {
    ticks.push({ date: cursor.getTime(), label: String(cursor.getUTCDate()).padStart(2, "0") });
    cursor.setUTCDate(cursor.getUTCDate() + stepDays);
  }
  return ticks;
}

function buildMonths(start: number, end: number) {
  const result: { key: string; label: string; middle: number }[] = [];
  const cursor = new Date(Date.UTC(new Date(start).getUTCFullYear(), new Date(start).getUTCMonth(), 1));
  while (cursor.getTime() <= end) {
    const monthStart = Math.max(start, cursor.getTime());
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    const monthEnd = Math.min(end + DAY_MS, cursor.getTime());
    result.push({
      key: String(monthStart),
      label: new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric", timeZone: "UTC" }).format(monthStart),
      middle: (monthStart + monthEnd) / 2
    });
  }
  return result;
}

function tooltip(child: ProjectTimelineChild, parent: ProjectTimelineParent): string {
  const meta = STATUS_META[child.status];
  return [
    child.name,
    parent.standalone ? null : `Parent project: ${parent.name}`,
    `Status: ${meta.label}`,
    `Start: ${dateLabel(child.startDate)}`,
    child.endDate ? `End: ${dateLabel(child.endDate)}` : "End: Ongoing",
    child.archiveDate ? `Archive date: ${dateLabel(child.archiveDate)}` : null,
    `Duration: ${child.durationDays} day${child.durationDays === 1 ? "" : "s"}`,
    `Completed events: ${child.completions}`,
    `Archived: ${child.archived ? "Yes" : "No"}`
  ].filter(Boolean).join("\n");
}

function WeeklyActivityRow({
  child,
  parent,
  start,
  end,
  timelineWidth
}: {
  child: ProjectTimelineChild;
  parent: ProjectTimelineParent;
  start: number;
  end: number;
  timelineWidth: number;
}) {
  const duration = Math.max(DAY_MS, end - start + DAY_MS);
  const xFor = (date: number) => (date - start) / duration * timelineWidth;
  const activityLeft = Math.max(0, xFor(parseDay(child.visualStart)));
  const activityRight = Math.min(timelineWidth, xFor(parseDay(child.visualEnd) + DAY_MS));
  const weekWidth = timelineWidth * 7 * DAY_MS / duration;
  const startDay = new Date(start).getUTCDay();
  const firstMonday = start - ((startDay + 6) % 7) * DAY_MS;
  const phaseDays = ((parseDay(child.visualStart) - firstMonday) / DAY_MS) % 7;
  const weekPhase = phaseDays / 7 * weekWidth;
  const details = tooltip(child, parent);

  return (
    <div className="timelineRow">
      <span
        className={`timelineActivitySpan ${child.archived ? "isArchivedProject" : "isOngoingProject"}`}
        style={{
          left: activityLeft,
          width: Math.max(3, activityRight - activityLeft),
          "--week-width": `${weekWidth}px`,
          "--week-phase": `${-weekPhase}px`
        } as CSSProperties}
        title={details}
        aria-label={details}
      />
      {child.completionWeeks.map((week) => {
        const weekStart = parseDay(week);
        const left = Math.max(activityLeft, xFor(weekStart));
        const right = Math.min(activityRight, xFor(weekStart + 7 * DAY_MS));
        if (right <= left) return null;
        const label = `${child.name}\nWeek of ${dateLabel(week)}\nAt least one completed task`;
        return (
          <span
            className="timelineCompletionCell"
            key={week}
            style={{ left, width: Math.max(3, right - left - 2) }}
            title={label}
            aria-label={label}
          />
        );
      })}
    </div>
  );
}

function ParentGroup({
  parent,
  collapsed,
  toggle,
  start,
  end,
  timelineWidth,
  onHorizontalWheel
}: {
  parent: ProjectTimelineParent;
  collapsed: boolean;
  toggle: () => void;
  start: number;
  end: number;
  timelineWidth: number;
  onHorizontalWheel: (event: WheelEvent) => void;
}) {
  const labelScrollRef = useRef<HTMLDivElement | null>(null);
  const rowsRef = useRef<HTMLDivElement | null>(null);
  const viewportHeight = Math.min(parent.children.length, MAX_VISIBLE_CHILD_ROWS) * ROW_HEIGHT;

  const updateVerticalScroll = (value: number) => {
    rowsRef.current?.style.setProperty("--group-scroll-top", `${value}px`);
  };

  if (parent.standalone) {
    const child = parent.children[0];
    return (
      <section className="timelineGroup timelineStandalone" data-parent-id={parent.id}>
        <div className="timelineStandaloneLabel" title={parent.name}>
          <strong>{parent.name}</strong><span>Archived root</span>
        </div>
        <div
          className="timelineRowsViewport"
          style={{ height: ROW_HEIGHT }}
          onWheel={(event) => {
            if (Math.abs(event.deltaX) > Math.abs(event.deltaY) || event.shiftKey) onHorizontalWheel(event);
          }}
        >
          <div className="timelineRows" style={{ width: timelineWidth, transform: "translateX(calc(0px - var(--scroll-left)))" }}>
            <WeeklyActivityRow child={child} parent={parent} start={start} end={end} timelineWidth={timelineWidth} />
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="timelineGroup" data-parent-id={parent.id}>
      <button className="timelineParent" type="button" onClick={toggle} aria-expanded={!collapsed}>
        <span className="timelineChevron" aria-hidden>{collapsed ? "›" : "⌄"}</span>
        <strong title={parent.name}>{parent.name}</strong>
        <span>{parent.children.length} subproject{parent.children.length === 1 ? "" : "s"}</span>
      </button>
      <div className="timelineParentTrack" aria-hidden />
      {!collapsed ? (
        <>
          <div
            ref={labelScrollRef}
            className={`timelineLabels${parent.children.length > MAX_VISIBLE_CHILD_ROWS ? " hasOverflow" : ""}`}
            style={{ height: viewportHeight }}
            onScroll={(event) => updateVerticalScroll(event.currentTarget.scrollTop)}
          >
            {parent.children.map((child) => <div className="timelineLabel" key={child.id} title={child.name}>{child.name}</div>)}
          </div>
          <div
            className="timelineRowsViewport"
            style={{ height: viewportHeight }}
            onWheel={(event) => {
              if (Math.abs(event.deltaX) > Math.abs(event.deltaY) || event.shiftKey) onHorizontalWheel(event);
              else if (labelScrollRef.current) {
                labelScrollRef.current.scrollTop += event.deltaY;
                event.preventDefault();
              }
            }}
          >
            <div ref={rowsRef} className="timelineRows" style={{ width: timelineWidth, transform: "translate(calc(0px - var(--scroll-left)), calc(0px - var(--group-scroll-top, 0px)))" }}>
              {parent.children.map((child) => <WeeklyActivityRow child={child} parent={parent} start={start} end={end} timelineWidth={timelineWidth} key={child.id} />)}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

export function ProjectTimelineView() {
  const { data, loading, error, refresh } = useProjectTimeline();
  const [filter, setFilter] = useState<"all" | TimelineStatus>("all");
  const [resolution, setResolution] = useState<TimelineResolution>("year");
  const [collapsed, setCollapsed] = useState(() => new Set(sessionState.collapsed));
  const [viewportWidth, setViewportWidth] = useState(MIN_TIMELINE_WIDTH);
  const matrixRef = useRef<HTMLDivElement | null>(null);
  const axisViewportRef = useRef<HTMLDivElement | null>(null);
  const scrollbarRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const viewport = axisViewportRef.current;
    if (!viewport) return;
    const updateWidth = () => setViewportWidth(Math.max(1, Math.round(viewport.clientWidth)));
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [data?.range]);

  const parents = useMemo(() => (data?.parents ?? []).map((parent) => ({
    ...parent,
    children: filter === "all" ? parent.children : parent.children.filter((child) => child.status === filter)
  })).filter((parent) => parent.children.length), [data?.parents, filter]);
  const archivedInPeriod = useMemo(
    () => (data?.parents ?? []).reduce(
      (total, parent) => total + parent.children.filter((child) => child.status === "completed").length,
      0
    ),
    [data?.parents]
  );

  const start = data?.range ? parseDay(data.range.start) : 0;
  const rangeEnd = data?.range ? parseDay(data.range.end) : start;
  const rangeDays = Math.max(1, Math.round((rangeEnd - start) / DAY_MS) + 1);
  const resolutionMeta = RESOLUTION_META[resolution];
  const timelineWidth = Math.max(viewportWidth, Math.ceil(viewportWidth * rangeDays / resolutionMeta.visibleDays));
  const ticks = useMemo(() => buildTicks(start, rangeEnd, resolutionMeta.tickDays), [start, rangeEnd, resolutionMeta.tickDays]);
  const months = useMemo(() => buildMonths(start, rangeEnd), [start, rangeEnd]);
  const xFor = (date: number) => (date - start) / Math.max(DAY_MS, rangeEnd - start + DAY_MS) * timelineWidth;
  const today = new Date();
  const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const showToday = Boolean(data?.range && todayUtc >= start && todayUtc <= rangeEnd);
  const matrixStyle = {
    "--timeline-width": `${timelineWidth}px`,
    "--scroll-left": "0px",
    "--today-x": `${xFor(todayUtc)}px`,
    "--grid-step": `${timelineWidth * resolutionMeta.tickDays / rangeDays}px`
  } as CSSProperties;

  const updateScrollLeft = (value: number) => {
    matrixRef.current?.style.setProperty("--scroll-left", `${value}px`);
  };

  useLayoutEffect(() => {
    const scrollbar = scrollbarRef.current;
    if (!scrollbar) return;
    const latest = Math.max(0, scrollbar.scrollWidth - scrollbar.clientWidth);
    scrollbar.scrollLeft = latest;
    updateScrollLeft(latest);
  }, [data?.range?.start, data?.range?.end, resolution, timelineWidth]);

  const horizontalWheel = (event: WheelEvent) => {
    if (!scrollbarRef.current) return;
    scrollbarRef.current.scrollLeft += event.shiftKey ? event.deltaY : event.deltaX;
    event.preventDefault();
  };
  return (
    <div className="projectTimelinePage">
      <LoadingBar active={loading} />
      <header className="timelineTitleRow">
        <div><p className="eyebrow">Stable</p><h1>Project Timeline</h1><p className="lede">Subprojects by parent project, aligned on one shared reporting axis.</p></div>
        <button className="button buttonGhost" type="button" onClick={refresh} disabled={loading}>Refresh</button>
      </header>

      <section className="timelineCard">
        <div className="timelineToolbar">
          <label className="timelineControl"><span>Resolution</span><select className="select" value={resolution} onChange={(event) => setResolution(event.target.value as TimelineResolution)}>{Object.entries(RESOLUTION_META).map(([value, meta]) => <option value={value} key={value}>{meta.label} per window</option>)}</select></label>
          <label className="timelineControl"><span>Filter</span><select className="select" value={filter} onChange={(event) => setFilter(event.target.value as "all" | TimelineStatus)}><option value="all">All projects</option>{Object.entries(STATUS_META).map(([value, meta]) => <option value={value} key={value}>{meta.label}{value === "completed" ? ` (${archivedInPeriod})` : ""}</option>)}</select></label>
          <div className="timelineLegend" aria-label="Timeline legend"><span className="timelineLegendTitle">Weekly activity</span>{Object.entries(WEEK_META).map(([status, meta]) => <span key={status}><i className={meta.className} />{meta.label}</span>)}</div>
        </div>

        {data?.history ? (
          <aside className="timelineHistoryPanel" aria-label="Fetched history coverage">
            <div><span>History coverage</span><strong>{data.history.activityStart && data.history.activityEnd ? `${dateLabel(data.history.activityStart)} – ${dateLabel(data.history.activityEnd)}` : "No cached activity"}</strong></div>
            <div><span>Projects fetched</span><strong>{data.history.activeProjects} active · {data.history.archivedProjects} archived</strong></div>
            <div><span>Archived loaded</span><strong>{data.history.archivedProjectsInView} of {data.history.archivedProjects}</strong></div>
          </aside>
        ) : null}

        {error ? <div className="timelineEmpty"><strong>Timeline unavailable</strong><span>{error}</span></div> : null}
        {!error && !loading && !parents.length ? <div className="timelineEmpty"><strong>No matching projects</strong><span>Choose another status filter.</span></div> : null}
        {!error && parents.length && data?.range ? (
          <div ref={matrixRef} className="projectTimelineMatrix" style={matrixStyle}>
            {showToday ? <div className="projectTimelineToday"><span>Today</span></div> : null}
            <div className="timelineAxisLabel">Parent project / subprojects</div>
            <div ref={axisViewportRef} className="timelineAxisViewport">
              <div className="timelineAxis" style={{ width: timelineWidth, transform: "translateX(calc(0px - var(--scroll-left)))" }}>
                {months.map((month) => <span className="timelineMonth" key={month.key} style={{ left: xFor(month.middle) }}>{month.label}</span>)}
                {ticks.map((tick) => <span className="timelineTick" key={tick.date} style={{ left: xFor(tick.date) }}>{tick.label}</span>)}
              </div>
            </div>
            <div className="timelineGroups">
              {parents.map((parent) => <ParentGroup key={parent.id} parent={parent} collapsed={collapsed.has(parent.id)} toggle={() => { const next = new Set(collapsed); next.has(parent.id) ? next.delete(parent.id) : next.add(parent.id); sessionState.collapsed = next; setCollapsed(next); }} start={start} end={rangeEnd} timelineWidth={timelineWidth} onHorizontalWheel={horizontalWheel} />)}
            </div>
            <div className="timelineScrollbarSpacer" aria-hidden />
            <div ref={scrollbarRef} className="timelineGlobalScrollbar" aria-label="Scroll the shared project timeline" onScroll={(event) => updateScrollLeft(event.currentTarget.scrollLeft)}><div style={{ width: timelineWidth }} /></div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
