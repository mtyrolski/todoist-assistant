"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { InfoTip } from "./InfoTip";
import { requestJson } from "../lib/adminApi";
import { NUMBER_FIELDS, settingsDraft, settingsPayload } from "../lib/dashboardSettings";
import type { DashboardSettings as Settings, SettingsDraft, PlotEventSetting } from "../lib/dashboardSettings";

type SettingsResponse = { settings: Settings };
type LabelsResponse = { labels: { name: string }[] };
const RULES = [
  ["dangerOnFireLabel", "Red alert for fire labels"],
  ["warnOnPriority", "Attention for selected priorities"],
  ["warnOnDue", "Attention for due dates"],
  ["warnOnDeadline", "Attention for deadlines"]
] as const;

export function DashboardSettings({ onAfterMutation }: { onAfterMutation: () => void }) {
  const [saved, setSaved] = useState<SettingsDraft | null>(null);
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const [labels, setLabels] = useState<string[]>([]);
  const [labelDraft, setLabelDraft] = useState("");
  const [labelWarning, setLabelWarning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(saved);
  const labelOptions = useMemo(() => [...new Set([...labels, ...(draft?.fireLabels ?? [])])].sort((a, b) => a.localeCompare(b)), [labels, draft?.fireLabels]);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError(null); setNotice(null);
    try {
      const response = await requestJson<SettingsResponse>("/api/admin/dashboard/settings", { signal }, "Could not load dashboard settings");
      const next = settingsDraft(response.settings); setSaved(next); setDraft(next);
    } catch (cause) {
      if (!signal?.aborted) setError(cause instanceof Error ? cause.message : "Could not load dashboard settings");
    } finally { if (!signal?.aborted) setLoading(false); }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    requestJson<LabelsResponse>("/api/admin/dashboard/labels", { signal: controller.signal })
      .then((response) => setLabels(response.labels.map((label) => label.name.trim()).filter(Boolean)))
      .catch(() => { if (!controller.signal.aborted) setLabelWarning(true); });
    return () => controller.abort();
  }, [load]);
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  const patch = <K extends keyof SettingsDraft>(key: K, value: SettingsDraft[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current); setNotice(null);
  };
  const updateEvent = (index: number, value: Partial<PlotEventSetting>) => {
    if (draft) patch("plotEvents", draft.plotEvents.map((item, position) => position === index ? { ...item, ...value } : item));
  };
  const save = async () => {
    if (!draft || saving) return;
    setError(null); setNotice(null);
    let payload;
    try { payload = settingsPayload(draft); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Check the form values."); return; }
    setSaving(true);
    let updated = false;
    try {
      const response = await requestJson<SettingsResponse>("/api/admin/dashboard/settings", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
      }, "Could not save dashboard settings");
      const next = settingsDraft(response.settings); setSaved(next); setDraft(next); updated = true;
      setNotice("Settings saved. Dashboard attention rules are updated.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save dashboard settings"); }
    finally { setSaving(false); }
    if (updated) {
      try { onAfterMutation(); }
      catch { setNotice("Settings saved. Refresh the dashboard to see the updated rules."); }
    }
  };

  return (
    <section id="dashboard-settings" className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Dashboard settings</h2>
          <InfoTip label="About dashboard settings" content="Choose which tasks need attention and when the dashboard shows a red alert. Rules are saved locally. Due windows include overdue tasks." />
        </div>
        {dirty ? <span className="pill pill-warn">Unsaved changes</span> : null}
      </header>
      {loading ? <div className="skeleton" style={{ minHeight: 180 }} /> : !draft ? (
        <div className="stack">
          <p role="alert" className="settingsError">{error ?? "Settings are unavailable."}</p>
          <button type="button" className="button buttonSmall" onClick={() => void load()}>Try again</button>
        </div>
      ) : (
        <form className="stack" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <fieldset className="settingsFields stack" disabled={saving}>
            <label className="settingsToggle">
              <input type="checkbox" checked={draft.enabled} onChange={(event) => patch("enabled", event.target.checked)} />
              <span>Enable attention monitoring</span>
            </label>
            <p className="muted tiny">Red alerts are triggered by fire labels. Attention warnings follow the priority, due date and deadline rules you enable.</p>
            {RULES.map(([key, label]) => (
              <label className="settingsToggle" key={key}>
                <input type="checkbox" checked={draft[key]} onChange={(event) => patch(key, event.target.checked)} />
                <span>{label}</span>
              </label>
            ))}
            <fieldset className="settingsFields stack">
              <legend className="fieldLabel">Fire labels · exact names</legend>
              <div className="settingsChoices">
                {labelOptions.map((name) => (
                  <button key={name} type="button" className={`settingsChoice${draft.fireLabels.includes(name) ? " settingsChoiceSelected" : ""}`}
                    aria-pressed={draft.fireLabels.includes(name)} onClick={() => patch("fireLabels", draft.fireLabels.includes(name) ? draft.fireLabels.filter((value) => value !== name) : [...draft.fireLabels, name])}>{name}</button>
                ))}
              </div>
              {labelWarning ? <p className="muted tiny">Could not fetch account labels. Saved selections are kept; you can add a label by name.</p> : null}
              <div className="settingsAddLabel">
                <input className="textInput" aria-label="Add a fire label by name" placeholder="Add a label by exact name" value={labelDraft} onChange={(event) => setLabelDraft(event.target.value)} />
                <button className="button buttonSmall buttonGhost" type="button" disabled={!labelDraft.trim()} onClick={() => {
                  const name = labelDraft.trim(); if (name && !draft.fireLabels.includes(name)) patch("fireLabels", [...draft.fireLabels, name]); setLabelDraft("");
                }}>Add label</button>
              </div>
              <p className="muted tiny">{draft.fireLabels.length ? `${draft.fireLabels.length} selected` : "No labels selected — fire labels will not trigger an alert."}</p>
            </fieldset>
            <fieldset className="settingsFields stack">
              <legend className="fieldLabel">Attention priorities</legend>
              <div className="settingsChoices">
                {[4, 3, 2, 1].map((value) => (
                  <button key={value} type="button" aria-pressed={draft.warnPriorityThresholds.includes(value)}
                    className={`settingsChoice${draft.warnPriorityThresholds.includes(value) ? " settingsChoiceSelected" : ""}`}
                    onClick={() => patch("warnPriorityThresholds", draft.warnPriorityThresholds.includes(value) ? draft.warnPriorityThresholds.filter((item) => item !== value) : [...draft.warnPriorityThresholds, value].sort((a, b) => b - a))}>P{5 - value}</button>
                ))}
              </div>
              <p className="muted tiny">Tap to toggle. No priorities selected means priority alone will not trigger a warning.</p>
            </fieldset>
            <div className="grid2">
              {NUMBER_FIELDS.map(({ key, label, min }) => (
                <label className="field" key={key}>
                  <span className="fieldLabel">{label}</span>
                  <input className="textInput" type="number" inputMode="numeric" min={min} max={100000} step={1} required value={draft[key]} onChange={(event) => patch(key, event.target.value)} />
                </label>
              ))}
            </div>
            <p className="muted tiny">A window of 0 includes today and all overdue dates. Larger windows also include upcoming dates. Minimum matches apply separately to each rule.</p>
            <div className="plotEventEditor">
              <div className="adminRow">
                <span className="fieldLabel">Plot event markers</span>
                <button className="button buttonSmall buttonGhost" type="button" onClick={() => patch("plotEvents", [...draft.plotEvents, { date: "", label: "", color: "#ff6b7a" }])}>Add event</button>
              </div>
              {draft.plotEvents.map((item, index) => (
                <div className="plotEventRow" key={index}>
                  <label className="field"><span className="fieldLabel">Date</span><input className="textInput" type="date" value={item.date} onChange={(event) => updateEvent(index, { date: event.target.value })} /></label>
                  <label className="field"><span className="fieldLabel">Label</span><input className="textInput" maxLength={200} value={item.label} onChange={(event) => updateEvent(index, { label: event.target.value })} /></label>
                  <label className="field"><span className="fieldLabel">Color</span><input className="textInput colorInput" type="color" value={item.color} onChange={(event) => updateEvent(index, { color: event.target.value })} /></label>
                  <button className="button buttonSmall buttonGhost" type="button" aria-label={`Remove event ${item.label || index + 1}`} onClick={() => patch("plotEvents", draft.plotEvents.filter((_, position) => index !== position))}>Remove</button>
                </div>
              ))}
              {!draft.plotEvents.length ? <p className="muted tiny">No plot event markers configured.</p> : null}
            </div>
            <div className="adminRowRight">
              <button className="button buttonSmall buttonGhost" type="button" disabled={!dirty} onClick={() => { setDraft(saved); setError(null); setNotice(null); }}>Discard changes</button>
              <button className="button buttonSmall" type="submit" disabled={!dirty}>{saving ? "Saving…" : "Save settings"}</button>
            </div>
          </fieldset>
          {notice ? <p role="status" className="pill pill-good">{notice}</p> : null}
          {error ? <p role="alert" className="settingsError">{error}</p> : null}
        </form>
      )}
    </section>
  );
}
