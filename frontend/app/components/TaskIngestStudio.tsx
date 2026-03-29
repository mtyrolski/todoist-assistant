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
          className="row rowTight"
          style={{ marginLeft: depth * 18, alignItems: "flex-start" }}
        >
          <div className={`dot ${depth === 0 ? "dot-beta" : "dot-neutral"}`} />
          <div className="rowMain">
            <p className="rowTitle">{task.content}</p>
            {task.description ? <p className="muted tiny" style={{ whiteSpace: "pre-wrap" }}>{task.description}</p> : null}
            {task.children?.length ? <TaskTreePreview tasks={task.children} depth={depth + 1} /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function TaskIngestStudio() {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [rawContent, setRawContent] = useState("");
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
      if (!selectedProjectId && payload.projects.length) {
        setSelectedProjectId(payload.projects[0].id);
      }
    } catch (err) {
      setProjects([]);
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoadingProjects(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
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
        body: JSON.stringify({ rawContent: trimmed })
      });
      const payload = await readJson<PreviewResponse & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to rewrite content");
      setPreview(payload);
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
          tasks: preview.tasks
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

  return (
    <section className="grid2" style={{ alignItems: "start" }}>
      <div className="card">
        <header className="cardHeader">
          <div>
            <h2>Source</h2>
            <p className="muted tiny">Click a project, paste rough content, then rewrite it into a nested task tree.</p>
          </div>
        </header>
        <div className="stack">
          <div className="field">
            <span className="fieldLabel">Target project</span>
            {loadingProjects ? (
              <div className="skeleton" style={{ minHeight: 88 }} />
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {projects.map((project) => (
                  <button
                    key={project.id}
                    type="button"
                    className={`button buttonSmall${project.id === selectedProjectId ? "" : " buttonGhost"}`}
                    onClick={() => setSelectedProjectId(project.id)}
                  >
                    {project.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <label className="field">
            <span className="fieldLabel">Raw content</span>
            <textarea
              className="textInput"
              style={{ minHeight: 320, whiteSpace: "pre-wrap" }}
              value={rawContent}
              onChange={(event) => setRawContent(event.target.value)}
              placeholder={`Example:\nLaunch client update\n- Finalize release notes\n- Prepare rollout\n  - Update changelog\n  - Draft email\n- QA smoke pass`}
            />
          </label>

          <div className="rowActions">
            <button className="button" type="button" onClick={handlePreview} disabled={loadingPreview || creating}>
              {loadingPreview ? "Rewriting..." : "Rewrite into tasks"}
            </button>
            <button
              className="button buttonGhost"
              type="button"
              onClick={handleCreate}
              disabled={creating || !preview?.tasks.length || !selectedProjectId}
            >
              {creating ? "Creating..." : "Create in Todoist"}
            </button>
            <button className="button buttonGhost" type="button" onClick={loadProjects} disabled={loadingProjects}>
              Refresh projects
            </button>
          </div>

          {error ? <p className="pill pill-warn">{error}</p> : null}
          {notice ? <p className="pill pill-good">{notice}</p> : null}
        </div>
      </div>

      <div className="card">
        <header className="cardHeader">
          <div>
            <h2>Generated tree</h2>
            <p className="muted tiny">
              {preview
                ? `${preview.totalCount} tasks across ${preview.topLevelCount} top-level items • source: ${preview.source}`
                : "The rewritten structure appears here before anything is created."}
            </p>
          </div>
        </header>
        {!preview ? (
          <div className="stack">
            <p className="muted tiny" style={{ margin: 0 }}>
              The importer keeps nesting bounded so deep notes stay manageable in Todoist. Use your pasted outline, meeting notes,
              or rough plan as input.
            </p>
          </div>
        ) : (
          <TaskTreePreview tasks={preview.tasks} />
        )}
      </div>
    </section>
  );
}
