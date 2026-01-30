"use client";

import { useEffect, useMemo, useState } from "react";
import { InfoTip } from "./InfoTip";

type ProjectAdjustmentsResponse = {
  files: string[];
  selectedFile: string;
  mappings: Record<string, string>;
  activeRootProjects: string[];
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
- Map archived projects to a root project.
- Save to update the dashboard data.`;

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

export function ProjectAdjustmentsBoard({ variant = "wide", showWhenEmpty = false, onAfterSave }: Props) {
  const [adjustments, setAdjustments] = useState<ProjectAdjustmentsResponse | null>(null);
  const [adjustmentFile, setAdjustmentFile] = useState("");
  const [mappingDraft, setMappingDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadAdjustments = async (file?: string, refresh = false) => {
    try {
      setLoading(true);
      setError(null);
      const qs = new URLSearchParams();
      if (file) qs.set("file", file);
      if (refresh) qs.set("refresh", "true");
      const res = await fetch(`/api/admin/project_adjustments${qs.toString() ? `?${qs.toString()}` : ""}`);
      const payload = await readJson<ProjectAdjustmentsResponse>(res);
      if (!res.ok) throw new Error("Failed to load adjustments");
      setAdjustments(payload);
      setAdjustmentFile(payload.selectedFile);
      setMappingDraft(payload.mappings ?? {});
    } catch (e) {
      setAdjustments(null);
      const message = e instanceof Error ? e.message : "Failed to load adjustments";
      if (message.startsWith("Invalid JSON response")) {
        setError("Project adjustments API error. Check backend logs.");
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAdjustments();
  }, []);

  const activeRoots = adjustments?.activeRootProjects ?? [];
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

  const saveAdjustments = async () => {
    if (!adjustmentFile) return;
    try {
      setSaving(true);
      setError(null);
      setNotice(null);
      const res = await fetch(`/api/admin/project_adjustments?file=${encodeURIComponent(adjustmentFile)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mappingDraft)
      });
      if (!res.ok) throw new Error("Failed to save adjustments");
      await loadAdjustments(adjustmentFile, true);
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
            Map archived projects to a root project so history and charts stay together.
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
              onChange={(e) => loadAdjustments(e.target.value)}
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
            <button className="button buttonSmall" type="button" onClick={() => loadAdjustments(adjustmentFile)} disabled={loading}>
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
        <div className="skeleton" style={{ minHeight: 180 }} />
      ) : (
        <>
          <div className="adjustmentsSummary">
            <span className="pill pill-warn">Unmapped: {unmappedProjects.length}</span>
            <span className="pill">Mapped: {mappingRows.length}</span>
            <span className="muted tiny">
              {archivedProjects.length} archived projects • {activeRoots.length} root projects
            </span>
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
                          {activeRoots.map((p) => (
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
                          {activeRoots.map((p) => (
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
