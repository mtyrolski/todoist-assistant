"use client";

import { useCallback, useEffect, useState } from "react";
import { InfoTip } from "./InfoTip";

type DashboardSettingsResponse = {
  settings: {
    enabled: boolean;
    fireLabel: string;
    fireLabels: string[];
    warnPriorityThresholds: number[];
    warnPriorityMinCount: number;
    warnDueWithinDays: number;
    warnDueMinCount: number;
    warnDeadlineWithinDays: number;
    warnDeadlineMinCount: number;
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

const PRIORITY_OPTIONS = [
  { value: 4, label: "P1" },
  { value: 3, label: "P2" },
  { value: 2, label: "P3" },
  { value: 1, label: "P4" }
];

async function readJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

export function DashboardSettings({ onAfterMutation }: { onAfterMutation: () => void }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [configPath, setConfigPath] = useState<string>("");
  const [enabled, setEnabled] = useState(true);
  const [fireLabels, setFireLabels] = useState<string[]>(["fire"]);
  const [labelOptions, setLabelOptions] = useState<string[]>([]);
  const [warnPriorityThresholds, setWarnPriorityThresholds] = useState<number[]>([4, 3]);
  const [warnPriorityMinCount, setWarnPriorityMinCount] = useState("1");
  const [warnDueWithinDays, setWarnDueWithinDays] = useState("0");
  const [warnDueMinCount, setWarnDueMinCount] = useState("1");
  const [warnDeadlineWithinDays, setWarnDeadlineWithinDays] = useState("0");
  const [warnDeadlineMinCount, setWarnDeadlineMinCount] = useState("1");

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setNotice(null);
      const res = await fetch("/api/admin/dashboard/settings");
      const payload = await readJson<DashboardSettingsResponse>(res);
      if (!res.ok) {
        throw new Error("Failed to load dashboard settings");
      }
      setEnabled(payload.settings.enabled);
      setFireLabels(
        payload.settings.fireLabels.length ? payload.settings.fireLabels : [payload.settings.fireLabel].filter(Boolean)
      );
      setWarnPriorityThresholds(payload.settings.warnPriorityThresholds);
      setWarnPriorityMinCount(String(payload.settings.warnPriorityMinCount));
      setWarnDueWithinDays(String(payload.settings.warnDueWithinDays));
      setWarnDueMinCount(String(payload.settings.warnDueMinCount));
      setWarnDeadlineWithinDays(String(payload.settings.warnDeadlineWithinDays));
      setWarnDeadlineMinCount(String(payload.settings.warnDeadlineMinCount));
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
      setNotice(null);
      const res = await fetch("/api/admin/dashboard/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled,
          fireLabels,
          fireLabel: fireLabels[0] ?? "",
          warnPriorityThresholds,
          warnPriorityMinCount: Number(warnPriorityMinCount),
          warnDueWithinDays: Number(warnDueWithinDays),
          warnDueMinCount: Number(warnDueMinCount),
          warnDeadlineWithinDays: Number(warnDeadlineWithinDays),
          warnDeadlineMinCount: Number(warnDeadlineMinCount)
        })
      });
      const payload = await readJson<DashboardSettingsResponse>(res);
      if (!res.ok) {
        throw new Error("Failed to save dashboard settings");
      }
      setEnabled(payload.settings.enabled);
      setFireLabels(payload.settings.fireLabels.length ? payload.settings.fireLabels : [payload.settings.fireLabel].filter(Boolean));
      setWarnPriorityThresholds(payload.settings.warnPriorityThresholds);
      setWarnPriorityMinCount(String(payload.settings.warnPriorityMinCount));
      setWarnDueWithinDays(String(payload.settings.warnDueWithinDays));
      setWarnDueMinCount(String(payload.settings.warnDueMinCount));
      setWarnDeadlineWithinDays(String(payload.settings.warnDeadlineWithinDays));
      setWarnDeadlineMinCount(String(payload.settings.warnDeadlineMinCount));
      setConfigPath(payload.settings.configPath ?? "");
      setNotice("Dashboard urgency settings updated.");
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
            <span className="fieldLabel">Fire labels</span>
            <select
              className="textInput multiSelectInput"
              multiple
              value={fireLabels}
              onChange={(event) =>
                setFireLabels(Array.from(event.target.selectedOptions, (option) => option.value))
              }
            >
              {fireLabels
                .filter((labelName) => !labelOptions.includes(labelName))
                .map((labelName) => (
                  <option key={labelName} value={labelName}>
                    {labelName}
                  </option>
                ))}
              {labelOptions.map((labelName) => (
                <option key={labelName} value={labelName}>
                  {labelName}
                </option>
              ))}
            </select>
            <p className="muted tiny">Hold Ctrl/Cmd to pick multiple labels.</p>
          </label>
          <div className="grid2">
            <label className="field">
              <span className="fieldLabel">Warn priorities</span>
              <select
                className="textInput multiSelectInput"
                multiple
                value={warnPriorityThresholds.map(String)}
                onChange={(event) =>
                  setWarnPriorityThresholds(
                    Array.from(event.target.selectedOptions, (option) => Number(option.value))
                  )
                }
              >
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option.value} value={String(option.value)}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="muted tiny">Explicit Todoist priorities: P1, P2, P3, P4.</p>
            </label>
            <label className="field">
              <span className="fieldLabel">Minimum priority matches</span>
              <input
                className="textInput"
                type="number"
                min="1"
                value={warnPriorityMinCount}
                onChange={(event) => setWarnPriorityMinCount(event.target.value)}
              />
            </label>
          </div>
          <div className="grid2">
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
            <label className="field">
              <span className="fieldLabel">Minimum due matches</span>
              <input
                className="textInput"
                type="number"
                min="1"
                value={warnDueMinCount}
                onChange={(event) => setWarnDueMinCount(event.target.value)}
              />
            </label>
          </div>
          <div className="grid2">
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
            <label className="field">
              <span className="fieldLabel">Minimum deadline matches</span>
              <input
                className="textInput"
                type="number"
                min="1"
                value={warnDeadlineMinCount}
                onChange={(event) => setWarnDeadlineMinCount(event.target.value)}
              />
            </label>
          </div>
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
