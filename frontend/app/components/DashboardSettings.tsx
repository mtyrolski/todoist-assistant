"use client";

import { useCallback, useEffect, useState } from "react";
import { InfoTip } from "./InfoTip";

type DashboardSettingsResponse = {
  settings: {
    enabled: boolean;
    fireLabel: string;
    warnPriorityThresholds: number[];
    warnDueWithinDays: number;
    warnDeadlineWithinDays: number;
    configPath?: string;
  };
};

type DashboardLabelsResponse = {
  labels: {
    name: string;
    color?: string | null;
  }[];
};

const DASHBOARD_SETTINGS_HELP = `**Dashboard Settings**
Tune dashboard-specific rules that drive warning cards and local monitoring.

- Changes are saved to local YAML files.
- Urgency settings change the watch/warn behavior on the main dashboard.`;

async function readJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

export function DashboardSettings({ onAfterMutation }: { onAfterMutation: () => void }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configPath, setConfigPath] = useState<string>("");
  const [enabled, setEnabled] = useState(true);
  const [fireLabel, setFireLabel] = useState("fire");
  const [labelOptions, setLabelOptions] = useState<string[]>([]);
  const [warnPriorityThresholds, setWarnPriorityThresholds] = useState("4,3");
  const [warnDueWithinDays, setWarnDueWithinDays] = useState("0");
  const [warnDeadlineWithinDays, setWarnDeadlineWithinDays] = useState("0");

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/admin/dashboard/settings");
      const payload = await readJson<DashboardSettingsResponse>(res);
      if (!res.ok) {
        throw new Error("Failed to load dashboard settings");
      }
      setEnabled(payload.settings.enabled);
      setFireLabel(payload.settings.fireLabel);
      setWarnPriorityThresholds(payload.settings.warnPriorityThresholds.join(","));
      setWarnDueWithinDays(String(payload.settings.warnDueWithinDays));
      setWarnDeadlineWithinDays(String(payload.settings.warnDeadlineWithinDays));
      setConfigPath(payload.settings.configPath ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard settings");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLabels = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/dashboard/labels");
      const payload = await readJson<DashboardLabelsResponse>(res);
      if (!res.ok) {
        throw new Error("Failed to load labels");
      }
      const nextLabels = payload.labels
        .map((item) => item.name.trim())
        .filter((value) => value.length > 0);
      setLabelOptions(nextLabels);
    } catch {
      setLabelOptions([]);
    }
  }, []);

  useEffect(() => {
    loadSettings();
    loadLabels();
  }, [loadLabels, loadSettings]);

  const saveSettings = async () => {
    try {
      setSaving(true);
      setError(null);
      const thresholds = warnPriorityThresholds
        .split(",")
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isFinite(value));
      const res = await fetch("/api/admin/dashboard/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled,
          fireLabel,
          warnPriorityThresholds: thresholds,
          warnDueWithinDays: Number(warnDueWithinDays),
          warnDeadlineWithinDays: Number(warnDeadlineWithinDays)
        })
      });
      const payload = await readJson<DashboardSettingsResponse>(res);
      if (!res.ok) {
        throw new Error("Failed to save dashboard settings");
      }
      setEnabled(payload.settings.enabled);
      setFireLabel(payload.settings.fireLabel);
      setWarnPriorityThresholds(payload.settings.warnPriorityThresholds.join(","));
      setWarnDueWithinDays(String(payload.settings.warnDueWithinDays));
      setWarnDeadlineWithinDays(String(payload.settings.warnDeadlineWithinDays));
      setConfigPath(payload.settings.configPath ?? "");
      onAfterMutation();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save dashboard settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section id="dashboard-settings" className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Dashboard Settings</h2>
          <InfoTip label="About dashboard settings" content={DASHBOARD_SETTINGS_HELP} />
        </div>
        {configPath ? <span className="pill pill-neutral">{configPath}</span> : null}
      </header>
      {loading ? (
        <div className="skeleton" style={{ minHeight: 180 }} />
      ) : (
        <div className="stack">
          <label className="field">
            <span className="fieldLabel">Urgency monitor enabled</span>
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          </label>
          <label className="field">
            <span className="fieldLabel">Fire label</span>
            <select className="textInput" value={fireLabel} onChange={(event) => setFireLabel(event.target.value)}>
              {fireLabel && !labelOptions.includes(fireLabel) ? (
                <option value={fireLabel}>{fireLabel}</option>
              ) : null}
              {labelOptions.map((labelName) => (
                <option key={labelName} value={labelName}>
                  {labelName}
                </option>
              ))}
            </select>
          </label>
          <div className="grid2">
            <label className="field">
              <span className="fieldLabel">Warn priorities</span>
              <input
                className="textInput"
                value={warnPriorityThresholds}
                onChange={(event) => setWarnPriorityThresholds(event.target.value)}
              />
            </label>
            <label className="field">
              <span className="fieldLabel">Due within days</span>
              <input
                className="textInput"
                type="number"
                min="0"
                value={warnDueWithinDays}
                onChange={(event) => setWarnDueWithinDays(event.target.value)}
              />
            </label>
          </div>
          <label className="field">
            <span className="fieldLabel">Deadline within days</span>
            <input
              className="textInput"
              type="number"
              min="0"
              value={warnDeadlineWithinDays}
              onChange={(event) => setWarnDeadlineWithinDays(event.target.value)}
            />
          </label>
          <div className="adminRowRight">
            <button className="button buttonSmall" type="button" onClick={saveSettings} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
          {error ? <p className="pill pill-warn">{error}</p> : null}
        </div>
      )}
    </section>
  );
}
