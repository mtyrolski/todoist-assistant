"use client";

import { useEffect, useMemo, useState } from "react";

type MultiplicationSettings = {
  flatLeafTemplate: string;
  deepLeafTemplate: string;
  flatLabelRegex: string;
  deepLabelRegex: string;
};

type MultiplicationResponse = {
  settings: MultiplicationSettings;
};

function renderTemplate(template: string, base: string, i: number, n: number) {
  return template
    .replace(/\{base\}/g, base)
    .replace(/\{i\}/g, String(i))
    .replace(/\{n\}/g, String(n));
}

export function MultiplicationSettings() {
  const [settings, setSettings] = useState<MultiplicationSettings | null>(null);
  const [draft, setDraft] = useState<MultiplicationSettings | null>(null);
  const [baseText, setBaseText] = useState("Draft proposal");
  const [factor, setFactor] = useState(3);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/admin/multiplication");
      const payload = (await res.json()) as MultiplicationResponse;
      if (!res.ok) throw new Error("Failed to load settings");
      setSettings(payload.settings);
      setDraft(payload.settings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const dirty = useMemo(() => {
    if (!settings || !draft) return false;
    return JSON.stringify(settings) !== JSON.stringify(draft);
  }, [settings, draft]);

  const flatPreview = useMemo(() => {
    if (!draft) return [] as string[];
    return Array.from({ length: factor }, (_, idx) => renderTemplate(draft.flatLeafTemplate, baseText, idx + 1, factor));
  }, [draft, baseText, factor]);

  const deepPreview = useMemo(() => {
    if (!draft) return [] as string[];
    return Array.from({ length: factor }, (_, idx) => renderTemplate(draft.deepLeafTemplate, baseText, idx + 1, factor));
  }, [draft, baseText, factor]);

  const handleSave = async () => {
    if (!draft) return;
    try {
      setSaving(true);
      setError(null);
      const res = await fetch("/api/admin/multiplication", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          flatLeafTemplate: draft.flatLeafTemplate,
          deepLeafTemplate: draft.deepLeafTemplate
        })
      });
      const payload = (await res.json()) as MultiplicationResponse & { detail?: string };
      if (!res.ok) throw new Error(payload.detail ?? "Failed to save settings");
      setSettings(payload.settings);
      setDraft(payload.settings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="stack">
      {error ? <p className="pill pill-warn">{error}</p> : null}
      <div className="grid2">
        <section className="card">
          <header className="cardHeader">
            <h2>Label templates</h2>
          </header>
          <p className="muted tiny">
            Use placeholders {`{base}`}, {`{i}`}, and {`{n}`} to control the generated task titles.
          </p>
          {!draft || loading ? (
            <div className="skeleton" style={{ minHeight: 220 }} />
          ) : (
            <div className="formStack">
              <label className="field">
                <span className="muted tiny">Flat label template (Xn)</span>
                <input
                  className="textInput"
                  value={draft.flatLeafTemplate}
                  onChange={(e) => setDraft({ ...draft, flatLeafTemplate: e.target.value })}
                />
                <span className="muted tiny">Pattern: {draft.flatLabelRegex}</span>
              </label>
              <label className="field">
                <span className="muted tiny">Deep label template (_Xn)</span>
                <input
                  className="textInput"
                  value={draft.deepLeafTemplate}
                  onChange={(e) => setDraft({ ...draft, deepLeafTemplate: e.target.value })}
                />
                <span className="muted tiny">Pattern: {draft.deepLabelRegex}</span>
              </label>
            </div>
          )}
        </section>

        <section className="card">
          <header className="cardHeader">
            <h2>Live preview</h2>
          </header>
          <div className="formStack">
            <label className="field">
              <span className="muted tiny">Sample task title</span>
              <input className="textInput" value={baseText} onChange={(e) => setBaseText(e.target.value)} />
            </label>
            <label className="field">
              <span className="muted tiny">Multiplication factor</span>
              <input
                className="textInput"
                type="number"
                min={1}
                value={factor}
                onChange={(e) => setFactor(Number(e.target.value) || 1)}
              />
            </label>
            <div className="previewGrid">
              <div>
                <p className="muted tiny">Flat results</p>
                <div className="list">
                  {flatPreview.map((item, idx) => (
                    <div key={idx} className="row rowTight">
                      <div className="dot dot-neutral" />
                      <div className="rowMain">
                        <p className="rowTitle">{item}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <p className="muted tiny">Deep results</p>
                <div className="list">
                  {deepPreview.map((item, idx) => (
                    <div key={idx} className="row rowTight">
                      <div className="dot dot-neutral" />
                      <div className="rowMain">
                        <p className="rowTitle">{item}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div className="actionRow">
        <button className="button" type="button" onClick={handleSave} disabled={!dirty || saving}>
          {saving ? "Saving..." : "Save changes"}
        </button>
      </div>
    </section>
  );
}
