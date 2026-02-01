"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
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
  warning?: string | null;
};

type Variant = "wide" | "embedded";

type Props = {
  variant?: Variant;
  showWhenEmpty?: boolean;
  onAfterSave?: () => void;
};

const HELP_TEXT = `**Project hierarchy adjustments**
Map archived projects to root projects so your history stays grouped.

- Pick a mapping file (stored locally in \`personal/\`).
- Drag archived project tiles into parent buckets to map them.
- Drop a tile onto "Make parent" to allow that archived project as a parent bucket.
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
  const [warning, setWarning] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadingHint, setLoadingHint] = useState<string | null>(null);
  const [progress, setProgress] = useState<DashboardProgress | null>(null);
  const [dragOverZone, setDragOverZone] = useState<string | null>(null);
  const retryAttempts = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draggedProjectRef = useRef<string | null>(null);

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
      setWarning(null);
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
      if (payload.warning) {
        setWarning(payload.warning);
      }
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
  const archivedProjects = adjustments?.archivedProjects ?? [];
  const parentSet = useMemo(() => {
    const set = new Set<string>();
    for (const name of activeRoots) set.add(name);
    for (const name of archivedParentsDraft) set.add(name);
    return set;
  }, [activeRoots, archivedParentsDraft]);

  const mappedEntries = useMemo(
    () => Object.entries(mappingDraft).filter(([, parent]) => Boolean(parent)),
    [mappingDraft]
  );

  const unmappedProjects = useMemo(() => {
    const mapped = new Set(mappedEntries.map(([archived]) => archived));
    return archivedProjects.filter((p) => !mapped.has(p));
  }, [archivedProjects, mappedEntries]);

  const assignments = useMemo(() => {
    const result: Record<string, string[]> = {};
    for (const [archived, parent] of mappedEntries) {
      if (!parent) continue;
      if (!result[parent]) result[parent] = [];
      result[parent].push(archived);
    }
    for (const list of Object.values(result)) {
      list.sort((a, b) => a.localeCompare(b));
    }
    return result;
  }, [mappedEntries]);

  const mappingTargets = useMemo(() => {
    const set = new Set<string>();
    for (const [, parent] of mappedEntries) {
      if (parent) set.add(parent);
    }
    return Array.from(set);
  }, [mappedEntries]);

  useEffect(() => {
    if (!archivedProjects.length) return;
    setArchivedParentsDraft((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const target of mappingTargets) {
        if (archivedProjects.includes(target) && !next.has(target)) {
          next.add(target);
          changed = true;
        }
      }
      return changed ? Array.from(next).sort((a, b) => a.localeCompare(b)) : prev;
    });
  }, [archivedProjects, mappingTargets]);

  const parentBuckets = useMemo(() => {
    const buckets: Array<{ name: string; kind: "active" | "archived" | "unknown"; removable: boolean }> = [];
    const seen = new Set<string>();
    for (const name of activeRoots) {
      if (seen.has(name)) continue;
      seen.add(name);
      buckets.push({ name, kind: "active", removable: false });
    }
    const archivedSorted = Array.from(new Set(archivedParentsDraft)).sort((a, b) => a.localeCompare(b));
    for (const name of archivedSorted) {
      if (seen.has(name)) continue;
      seen.add(name);
      buckets.push({ name, kind: "archived", removable: true });
    }
    const unknown = mappingTargets.filter((name) => !seen.has(name));
    unknown.sort((a, b) => a.localeCompare(b));
    for (const name of unknown) {
      buckets.push({ name, kind: "unknown", removable: true });
    }
    return buckets;
  }, [activeRoots, archivedParentsDraft, mappingTargets]);

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

  const addParent = (name: string) => {
    if (!name || activeRoots.includes(name)) return;
    setArchivedParentsDraft((prev) => {
      if (prev.includes(name)) return prev;
      const next = [...prev, name];
      next.sort((a, b) => a.localeCompare(b));
      return next;
    });
  };

  const removeParent = (name: string) => {
    setArchivedParentsDraft((prev) => prev.filter((item) => item !== name));
    setMappingDraft((prev) => {
      const next = { ...prev };
      for (const [archived, parent] of Object.entries(next)) {
        if (parent === name) delete next[archived];
      }
      return next;
    });
  };

  const startDrag = (name: string) => (event: DragEvent) => {
    draggedProjectRef.current = name;
    event.dataTransfer.setData("text/plain", name);
    event.dataTransfer.effectAllowed = "move";
  };

  const endDrag = () => {
    draggedProjectRef.current = null;
    setDragOverZone(null);
  };

  const resolveDraggedName = (event: DragEvent): string | null => {
    const fromData = event.dataTransfer.getData("text/plain");
    return fromData || draggedProjectRef.current || null;
  };

  const handleDropOnBucket = (bucket: string) => (event: DragEvent) => {
    event.preventDefault();
    const name = resolveDraggedName(event);
    if (!name) return;
    setMappingDraft((prev) => ({ ...prev, [name]: bucket }));
    setDragOverZone(null);
  };

  const handleDropUnassigned = (event: DragEvent) => {
    event.preventDefault();
    const name = resolveDraggedName(event);
    if (!name) return;
    setMappingDraft((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    setDragOverZone(null);
  };

  const handleDropMakeParent = (event: DragEvent) => {
    event.preventDefault();
    const name = resolveDraggedName(event);
    if (!name) return;
    addParent(name);
    setDragOverZone(null);
  };

  const handleDragOverZone = (zone: string) => (event: DragEvent) => {
    event.preventDefault();
    if (dragOverZone !== zone) {
      setDragOverZone(zone);
    }
    event.dataTransfer.dropEffect = "move";
  };

  const handleDragLeaveZone = (zone: string) => () => {
    setDragOverZone((prev) => (prev === zone ? null : prev));
  };

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
      {warning ? <p className="pill pill-warn" style={{ margin: "0 0 12px" }}>{warning}</p> : null}
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
            <span className="pill">Mapped: {mappedEntries.length}</span>
            <span className="pill">Parents: {parentBuckets.length}</span>
            <span className="muted tiny">
              {archivedProjects.length} archived projects • {activeRoots.length} active roots
            </span>
          </div>

          <div className="adjustmentsDnD">
            <div
              className="card cardInner adjustmentsPool"
              onDragOver={handleDragOverZone("pool")}
              onDragLeave={handleDragLeaveZone("pool")}
              onDrop={handleDropUnassigned}
            >
              <header className="cardHeader">
                <h3>Archived projects</h3>
              </header>
              <p className="muted tiny" style={{ margin: 0 }}>
                Drag tiles into parent buckets to map them. Drop a tile onto Make parent to create a new parent bucket.
              </p>
              <div
                className={`adjustmentsDropzone ${dragOverZone === "make-parent" ? "isDragOver" : ""}`}
                onDragOver={handleDragOverZone("make-parent")}
                onDragLeave={handleDragLeaveZone("make-parent")}
                onDrop={handleDropMakeParent}
              >
                <strong>Make parent</strong>
                <span className="muted tiny">Drop archived project here to allow it as a parent bucket</span>
              </div>
              <div className={`adjustmentsTiles ${dragOverZone === "pool" ? "isDragOver" : ""}`}>
                {unmappedProjects.length ? (
                  unmappedProjects.map((name) => {
                    const isParent = parentSet.has(name);
                    return (
                      <div
                        key={name}
                        className="adjustmentsTile"
                        draggable
                        onDragStart={startDrag(name)}
                        onDragEnd={endDrag}
                      >
                        <span>{name}</span>
                        <div className="adjustmentsTileActions">
                          <button
                            className="button buttonSmall buttonGhost"
                            type="button"
                            onClick={() => addParent(name)}
                            disabled={isParent}
                          >
                            {isParent ? "Parent" : "Make parent"}
                          </button>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <p className="muted tiny" style={{ margin: 0 }}>
                    {warning && !archivedProjects.length
                      ? "Archived project list unavailable. Showing saved mappings only."
                      : "All archived projects are mapped."}
                  </p>
                )}
              </div>
            </div>

            <div className="adjustmentsBuckets">
              {parentBuckets.length ? (
                parentBuckets.map((bucket) => {
                  const zone = `bucket:${bucket.name}`;
                  const items = assignments[bucket.name] ?? [];
                  const meta =
                    bucket.kind === "active"
                      ? "Active root"
                      : bucket.kind === "archived"
                      ? "Archived parent"
                      : "Custom target";
                  return (
                    <div
                      key={bucket.name}
                      className={`card cardInner adjustmentsBucket ${dragOverZone === zone ? "isDragOver" : ""}`}
                      onDragOver={handleDragOverZone(zone)}
                      onDragLeave={handleDragLeaveZone(zone)}
                      onDrop={handleDropOnBucket(bucket.name)}
                    >
                      <div className="adjustmentsBucketHeader">
                        <div>
                          <p className="bucketTitle">{bucket.name}</p>
                          <p className="muted tiny" style={{ margin: 0 }}>
                            {meta}
                          </p>
                        </div>
                        {bucket.removable ? (
                          <button
                            className="button buttonSmall buttonGhost"
                            type="button"
                            onClick={() => removeParent(bucket.name)}
                          >
                            Remove parent
                          </button>
                        ) : null}
                      </div>
                      <div className="adjustmentsBucketBody">
                        {items.length ? (
                          items.map((name) => (
                            <div
                              key={name}
                              className="adjustmentsTile adjustmentsTileCompact"
                              draggable
                              onDragStart={startDrag(name)}
                              onDragEnd={endDrag}
                            >
                              <span>{name}</span>
                              <div className="adjustmentsTileActions">
                                <button
                                  className="button buttonSmall buttonGhost"
                                  type="button"
                                  onClick={() =>
                                    setMappingDraft((prev) => {
                                      const next = { ...prev };
                                      delete next[name];
                                      return next;
                                    })
                                  }
                                >
                                  Unmap
                                </button>
                                {!parentSet.has(name) ? (
                                  <button
                                    className="button buttonSmall buttonGhost"
                                    type="button"
                                    onClick={() => addParent(name)}
                                  >
                                    Make parent
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          ))
                        ) : (
                          <div className="adjustmentsBucketEmpty">
                            Drop archived projects here
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <p className="muted tiny" style={{ margin: 0 }}>
                  No parent buckets available yet.
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
