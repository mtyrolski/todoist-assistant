"use client";

import { useEffect, useMemo, useState } from "react";

export type TemplateNode = {
  content: string;
  description?: string;
  dueDateDaysDifference?: number | null;
  children?: TemplateNode[];
};

type TemplateSummary = {
  category: string;
  name: string;
  title: string;
  description?: string | null;
  path: string;
  label: string;
  childrenCount: number;
};

type TemplateDetail = {
  category: string;
  name: string;
  label: string;
  template: TemplateNode;
};

type TemplatesResponse = {
  templates: TemplateSummary[];
  categories: string[];
};

const EMPTY_TEMPLATE: TemplateNode = {
  content: "",
  description: "",
  dueDateDaysDifference: null,
  children: []
};

function normalizeIdentifier(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_-]/g, "");
}

function updateNode(root: TemplateNode, path: number[], updater: (node: TemplateNode) => TemplateNode): TemplateNode {
  if (!path.length) return updater(root);
  const [index, ...rest] = path;
  const children = root.children ?? [];
  return {
    ...root,
    children: children.map((child, idx) => (idx === index ? updateNode(child, rest, updater) : child))
  };
}

function addChild(root: TemplateNode, path: number[]): TemplateNode {
  return updateNode(root, path, (node) => ({
    ...node,
    children: [...(node.children ?? []), { ...EMPTY_TEMPLATE }]
  }));
}

function removeNode(root: TemplateNode, path: number[]): TemplateNode {
  if (!path.length) return root;
  const [index, ...rest] = path;
  if (!rest.length) {
    const nextChildren = (root.children ?? []).filter((_, idx) => idx !== index);
    return { ...root, children: nextChildren };
  }
  return {
    ...root,
    children: (root.children ?? []).map((child, idx) =>
      idx === index ? removeNode(child, rest) : child
    )
  };
}

