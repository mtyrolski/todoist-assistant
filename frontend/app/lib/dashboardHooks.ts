"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { DashboardHome, DashboardStatus, Granularity, Health } from "./dashboardData";
import type { DashboardProgress } from "../components/ProgressSteps";
import type { LlmBreakdownProgress } from "../components/LlmBreakdownStatus";

const DASHBOARD_RETRY_LIMIT = 300;
const DASHBOARD_RETRY_DELAY_MS = 2500;

async function readJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    const snippet = text.trim();
    const summary = snippet.length > 200 ? `${snippet.slice(0, 200)}...` : snippet;
    throw new Error(summary ? `Invalid JSON response: ${summary}` : "Invalid JSON response");
  }
}

function isRetryableFetchError(message: string): boolean {
  return /invalid json response|failed to fetch|networkerror|socket hang up|econnrefused|econnreset|timed out|timeout/i.test(
    message
  );
}

export function useApiHealth(pollMs = 10_000) {
  const [health, setHealth] = useState<Health>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        setLoadingHealth(true);
        setError(null);
        const res = await fetch("/api/health");
        if (!res.ok) throw new Error("API unavailable");
        const data = await readJson<Health>(res);
        setHealth(data);
      } catch {
        setError("Unable to connect to the API server. Please check that the backend is running.");
      } finally {
        setLoadingHealth(false);
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, pollMs);
    return () => clearInterval(interval);
  }, [pollMs]);

  return { health, loadingHealth, error };
}

export function useDashboardHome({
  defaultGranularity = "W",
  defaultWeeks = 12,
  enabled = true
}: {
  defaultGranularity?: Granularity;
  defaultWeeks?: number;
  enabled?: boolean;
} = {}) {
  const [granularity, setGranularity] = useState<Granularity>(defaultGranularity);
  const [weeks, setWeeks] = useState<number>(defaultWeeks);
  const [rangeMode, setRangeMode] = useState<"rolling" | "custom">("rolling");
  const [customBeg, setCustomBeg] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [refreshNonce, setRefreshNonce] = useState<number>(0);
  const lastRefreshNonce = useRef<number>(0);
  const [retryNonce, setRetryNonce] = useState<number>(0);
  const retryAttempts = useRef<number>(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [dashboard, setDashboard] = useState<DashboardHome | null>(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [progress, setProgress] = useState<DashboardProgress | null>(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setLoadingDashboard(false);
      setDashboardError(null);
      setRetrying(false);
      if (retryTimer.current) {
        clearTimeout(retryTimer.current);
        retryTimer.current = null;
      }
      return;
    }
    const controller = new AbortController();
    const load = async () => {
      try {
        setLoadingDashboard(true);
        setDashboardError(null);
        const shouldRefresh = refreshNonce !== lastRefreshNonce.current;
        lastRefreshNonce.current = refreshNonce;
        const qs = new URLSearchParams({ granularity, refresh: shouldRefresh ? "true" : "false" });
        if (rangeMode === "custom" && customBeg && customEnd) {
          qs.set("beg", customBeg);
          qs.set("end", customEnd);
        } else {
          qs.set("weeks", String(weeks));
        }
        const res = await fetch(`/api/dashboard/home?${qs.toString()}`, { signal: controller.signal });
        const payload = await readJson<DashboardHome>(res);
        if (!res.ok || payload.error) {
          const detail = payload.error ?? (payload as unknown as { detail?: string })?.detail;
          throw new Error(detail ?? `Failed to load dashboard (${res.status})`);
        }
        setDashboard(payload);
        setRetrying(false);
        retryAttempts.current = 0;
        if (retryTimer.current) {
          clearTimeout(retryTimer.current);
          retryTimer.current = null;
        }
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
        setDashboard(null);
        const message = e instanceof Error ? e.message : "Failed to load dashboard";
        if (isRetryableFetchError(message) && retryAttempts.current < DASHBOARD_RETRY_LIMIT) {
          retryAttempts.current += 1;
          setRetrying(true);
          setDashboardError("Dashboard API is starting. Retrying shortly...");
          if (retryTimer.current) {
            clearTimeout(retryTimer.current);
          }
          retryTimer.current = setTimeout(() => {
            setRetryNonce((value) => value + 1);
          }, DASHBOARD_RETRY_DELAY_MS);
          return;
        }
        setRetrying(false);
        setDashboardError(message);
      } finally {
        setLoadingDashboard(false);
      }
    };
    load();
    return () => controller.abort();
  }, [enabled, granularity, weeks, rangeMode, customBeg, customEnd, refreshNonce, retryNonce]);

  useEffect(() => {
    return () => {
      if (retryTimer.current) {
        clearTimeout(retryTimer.current);
        retryTimer.current = null;
      }
    };
  }, []);

  const shouldPollProgress = enabled && (loadingDashboard || retrying || (!dashboard && !dashboardError));

  useEffect(() => {
    if (!shouldPollProgress) {
      setProgress(null);
      return;
    }
    const controller = new AbortController();
    let active = true;

    const loadProgress = async () => {
      try {
        const res = await fetch("/api/dashboard/progress", { signal: controller.signal });
        if (!res.ok) return;
        const payload = await readJson<DashboardProgress>(res);
        if (!active) return;
        setProgress(payload);
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
      }
    };

    loadProgress();
    const interval = setInterval(loadProgress, 700);
    return () => {
      active = false;
      controller.abort();
      clearInterval(interval);
    };
  }, [shouldPollProgress]);

  const progressDisplay = useMemo(() => {
    if (progress?.active) return progress;
    if (!shouldPollProgress) return null;
    return {
      active: true,
      stage: null,
      step: 1,
      totalSteps: 3,
      startedAt: null,
      updatedAt: null,
      detail: "Connecting to the API and preparing the dashboard...",
      error: null
    } satisfies DashboardProgress;
  }, [progress, shouldPollProgress]);

  const refresh = () => setRefreshNonce((value) => value + 1);

  return {
    dashboard,
    loadingDashboard,
    dashboardError,
    progressDisplay,
    retrying,
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
  };
}

