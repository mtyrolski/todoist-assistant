"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { InfoTip } from "./InfoTip";
import { ProgressSteps } from "./ProgressSteps";
import type { DashboardProgress } from "./ProgressSteps";

type ProjectAdjustmentsResponse = {
  files: string[];
  selectedFile: string;
  mappings: Record<string, string>;
  activeRootProjects: string[];
  archivedRootProjects: string[];
  archivedParentProjects: string[];
  archivedProjects: string[];
  unmappedArchivedProjects: string[];
};

type Variant = "wide" | "embedded";

type Props = {
  variant?: Variant;
  showWhenEmpty?: boolean;
  onAfterSave?: () => void;
};

const HELP_TEXT = `**Project hierarchy adjustments**
Map archived projects to active root projects so your history stays grouped.

- Pick a mapping file (stored locally in \`personal/\`).
- Select archived root projects you want to use as parent targets.
- Map archived projects to a root project.
- Save to update the dashboard data.`;

const RETRY_LIMIT = 6;
const RETRY_DELAY_MS = 2000;

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
  return /invalid json response|failed to fetch|networkerror|econnrefused|socket hang up|econnreset/i.test(message);
}

export function ProjectAdjustmentsBoard({ variant = "wide", showWhenEmpty = false, onAfterSave }: Props) {
  const [adjustments, setAdjustments] = useState<ProjectAdjustmentsResponse | null>(null);
  const [adjustmentFile, setAdjustmentFile] = useState("");
  const [mappingDraft, setMappingDraft] = useState<Record<string, string>>({});
  const [archivedParentsDraft, setArchivedParentsDraft] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadingHint, setLoadingHint] = useState<string | null>(null);
  const [progress, setProgress] = useState<DashboardProgress | null>(null);
  const retryAttempts = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadAdjustments = async (file?: string, refresh = false, resetRetries = false) => {
    let keepLoading = false;
    try {
      if (retryTimer.current) {
        clearTimeout(retryTimer.current);
        retryTimer.current = null;
      }
      if (resetRetries) {
        retryAttempts.current = 0;
      }
      setLoading(true);
      setError(null);
      setLoadingHint("Fetching archived and active projects from Todoist. This can take a few minutes on first sync.");
      const qs = new URLSearchParams();
      if (file) qs.set("file", file);
      if (refresh) qs.set("refresh", "true");
      const res = await fetch(`/api/admin/project_adjustments${qs.toString() ? `?${qs.toString()}` : ""}`);
      const payload = await readJson<ProjectAdjustmentsResponse>(res);
      if (!res.ok) {
        const detail = (payload as unknown as { detail?: string })?.detail;
        throw new Error(detail ?? "Failed to load adjustments");
      }
      setAdjustments(payload);
      setAdjustmentFile(payload.selectedFile);
      setMappingDraft(payload.mappings ?? {});
      setArchivedParentsDraft(payload.archivedParentProjects ?? []);
      retryAttempts.current = 0;
      setLoadingHint(null);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to load adjustments";
      const retryable = isRetryableFetchError(message) && retryAttempts.current < RETRY_LIMIT;
      if (retryable) {
        retryAttempts.current += 1;
        keepLoading = true;
        setError(null);
        setLoadingHint(
          "Preparing project adjustments. The Todoist API can be rate-limited during first sync — retrying shortly…"
        );
        if (retryTimer.current) {
          clearTimeout(retryTimer.current);
        }
        retryTimer.current = setTimeout(() => {
          loadAdjustments(file, refresh);
        }, RETRY_DELAY_MS);
      } else {
        setLoadingHint(null);
        if (message.startsWith("Invalid JSON response")) {
          setError("Project adjustments API error. Check backend logs.");
        } else if (/socket hang up|econnreset/i.test(message)) {
          setError("Connection dropped while loading adjustments. The backend may still be syncing; try Refresh.");
        } else {
          setError(message);
        }
      }
    } finally {
      if (!keepLoading) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    loadAdjustments(undefined, false, true);
  }, []);

  useEffect(() => {
    return () => {
      if (retryTimer.current) {
        clearTimeout(retryTimer.current);
        retryTimer.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!loading) {
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
  }, [loading]);

  const activeRoots = adjustments?.activeRootProjects ?? [];
  const archivedRootProjects = adjustments?.archivedRootProjects ?? [];
  const archivedProjects = adjustments?.archivedProjects ?? [];

  const unmappedProjects = useMemo(() => {
    const mapped = new Set(Object.keys(mappingDraft));
    return archivedProjects.filter((p) => !mapped.has(p));
  }, [archivedProjects, mappingDraft]);

  const mappingRows = useMemo(() => {
    const entries = Object.entries(mappingDraft);
    entries.sort(([a], [b]) => a.localeCompare(b));
    return entries;
  }, [mappingDraft]);

  const parentOptions = useMemo(() => {
    const options = new Set<string>();
    for (const name of activeRoots) options.add(name);
    for (const name of archivedParentsDraft) options.add(name);
    for (const target of Object.values(mappingDraft)) {
      if (target) options.add(target);
    }
    return Array.from(options).sort((a, b) => a.localeCompare(b));
  }, [activeRoots, archivedParentsDraft, mappingDraft]);

  const progressDisplay = useMemo(() => {
    if (progress?.active) return progress;
    if (!loading) return null;
    return {
      active: true,
      stage: "Building project hierarchy",
      step: 2,
      totalSteps: 3,
      startedAt: null,
      updatedAt: null,
      detail:
        loadingHint ??
        "Fetching archived and active projects from Todoist. This can take a few minutes on first sync.",
      error: null
    } satisfies DashboardProgress;
  }, [progress, loading, loadingHint]);

  const saveAdjustments = async () => {
    if (!adjustmentFile) return;
    try {
      setSaving(true);
      setError(null);
      setNotice(null);
      const res = await fetch(`/api/admin/project_adjustments?file=${encodeURIComponent(adjustmentFile)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mappings: mappingDraft, archivedParents: archivedParentsDraft })
      });
      if (!res.ok) throw new Error("Failed to save adjustments");
      await loadAdjustments(adjustmentFile, true, true);
      setNotice("Mappings saved.");
      onAfterSave?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save adjustments");
    } finally {
      setSaving(false);
    }
  };

  const wrapperClass =
    variant === "embedded" ? "card cardInner adjustmentsBoard" : "card adjustmentsBoard adjustmentsBoardWide";

  if (!showWhenEmpty && !loading && adjustments && unmappedProjects.length === 0) {
    return null;
  }

  return (
    <section className={wrapperClass}>
      <header className="adjustmentsHeader">
        <div>
          <p className="eyebrow">Project adjustments</p>
          <div className="adjustmentsTitleRow">
            <h2>Fix project hierarchy</h2>
            <InfoTip label="About adjustments" content={HELP_TEXT} />
          </div>
          <p className="muted tiny" style={{ margin: 0 }}>
            Map archived projects to a root project so history and charts stay together. First load may take a few minutes while
            Todoist data syncs.
          </p>
        </div>
        <div className="adjustmentsHeaderActions">
          <div className="control" style={{ margin: 0 }}>
            <label className="muted tiny" htmlFor={`adjustment-file-${variant}`}>
              Mapping file
            </label>
            <select
              id={`adjustment-file-${variant}`}
              value={adjustmentFile}
              onChange={(e) => loadAdjustments(e.target.value, false, true)}
              className="select"
            >
              {(adjustments?.files ?? []).map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <div className="adjustmentsHeaderButtons">
            <button className="button buttonSmall" type="button" onClick={() => loadAdjustments(adjustmentFile, false, true)} disabled={loading}>
              Refresh
            </button>
            <button className="button buttonSmall" type="button" onClick={saveAdjustments} disabled={saving || loading}>
              {saving ? "Saving…" : "Save mappings"}
            </button>
          </div>
        </div>
      </header>

      {error ? <p className="pill pill-warn" style={{ margin: "0 0 12px" }}>{error}</p> : null}
      {notice ? <p className="pill" style={{ margin: "0 0 12px" }}>{notice}</p> : null}

      {loading ? (
        <div className="adjustmentsLoading">
          <ProgressSteps progress={progressDisplay} />
          <p className="muted tiny" style={{ margin: 0 }}>
            {loadingHint ??
              "Fetching archived and active projects. If this is your first sync, the Todoist API may be rate-limited; progress will appear above."}
          </p>
          <div className="skeleton" style={{ minHeight: 180 }} />
        </div>
      ) : (
        <>
          <div className="adjustmentsSummary">
            <span className="pill pill-warn">Unmapped: {unmappedProjects.length}</span>
            <span className="pill">Mapped: {mappingRows.length}</span>
            <span className="pill">Archived parents: {archivedParentsDraft.length}</span>
            <span className="muted tiny">
              {archivedProjects.length} archived projects • {activeRoots.length} root projects
            </span>
          </div>

          <div className="card cardInner adjustmentsParents">
            <header className="cardHeader">
              <h3>Archived parent candidates</h3>
            </header>
            <p className="muted tiny" style={{ margin: 0 }}>
              Select archived projects that should be available as mapping targets (roots recommended). You can edit this list anytime.
            </p>
            <div className="adjustmentsParentActions">
              <button
                className="button buttonSmall buttonGhost"
                type="button"
                onClick={() => setArchivedParentsDraft(archivedRootProjects)}
                disabled={!archivedRootProjects.length}
              >
                Use all archived roots
              </button>
              <button
                className="button buttonSmall buttonGhost"
                type="button"
                onClick={() => setArchivedParentsDraft([])}
                disabled={!archivedParentsDraft.length}
              >
                Clear selection
              </button>
            </div>
            <div className="list scrollArea">
              {archivedProjects.length ? (
                archivedProjects.map((name) => {
                  const checked = archivedParentsDraft.includes(name);
                  return (
                    <label key={name} className="adjustmentsParentRow">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          setArchivedParentsDraft((prev) => {
                            if (prev.includes(name)) {
                              return prev.filter((item) => item !== name);
                            }
                            return [...prev, name];
                          });
                        }}
                      />
                      <span>{name}</span>
                    </label>
                  );
                })
              ) : (
                <p className="muted tiny" style={{ margin: 0 }}>
                  No archived projects detected.
                </p>
              )}
            </div>
          </div>

          <div className="adjustmentsGrid">
            <div className="card cardInner">
              <header className="cardHeader">
                <h3>Unmapped archived projects</h3>
              </header>
              <div className="list scrollArea">
                {unmappedProjects.length ? (
                  unmappedProjects.map((archived) => (
                    <div key={archived} className="row rowTight adjustmentsRow">
                      <div className="dot dot-neutral" />
                      <div className="rowMain">
                        <p className="rowTitle">{archived}</p>
                        <p className="muted tiny">Assign a root project</p>
                      </div>
                      <div className="rowActions">
                        <select
                          className="select adjustmentsSelect"
                          value={mappingDraft[archived] ?? ""}
                          onChange={(e) => {
                            const value = e.target.value;
                            setMappingDraft((prev) => {
                              const next = { ...prev };
                              if (!value) {
                                delete next[archived];
                              } else {
                                next[archived] = value;
                              }
                              return next;
                            });
                          }}
                        >
                          <option value="">Choose root…</option>
                          {parentOptions.map((p) => (
                            <option key={p} value={p}>
                              {p}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="muted tiny" style={{ margin: 0 }}>
                    All archived projects are mapped.
                  </p>
                )}
              </div>
            </div>

            <div className="card cardInner">
              <header className="cardHeader">
                <h3>Current mappings</h3>
              </header>
              <div className="list scrollArea">
                {mappingRows.length ? (
                  mappingRows.map(([archived, active]) => (
                    <div key={archived} className="row rowTight adjustmentsRow">
                      <div className="dot dot-neutral" />
                      <div className="rowMain">
                        <p className="rowTitle">{archived}</p>
                        <p className="muted tiny">→ {active}</p>
                      </div>
                      <div className="rowActions">
                        <select
                          className="select adjustmentsSelect"
                          value={active}
                          onChange={(e) => {
                            const value = e.target.value;
                            setMappingDraft((prev) => ({ ...prev, [archived]: value }));
                          }}
                        >
                          {parentOptions.map((p) => (
                            <option key={p} value={p}>
                              {p}
                            </option>
                          ))}
                        </select>
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
    </section>
  );
}
