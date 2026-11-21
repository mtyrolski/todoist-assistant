export type PlotEventSetting = { date: string; label: string; color: string };
export type DashboardSettings = {
  enabled: boolean;
  dangerOnFireLabel: boolean;
  warnOnPriority: boolean;
  warnOnDue: boolean;
  warnOnDeadline: boolean;
  fireLabel: string;
  fireLabels: string[];
  warnPriorityThresholds: number[];
  warnPriorityMinCount: number;
  warnDueWithinDays: number;
  warnDueMinCount: number;
  warnDeadlineWithinDays: number;
  warnDeadlineMinCount: number;
  plotEvents: PlotEventSetting[];
  configPath?: string;
};
export const NUMBER_FIELDS = [
  { key: "warnPriorityMinCount", label: "Minimum priority matches", min: 1 },
  { key: "warnDueWithinDays", label: "Due within days", min: 0 },
  { key: "warnDueMinCount", label: "Minimum due matches", min: 1 },
  { key: "warnDeadlineWithinDays", label: "Deadline within days", min: 0 },
  { key: "warnDeadlineMinCount", label: "Minimum deadline matches", min: 1 }
] as const;
export type NumberKey = typeof NUMBER_FIELDS[number]["key"];
export type SettingsDraft = Omit<DashboardSettings, NumberKey> & Record<NumberKey, string>;

export function settingsDraft(settings: DashboardSettings): SettingsDraft {
  return {
    ...settings,
    fireLabels: settings.fireLabels ?? [],
    plotEvents: settings.plotEvents ?? [],
    warnPriorityMinCount: String(settings.warnPriorityMinCount),
    warnDueWithinDays: String(settings.warnDueWithinDays),
    warnDueMinCount: String(settings.warnDueMinCount),
    warnDeadlineWithinDays: String(settings.warnDeadlineWithinDays),
    warnDeadlineMinCount: String(settings.warnDeadlineMinCount)
  };
}

export function settingsPayload(draft: SettingsDraft): Record<string, unknown> {
  const { configPath: _configPath, ...settings } = draft;
  const payload: Record<string, unknown> = { ...settings, fireLabel: draft.fireLabels[0] ?? "" };
  for (const { key, label, min } of NUMBER_FIELDS) {
    const raw = draft[key].trim();
    const value = Number(raw);
    if (!/^\d+$/.test(raw) || !Number.isSafeInteger(value) || value < min || value > 100000) {
      throw new Error(`${label}: enter a whole number from ${min} to 100000.`);
    }
    payload[key] = value;
  }
  payload.plotEvents = draft.plotEvents
    .map((item) => ({ date: item.date.trim(), label: item.label.trim(), color: item.color || "#ff6b7a" }))
    .filter((item) => item.date || item.label);
  for (const item of payload.plotEvents as PlotEventSetting[]) {
    if (!item.date || !item.label) throw new Error("Each plot event needs both a date and a label.");
  }
  return payload;
}
