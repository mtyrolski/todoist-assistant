"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type ProjectOption = {
  id: string;
  name: string;
  label: string;
  parentId?: string | null;
};

type TaskNode = {
  content: string;
  description?: string | null;
  children?: TaskNode[];
};

type ProjectsResponse = {
  projects: ProjectOption[];
};

type PreviewResponse = {
  source: string;
  tasks: TaskNode[];
  topLevelCount: number;
  totalCount: number;
};

type CreateResponse = {
  created: Array<{ id: string; content: string }>;
  createdCount: number;
  topLevelCount: number;
};

type Granularity = "compact" | "balanced" | "detailed";
type StructurePreference = "action-first" | "milestone-driven" | "checklist-heavy" | "meeting-notes";
type IngestOptions = {
  maxDepth: 2 | 3 | 4;
  granularity: Granularity;
  preference: StructurePreference;
  includeDescriptions: boolean;
};

const DEPTH_OPTIONS: Array<{ value: IngestOptions["maxDepth"]; label: string; hint: string }> = [
  { value: 2, label: "2 levels", hint: "Lean and compact" },
  { value: 3, label: "3 levels", hint: "Balanced structure" },
  { value: 4, label: "4 levels", hint: "Deep planning detail" }
];

const GRANULARITY_OPTIONS: Array<{ value: Granularity; label: string; hint: string }> = [
  { value: "compact", label: "Compact", hint: "Fewer branches, fewer subtasks" },
  { value: "balanced", label: "Balanced", hint: "A practical default" },
  { value: "detailed", label: "Detailed", hint: "More nested steps and substeps" }
];

const PREFERENCE_OPTIONS: Array<{ value: StructurePreference; label: string; hint: string }> = [
  { value: "action-first", label: "Action-first", hint: "Write the next concrete action" },
  { value: "milestone-driven", label: "Milestones", hint: "Group around checkpoints" },
  { value: "checklist-heavy", label: "Checklist", hint: "Use crisp step-by-step items" },
  { value: "meeting-notes", label: "Meeting notes", hint: "Turn notes into decisions and follow-ups" }
];

async function readJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

