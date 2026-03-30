"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { InfoTip } from "./InfoTip";

type ProjectOption = {
  id: string;
  name: string;
  label: string;
  parentId?: string | null;
};

type StatusUpdateProjectResponse = {
  projects: ProjectOption[];
};

type StatusUpdateComment =
  | string
  | {
      content: string;
      createdAt?: string | null;
      author?: string | null;
      snippet?: string | null;
    };

type StatusUpdateTask = {
  taskId?: string;
  id?: string;
  content: string;
  projectId?: string;
  projectName?: string;
  completedAt?: string | string[] | null;
  completed_at?: string | null;
  comments?: StatusUpdateComment[];
  commentCount?: number;
  summary?: string;
};

type StatusUpdateSummary = {
  selectedProjectCount?: number;
  expandedProjectCount?: number;
  completedEventCount?: number;
  completedTaskCount?: number;
  commentedTaskCount?: number;
  commentCount?: number;
};

type StatusUpdateSelection = {
  beg?: string;
  end?: string;
  label?: string;
  syncLabel?: string;
  preset?: string | null;
  requestedProjects?: Array<ProjectOption | string>;
};

type StatusUpdateReport = {
  markdown?: string;
  title?: string;
  summary?: string | StatusUpdateSummary;
  summaryText?: string;
  generatedAt?: string;
  generated_at?: string;
  syncLabel?: string;
  preset?: string;
  selection?: StatusUpdateSelection;
  range?: {
    beg?: string;
    end?: string;
    label?: string;
  };
  selectedProjects?: Array<ProjectOption | string>;
  completedTasks?: StatusUpdateTask[];
  sourceTasks?: StatusUpdateTask[];
  tasks?: StatusUpdateTask[];
  highlights?: string[];
  notes?: string[];
  stats?: {
    completedCount?: number;
    commentCount?: number;
    projectCount?: number;
    activityCount?: number;
  };
};

type GenerateResponse = StatusUpdateReport & {
  detail?: string;
};

type RangePreset = "daily" | "weekly" | "custom";

type RangeSelection = {
  beg: string;
  end: string;
};

const PRESET_LABELS: Record<RangePreset, string> = {
  daily: "Daily",
  weekly: "Weekly",
  custom: "Custom"
};

const HELP = `**Status update studio**
Pick a time range, choose several projects, and generate a sync-ready update from completed tasks plus task comments.

- Daily and weekly presets set the date range for you.
- Custom mode lets you click out any date span.
- The draft below is ready to paste into a daily, weekly, or ad-hoc sync message.`;

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

function toDateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDays(date: Date, deltaDays: number): Date {
  const next = new Date(date);
  next.setDate(date.getDate() + deltaDays);
  return next;
}

