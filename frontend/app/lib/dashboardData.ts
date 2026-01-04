import type { PlotlyFigure } from "../components/PlotCard";
import type { InsightItem } from "../components/InsightCard";
import type { LeaderboardItem } from "../components/LeaderboardCard";
import type { ServiceStatus } from "../components/ServiceMonitor";

export type Health = { status: string; version?: string } | null;

export type Granularity = "W" | "ME" | "3ME";

export type DashboardHome = {
  range: { beg: string; end: string; granularity: Granularity; weeks: number };
  metrics: {
    items: { name: string; value: number; deltaPercent: number | null; inverseDelta: boolean }[];
    currentPeriod: string;
    previousPeriod: string;
  };
  badges: { p1: number; p2: number; p3: number; p4: number };
  insights?: { label?: string; items: InsightItem[] };
  leaderboards?: {
    lastCompletedWeek: {
      label: string;
      beg: string;
      end: string;
      parentProjects: { items: LeaderboardItem[]; totalCompleted: number; figure: PlotlyFigure };
      rootProjects: { items: LeaderboardItem[]; totalCompleted: number; figure: PlotlyFigure };
    };
  };
  figures: Record<string, PlotlyFigure>;
  refreshedAt: string;
  error?: string;
};

export type DashboardStatus = {
  services: ServiceStatus[];
  apiCache: { lastRefresh: string | null };
  activityCache: { path: string; mtime: string | null; size: number | null } | null;
  now: string;
};