function TemplateNodeEditor({
  node,
  path,
  depth,
  onChange,
  onAddChild,
  onRemove
}: {
  node: TemplateNode;
  path: number[];
  depth: number;
  onChange: (path: number[], next: TemplateNode) => void;
  onAddChild: (path: number[]) => void;
  onRemove: (path: number[]) => void;
}) {
  const indentStyle = { paddingLeft: `${depth * 16}px` };
  return (
    <div className="templateNode" style={indentStyle}>
      <div className="templateNodeHeader">
        <p className="muted tiny">{depth === 0 ? "Root task" : `Subtask ${depth}`}</p>
        {depth > 0 ? (
          <button className="button buttonSmall" type="button" onClick={() => onRemove(path)}>
            Remove
          </button>
        ) : null}
      </div>
      <div className="formStack">
        <label className="field">
          <span className="muted tiny">Title</span>
          <input
            className="textInput"
            value={node.content}
            onChange={(e) => onChange(path, { ...node, content: e.target.value })}
            placeholder="Task title"
          />
        </label>
        <label className="field">
          <span className="muted tiny">Description</span>
          <textarea
            className="textInput"
            value={node.description ?? ""}
            onChange={(e) => onChange(path, { ...node, description: e.target.value })}
            placeholder="Optional details"
          />
        </label>
        <label className="field">
          <span className="muted tiny">Due date offset (days)</span>
          <input
            className="textInput"
            type="number"
            value={node.dueDateDaysDifference ?? ""}
            onChange={(e) =>
              onChange(path, {
                ...node,
                dueDateDaysDifference: e.target.value ? Number(e.target.value) : null
              })
            }
            placeholder="e.g. -3"
          />
        </label>
      </div>
      <div className="templateNodeActions">
        <button className="button buttonSmall" type="button" onClick={() => onAddChild(path)}>
          Add subtask
        </button>
      </div>
      {(node.children ?? []).length ? (
        <div className="templateChildren">
          {(node.children ?? []).map((child, idx) => (
            <TemplateNodeEditor
              key={`${path.join("-")}-${idx}`}
              node={child}
              path={[...path, idx]}
              depth={depth + 1}
              onChange={onChange}
              onAddChild={onAddChild}
              onRemove={onRemove}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function TaskTemplateManager() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [selected, setSelected] = useState<TemplateSummary | null>(null);
  const [editor, setEditor] = useState<TemplateNode | null>(null);
  const [editorCategory, setEditorCategory] = useState("");
  const [editorName, setEditorName] = useState("");
  const [labelPreview, setLabelPreview] = useState("");
  const [loadingList, setLoadingList] = useState(false);
  const [loadingEditor, setLoadingEditor] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadTemplates = async () => {
    try {
      setLoadingList(true);
      setError(null);
      const res = await fetch("/api/admin/templates");
      const payload = (await res.json()) as TemplatesResponse;
      if (!res.ok) throw new Error("Failed to load templates");
      setTemplates(payload.templates);
      if (!selected && !creating && payload.templates.length) {
        setSelected(payload.templates[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load templates");
      setTemplates([]);
    } finally {
      setLoadingList(false);
    }
  };

  const loadTemplateDetail = async (category: string, name: string) => {
    try {
      setLoadingEditor(true);
      setError(null);
      const res = await fetch(`/api/admin/templates/${encodeURIComponent(category)}/${encodeURIComponent(name)}`);
      const payload = (await res.json()) as TemplateDetail;
      if (!res.ok) throw new Error("Failed to load template");
      setEditor(payload.template);
      setEditorCategory(payload.category);
      setEditorName(payload.name);
      setLabelPreview(payload.label);
      setCreating(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load template");
      setEditor(null);
    } finally {
      setLoadingEditor(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  useEffect(() => {
    if (!selected) return;
    loadTemplateDetail(selected.category, selected.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.category, selected?.name]);

  const handleNewTemplate = () => {
    setCreating(true);
    setEditor({ ...EMPTY_TEMPLATE });
    setEditorCategory("");
    setEditorName("");
    setLabelPreview("");
    setSelected(null);
  };

  const handleSave = async () => {
    if (!editor) return;
    try {
      setSaving(true);
      setError(null);
      if (creating) {
        const safeCategory = normalizeIdentifier(editorCategory);
        const safeName = normalizeIdentifier(editorName);
        if (!safeCategory || !safeName) {
          setError("Category and template name are required.");
          setSaving(false);
          return;
        }
        setEditorCategory(safeCategory);
        setEditorName(safeName);
        const res = await fetch("/api/admin/templates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            category: safeCategory,
            name: safeName,
            template: editor
          })
        });
        const payload = (await res.json()) as { detail?: string };
        if (!res.ok) throw new Error(payload.detail ?? "Failed to create template");
        setCreating(false);
        await loadTemplates();
        setSelected({
          category: safeCategory,
          name: safeName,
          title: editor.content || safeName,
          description: editor.description ?? "",
          path: "",
          label: `template-${safeName}`,
          childrenCount: editor.children?.length ?? 0
        });
      } else {
        const res = await fetch(`/api/admin/templates/${encodeURIComponent(editorCategory)}/${encodeURIComponent(editorName)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ template: editor })
        });
        const payload = (await res.json()) as { detail?: string };
        if (!res.ok) throw new Error(payload.detail ?? "Failed to save template");
        await loadTemplates();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save template");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    const ok = window.confirm(`Delete template ${selected.name}? This cannot be undone.`);
    if (!ok) return;
    try {
      setSaving(true);
      const res = await fetch(`/api/admin/templates/${encodeURIComponent(selected.category)}/${encodeURIComponent(selected.name)}`, {
        method: "DELETE"
      });
      const payload = (await res.json()) as { detail?: string };
      if (!res.ok) throw new Error(payload.detail ?? "Failed to delete template");
      setSelected(null);
      setEditor(null);
      await loadTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete template");
    } finally {
      setSaving(false);
    }
  };

  const canSave = useMemo(() => {
    if (!editor) return false;
    if (creating) {
      return normalizeIdentifier(editorCategory).length > 0 && normalizeIdentifier(editorName).length > 0 && editor.content.trim().length > 0;
    }
    return editor.content.trim().length > 0;
  }, [editor, creating, editorCategory, editorName]);

  return (
    <section className="grid2">
      <div className="card">
        <header className="cardHeader">
          <div>
            <h2>Templates library</h2>
            <p className="muted tiny">Choose a template to edit or create a new one.</p>
          </div>
          <button className="button buttonSmall" type="button" onClick={handleNewTemplate}>
            New template
          </button>
        </header>
        {loadingList ? (
          <div className="skeleton" style={{ minHeight: 180 }} />
        ) : (
          <div className="list">
            {templates.length ? (
              templates.map((tpl) => (
                <button
                  key={`${tpl.category}-${tpl.name}`}
                  type="button"
                  className={`row rowButton ${selected?.name === tpl.name && selected?.category === tpl.category ? "rowActive" : ""}`}
                  onClick={() => setSelected(tpl)}
                >
                  <div className="dot dot-neutral" />
                  <div className="rowMain">
                    <p className="rowTitle">{tpl.title}</p>
                    <p className="muted tiny">
                      {tpl.category} / {tpl.label} / {tpl.childrenCount} steps
                    </p>
                  </div>
                  <p className="rowDetail">{tpl.description || tpl.name}</p>
                </button>
              ))
            ) : (
              <p className="muted tiny">No templates yet.</p>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <header className="cardHeader">
          <div>
            <h2>{creating ? "Create new template" : "Template editor"}</h2>
            <p className="muted tiny">Use the label to trigger this template in Todoist.</p>
          </div>
          <div className="rowActions">
            {!creating && selected ? (
              <button className="button buttonSmall" type="button" onClick={handleDelete} disabled={saving}>
                Delete
              </button>
            ) : null}
            <button className="button buttonSmall" type="button" onClick={handleSave} disabled={!canSave || saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </header>

        {error ? <p className="pill pill-warn">{error}</p> : null}

        {loadingEditor || !editor ? (
          <div className="skeleton" style={{ minHeight: 220 }} />
        ) : (
          <div className="stack">
            {creating ? (
              <div className="grid2">
                <label className="field">
                  <span className="muted tiny">Category</span>
                  <input
                    className="textInput"
                    value={editorCategory}
                    onChange={(e) => setEditorCategory(e.target.value)}
                    placeholder="development"
                  />
                </label>
                <label className="field">
                  <span className="muted tiny">Template name</span>
                  <input
                    className="textInput"
                    value={editorName}
                    onChange={(e) => setEditorName(e.target.value)}
                    placeholder="feature"
                  />
                </label>
                <p className="muted tiny" style={{ gridColumn: "1 / -1" }}>
                  Use lowercase letters, numbers, hyphens, or underscores for names.
                </p>
              </div>
            ) : null}
            <div className="pillRow">
              <span className="pill pill-neutral">
                Label: {creating ? `template-${normalizeIdentifier(editorName) || "new"}` : labelPreview}
              </span>
              <span className="pill pill-neutral">Category: {creating ? normalizeIdentifier(editorCategory) || "-" : editorCategory || "-"}</span>
            </div>
            <TemplateNodeEditor
              node={editor}
              path={[]}
              depth={0}
              onChange={(path, next) => setEditor(updateNode(editor, path, () => next))}
              onAddChild={(path) => setEditor(addChild(editor, path))}
              onRemove={(path) => setEditor(removeNode(editor, path))}
            />
          </div>
        )}
      </div>
    </section>
  );
}
