"use client";

import { useEffect, useMemo, useState } from "react";
import { InfoTip } from "./InfoTip";

type Tab = "automations" | "logs" | "adjustments" | "settings";

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

type LogFile = { path: string; size: number; mtime: string };
type LogsResponse = { logs: LogFile[] };

type LogReadResponse = LogFile & {
  content: string;
  page: number;
  perPage: number;
  totalPages: number;
  totalLines: number;
};

type ProjectAdjustmentsResponse = {
  files: string[];
  selectedFile: string;
  mappings: Record<string, string>;
  activeRootProjects: string[];
  archivedProjects: string[];
  unmappedArchivedProjects: string[];
};

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
Manage automations, logs, and project mappings.

- Automations follow the same cooldown rules as the observer.
- Logs read from local files for quick debugging.
- Adjustments map archived projects to active roots.
- Settings updates your local Todoist API token.`;

type ApiTokenStatus = {
  configured: boolean;
  masked: string;
  envPath: string;
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

  const [logs, setLogs] = useState<LogFile[] | null>(null);
  const [selectedLog, setSelectedLog] = useState<string>("");
  const [logRead, setLogRead] = useState<LogReadResponse | null>(null);
  const [logLines, setLogLines] = useState<number>(80);
  const [logPage, setLogPage] = useState<number>(1);

  const [adjustments, setAdjustments] = useState<ProjectAdjustmentsResponse | null>(null);
  const [adjustmentFile, setAdjustmentFile] = useState<string>("");
  const [mappingDraft, setMappingDraft] = useState<Record<string, string>>({});
  const [selectedArchived, setSelectedArchived] = useState<string>("");
  const [selectedActive, setSelectedActive] = useState<string>("");
  const [savingAdjustments, setSavingAdjustments] = useState(false);

  const [tokenStatus, setTokenStatus] = useState<ApiTokenStatus | null>(null);
  const [tokenDraft, setTokenDraft] = useState<string>("");
  const [tokenSaving, setTokenSaving] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenNotice, setTokenNotice] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);

  const mergedMappings = mappingDraft;

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

  useEffect(() => {
    const loadLogs = async () => {
      try {
        const res = await fetch("/api/admin/logs");
        const payload = (await res.json()) as LogsResponse;
        if (!res.ok) throw new Error("logs");
        setLogs(payload.logs);
        if (!selectedLog && payload.logs.length) {
          setSelectedLog(payload.logs[0].path);
        }
      } catch {
        setLogs(null);
      }
    };
    loadLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const loadAdjustments = async (file?: string) => {
      try {
        const qs = file ? `?file=${encodeURIComponent(file)}` : "";
        const res = await fetch(`/api/admin/project_adjustments${qs}`);
        const payload = (await res.json()) as ProjectAdjustmentsResponse;
        if (!res.ok) throw new Error("adjustments");
        setAdjustments(payload);
        setAdjustmentFile(payload.selectedFile);
        setMappingDraft(payload.mappings ?? {});
        setSelectedArchived(payload.unmappedArchivedProjects[0] ?? payload.archivedProjects[0] ?? "");
        setSelectedActive(payload.activeRootProjects[0] ?? "");
      } catch {
        setAdjustments(null);
      }
    };
    loadAdjustments();
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

  useEffect(() => {
    loadApiToken();
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

  const readLog = async (path: string, page: number) => {
    try {
      const qs = new URLSearchParams({
        path,
        tail_lines: String(logLines),
        page: String(page)
      });
      const res = await fetch(`/api/admin/logs/read?${qs.toString()}`);
      const payload = (await res.json()) as LogReadResponse;
      if (!res.ok) throw new Error("read_log");
      setLogRead(payload);
      setLogPage(payload.page);
    } catch {
      setLogRead(null);
    }
  };

  useEffect(() => {
    if (!selectedLog) return;
    readLog(selectedLog, 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLog]);

  useEffect(() => {
    if (!selectedLog) return;
    readLog(selectedLog, logPage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logLines, logPage]);

  const saveAdjustments = async () => {
    if (!adjustmentFile) return;
    try {
      setSavingAdjustments(true);
      setAdminError(null);
      const res = await fetch(`/api/admin/project_adjustments?file=${encodeURIComponent(adjustmentFile)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mappingDraft)
      });
      if (!res.ok) throw new Error("save_adjustments");
      const reload = await fetch(`/api/admin/project_adjustments?file=${encodeURIComponent(adjustmentFile)}&refresh=true`);
      if (reload.ok) {
        const payload = (await reload.json()) as ProjectAdjustmentsResponse;
        setAdjustments(payload);
        setMappingDraft(payload.mappings ?? {});
        onAfterMutation();
      }
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : "Failed to save adjustments");
    } finally {
      setSavingAdjustments(false);
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

  const mappingRows = useMemo(() => {
    const entries = Object.entries(mergedMappings);
    entries.sort(([a], [b]) => a.localeCompare(b));
    return entries;
  }, [mergedMappings]);

  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Dashboard Admin</h2>
          <InfoTip label="About dashboard admin" content={ADMIN_HELP} />
        </div>
        <div className="segmented">
          <button className={`seg ${tab === "automations" ? "segActive" : ""}`} onClick={() => setTab("automations")} type="button">
            Automations
          </button>
          <button className={`seg ${tab === "logs" ? "segActive" : ""}`} onClick={() => setTab("logs")} type="button">
            Logs
          </button>
          <button className={`seg ${tab === "adjustments" ? "segActive" : ""}`} onClick={() => setTab("adjustments")} type="button">
            Project Adjustments
          </button>
          <button className={`seg ${tab === "settings" ? "segActive" : ""}`} onClick={() => setTab("settings")} type="button">
            Settings
          </button>
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

      {tab === "logs" ? (
        <div className="stack">
          <div className="adminRow">
            <div className="control" style={{ margin: 0 }}>
              <label className="muted tiny" htmlFor="log-select">
                Log file
              </label>
              <select
                id="log-select"
                value={selectedLog}
                onChange={(e) => setSelectedLog(e.target.value)}
                className="select"
              >
                {(logs ?? []).map((l) => (
                  <option key={l.path} value={l.path}>
                    {l.path}
                  </option>
                ))}
              </select>
            </div>
            <div className="adminRowRight">
              <label className="muted tiny" htmlFor="log-lines">
                Lines/page
              </label>
              <input
                id="log-lines"
                className="dateInput"
                type="number"
                min={10}
                max={2000}
                value={logLines}
                onChange={(e) => setLogLines(Number(e.target.value))}
              />
              <button className="button buttonSmall" type="button" onClick={() => selectedLog && readLog(selectedLog, logPage)}>
                Refresh
              </button>
            </div>
          </div>

          {!logRead ? (
            <div className="skeleton" style={{ minHeight: 180 }} />
          ) : (
            <div className="stack">
              <div className="adminRow">
                <p className="muted tiny" style={{ margin: 0 }}>
                  {logRead.path} • {Math.round(logRead.size / 1024)} KB • modified {logRead.mtime}
                </p>
                <div className="adminRowRight">
                  <button className="button buttonSmall" type="button" disabled={logRead.page <= 1} onClick={() => setLogPage(1)}>
                    First
                  </button>
                  <button className="button buttonSmall" type="button" disabled={logRead.page <= 1} onClick={() => setLogPage((p) => Math.max(1, p - 1))}>
                    Prev
                  </button>
                  <span className="muted tiny">
                    Page {logRead.page} / {logRead.totalPages}
                  </span>
                  <button className="button buttonSmall" type="button" disabled={logRead.page >= logRead.totalPages} onClick={() => setLogPage((p) => p + 1)}>
                    Next
                  </button>
                  <button className="button buttonSmall" type="button" disabled={logRead.page >= logRead.totalPages} onClick={() => setLogPage(logRead.totalPages)}>
                    Last
                  </button>
                </div>
              </div>
              <pre className="codeBlock" style={{ maxHeight: 420, overflow: "auto" }}>
                {logRead.content || "(empty)"}
              </pre>
            </div>
          )}
        </div>
      ) : null}

      {tab === "adjustments" ? (
        <div className="stack">
          {!adjustments ? (
            <div className="skeleton" style={{ minHeight: 180 }} />
          ) : (
            <>
              <div className="adminRow">
                <div className="control" style={{ margin: 0 }}>
                  <label className="muted tiny" htmlFor="mapping-file">
                    Mapping file
                  </label>
                  <select
                    id="mapping-file"
                    value={adjustmentFile}
                    onChange={async (e) => {
                      const next = e.target.value;
                      setAdjustmentFile(next);
                      const res = await fetch(`/api/admin/project_adjustments?file=${encodeURIComponent(next)}`);
                      if (res.ok) {
                        const payload = (await res.json()) as ProjectAdjustmentsResponse;
                      setAdjustments(payload);
                      setMappingDraft(payload.mappings ?? {});
                      setSelectedArchived(payload.unmappedArchivedProjects[0] ?? payload.archivedProjects[0] ?? "");
                      setSelectedActive(payload.activeRootProjects[0] ?? "");
                    }
                  }}
                    className="select"
                  >
                    {adjustments.files.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="adminRowRight">
                  <button className="button buttonSmall" onClick={saveAdjustments} type="button" disabled={savingAdjustments}>
                    {savingAdjustments ? "Saving…" : "Save"}
                  </button>
                </div>
              </div>

              <div className="grid2">
                <div className="card cardInner">
                  <header className="cardHeader">
                    <h3>Create mapping</h3>
                  </header>
                  <div className="stack">
                    <div className="control">
                      <label className="muted tiny" htmlFor="archived-project">
                        Archived project
                      </label>
                      <select
                        id="archived-project"
                        value={selectedArchived}
                        onChange={(e) => setSelectedArchived(e.target.value)}
                        className="select"
                      >
                        {adjustments.archivedProjects.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="control">
                      <label className="muted tiny" htmlFor="active-project">
                        Map to active root project
                      </label>
                      <select
                        id="active-project"
                        value={selectedActive}
                        onChange={(e) => setSelectedActive(e.target.value)}
                        className="select"
                      >
                        {adjustments.activeRootProjects.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      className="button"
                      type="button"
                      onClick={() => {
                        if (!selectedArchived || !selectedActive) return;
                        setMappingDraft((prev) => ({ ...prev, [selectedArchived]: selectedActive }));
                      }}
                    >
                      Add mapping
                    </button>
                    <p className="muted tiny" style={{ margin: 0 }}>
                      Unmapped archived projects: {adjustments.unmappedArchivedProjects.length}
                    </p>
                  </div>
                </div>

                <div className="card cardInner">
                  <header className="cardHeader">
                    <h3>Current mappings</h3>
                  </header>
                  <div className="list scrollArea">
                    {mappingRows.length ? (
                      mappingRows.map(([archived, active]) => (
                        <div key={archived} className="row rowTight">
                          <div className="dot dot-neutral" />
                          <div className="rowMain">
                            <p className="rowTitle">{archived}</p>
                            <p className="muted tiny">→ {active}</p>
                          </div>
                          <div className="rowActions">
                            <button
                              className="button buttonSmall"
                              type="button"
                              onClick={() =>
                                setMappingDraft((prev) => {
                                  const next = { ...prev };
                                  delete next[archived];
                                  return next;
                                })
                              }
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="muted tiny" style={{ margin: 0 }}>
                        No mappings yet.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
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
        </div>
      ) : null}
    </section>
  );
}
