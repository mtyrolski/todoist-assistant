"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { InfoTip } from "./InfoTip";
import { ProjectAdjustmentsBoard } from "./ProjectAdjustmentsBoard";

type Tab = "automations" | "adjustments" | "settings";

type AutomationInfo = {
  name: string;
  frequencyMinutes: number;
  isLong: boolean;
  launchCount: number;
  lastLaunch: string | null;
};

type AutomationListResponse = { automations: AutomationInfo[] };

type RunResult = {
  name: string;
  startedAt: string;
  finishedAt: string;
  durationSeconds: number;
  output: string;
  taskDelegations: unknown;
};

type RunAllResult = { results: RunResult[] };

type AdminJob = {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  result: unknown;
  error: string | null;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const ADMIN_HELP = `**Dashboard Admin**
Manage automations, project mappings, and local dashboard settings.

- Automations follow the same cooldown rules as the observer.
- Adjustments map archived projects to active roots.
- Settings updates your local Todoist API token.`;

type ApiTokenStatus = {
  configured: boolean;
  masked: string;
  envPath: string;
};

type TimezoneStatus = {
  configured: boolean;
  timezone: string;
  source: "system" | "env";
  override: string | null;
  overrideValid: boolean;
  system: string;
  envPath: string;
  invalidOverride?: string;
};

function formatLaunchMeta(a: AutomationInfo): string {
  const last = a.lastLaunch ? `last: ${a.lastLaunch}` : "never run";
  const freq = `freq: ${a.frequencyMinutes}m`;
  const count = `runs: ${a.launchCount}`;
  return `${last} • ${freq} • ${count}`;
}

export function AdminPanel({ onAfterMutation }: { onAfterMutation: () => void }) {
  const [tab, setTab] = useState<Tab>("automations");

  const [automations, setAutomations] = useState<AutomationInfo[] | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [runOutput, setRunOutput] = useState<Record<string, RunResult>>({});
  const [adminError, setAdminError] = useState<string | null>(null);
  const [adminNotice, setAdminNotice] = useState<string | null>(null);

  const [tokenStatus, setTokenStatus] = useState<ApiTokenStatus | null>(null);
  const [tokenDraft, setTokenDraft] = useState<string>("");
  const [tokenSaving, setTokenSaving] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenNotice, setTokenNotice] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [timezoneStatus, setTimezoneStatus] = useState<TimezoneStatus | null>(null);
  const [timezoneDraft, setTimezoneDraft] = useState<string>("");
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [timezoneError, setTimezoneError] = useState<string | null>(null);
  const [timezoneNotice, setTimezoneNotice] = useState<string | null>(null);

  useEffect(() => {
    const loadAutomations = async () => {
      try {
        const res = await fetch("/api/admin/automations");
        const payload = (await res.json()) as AutomationListResponse & { error?: string };
        if (!res.ok) throw new Error("automations");
        if (payload.error) {
          setAutomations(payload.automations ?? []);
          setAdminError(payload.error);
          return;
        }
        setAutomations(payload.automations);
      } catch {
        setAutomations(null);
        setAdminError("Failed to load automations (check API logs).");
      }
    };
    loadAutomations();
  }, []);

  const loadApiToken = async () => {
    try {
      const res = await fetch("/api/admin/api_token");
      const payload = (await res.json()) as ApiTokenStatus;
      if (!res.ok) throw new Error("api_token");
      setTokenStatus(payload);
    } catch {
      setTokenStatus(null);
    }
  };

  const loadTimezone = async () => {
    try {
      const res = await fetch("/api/admin/timezone");
      const payload = (await res.json()) as TimezoneStatus;
      if (!res.ok) throw new Error("timezone");
      setTimezoneStatus(payload);
      setTimezoneDraft(payload.override ?? "");
    } catch {
      setTimezoneStatus(null);
    }
  };

  useEffect(() => {
    loadApiToken();
  }, []);

  useEffect(() => {
    loadTimezone();
  }, []);

  const waitForJob = async (jobId: string): Promise<AdminJob> => {
    for (;;) {
      const res = await fetch(`/api/admin/jobs/${encodeURIComponent(jobId)}`);
      const payload = (await res.json()) as AdminJob;
      if (!res.ok) {
        const detail = (payload as unknown as { detail?: unknown })?.detail;
        throw new Error(String(detail ?? "Job lookup failed"));
      }
      if (payload.status === "done" || payload.status === "failed") return payload;
      await sleep(800);
    }
  };

  const runAutomation = async (name: string) => {
    try {
      setAdminError(null);
      setAdminNotice(null);
      setRunning(name);
      const start = await fetch(`/api/admin/automations/run_async?name=${encodeURIComponent(name)}`, { method: "POST" });
      const startPayload = (await start.json()) as { jobId?: string; detail?: unknown };
      if (!start.ok || !startPayload.jobId) {
        throw new Error(String(startPayload.detail ?? "Failed to start automation job"));
      }
      setAdminNotice(`Automation job started: ${startPayload.jobId}`);
      const job = await waitForJob(startPayload.jobId);
      if (job.status === "failed") {
        throw new Error(job.error ?? "Automation job failed");
      }
      const run = job.result as RunResult;
      setRunOutput((prev) => ({ ...prev, [name]: run }));
      onAfterMutation();
      const metaRes = await fetch("/api/admin/automations");
      if (metaRes.ok) {
        const list = (await metaRes.json()) as AutomationListResponse;
        setAutomations(list.automations);
      }
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : "Failed to run automation");
    } finally {
      setRunning(null);
    }
  };

  const runAll = async () => {
    try {
      setAdminError(null);
      setAdminNotice(null);
      setRunning("__all__");
      const start = await fetch("/api/admin/automations/run_all_async", { method: "POST" });
      const startPayload = (await start.json()) as { jobId?: string; detail?: unknown };
      if (!start.ok || !startPayload.jobId) {
        throw new Error(String(startPayload.detail ?? "Failed to start automation job"));
      }
      setAdminNotice(`Automation job started: ${startPayload.jobId}`);
      const job = await waitForJob(startPayload.jobId);
      if (job.status === "failed") {
        throw new Error(job.error ?? "Automation job failed");
      }
      const result = job.result as RunAllResult;
      const byName: Record<string, RunResult> = {};
      for (const r of result.results) byName[r.name] = r;
      setRunOutput((prev) => ({ ...prev, ...byName }));
      onAfterMutation();
      const metaRes = await fetch("/api/admin/automations");
      if (metaRes.ok) {
        const list = (await metaRes.json()) as AutomationListResponse;
        setAutomations(list.automations);
      }
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : "Failed to run automations");
    } finally {
      setRunning(null);
    }
  };

  const saveApiToken = async () => {
    if (!tokenDraft.trim()) {
      setTokenError("Paste your Todoist API token.");
      return;
    }
    try {
      setTokenSaving(true);
      setTokenError(null);
      setTokenNotice(null);
      const res = await fetch("/api/admin/api_token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: tokenDraft.trim(), validate: true })
      });
      const payload = (await res.json()) as ApiTokenStatus & { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to save token");
      }
      setTokenStatus(payload);
      setTokenDraft("");
      setTokenNotice("API token saved and validated.");
      onAfterMutation();
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "Failed to save token");
    } finally {
      setTokenSaving(false);
    }
  };

  const clearApiToken = async () => {
    try {
      setTokenSaving(true);
      setTokenError(null);
      setTokenNotice(null);
      const res = await fetch("/api/admin/api_token", { method: "DELETE" });
      const payload = (await res.json()) as ApiTokenStatus;
      if (!res.ok) throw new Error("clear_token");
      setTokenStatus(payload);
      setTokenNotice("API token removed.");
      onAfterMutation();
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "Failed to clear token");
    } finally {
      setTokenSaving(false);
    }
  };

  const saveTimezone = async () => {
    if (!timezoneDraft.trim()) {
      setTimezoneError("Provide an IANA timezone (example: Europe/Warsaw).");
      return;
    }
    try {
      setTimezoneSaving(true);
      setTimezoneError(null);
      setTimezoneNotice(null);
      const res = await fetch("/api/admin/timezone", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timezone: timezoneDraft.trim() })
      });
      const payload = (await res.json()) as TimezoneStatus & { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to save timezone");
      }
      setTimezoneStatus(payload);
      setTimezoneDraft(payload.override ?? "");
      setTimezoneNotice("Timezone override saved.");
      onAfterMutation();
    } catch (e) {
      setTimezoneError(e instanceof Error ? e.message : "Failed to save timezone");
    } finally {
      setTimezoneSaving(false);
    }
  };

  const clearTimezone = async () => {
    try {
      setTimezoneSaving(true);
      setTimezoneError(null);
      setTimezoneNotice(null);
      const res = await fetch("/api/admin/timezone", { method: "DELETE" });
      const payload = (await res.json()) as TimezoneStatus;
      if (!res.ok) throw new Error("clear_timezone");
      setTimezoneStatus(payload);
      setTimezoneDraft("");
      setTimezoneNotice("Timezone override removed (using system timezone).");
      onAfterMutation();
    } catch (e) {
      setTimezoneError(e instanceof Error ? e.message : "Failed to clear timezone");
    } finally {
      setTimezoneSaving(false);
    }
  };

  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Dashboard Admin</h2>
          <InfoTip label="About dashboard admin" content={ADMIN_HELP} />
        </div>
        <div className="adminRowRight">
          <div className="segmented">
            <button className={`seg ${tab === "automations" ? "segActive" : ""}`} onClick={() => setTab("automations")} type="button">
              Automations
            </button>
            <button className={`seg ${tab === "adjustments" ? "segActive" : ""}`} onClick={() => setTab("adjustments")} type="button">
              Project Adjustments
            </button>
            <button className={`seg ${tab === "settings" ? "segActive" : ""}`} onClick={() => setTab("settings")} type="button">
              Settings
            </button>
          </div>
          <Link className="button buttonSmall buttonGhost" href="/live-logs">
            Open Live Logs
          </Link>
        </div>
      </header>

      {adminError ? <p className="pill pill-warn" style={{ margin: "0 0 12px" }}>{adminError}</p> : null}
      {adminNotice ? <p className="pill" style={{ margin: "0 0 12px" }}>{adminNotice}</p> : null}

      {tab === "automations" ? (
        <div className="stack">
          <div className="adminRow">
            <p className="muted tiny" style={{ margin: 0 }}>
              Run configured automations (same frequency gating as the observer).
            </p>
            <button className="button buttonSmall" onClick={runAll} type="button" disabled={running !== null}>
              {running === "__all__" ? "Running…" : "Run all"}
            </button>
          </div>
          <div className="list">
            {!automations ? (
              <p className="muted tiny" style={{ margin: 0 }}>
                Automations list unavailable.
              </p>
            ) : (
              automations.map((a) => (
                <div key={a.name} className="row rowTight">
                  <div className="dot dot-neutral" />
                  <div className="rowMain">
                    <p className="rowTitle">{a.name}</p>
                    <p className="muted tiny">{formatLaunchMeta(a)}</p>
                  </div>
                  <div className="rowActions">
                    <button
                      className="button buttonSmall"
                      onClick={() => runAutomation(a.name)}
                      type="button"
                      disabled={running !== null}
                    >
                      {running === a.name ? "Running…" : "Run"}
                    </button>
                  </div>
                  {runOutput[a.name] ? (
                    <details className="rowDetails">
                      <summary className="muted tiny">Output</summary>
                      <pre className="codeBlock">{runOutput[a.name].output || "(no output)"}</pre>
                    </details>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>
      ) : null}

      {tab === "adjustments" ? (
        <div className="stack">
          <ProjectAdjustmentsBoard variant="embedded" showWhenEmpty onAfterSave={onAfterMutation} />
        </div>
      ) : null}

      {tab === "settings" ? (
        <div className="stack">
          <div className="card cardInner">
            <header className="cardHeader">
              <h3>Todoist API Token</h3>
            </header>
            <div className="stack">
              <p className="muted tiny" style={{ margin: 0 }}>
                Paste your Todoist API token to enable the dashboard. Find it in Todoist: Settings → Integrations → Developer.
              </p>
              <div className="adminRow">
                <span className={`pill ${tokenStatus?.configured ? "pill-good" : "pill-warn"}`}>
                  {tokenStatus?.configured ? `Configured (${tokenStatus.masked})` : "Missing token"}
                </span>
                {tokenStatus?.envPath ? (
                  <span className="muted tiny" style={{ marginLeft: 8 }}>
                    {tokenStatus.envPath}
                  </span>
                ) : null}
              </div>
              <div className="control">
                <label className="muted tiny" htmlFor="api-token-input">
                  API token
                </label>
                <input
                  id="api-token-input"
                  className="dateInput"
                  type={showToken ? "text" : "password"}
                  placeholder="Paste token here"
                  value={tokenDraft}
                  onChange={(e) => setTokenDraft(e.target.value)}
                />
              </div>
              <div className="adminRow">
                <div className="adminRowRight">
                  <label className="muted tiny" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input type="checkbox" checked={showToken} onChange={(e) => setShowToken(e.target.checked)} />
                    Show
                  </label>
                  <button className="button buttonSmall" type="button" onClick={saveApiToken} disabled={tokenSaving}>
                    {tokenSaving ? "Saving…" : "Save token"}
                  </button>
                  <button className="button buttonSmall" type="button" onClick={clearApiToken} disabled={tokenSaving}>
                    Clear token
                  </button>
                  <button className="button buttonSmall" type="button" onClick={loadApiToken} disabled={tokenSaving}>
                    Refresh
                  </button>
                </div>
              </div>
              {tokenError ? <p className="pill pill-warn">{tokenError}</p> : null}
              {tokenNotice ? <p className="pill">{tokenNotice}</p> : null}
            </div>
          </div>

          <div className="card cardInner">
            <header className="cardHeader">
              <h3>Timezone Override</h3>
            </header>
            <div className="stack">
              <p className="muted tiny" style={{ margin: 0 }}>
                The app uses system timezone by default. Set an IANA timezone in .env to override it.
              </p>
              <div className="adminRow">
                <span className={`pill ${timezoneStatus?.source === "env" ? "pill-good" : "pill"}`}>
                  {timezoneStatus ? `${timezoneStatus.timezone} (${timezoneStatus.source})` : "Timezone unavailable"}
                </span>
                {timezoneStatus?.envPath ? (
                  <span className="muted tiny" style={{ marginLeft: 8 }}>
                    {timezoneStatus.envPath}
                  </span>
                ) : null}
              </div>
              {timezoneStatus && !timezoneStatus.overrideValid ? (
                <p className="pill pill-warn">
                  Invalid override in .env ({timezoneStatus.invalidOverride}). Falling back to system timezone.
                </p>
              ) : null}
              <div className="adminRow">
                <span className="muted tiny">
                  System timezone: {timezoneStatus?.system ?? "unknown"}
                </span>
              </div>
              <div className="control">
                <label className="muted tiny" htmlFor="timezone-input">
                  Timezone (IANA name)
                </label>
                <input
                  id="timezone-input"
                  className="dateInput"
                  type="text"
                  placeholder="Europe/Warsaw"
                  value={timezoneDraft}
                  onChange={(e) => setTimezoneDraft(e.target.value)}
                />
              </div>
              <div className="adminRow">
                <div className="adminRowRight">
                  <button className="button buttonSmall" type="button" onClick={saveTimezone} disabled={timezoneSaving}>
                    {timezoneSaving ? "Saving…" : "Save timezone"}
                  </button>
                  <button className="button buttonSmall" type="button" onClick={clearTimezone} disabled={timezoneSaving}>
                    Use system timezone
                  </button>
                  <button className="button buttonSmall" type="button" onClick={loadTimezone} disabled={timezoneSaving}>
                    Refresh
                  </button>
                </div>
              </div>
              {timezoneError ? <p className="pill pill-warn">{timezoneError}</p> : null}
              {timezoneNotice ? <p className="pill">{timezoneNotice}</p> : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
