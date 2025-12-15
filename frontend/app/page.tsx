"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PlotCard, type PlotlyFigure } from "./components/PlotCard";
import { StatCard } from "./components/StatCard";

type Health = { status: string } | null;

type Granularity = "W" | "ME" | "3ME";

type DashboardHome = {
  range: { beg: string; end: string; granularity: Granularity; weeks: number };
  metrics: {
    items: { name: string; value: number; deltaPercent: number | null; inverseDelta: boolean }[];
    currentPeriod: string;
    previousPeriod: string;
  };
  badges: { p1: number; p2: number; p3: number; p4: number };
  figures: Record<string, PlotlyFigure>;
  refreshedAt: string;
  error?: string;
};

export default function Page() {
  const [health, setHealth] = useState<Health>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [granularity, setGranularity] = useState<Granularity>("W");
  const [weeks, setWeeks] = useState<number>(12);
  const [refreshNonce, setRefreshNonce] = useState<number>(0);
  const lastRefreshNonce = useRef<number>(0);
  const [dashboard, setDashboard] = useState<DashboardHome | null>(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);

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
        setError("Backend not reachable yet. Start `make run_dashboard`.");
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
        const shouldRefresh = refreshNonce !== lastRefreshNonce.current;
        lastRefreshNonce.current = refreshNonce;
        const qs = new URLSearchParams({
          granularity,
          weeks: String(weeks),
          refresh: shouldRefresh ? "true" : "false"
        });
        const res = await fetch(`/api/dashboard/home?${qs.toString()}`, { signal: controller.signal });
        const payload = (await res.json()) as DashboardHome;
        if (!res.ok || payload.error) {
          throw new Error(payload.error ?? "Failed to load dashboard");
        }
        setDashboard(payload);
      } catch (e) {
        setDashboard(null);
      } finally {
        setLoadingDashboard(false);
      }
    };
    load();
    return () => controller.abort();
  }, [granularity, weeks, refreshNonce]);

  const periodLabel = useMemo(() => {
    if (!dashboard) return null;
    return `${dashboard.range.beg} → ${dashboard.range.end}`;
  }, [dashboard]);

  const figures = dashboard?.figures ?? {};

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Todoist Assistant</p>
          <h1>Dashboard</h1>
          <p className="lede">
            Same signals as the Streamlit home page, in a faster, cleaner dark UI.
          </p>
          <div className="status-row">
            <span className={`pill ${health?.status === "ok" ? "pill-good" : "pill-warn"}`}>
              {loadingHealth ? "Checking API…" : health?.status === "ok" ? "API online" : "API offline"}
            </span>
            {periodLabel && <span className="pill">{periodLabel}</span>}
            {error && <span className="pill pill-warn">{error}</span>}
          </div>
        </div>
        <div className="controls">
          <label className="control">
            <span className="muted tiny">Granularity</span>
            <select
              value={granularity}
              onChange={(e) => setGranularity(e.target.value as Granularity)}
              className="select"
            >
              <option value="W">Week</option>
              <option value="ME">Month</option>
              <option value="3ME">Three Months</option>
            </select>
          </label>
          <label className="control">
            <span className="muted tiny">Range</span>
            <select value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} className="select">
              <option value={12}>Last 12 weeks</option>
              <option value={26}>Last 26 weeks</option>
              <option value={52}>Last 52 weeks</option>
            </select>
          </label>
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

      <section className="grid2">
        <PlotCard title="Current Tasks Types" figure={figures.currentTasksTypes} height={420} />
        <PlotCard title="Most Popular Labels" figure={figures.mostPopularLabels} height={420} />
      </section>

      <section className="statsRow">
        {(dashboard?.metrics.items ?? Array.from({ length: 4 }).map(() => null)).map((m, idx) =>
          m ? (
            <StatCard
              key={m.name}
              name={m.name}
              value={m.value}
              deltaPercent={m.deltaPercent}
              inverseDelta={m.inverseDelta}
              currentPeriod={dashboard.metrics.currentPeriod}
              previousPeriod={dashboard.metrics.previousPeriod}
            />
          ) : (
            <div key={idx} className="stat skeleton" />
          )
        )}
      </section>

      <section className="badges">
        <span className="badge badge-p1">P1 {dashboard?.badges.p1 ?? "—"}</span>
        <span className="badge badge-p2">P2 {dashboard?.badges.p2 ?? "—"}</span>
        <span className="badge badge-p3">P3 {dashboard?.badges.p3 ?? "—"}</span>
        <span className="badge badge-p4">P4 {dashboard?.badges.p4 ?? "—"}</span>
      </section>

      <section className="stack">
        <PlotCard title="Task Lifespans: Time to Completion" figure={figures.taskLifespans} height={460} />
        <PlotCard
          title="Periodically Completed Tasks Per Project"
          figure={figures.completedTasksPeriodically}
          height={520}
        />
        <PlotCard
          title="Cumulative Periodically Completed Tasks Per Project"
          figure={figures.cumsumCompletedTasksPeriodically}
          height={520}
        />
        <PlotCard title="Heatmap of Events by Day and Hour" figure={figures.heatmapEventsByDayHour} height={520} />
        <PlotCard title="Events Over Time" figure={figures.eventsOverTime} height={520} />
      </section>
    </div>
  );
}
