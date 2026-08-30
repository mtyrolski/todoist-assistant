"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties, type WheelEvent } from "react";
import { LoadingBar } from "./LoadingBar";
import { useProjectTimeline } from "../lib/dashboardHooks";
import type { ProjectTimelineChild, ProjectTimelineParent, TimelineStatus } from "../lib/projectTimeline";

const ROW_HEIGHT = 31;
const MAX_VISIBLE_CHILD_ROWS = 6;
const MIN_TIMELINE_WIDTH = 1060;
const PIXELS_PER_DAY = 12;
const DAY_MS = 86_400_000;

const STATUS_META: Record<TimelineStatus, { label: string; className: string }> = {
  completed: { label: "Archived in period", className: "isCompleted" },
  ongoing: { label: "Ongoing", className: "isOngoing" },
  unresolved: { label: "No completion in period", className: "isUnresolved" },
  inactive: { label: "No activity", className: "isInactive" }
};

const sessionState = {
  collapsed: new Set<string>(),
  scrollLeft: 0,
  scrollTop: new Map<string, number>()
};

function parseDay(value: string): number {
  return Date.parse(`${value}T00:00:00Z`);
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(parseDay(value));
}

function buildTicks(start: number, end: number) {
  const ticks: { date: number; label: string }[] = [];
  const cursor = new Date(start);
  cursor.setUTCDate(cursor.getUTCDate() + ((8 - cursor.getUTCDay()) % 7));
  while (cursor.getTime() <= end) {
    ticks.push({ date: cursor.getTime(), label: String(cursor.getUTCDate()).padStart(2, "0") });
    cursor.setUTCDate(cursor.getUTCDate() + 7);
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
    `Parent project: ${parent.name}`,
    `Status: ${meta.label}`,
    `Start: ${dateLabel(child.startDate)}`,
    child.endDate ? `End: ${dateLabel(child.endDate)}` : "End: Ongoing",
    child.archiveDate ? `Archive date: ${dateLabel(child.archiveDate)}` : null,
    `Duration: ${child.durationDays} day${child.durationDays === 1 ? "" : "s"}`,
    `Archived: ${child.archived ? "Yes" : "No"}`
  ].filter(Boolean).join("\n");
}

function ParentGroup({
  parent,
  collapsed,
  toggle,
  start,
  end,
  timelineWidth,
  scrollLeft,
  scrollTop,
  onScrollTop,
  onScrollLeft
}: {
  parent: ProjectTimelineParent;
  collapsed: boolean;
  toggle: () => void;
  start: number;
  end: number;
  timelineWidth: number;
  scrollLeft: number;
  scrollTop: number;
  onScrollTop: (value: number) => void;
  onScrollLeft: (value: number) => void;
}) {
  const labelScrollRef = useRef<HTMLDivElement | null>(null);
  const horizontalScrollRef = useRef<HTMLDivElement | null>(null);
  const viewportHeight = Math.min(parent.children.length, MAX_VISIBLE_CHILD_ROWS) * ROW_HEIGHT;
  const duration = Math.max(DAY_MS, end - start + DAY_MS);

  useEffect(() => {
    if (labelScrollRef.current && labelScrollRef.current.scrollTop !== scrollTop) labelScrollRef.current.scrollTop = scrollTop;
  }, [scrollTop]);

  useEffect(() => {
    if (horizontalScrollRef.current && horizontalScrollRef.current.scrollLeft !== scrollLeft) horizontalScrollRef.current.scrollLeft = scrollLeft;
  }, [scrollLeft]);

  const horizontalWheel = (event: WheelEvent) => {
    if (!horizontalScrollRef.current) return;
    horizontalScrollRef.current.scrollLeft += event.shiftKey ? event.deltaY : event.deltaX;
    event.preventDefault();
  };

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
            onScroll={(event) => onScrollTop(event.currentTarget.scrollTop)}
          >
            {parent.children.map((child) => <div className="timelineLabel" key={child.id} title={child.name}>{child.name}</div>)}
          </div>
          <div
            className="timelineRowsViewport"
            style={{ height: viewportHeight }}
            onWheel={(event) => {
              if (Math.abs(event.deltaX) > Math.abs(event.deltaY) || event.shiftKey) horizontalWheel(event);
              else if (labelScrollRef.current) {
                labelScrollRef.current.scrollTop += event.deltaY;
                event.preventDefault();
              }
            }}
          >
            <div className="timelineRows" style={{ width: timelineWidth, transform: `translate(${-scrollLeft}px, ${-scrollTop}px)` }}>
              {parent.children.map((child) => {
                const left = Math.max(0, (parseDay(child.visualStart) - start) / duration * timelineWidth);
                const right = Math.min(timelineWidth, (parseDay(child.visualEnd) - start + DAY_MS) / duration * timelineWidth);
                return (
                  <div className="timelineRow" key={child.id}>
                    <span
                      className={`timelineBar ${STATUS_META[child.status].className}`}
                      style={{ left, width: Math.max(5, right - left) }}
                      title={tooltip(child, parent)}
                      aria-label={tooltip(child, parent)}
                    />
                  </div>
                );
              })}
            </div>
          </div>
          <div className="timelineGroupScrollbarSpacer" aria-hidden />
          <div
            ref={horizontalScrollRef}
            className="timelineGroupScrollbar"
            aria-label={`Scroll ${parent.name} timeline`}
            onScroll={(event) => onScrollLeft(event.currentTarget.scrollLeft)}
          >
            <div style={{ width: timelineWidth }} />
          </div>
        </>
      ) : null}
    </section>
  );
}

