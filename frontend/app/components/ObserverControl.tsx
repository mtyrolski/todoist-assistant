"use client";

import { useCallback, useEffect, useState } from "react";
import { InfoTip } from "./InfoTip";

type ObserverState = {
  enabled: boolean;
  updatedAt?: string | null;
  lastRunAt?: string | null;
  lastDurationSeconds?: number | null;
  lastEvents?: number | null;
  lastStatus?: string | null;
  lastError?: string | null;
};

const OBSERVER_HELP = `**Observer**
Watches Todoist activity and triggers short automations.

- Disable to pause background polling.
- Run once to poll immediately and update activity.`;

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

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "n/a";
  return value.replace("T", " ");
}

function formatDuration(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "n/a";
  return `${value.toFixed(2)}s`;
}

export function ObserverControl({ onAfterMutation }: { onAfterMutation: () => void }) {
  const [state, setState] = useState<ObserverState | null>(null);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState<"toggle" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadState = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/admin/observer");
      const payload = await readJson<ObserverState>(res);
      if (!res.ok) {
        const detail = (payload as unknown as { detail?: unknown })?.detail;
        throw new Error(String(detail ?? "Failed to load observer state"));
      }
      setState(payload);
    } catch (err) {
      setState(null);
      setError(err instanceof Error ? err.message : "Failed to load observer state");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const updateState = async (nextEnabled: boolean) => {
    try {
      setAction("toggle");
      setError(null);
      const res = await fetch("/api/admin/observer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextEnabled })
      });
      const payload = await readJson<ObserverState>(res);
      if (!res.ok) {
        const detail = (payload as unknown as { detail?: unknown })?.detail;
        throw new Error(String(detail ?? "Failed to update observer"));
      }
      setState(payload);
      onAfterMutation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update observer");
    } finally {
      setAction(null);
    }
  };

  const runOnce = async () => {
    try {
      setAction("run");
      setError(null);
      const res = await fetch("/api/admin/observer/run", { method: "POST" });
      const payload = await readJson<{ state?: ObserverState }>(res);
      if (!res.ok) {
        const detail = (payload as unknown as { detail?: unknown })?.detail;
        throw new Error(String(detail ?? "Failed to run observer"));
      }
      if (payload.state) {
        setState(payload.state);
      } else if (payload as unknown as ObserverState) {
        setState(payload as unknown as ObserverState);
      }
      onAfterMutation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run observer");
    } finally {
      setAction(null);
    }
  };

  const enabled = state?.enabled ?? true;
  const statusTone = enabled ? "good" : "warn";
  const statusLabel = enabled ? "Enabled" : "Disabled";
  const lastStatus = state?.lastStatus ? `Status: ${state.lastStatus}` : "No runs yet";
  const lastEvents =
    typeof state?.lastEvents === "number" ? `${state.lastEvents} new events` : "No activity yet";

  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Observer</h2>
          <InfoTip label="About observer" content={OBSERVER_HELP} />
        </div>
        <div className="adminRowRight">
          <span className={`pill pill-${statusTone}`}>{statusLabel}</span>
          <button
            className="button buttonSmall buttonGhost"
            type="button"
            onClick={runOnce}
            disabled={!enabled || action !== null}
          >
            {action === "run" ? "Running..." : "Run once"}
          </button>
          <button
            className="button buttonSmall"
            type="button"
            onClick={() => updateState(!enabled)}
            disabled={action !== null}
          >
            {action === "toggle" ? "Updating..." : enabled ? "Disable" : "Enable"}
          </button>
        </div>
      </header>

      {loading && !state ? (
        <div className="skeleton" style={{ minHeight: 140 }} />
      ) : (
        <div className="list">
          <div className="row rowTight">
            <div className={`dot dot-${enabled ? "ok" : "warn"}`} />
            <div className="rowMain">
              <p className="rowTitle">Observer {statusLabel.toLowerCase()}</p>
              <p className="muted tiny">Last run {formatTimestamp(state?.lastRunAt)}</p>
            </div>
            <p className="rowDetail">{lastStatus}</p>
          </div>
          <div className="row rowTight">
            <div className="dot dot-neutral" />
            <div className="rowMain">
              <p className="rowTitle">Latest tick</p>
              <p className="muted tiny">{lastEvents}</p>
            </div>
            <p className="rowDetail">{formatDuration(state?.lastDurationSeconds)}</p>
          </div>
          {state?.lastError ? <p className="muted tiny">Error: {state.lastError}</p> : null}
          {error ? <p className="muted tiny">Notice: {error}</p> : null}
        </div>
      )}
    </section>
  );
}
