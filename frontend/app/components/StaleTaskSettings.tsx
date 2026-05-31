"use client";

import { useCallback, useEffect, useState } from "react";
import { InfoTip } from "./InfoTip";

type StaleTaskSettingsResponse = {
  settings: {
    oldAfterDays: number;
    veryOldAfterDays: number;
    warningLabel: string;
    veryOldLabel: string;
    deleteAfterWarningDays: number;
    dryRun: boolean;
    maxUpdatesPerTick: number | null;
  };
};

const STALE_TASK_HELP = `**Stale Task Automation**
Adds a warning label to untouched tasks, tracks when the label was added, and removes tasks after the configured grace period.

- Dry run records what would happen without mutating Todoist.
- The delete timer starts when the automation first applies or observes the warning label.`;

async function readJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

export function StaleTaskSettings({ onAfterMutation }: { onAfterMutation: () => void }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [oldAfterDays, setOldAfterDays] = useState("30");
  const [veryOldAfterDays, setVeryOldAfterDays] = useState("90");
  const [warningLabel, setWarningLabel] = useState("old");
  const [veryOldLabel, setVeryOldLabel] = useState("very-old");
  const [deleteAfterWarningDays, setDeleteAfterWarningDays] = useState("7");
  const [dryRun, setDryRun] = useState(true);
  const [maxUpdatesPerTick, setMaxUpdatesPerTick] = useState("25");

  const applySettings = (payload: StaleTaskSettingsResponse) => {
    setOldAfterDays(String(payload.settings.oldAfterDays));
    setVeryOldAfterDays(String(payload.settings.veryOldAfterDays));
    setWarningLabel(payload.settings.warningLabel);
    setVeryOldLabel(payload.settings.veryOldLabel);
    setDeleteAfterWarningDays(String(payload.settings.deleteAfterWarningDays));
    setDryRun(payload.settings.dryRun);
    setMaxUpdatesPerTick(String(payload.settings.maxUpdatesPerTick ?? 0));
  };

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/admin/stale_tasks");
      const payload = await readJson<StaleTaskSettingsResponse>(res);
      if (!res.ok) throw new Error("Failed to load stale task settings");
      applySettings(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load stale task settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const saveSettings = async () => {
    try {
      setSaving(true);
      setError(null);
      setNotice(null);
      const res = await fetch("/api/admin/stale_tasks", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          oldAfterDays: Number(oldAfterDays),
          veryOldAfterDays: Number(veryOldAfterDays),
          warningLabel,
          veryOldLabel,
          deleteAfterWarningDays: Number(deleteAfterWarningDays),
          dryRun,
          maxUpdatesPerTick: Number(maxUpdatesPerTick)
        })
      });
      const payload = await readJson<StaleTaskSettingsResponse & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to save stale task settings");
      applySettings(payload);
      setNotice("Stale task settings updated.");
      onAfterMutation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save stale task settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section id="stale-task-settings" className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Stale Tasks</h2>
          <InfoTip label="About stale tasks" content={STALE_TASK_HELP} />
        </div>
        <span className={`pill ${dryRun ? "pill-warn" : "pill-good"}`}>{dryRun ? "Dry run" : "Writes enabled"}</span>
      </header>
      {loading ? (
        <div className="skeleton" style={{ minHeight: 180 }} />
      ) : (
        <div className="stack">
          <div className="grid2">
            <label className="field">
              <span className="fieldLabel">Warning after days</span>
              <input className="textInput" type="number" min="0" value={oldAfterDays} onChange={(event) => setOldAfterDays(event.target.value)} />
            </label>
            <label className="field">
              <span className="fieldLabel">Escalate after days</span>
              <input className="textInput" type="number" min="0" value={veryOldAfterDays} onChange={(event) => setVeryOldAfterDays(event.target.value)} />
            </label>
          </div>
          <div className="grid2">
            <label className="field">
              <span className="fieldLabel">Warning label</span>
              <input className="textInput" value={warningLabel} onChange={(event) => setWarningLabel(event.target.value)} />
            </label>
            <label className="field">
              <span className="fieldLabel">Escalation label</span>
              <input className="textInput" value={veryOldLabel} onChange={(event) => setVeryOldLabel(event.target.value)} />
            </label>
          </div>
          <div className="grid2">
            <label className="field">
              <span className="fieldLabel">Delete after warning days</span>
              <input className="textInput" type="number" min="0" value={deleteAfterWarningDays} onChange={(event) => setDeleteAfterWarningDays(event.target.value)} />
            </label>
            <label className="field">
              <span className="fieldLabel">Max mutations per run</span>
              <input className="textInput" type="number" min="0" value={maxUpdatesPerTick} onChange={(event) => setMaxUpdatesPerTick(event.target.value)} />
            </label>
          </div>
          <label className="field">
            <span className="fieldLabel">Dry run</span>
            <input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} />
          </label>
          <div className="adminRowRight">
            <button className="button buttonSmall" type="button" onClick={saveSettings} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
          {notice ? <p className="pill pill-good">{notice}</p> : null}
          {error ? <p className="pill pill-warn">{error}</p> : null}
        </div>
      )}
    </section>
  );
}