export function ProjectTimelineView() {
  const { data, loading, error, weeks, setRollingWeeks, setCustomRange, refresh } = useProjectTimeline();
  const [filter, setFilter] = useState<"all" | TimelineStatus>("all");
  const [collapsed, setCollapsed] = useState(() => new Set(sessionState.collapsed));
  const [scrollLeft, setScrollLeft] = useState(sessionState.scrollLeft);
  const [parentScroll, setParentScroll] = useState(() => new Map(sessionState.scrollTop));
  const [beg, setBeg] = useState("");
  const [end, setEnd] = useState("");

  useEffect(() => {
    if (data?.range) { setBeg(data.range.start); setEnd(data.range.end); }
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
  const timelineWidth = Math.max(MIN_TIMELINE_WIDTH, rangeDays * PIXELS_PER_DAY);
  const ticks = useMemo(() => buildTicks(start, rangeEnd), [start, rangeEnd]);
  const months = useMemo(() => buildMonths(start, rangeEnd), [start, rangeEnd]);
  const xFor = (date: number) => (date - start) / Math.max(DAY_MS, rangeEnd - start + DAY_MS) * timelineWidth;
  const today = new Date();
  const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const showToday = Boolean(data?.range && todayUtc >= start && todayUtc <= rangeEnd);
  const matrixStyle = {
    "--timeline-width": `${timelineWidth}px`,
    "--scroll-left": `${scrollLeft}px`,
    "--today-x": `${xFor(todayUtc)}px`,
    "--grid-step": `${timelineWidth * 7 / rangeDays}px`
  } as CSSProperties;

  const updateScrollLeft = (value: number) => {
    sessionState.scrollLeft = value;
    setScrollLeft(value);
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
          <div className="timelineControl timelineRangeControl">
            <span>Range</span>
            <div><input className="dateInput" type="date" value={beg} onChange={(event) => setBeg(event.target.value)} /><span>–</span><input className="dateInput" type="date" value={end} onChange={(event) => setEnd(event.target.value)} /><button className="button buttonGhost" type="button" disabled={!beg || !end || beg > end} onClick={() => setCustomRange({ beg, end })}>Apply</button></div>
          </div>
          <label className="timelineControl"><span>Period</span><select className="select" value={weeks} onChange={(event) => setRollingWeeks(Number(event.target.value))}><option value={0}>All fetched history</option><option value={4}>1 month</option><option value={12}>3 months</option><option value={26}>6 months</option><option value={52}>12 months</option></select></label>
          <label className="timelineControl"><span>Filter</span><select className="select" value={filter} onChange={(event) => setFilter(event.target.value as "all" | TimelineStatus)}><option value="all">All projects</option>{Object.entries(STATUS_META).map(([value, meta]) => <option value={value} key={value}>{meta.label}{value === "completed" ? ` (${archivedInPeriod})` : ""}</option>)}</select></label>
          <div className="timelineLegend" aria-label="Timeline legend"><span className="timelineLegendTitle">Legend</span>{Object.entries(STATUS_META).map(([status, meta]) => <span key={status}><i className={meta.className} />{meta.label}</span>)}</div>
        </div>

        {data?.history ? (
          <aside className="timelineHistoryPanel" aria-label="Fetched history coverage">
            <div><span>History coverage</span><strong>{data.history.activityStart && data.history.activityEnd ? `${dateLabel(data.history.activityStart)} – ${dateLabel(data.history.activityEnd)}` : "No cached activity"}</strong></div>
            <div><span>Projects fetched</span><strong>{data.history.activeProjects} active · {data.history.archivedProjects} archived</strong></div>
            <div><span>Archived in view</span><strong>{data.history.archivedProjectsInView} of {data.history.archivedProjects}</strong></div>
          </aside>
        ) : null}

        {error ? <div className="timelineEmpty"><strong>Timeline unavailable</strong><span>{error}</span></div> : null}
        {!error && !loading && !parents.length ? <div className="timelineEmpty"><strong>No projects in this period</strong><span>Choose another range or status filter.</span></div> : null}
        {!error && parents.length && data?.range ? (
          <div className="projectTimelineMatrix" style={matrixStyle}>
            {showToday ? <div className="projectTimelineToday"><span>Today</span></div> : null}
            <div className="timelineAxisLabel">Parent project / subprojects</div>
            <div className="timelineAxisViewport">
              <div className="timelineAxis" style={{ width: timelineWidth, transform: `translateX(${-scrollLeft}px)` }}>
                {months.map((month) => <span className="timelineMonth" key={month.key} style={{ left: xFor(month.middle) }}>{month.label}</span>)}
                {ticks.map((tick) => <span className="timelineTick" key={tick.date} style={{ left: xFor(tick.date) }}>{tick.label}</span>)}
              </div>
            </div>
            <div className="timelineGroups">
              {parents.map((parent) => <ParentGroup key={parent.id} parent={parent} collapsed={collapsed.has(parent.id)} toggle={() => { const next = new Set(collapsed); next.has(parent.id) ? next.delete(parent.id) : next.add(parent.id); sessionState.collapsed = next; setCollapsed(next); }} start={start} end={rangeEnd} timelineWidth={timelineWidth} scrollLeft={scrollLeft} scrollTop={parentScroll.get(parent.id) ?? 0} onScrollTop={(value) => { const next = new Map(parentScroll).set(parent.id, value); sessionState.scrollTop = next; setParentScroll(next); }} onScrollLeft={updateScrollLeft} />)}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