export function useDashboardStatus({ pollMs = 30_000 }: { pollMs?: number } = {}) {
  const [status, setStatus] = useState<DashboardStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [statusRefreshNonce, setStatusRefreshNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        setLoadingStatus(true);
        const qs = new URLSearchParams({ refresh: statusRefreshNonce ? "true" : "false" });
        const res = await fetch(`/api/dashboard/status?${qs.toString()}`, { signal: controller.signal });
        if (!res.ok) throw new Error("status");
        const payload = await readJson<DashboardStatus>(res);
        setStatus(payload);
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
        setStatus(null);
      } finally {
        setLoadingStatus(false);
      }
    };
    load();
    return () => controller.abort();
  }, [statusRefreshNonce]);

  const refreshStatus = () => setStatusRefreshNonce((value) => value + 1);

  useEffect(() => {
    if (!pollMs) return;
    const interval = setInterval(() => setStatusRefreshNonce((value) => value + 1), pollMs);
    return () => clearInterval(interval);
  }, [pollMs]);

  return { status, loadingStatus, refreshStatus };
}

export function useSyncLabel(status: DashboardStatus | null) {
  const [syncClock, setSyncClock] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setSyncClock(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, []);

  const label = useMemo(() => {
    if (!status) return "Sync status unavailable";
    const activityCache = status.activityCache;
    if (!activityCache) return "Activity cache missing";
    const lastRefresh = activityCache.mtime;
    if (!lastRefresh) return "Sync time unknown";
    const lastMs = Date.parse(lastRefresh);
    if (Number.isNaN(lastMs)) return "Sync unknown";
    const diffMs = Math.max(0, syncClock - lastMs);
    if (diffMs < 60_000) return "Synced just now";
    const minutes = Math.floor(diffMs / 60_000);
    if (minutes < 60) return `Synced ${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Synced ${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `Synced ${days}d ago`;
  }, [status, syncClock]);

  const title = useMemo(() => {
    if (!status) return undefined;
    if (!status.activityCache) return "activity.joblib missing";
    return status.activityCache.mtime ?? "sync time unavailable";
  }, [status]);

  return { label, title };
}

export function useLlmBreakdownProgress({ pollMs = 2000 }: { pollMs?: number } = {}) {
  const [progress, setProgress] = useState<LlmBreakdownProgress | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    const load = async () => {
      try {
        setLoading(true);
        const res = await fetch("/api/dashboard/llm_breakdown", { signal: controller.signal });
        if (!res.ok) throw new Error("llm-progress");
        const payload = await readJson<LlmBreakdownProgress>(res);
        if (!active) return;
        setProgress(payload);
      } catch (e) {
        if (e && typeof e === "object" && "name" in e && (e as { name?: string }).name === "AbortError") {
          return;
        }
        setProgress(null);
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    const interval = setInterval(load, pollMs);
    return () => {
      active = false;
      controller.abort();
      clearInterval(interval);
    };
  }, [pollMs, refreshNonce]);

  const refresh = () => setRefreshNonce((value) => value + 1);

  return { progress, loading, refresh };
}
