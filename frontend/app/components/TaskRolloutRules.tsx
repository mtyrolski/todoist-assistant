"use client";

import { useEffect, useMemo, useState } from "react";

type VariantConfig = {
  instruction: string;
  maxDepth?: number | null;
  maxChildren?: number | null;
  queueDepth?: number | null;
};

type RolloutSettings = {
  labelPrefix: string;
  defaultVariant: string;
  maxDepth: number;
  maxChildren: number;
  maxTotalTasks: number;
  maxQueueDepth: number;
  autoQueueChildren: boolean;
  variants: Record<string, VariantConfig>;
};

type RolloutResponse = {
  settings: RolloutSettings;
  basePrompt: string;
};

const NEW_VARIANT_TEMPLATE: VariantConfig = {
  instruction: "",
  maxDepth: null,
  maxChildren: null,
  queueDepth: null
};

function normalizeVariantName(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "");
}

export function TaskRolloutRules() {
  const [settings, setSettings] = useState<RolloutSettings | null>(null);
  const [draft, setDraft] = useState<RolloutSettings | null>(null);
  const [basePrompt, setBasePrompt] = useState("");
  const [selectedVariant, setSelectedVariant] = useState<string>("");
  const [newVariantName, setNewVariantName] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/admin/llm_breakdown/settings");
      const payload = (await res.json()) as RolloutResponse;
      if (!res.ok) {
        throw new Error("Failed to load LLM breakdown settings");
      }
      setSettings(payload.settings);
      setDraft(payload.settings);
      setBasePrompt(payload.basePrompt);
      setSelectedVariant(payload.settings.defaultVariant);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load LLM breakdown settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    if (!draft) return;
    if (!draft.variants[selectedVariant]) {
      setSelectedVariant(draft.defaultVariant);
    }
  }, [draft, selectedVariant]);

  const dirty = useMemo(() => {
    if (!settings || !draft) return false;
    return JSON.stringify(settings) !== JSON.stringify(draft);
  }, [settings, draft]);

  const activeVariant = draft?.variants[selectedVariant];

  const effectivePrompt = useMemo(() => {
    if (!draft || !activeVariant) return "";
    const depth = activeVariant.maxDepth ?? draft.maxDepth;
    const children = activeVariant.maxChildren ?? draft.maxChildren;
    let prompt = basePrompt.replace("{max_depth}", String(depth)).replace("{max_children}", String(children));
    if (activeVariant.instruction) {
      prompt = `${prompt} ${activeVariant.instruction}`;
    }
    return prompt;
  }, [draft, activeVariant, basePrompt]);

  const handleVariantUpdate = (key: string, updates: Partial<VariantConfig>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        variants: {
          ...prev.variants,
          [key]: {
            ...prev.variants[key],
            ...updates
          }
        }
      };
    });
    setError(null);
  };

  const handleSave = async () => {
    if (!draft) return;
    try {
      setSaving(true);
      setError(null);
      const res = await fetch("/api/admin/llm_breakdown/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft)
      });
      const payload = (await res.json()) as RolloutResponse & { saved?: boolean; detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to save settings");
      }
      setSettings(payload.settings);
      setDraft(payload.settings);
      setBasePrompt(payload.basePrompt);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!settings) return;
    setDraft(settings);
    setSelectedVariant(settings.defaultVariant);
  };

  const handleAddVariant = () => {
    const next = normalizeVariantName(newVariantName);
    if (!next || !draft) {
      setError("Variant name must use letters, numbers, hyphens, or underscores.");
      return;
    }
    if (draft.variants[next]) {
      setError("Variant already exists.");
      return;
    }
    setDraft({
      ...draft,
      variants: { ...draft.variants, [next]: { ...NEW_VARIANT_TEMPLATE } }
    });
    setSelectedVariant(next);
    setNewVariantName("");
    setError(null);
  };

  const handleRemoveVariant = (key: string) => {
    if (!draft) return;
    if (key === draft.defaultVariant) {
      setError("Default variant cannot be removed.");
      return;
    }
    if (Object.keys(draft.variants).length <= 1) {
      setError("At least one variant is required.");
      return;
    }
    const nextVariants = { ...draft.variants };
    delete nextVariants[key];
    setDraft({
      ...draft,
      variants: nextVariants
    });
    if (selectedVariant === key) {
      const fallback = Object.keys(nextVariants)[0] ?? draft.defaultVariant;
      setSelectedVariant(fallback);
    }
    setError(null);
  };

  return (
    <section className="stack">
      <div className="card">
        <header className="cardHeader">
          <h2>How task rollout works</h2>
        </header>
        <p className="muted tiny">
          Apply a label that starts with <strong>{draft?.labelPrefix ?? "llm-"}</strong> to any Todoist task. The
          automation will generate structured subtasks using the selected variant. The label after the prefix selects
          the variant, for example <strong>{draft?.labelPrefix ?? "llm-"}breakdown</strong>.
        </p>
      </div>

      {error ? <p className="pill pill-warn">{error}</p> : null}

      <div className="grid2">
        <section className="card">
          <header className="cardHeader">
            <h2>Global defaults</h2>
          </header>
          {!draft ? (
            <div className="skeleton" style={{ minHeight: 220 }} />
          ) : (
            <div className="formStack">
              <label className="field">
                <span className="muted tiny">Label prefix</span>
                <input
                  className="textInput"
                  value={draft.labelPrefix}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      labelPrefix: e.target.value
                    })
                  }
                />
              </label>
              <label className="field">
                <span className="muted tiny">Default variant</span>
                <select
                  className="select"
                  value={draft.defaultVariant}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      defaultVariant: e.target.value
                    })
                  }
                >
                  {Object.keys(draft.variants).map((key) => (
                    <option key={key} value={key}>
                      {key}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grid2">
                <label className="field">
                  <span className="muted tiny">Max depth</span>
                  <input
                    className="textInput"
                    type="number"
                    min={1}
                    value={draft.maxDepth}
                    onChange={(e) =>
                      setDraft({ ...draft, maxDepth: Math.max(1, Number(e.target.value) || 1) })
                    }
                  />
                </label>
                <label className="field">
                  <span className="muted tiny">Max children</span>
                  <input
                    className="textInput"
                    type="number"
                    min={1}
                    value={draft.maxChildren}
                    onChange={(e) =>
                      setDraft({ ...draft, maxChildren: Math.max(1, Number(e.target.value) || 1) })
                    }
                  />
                </label>
              </div>
              <div className="grid2">
                <label className="field">
                  <span className="muted tiny">Max total tasks</span>
                  <input
                    className="textInput"
                    type="number"
                    min={1}
                    value={draft.maxTotalTasks}
                    onChange={(e) =>
                      setDraft({ ...draft, maxTotalTasks: Math.max(1, Number(e.target.value) || 1) })
                    }
                  />
                </label>
                <label className="field">
                  <span className="muted tiny">Queue depth</span>
                  <input
                    className="textInput"
                    type="number"
                    min={1}
                    value={draft.maxQueueDepth}
                    onChange={(e) =>
                      setDraft({ ...draft, maxQueueDepth: Math.max(1, Number(e.target.value) || 1) })
                    }
                  />
                </label>
              </div>
              <label className="fieldToggle">
                <input
                  type="checkbox"
                  checked={draft.autoQueueChildren}
                  onChange={(e) => setDraft({ ...draft, autoQueueChildren: e.target.checked })}
                />
                <span>Auto-queue child tasks for deeper breakdowns</span>
              </label>
            </div>
          )}
        </section>

        <section className="card">
          <header className="cardHeader">
            <h2>Prompt preview</h2>
          </header>
          {!draft || !activeVariant ? (
            <div className="skeleton" style={{ minHeight: 220 }} />
          ) : (
            <div className="stack">
              <div className="pillRow">
                <span className="pill pill-neutral">Variant: {selectedVariant}</span>
                <span className="pill pill-neutral">Label: {draft.labelPrefix}{selectedVariant}</span>
              </div>
              <pre className="codeBlock" style={{ minHeight: 160 }}>
                {effectivePrompt || "Edit the instruction to preview the full prompt."}
              </pre>
            </div>
          )}
        </section>
      </div>

      <section className="card">
        <header className="cardHeader">
          <div className="cardTitleRow">
            <h2>Variants</h2>
            <span className="muted tiny">Customize how deep and detailed each rollout should be.</span>
          </div>
          <div className="rowActions">
            <input
              className="textInput"
              placeholder="New variant name"
              value={newVariantName}
              onChange={(e) => setNewVariantName(e.target.value)}
            />
            <button
              className="button buttonSmall"
              type="button"
              onClick={handleAddVariant}
              disabled={!normalizeVariantName(newVariantName)}
            >
              Add variant
            </button>
          </div>
        </header>

        {!draft ? (
          <div className="skeleton" style={{ minHeight: 180 }} />
        ) : (
          <div className="variantGrid">
            {Object.entries(draft.variants).map(([key, variant]) => {
              const disableRemove = key === draft.defaultVariant || Object.keys(draft.variants).length <= 1;
              return (
              <div key={key} className={`variantCard${selectedVariant === key ? " variantCardActive" : ""}`}>
                <div className="variantHeader">
                  <button type="button" className="variantSelect" onClick={() => setSelectedVariant(key)}>
                    {key}
                  </button>
                  <button className="button buttonSmall" type="button" onClick={() => handleRemoveVariant(key)} disabled={disableRemove}>
                    Remove
                  </button>
                </div>
                <label className="field">
                  <span className="muted tiny">Instruction</span>
                  <textarea
                    className="textInput"
                    value={variant.instruction}
                    onChange={(e) => handleVariantUpdate(key, { instruction: e.target.value })}
                  />
                </label>
                <div className="grid2">
                  <label className="field">
                    <span className="muted tiny">Max depth override</span>
                    <input
                      className="textInput"
                      type="number"
                      min={1}
                      value={variant.maxDepth ?? ""}
                      placeholder={String(draft.maxDepth)}
                      onChange={(e) =>
                        handleVariantUpdate(key, {
                          maxDepth: e.target.value ? Number(e.target.value) : null
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span className="muted tiny">Max children override</span>
                    <input
                      className="textInput"
                      type="number"
                      min={1}
                      value={variant.maxChildren ?? ""}
                      placeholder={String(draft.maxChildren)}
                      onChange={(e) =>
                        handleVariantUpdate(key, {
                          maxChildren: e.target.value ? Number(e.target.value) : null
                        })
                      }
                    />
                  </label>
                </div>
                <label className="field">
                  <span className="muted tiny">Queue depth override</span>
                  <input
                    className="textInput"
                    type="number"
                    min={1}
                    value={variant.queueDepth ?? ""}
                    placeholder={String(draft.maxQueueDepth)}
                    onChange={(e) =>
                      handleVariantUpdate(key, {
                        queueDepth: e.target.value ? Number(e.target.value) : null
                      })
                    }
                  />
                </label>
              </div>
              );
            })}
          </div>
        )}
      </section>

      <div className="actionRow">
        <button className="button" type="button" onClick={handleSave} disabled={!dirty || saving || loading}>
          {saving ? "Saving..." : "Save changes"}
        </button>
        <button className="button buttonGhost" type="button" onClick={handleReset} disabled={!dirty || saving}>
          Reset
        </button>
      </div>
    </section>
  );
}