function startOfLocalDay(date: Date): Date {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

function endOfLocalDay(date: Date): Date {
  const next = new Date(date);
  next.setHours(23, 59, 59, 999);
  return next;
}

function getPresetRange(preset: RangePreset): RangeSelection {
  const today = new Date();
  const todayStart = startOfLocalDay(today);
  if (preset === "daily") {
    return {
      beg: toDateInputValue(todayStart),
      end: toDateInputValue(endOfLocalDay(todayStart))
    };
  }
  if (preset === "weekly") {
    return {
      beg: toDateInputValue(startOfLocalDay(shiftDays(todayStart, -6))),
      end: toDateInputValue(endOfLocalDay(todayStart))
    };
  }
  return {
    beg: toDateInputValue(startOfLocalDay(shiftDays(todayStart, -13))),
    end: toDateInputValue(endOfLocalDay(todayStart))
  };
}

function formatShortDate(value: string | null | undefined): string {
  if (!value) return "Unknown";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function getTaskKey(task: StatusUpdateTask, index: number): string {
  return task.taskId ?? task.id ?? `${index}-${task.content}`;
}

function normalizeComment(comment: StatusUpdateComment): {
  content: string;
  createdAt?: string | null;
  author?: string | null;
} {
  if (typeof comment === "string") {
    return { content: comment };
  }
  return {
    content: comment.snippet ?? comment.content,
    createdAt: comment.createdAt,
    author: comment.author
  };
}

function getTaskCompletedAt(task: StatusUpdateTask): string | null {
  if (Array.isArray(task.completedAt)) {
    return task.completedAt.at(-1) ?? null;
  }
  return task.completedAt ?? task.completed_at ?? null;
}

function getSummaryStats(report: StatusUpdateReport | null): StatusUpdateReport["stats"] | null {
  if (!report) return null;
  if (report.stats) return report.stats;
  if (report.summary && typeof report.summary === "object") {
    return {
      completedCount: report.summary.completedTaskCount,
      commentCount: report.summary.commentCount,
      projectCount: report.summary.expandedProjectCount,
      activityCount: report.summary.completedEventCount
    };
  }
  return null;
}

function getSelectedProjectNames(report: StatusUpdateReport | null): string[] {
  if (!report) return [];
  const projects = report.selectedProjects ?? report.selection?.requestedProjects ?? [];
  return projects.map((project) => (typeof project === "string" ? project : project.label));
}

export function StatusUpdateStudio() {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [preset, setPreset] = useState<RangePreset>("weekly");
  const [beg, setBeg] = useState(() => getPresetRange("weekly").beg);
  const [end, setEnd] = useState(() => getPresetRange("weekly").end);
  const [syncLabel, setSyncLabel] = useState("Weekly sync");
  const [markdown, setMarkdown] = useState("");
  const [report, setReport] = useState<StatusUpdateReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      setLoadingProjects(true);
      setError(null);
      const res = await fetch("/api/admin/status_update/projects");
      const payload = await readJson<StatusUpdateProjectResponse & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to load projects");
      setProjects(payload.projects ?? []);
    } catch (err) {
      setProjects([]);
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    const nextRange = getPresetRange(preset);
    if (preset !== "custom") {
      setBeg(nextRange.beg);
      setEnd(nextRange.end);
      setSyncLabel(`${PRESET_LABELS[preset]} sync`);
    }
  }, [preset]);

  const selectedProjects = useMemo(
    () => projects.filter((project) => selectedProjectIds.includes(project.id)),
    [projects, selectedProjectIds]
  );

  const filteredProjects = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    if (!query) return projects;
    return projects.filter((project) => {
      const haystack = `${project.name} ${project.label}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [projects, deferredSearch]);

  const windowLabel = useMemo(() => {
    if (!beg || !end) return "Pick a range";
    return `${formatShortDate(beg)} to ${formatShortDate(end)}`;
  }, [beg, end]);

  const selectionSummary = useMemo(() => {
    const count = selectedProjectIds.length;
    if (!count) return "No projects selected yet.";
    return `${count} project${count === 1 ? "" : "s"} selected`;
  }, [selectedProjectIds.length]);

  const toggleProject = (projectId: string) => {
    setSelectedProjectIds((current) =>
      current.includes(projectId) ? current.filter((id) => id !== projectId) : [...current, projectId]
    );
  };

  const selectVisible = () => {
    setSelectedProjectIds((current) => {
      const next = new Set(current);
      filteredProjects.forEach((project) => next.add(project.id));
      return Array.from(next);
    });
  };

  const clearSelected = () => {
    setSelectedProjectIds([]);
  };

  const applyPreset = (nextPreset: RangePreset) => {
    setPreset(nextPreset);
    if (nextPreset !== "custom") {
      const range = getPresetRange(nextPreset);
      setBeg(range.beg);
      setEnd(range.end);
    }
  };

  const handleBegChange = (value: string) => {
    setPreset("custom");
    setBeg(value);
  };

  const handleEndChange = (value: string) => {
    setPreset("custom");
    setEnd(value);
  };

  const draftMarkdown = report?.markdown ?? markdown;
  const completedTasks = report?.completedTasks ?? report?.sourceTasks ?? report?.tasks ?? [];
  const selectedProjectNames = getSelectedProjectNames(report);
  const stats = getSummaryStats(report);
  const generatedAt = report?.generatedAt ?? report?.generated_at ?? null;
  const summaryText =
    typeof report?.summary === "string"
      ? report.summary
      : report?.summaryText ?? null;

  const handleGenerate = async () => {
    if (!selectedProjectIds.length) {
      setError("Select at least one project.");
      return;
    }
    if (!beg || !end) {
      setError("Choose a start and end date.");
      return;
    }
    try {
      setLoadingReport(true);
      setError(null);
      setNotice(null);
      const res = await fetch("/api/admin/status_update/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectIds: selectedProjectIds,
          beg,
          end,
          syncLabel,
          preset
        })
      });
      const payload = await readJson<GenerateResponse>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to generate status update");
      setReport(payload);
      setMarkdown(payload.markdown ?? "");
      setNotice("Status update draft generated.");
    } catch (err) {
      setReport(null);
      setMarkdown("");
      setError(err instanceof Error ? err.message : "Failed to generate status update");
    } finally {
      setLoadingReport(false);
    }
  };

  const copyMarkdown = async () => {
    const text = draftMarkdown.trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setNotice("Draft copied to clipboard.");
    } catch {
      setError("Could not copy the draft to the clipboard.");
    }
  };

  return (
    <section className="statusUpdateStudio">
      <section className="card statusUpdateHero">
        <div className="statusUpdateHeroCopy">
          <p className="eyebrow">Status update studio</p>
          <h2>Draft sync updates from completed tasks and task comments</h2>
          <p className="muted">
            Pick a date range, choose the projects that matter, and generate a daily, weekly, or custom update that is
            grounded in what actually got finished.
          </p>
          <div className="statusUpdateHeroPills">
            <span className="pill pill-good">{selectionSummary}</span>
            <span className="pill pill-warn">{windowLabel}</span>
            <span className="pill pill-neutral">{PRESET_LABELS[preset]} preset</span>
          </div>
        </div>
        <div className="statusUpdateHeroPanel">
          <InfoTip label="About the studio" content={HELP} />
          <div className="statusUpdateHeroMetrics">
            <div className="statusUpdateHeroMetric">
              <span className="statusUpdateMetricLabel">Projects</span>
              <strong>{selectedProjectIds.length}</strong>
            </div>
            <div className="statusUpdateHeroMetric">
              <span className="statusUpdateMetricLabel">Range</span>
              <strong>{windowLabel}</strong>
            </div>
            <div className="statusUpdateHeroMetric">
              <span className="statusUpdateMetricLabel">Sync label</span>
              <strong>{syncLabel || "Untitled sync"}</strong>
            </div>
          </div>
        </div>
      </section>

      {error ? <p className="pill pill-warn statusUpdateBanner">{error}</p> : null}
      {notice ? <p className="pill pill-good statusUpdateBanner">{notice}</p> : null}

      <div className="statusUpdateLayout">
        <div className="stack">
          <section className="card statusUpdateControls">
            <header className="cardHeader">
              <div>
                <p className="eyebrow">Range</p>
                <h2>Choose the sync window</h2>
              </div>
              <div className="statusUpdatePresetRow">
                {(["daily", "weekly", "custom"] as RangePreset[]).map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={`statusUpdatePreset${preset === option ? " statusUpdatePresetActive" : ""}`}
                    onClick={() => applyPreset(option)}
                    aria-pressed={preset === option}
                  >
                    <span>{PRESET_LABELS[option]}</span>
                    <small>{option === "custom" ? "Pick any range" : option === "daily" ? "Today" : "Last 7 days"}</small>
                  </button>
                ))}
              </div>
            </header>
            <div className="statusUpdateDateGrid">
              <label className="field">
                <span className="fieldLabel">Start date</span>
                <input className="textInput" type="date" value={beg} onChange={(event) => handleBegChange(event.target.value)} />
              </label>
              <label className="field">
                <span className="fieldLabel">End date</span>
                <input className="textInput" type="date" value={end} onChange={(event) => handleEndChange(event.target.value)} />
              </label>
            </div>
            <div className="statusUpdateMetaRow">
              <span className="pill">{beg ? formatShortDate(beg) : "No start selected"}</span>
              <span className="pill">{end ? formatShortDate(end) : "No end selected"}</span>
              <span className="pill pill-neutral">{preset === "custom" ? "Custom range" : `${PRESET_LABELS[preset]} preset`}</span>
            </div>
          </section>

          <section className="card statusUpdateControls">
            <header className="cardHeader">
              <div>
                <p className="eyebrow">Projects</p>
                <h2>Select the source projects</h2>
              </div>
              <div className="statusUpdateProjectActions">
                <button className="button buttonSmall buttonGhost" type="button" onClick={selectVisible} disabled={!filteredProjects.length}>
                  Select visible
                </button>
                <button className="button buttonSmall buttonGhost" type="button" onClick={clearSelected} disabled={!selectedProjectIds.length}>
                  Clear all
                </button>
              </div>
            </header>
            <label className="field">
              <span className="fieldLabel">Search projects</span>
              <input
                className="textInput"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Filter by name or path"
              />
            </label>
            <p className="muted tiny" style={{ margin: 0 }}>
              {loadingProjects ? "Loading projects..." : `${filteredProjects.length} projects shown`}
            </p>
            <div className="statusUpdateProjectGrid">
              {filteredProjects.length ? (
                filteredProjects.map((project) => {
                  const active = selectedProjectIds.includes(project.id);
                  return (
                    <button
                      key={project.id}
                      type="button"
                      className={`statusUpdateProjectCard${active ? " statusUpdateProjectCardActive" : ""}`}
                      onClick={() => toggleProject(project.id)}
                      aria-pressed={active}
                    >
                      <span className="statusUpdateProjectName">{project.name}</span>
                      <span className="statusUpdateProjectLabel">{project.label}</span>
                      <span className="statusUpdateProjectMeta">
                        {project.parentId ? "Nested project" : "Root project"}
                      </span>
                    </button>
                  );
                })
              ) : (
                <div className="statusUpdateEmpty">
                  {loadingProjects ? "Loading..." : "No projects match the current search."}
                </div>
              )}
            </div>
            <div className="statusUpdateSelectedBar">
              {selectedProjects.length ? (
                selectedProjects.map((project) => (
                  <span key={project.id} className="pill pill-neutral">
                    {project.label}
                  </span>
                ))
              ) : (
                <span className="muted tiny">Pick one or more projects to include in the draft.</span>
              )}
            </div>
          </section>

          <section className="card statusUpdateControls">
            <header className="cardHeader">
              <div>
                <p className="eyebrow">Draft details</p>
                <h2>Name the sync and generate it</h2>
              </div>
            </header>
            <div className="statusUpdateDateGrid">
              <label className="field">
                <span className="fieldLabel">Sync label</span>
                <input className="textInput" value={syncLabel} onChange={(event) => setSyncLabel(event.target.value)} placeholder="Weekly sync" />
              </label>
              <label className="field">
                <span className="fieldLabel">Selected preset</span>
                <input className="textInput" value={PRESET_LABELS[preset]} readOnly />
              </label>
            </div>
            <div className="actionRow">
              <button className="button" type="button" onClick={handleGenerate} disabled={loadingReport}>
                {loadingReport ? "Generating..." : "Generate update"}
              </button>
              <button className="button buttonGhost" type="button" onClick={copyMarkdown} disabled={!draftMarkdown.trim()}>
                Copy markdown
              </button>
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="card statusUpdateOutput">
            <header className="cardHeader">
              <div>
                <p className="eyebrow">Generated draft</p>
                <h2>Markdown ready to paste into a sync update</h2>
              </div>
              <div className="statusUpdateOutputMeta">
                <span className="pill pill-good">{(report?.title ?? syncLabel) || "Draft"}</span>
                <span className="pill pill-neutral">{generatedAt ? `Generated ${formatTime(generatedAt)}` : "Not generated yet"}</span>
              </div>
            </header>
            {draftMarkdown.trim() ? (
              <textarea className="textInput statusUpdateMarkdown" value={draftMarkdown} readOnly rows={18} />
            ) : (
              <div className="statusUpdateEmpty statusUpdateEmptyTall">
                Generate a draft to see the markdown output here.
              </div>
            )}
            <div className="statusUpdateMetaRow">
              <span className="pill">{stats?.completedCount ?? completedTasks.length} completed tasks</span>
              <span className="pill">{stats?.commentCount ?? completedTasks.reduce((total, task) => total + (task.comments?.length ?? 0), 0)} comments</span>
              <span className="pill">{stats?.projectCount ?? selectedProjects.length} projects</span>
            </div>
            {summaryText ? <p className="muted" style={{ margin: 0 }}>{summaryText}</p> : null}
            {selectedProjectNames?.length ? (
              <div className="statusUpdateNotes">
                <p className="eyebrow">Included projects</p>
                <div className="statusUpdateSelectedBar">
                  {selectedProjectNames.map((name, index) => (
                    <span key={`${name}-${index}`} className="pill pill-neutral">
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          <section className="card statusUpdateEvidenceCard">
            <header className="cardHeader">
              <div>
                <p className="eyebrow">Source evidence</p>
                <h2>Completed tasks and comments behind the draft</h2>
              </div>
            </header>
            <div className="statusUpdateEvidenceList">
              {completedTasks.length ? (
                completedTasks.map((task, index) => {
                  const key = getTaskKey(task, index);
                  const comments = task.comments ?? [];
                  return (
                    <article key={key} className="statusUpdateEvidenceItem">
                      <div className="statusUpdateEvidenceTop">
                        <div>
                          <p className="statusUpdateEvidenceTitle">{task.content}</p>
                          <p className="muted tiny" style={{ margin: 0 }}>
                            {task.projectName ?? "Unknown project"} • {formatTime(getTaskCompletedAt(task))}
                          </p>
                        </div>
                        <span className="pill pill-neutral">{comments.length} comment{comments.length === 1 ? "" : "s"}</span>
                      </div>
                      {task.summary ? <p className="statusUpdateEvidenceSummary">{task.summary}</p> : null}
                      {comments.length ? (
                        <div className="statusUpdateCommentList">
                          {comments.map((comment, commentIndex) => {
                            const normalized = normalizeComment(comment);
                            return (
                              <div key={`${key}-${commentIndex}`} className="statusUpdateComment">
                                <p className="statusUpdateCommentBody">{normalized.content}</p>
                                <p className="muted tiny" style={{ margin: 0 }}>
                                  {normalized.author ?? "Comment"}{" "}
                                  {normalized.createdAt ? `• ${formatTime(normalized.createdAt)}` : ""}
                                </p>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="muted tiny" style={{ margin: 0 }}>
                          No task comments returned for this item.
                        </p>
                      )}
                    </article>
                  );
                })
              ) : (
                <div className="statusUpdateEmpty statusUpdateEmptyTall">
                  Generated tasks will appear here with their comment snippets.
                </div>
              )}
            </div>
          </section>

          <section className="card statusUpdateNotesCard">
            <header className="cardHeader">
              <div>
                <p className="eyebrow">Notes</p>
                <h2>What the studio is doing</h2>
              </div>
            </header>
            <div className="statusUpdateNotes">
              <p className="muted">
                This workflow is intentionally manual: you choose the range, choose the projects, and generate a draft from
                completed-task activity plus the comments on those tasks.
              </p>
              <p className="muted">
                The backend is expected to return a structured report, but the page still renders useful evidence if the
                payload only includes a markdown draft and the completed tasks.
              </p>
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