function TaskTreePreview({ tasks, depth = 0 }: { tasks: TaskNode[]; depth?: number }) {
  return (
    <div className="list">
      {tasks.map((task, index) => (
        <div
          key={`${depth}-${index}-${task.content}`}
          className="row rowTight taskTreeRow"
          data-depth={depth}
          style={{ marginLeft: depth * 18, alignItems: "flex-start" }}
        >
          <div className={`dot ${depth === 0 ? "dot-beta" : depth % 2 === 0 ? "dot-ok" : "dot-neutral"}`} />
          <div className="rowMain">
            <p className="rowTitle">{task.content}</p>
            <p className="muted tiny taskTreeMeta">
              {depth === 0 ? "Top-level task" : `Subtask level ${depth + 1}`}
              {task.children?.length ? ` • ${task.children.length} nested item${task.children.length === 1 ? "" : "s"}` : " • leaf node"}
            </p>
            {task.description ? <p className="taskTreeDescription">{task.description}</p> : null}
            {task.children?.length ? <TaskTreePreview tasks={task.children} depth={depth + 1} /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function countTaskNodes(tasks: TaskNode[]): number {
  return tasks.reduce((total, task) => total + 1 + countTaskNodes(task.children ?? []), 0);
}

function maxTaskDepth(tasks: TaskNode[], depth = 1): number {
  if (!tasks.length) return depth - 1;
  return tasks.reduce((max, task) => Math.max(max, maxTaskDepth(task.children ?? [], depth + 1)), depth);
}

function formatPreferenceLabel(value: StructurePreference): string {
  return PREFERENCE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function formatGranularityLabel(value: Granularity): string {
  return GRANULARITY_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function buildIngestOptions(options: IngestOptions): Record<string, unknown> {
  return {
    maxDepth: options.maxDepth,
    granularity: options.granularity,
    preference: options.preference,
    includeDescriptions: options.includeDescriptions
  };
}

function ChoiceGroup<T extends string | number>({
  label,
  hint,
  options,
  value,
  onChange
}: {
  label: string;
  hint: string;
  options: Array<{ value: T; label: string; hint: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="taskIngestChoiceGroup">
      <div className="taskIngestChoiceHeader">
        <span className="fieldLabel">{label}</span>
        <p className="muted tiny" style={{ margin: 0 }}>{hint}</p>
      </div>
      <div className="taskIngestChoiceRow">
        {options.map((option) => (
          <button
            key={String(option.value)}
            type="button"
            className={`taskIngestChoice${option.value === value ? " taskIngestChoiceActive" : ""}`}
            onClick={() => onChange(option.value)}
            aria-pressed={option.value === value}
          >
            <span>{option.label}</span>
            <small>{option.hint}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

export function TaskIngestStudio() {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [rawContent, setRawContent] = useState("");
  const [maxDepth, setMaxDepth] = useState<IngestOptions["maxDepth"]>(3);
  const [granularity, setGranularity] = useState<Granularity>("balanced");
  const [preference, setPreference] = useState<StructurePreference>("action-first");
  const [includeDescriptions, setIncludeDescriptions] = useState(true);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      setLoadingProjects(true);
      setError(null);
      const res = await fetch("/api/admin/task_ingest/projects");
      const payload = await readJson<ProjectsResponse & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to load projects");
      setProjects(payload.projects);
      setSelectedProjectId((current) => current || payload.projects[0]?.id || "");
    } catch (err) {
      setProjects([]);
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );

  const previewStats = useMemo(() => {
    if (!preview) {
      return { totalNodes: 0, maxDepthObserved: 0 };
    }
    return {
      totalNodes: countTaskNodes(preview.tasks),
      maxDepthObserved: maxTaskDepth(preview.tasks)
    };
  }, [preview]);

  const ingestOptions = useMemo(
    () => buildIngestOptions({ maxDepth, granularity, preference, includeDescriptions }),
    [maxDepth, granularity, preference, includeDescriptions]
  );

  const handlePreview = async () => {
    const trimmed = rawContent.trim();
    if (!trimmed) {
      setError("Paste the raw content you want to convert.");
      return;
    }
    try {
      setLoadingPreview(true);
      setError(null);
      setNotice(null);
      const res = await fetch("/api/admin/task_ingest/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rawContent: trimmed,
          options: ingestOptions
        })
      });
      const payload = await readJson<PreviewResponse & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to rewrite content");
      setPreview(payload);
      setNotice(`Preview ready as a ${maxDepth}-level ${formatGranularityLabel(granularity).toLowerCase()} tree.`);
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "Failed to rewrite content");
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleCreate = async () => {
    if (!selectedProjectId) {
      setError("Select a project first.");
      return;
    }
    if (!preview?.tasks.length) {
      setError("Generate the task tree first.");
      return;
    }
    try {
      setCreating(true);
      setError(null);
      setNotice(null);
      const res = await fetch("/api/admin/task_ingest/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: selectedProjectId,
          rawContent: rawContent.trim(),
          tasks: preview.tasks,
          options: ingestOptions
        })
      });
      const payload = await readJson<CreateResponse & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to create tasks");
      setNotice(`Created ${payload.createdCount} tasks in ${selectedProject?.label ?? "the selected project"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create tasks");
    } finally {
      setCreating(false);
    }
  };

  const sourceSummary = [
    selectedProject ? selectedProject.label : "No project selected",
    `${maxDepth}-level depth`,
    formatGranularityLabel(granularity),
    formatPreferenceLabel(preference),
    includeDescriptions ? "descriptions on" : "descriptions off"
  ];

  const previewDepthWarning =
    preview && previewStats.maxDepthObserved > maxDepth
      ? `Preview reached depth ${previewStats.maxDepthObserved}, which is deeper than your target ${maxDepth}.`
      : null;

  return (
    <section className="stack taskIngestLayout">
      <div className="taskIngestHero">
        <div className="stack" style={{ gap: 10 }}>
          <div className="taskIngestEyebrowRow">
            <span className="pill pill-beta">Structured ingest</span>
            <span className="pill pill-neutral">Paste once, create clean task trees</span>
          </div>
          <div>
            <h2 className="taskIngestTitle">Turn rough notes into a nested Todoist plan.</h2>
            <p className="muted tiny taskIngestLead">
              Pick a project, choose the tree depth and writing style, then preview the result before anything is created.
            </p>
          </div>
        </div>
        <div className="taskIngestHeroStats">
          {sourceSummary.map((item) => (
            <span key={item} className="taskIngestHeroStat">
              {item}
            </span>
          ))}
        </div>
      </div>

      <div className="taskIngestGrid">
        <div className="card taskIngestPanel">
        <header className="cardHeader">
          <div>
            <h2>Source</h2>
            <p className="muted tiny">Choose the target project, tune the structure, and paste the raw content to rewrite.</p>
          </div>
        </header>
        <div className="stack">
          <div className="taskIngestStatus taskIngestStatusInfo">
            <div>
              <p className="taskIngestStatusTitle">Current ingest profile</p>
              <p className="muted tiny" style={{ margin: 0 }}>
                {selectedProject?.label ?? "Pick a project"} • {maxDepth} levels • {formatGranularityLabel(granularity)} •{" "}
                {formatPreferenceLabel(preference)}
              </p>
            </div>
            <span className="pill pill-neutral">{includeDescriptions ? "Descriptions kept" : "Descriptions trimmed"}</span>
          </div>

          <div className="field">
            <span className="fieldLabel">Target project</span>
            {loadingProjects ? (
              <div className="skeleton" style={{ minHeight: 88 }} />
            ) : (
              <div className="taskIngestProjectGrid">
                {projects.map((project) => (
                  <button
                    key={project.id}
                    type="button"
                    className={`taskIngestProject${project.id === selectedProjectId ? " taskIngestProjectActive" : ""}`}
                    onClick={() => setSelectedProjectId(project.id)}
                  >
                    <span className="taskIngestProjectName">{project.label}</span>
                    <span className="taskIngestProjectMeta">
                      {project.parentId ? `subproject of ${project.parentId}` : "top-level project"}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="taskIngestSettingsCard">
            <ChoiceGroup
              label="Depth"
              hint="How many nested levels the rewrite should aim for."
              options={DEPTH_OPTIONS}
              value={maxDepth}
              onChange={setMaxDepth}
            />
            <ChoiceGroup
              label="Granularity"
              hint="Controls how much intermediate structure the model should create."
              options={GRANULARITY_OPTIONS}
              value={granularity}
              onChange={setGranularity}
            />
            <ChoiceGroup
              label="Preference"
              hint="Choose the kind of structure you want in the final task tree."
              options={PREFERENCE_OPTIONS}
              value={preference}
              onChange={setPreference}
            />
            <label className="taskIngestToggle">
              <input
                type="checkbox"
                checked={includeDescriptions}
                onChange={(event) => setIncludeDescriptions(event.target.checked)}
              />
              <span>
                <strong>Keep descriptions</strong>
                <small>Carry explanatory text into task notes when it helps.</small>
              </span>
            </label>
          </div>

          <label className="field">
            <span className="fieldLabel">Raw content</span>
            <textarea
              className="textInput taskIngestTextarea"
              style={{ whiteSpace: "pre-wrap" }}
              value={rawContent}
              onChange={(event) => setRawContent(event.target.value)}
              placeholder={`Example:\nLaunch client update\n- Finalize release notes\n- Prepare rollout\n  - Update changelog\n  - Draft email\n- QA smoke pass`}
            />
            <p className="muted tiny taskIngestHint">
              The rewrite uses your selected depth, granularity, and preference hints, so the generated tree can be more structured.
            </p>
          </label>

          <div className="rowActions">
            <button className="button taskIngestPrimaryButton" type="button" onClick={handlePreview} disabled={loadingPreview || creating}>
              {loadingPreview ? "Rewriting…" : "Rewrite into tasks"}
            </button>
            <button
              className="button buttonGhost taskIngestSecondaryButton"
              type="button"
              onClick={handleCreate}
              disabled={creating || !preview?.tasks.length || !selectedProjectId}
            >
              {creating ? "Creating…" : "Create in Todoist"}
            </button>
            <button className="button buttonGhost taskIngestSecondaryButton" type="button" onClick={loadProjects} disabled={loadingProjects}>
              {loadingProjects ? "Reloading…" : "Reload projects"}
            </button>
          </div>

          {error ? <p className="taskIngestBanner taskIngestBannerError">{error}</p> : null}
          {notice ? <p className="taskIngestBanner taskIngestBannerSuccess">{notice}</p> : null}
        </div>
        </div>

        <div className="card taskIngestPanel taskIngestPreviewPanel">
        <header className="cardHeader">
          <div>
            <h2>Generated tree</h2>
            <div className="taskIngestPreviewSummary">
              <span className={`pill ${preview ? "pill-good" : "pill-neutral"}`}>
                {preview ? `${preview.totalCount} tasks` : "Awaiting preview"}
              </span>
              <span className="pill pill-neutral">
                {preview ? `${preview.topLevelCount} top-level` : "Preview will summarize structure"}
              </span>
              {preview ? <span className="pill pill-beta">source: {preview.source}</span> : null}
            </div>
          </div>
        </header>
        {!preview ? (
          <div className="taskIngestEmptyState">
            <p className="taskIngestEmptyTitle">Preview the tree to check structure before creating tasks.</p>
            <p className="muted tiny" style={{ margin: 0 }}>
              The controls on the left influence how the rewrite is organized. Start with balanced depth, then tighten or expand
              until the tree matches how you think about the project.
            </p>
          </div>
        ) : (
          <div className="stack">
            <div className={`taskIngestStatus ${previewDepthWarning ? "taskIngestStatusWarn" : "taskIngestStatusSuccess"}`}>
              <div>
                <p className="taskIngestStatusTitle">{previewDepthWarning ? "Depth mismatch" : "Preview is ready"}</p>
                <p className="muted tiny" style={{ margin: 0 }}>
                  {previewDepthWarning ?? `${previewStats.totalNodes} total tasks with a max depth of ${previewStats.maxDepthObserved}.`}
                </p>
              </div>
              <span className="pill pill-neutral">
                Target {maxDepth} / observed {previewStats.maxDepthObserved}
              </span>
            </div>
            <TaskTreePreview tasks={preview.tasks} />
          </div>
        )}
        </div>
      </div>
    </section>
  );
}
