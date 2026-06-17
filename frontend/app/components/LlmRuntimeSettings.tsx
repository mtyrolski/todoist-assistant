"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type LlmOption = {
  id: string;
  label: string;
  available?: boolean;
  selected?: boolean;
};

type LlmUsageCounter = {
  backend?: string | null;
  modelId?: string | null;
  inferenceCount: number;
  chatCount: number;
  structuredCount: number;
  repairCount: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  lastUsedAt?: string | null;
};

type LlmUsageSnapshot = {
  totals: LlmUsageCounter;
  current: LlmUsageCounter;
  updatedAt?: string | null;
  lastRequest?: {
    at?: string | null;
    backend?: string | null;
    modelId?: string | null;
    operation?: string | null;
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
  } | null;
};

type LlmSettingsStatus = {
  backend: string;
  backendLabel: string;
  lockedBackend?: string | null;
  device: string;
  deviceLabel: string;
  availableBackends: LlmOption[];
  availableDevices: LlmOption[];
  codex: {
    model?: string | null;
    modelOptions: LlmOption[];
  };
  usage?: LlmUsageSnapshot;
  envPath?: string;
  enabled?: boolean;
  loading?: boolean;
  reloadedRequired?: boolean;
};

const DISABLED_BACKEND_ID = "disabled";
const CODEX_BACKEND_ID = "codex";
const AVAILABLE_BACKEND_IDS = new Set([DISABLED_BACKEND_ID, CODEX_BACKEND_ID]);

function normalizeBackendId(backendId?: string | null): string {
  return backendId && AVAILABLE_BACKEND_IDS.has(backendId) ? backendId : DISABLED_BACKEND_ID;
}

function visibleBackendOptions(options: LlmOption[]): LlmOption[] {
  return options.filter((option) => AVAILABLE_BACKEND_IDS.has(option.id));
}

function formatMetricCount(value?: number | null): string {
  const normalized = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return new Intl.NumberFormat("en-US").format(normalized);
}

function formatUsageTimestamp(value?: string | null): string {
  if (!value) return "Never";
  return value.replace("T", " ");
}

export function LlmRuntimeSettings({
  onAfterMutation,
  compact = false
}: {
  onAfterMutation?: () => void;
  compact?: boolean;
}) {
  const [llmStatus, setLlmStatus] = useState<LlmSettingsStatus | null>(null);
  const [llmBackendDraft, setLlmBackendDraft] = useState("disabled");
  const [llmDeviceDraft, setLlmDeviceDraft] = useState("cpu");
  const [llmModelDraft, setLlmModelDraft] = useState("");
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmNotice, setLlmNotice] = useState<string | null>(null);

  const loadLlmSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/llm_chat/settings");
      const payload = (await res.json()) as LlmSettingsStatus & { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to load LLM settings");
      }
      setLlmStatus(payload);
      const normalizedBackend = normalizeBackendId(payload.backend);
      setLlmBackendDraft(normalizedBackend);
      setLlmDeviceDraft(payload.device);
      setLlmModelDraft(normalizedBackend === CODEX_BACKEND_ID ? payload.codex.model ?? "" : "");
    } catch (e) {
      setLlmStatus(null);
      setLlmError(e instanceof Error ? e.message : "Failed to load LLM settings");
    }
  }, []);

  useEffect(() => {
    loadLlmSettings();
  }, [loadLlmSettings]);

  const selectedLlmBackend = normalizeBackendId(llmBackendDraft || llmStatus?.backend);
  const llmUsesRemoteDevice = selectedLlmBackend === CODEX_BACKEND_ID;
  const modelOptions = useMemo(() => {
    if (!llmStatus) return [];
    if (selectedLlmBackend === CODEX_BACKEND_ID) return llmStatus.codex.modelOptions;
    return [];
  }, [llmStatus, selectedLlmBackend]);

  useEffect(() => {
    if (!llmStatus) return;
    setLlmModelDraft(selectedLlmBackend === CODEX_BACKEND_ID ? llmStatus.codex.model ?? "" : "");
  }, [llmStatus, selectedLlmBackend]);

  const llmSettingsChanged = useMemo(() => {
    if (!llmStatus) return false;
    const normalizedStatusBackend = normalizeBackendId(llmStatus.backend);
    const normalizedDraftBackend = normalizeBackendId(llmBackendDraft);
    const currentModel = normalizedDraftBackend === CODEX_BACKEND_ID ? llmStatus.codex.model ?? "" : "";
    return (
      normalizedDraftBackend !== normalizedStatusBackend ||
      llmDeviceDraft !== llmStatus.device ||
      llmModelDraft !== currentModel
    );
  }, [llmBackendDraft, llmDeviceDraft, llmModelDraft, llmStatus]);

  const currentSummary = useMemo(() => {
    if (!llmStatus) return "LLM settings unavailable";
    const backend = normalizeBackendId(llmStatus.backend);
    if (backend === DISABLED_BACKEND_ID) return "AI disabled";
    if (backend === CODEX_BACKEND_ID) return `Codex • ${llmStatus.codex.model ?? "unknown model"}`;
    return backend;
  }, [llmStatus]);

  const saveLlmSettings = async () => {
    try {
      setLlmSaving(true);
      setLlmError(null);
      setLlmNotice(null);
      const res = await fetch("/api/llm_chat/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          backend: normalizeBackendId(llmBackendDraft),
          device: llmDeviceDraft,
          codexModel: normalizeBackendId(llmBackendDraft) === CODEX_BACKEND_ID ? llmModelDraft : llmStatus?.codex.model
        })
      });
      const payload = (await res.json()) as LlmSettingsStatus & { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to save LLM settings");
      }
      setLlmStatus(payload);
      const normalizedBackend = normalizeBackendId(payload.backend);
      setLlmBackendDraft(normalizedBackend);
      setLlmDeviceDraft(payload.device);
      setLlmModelDraft(normalizedBackend === CODEX_BACKEND_ID ? payload.codex.model ?? "" : "");
      setLlmNotice(payload.reloadedRequired ? "LLM updated. Re-enable chat to load the new model." : "LLM updated.");
      onAfterMutation?.();
    } catch (e) {
      setLlmError(e instanceof Error ? e.message : "Failed to save LLM settings");
    } finally {
      setLlmSaving(false);
    }
  };

  return (
    <section className={`card${compact ? " cardInner" : ""}`}>
      <header className="cardHeader">
        <div>
          <h2>{compact ? "Underlying LLM" : "Underlying LLM"}</h2>
          <p className="muted tiny" style={{ margin: "6px 0 0" }}>
            Pick Codex/langgraph-codex or disable AI. This controls dashboard chat, task ingest, and the LLM task
            rollout automation.
          </p>
        </div>
      </header>
      <div className="stack">
        <div className="adminRow">
          <span className="pill pill-beta">{currentSummary}</span>
          {llmStatus?.envPath ? <span className="muted tiny">{llmStatus.envPath}</span> : null}
        </div>
        <div className="chatSection">
          <div className="chatSectionHeader">
            <div className="chatSectionHeaderMain">
              <p className="rowTitle">AI usage</p>
              <p className="muted tiny">
                Local cumulative stats across dashboard chat, task ingest, and AI breakdown work.
              </p>
            </div>
            <div className="chatSectionMeta">
              <span className="pill pill-neutral">
                {formatMetricCount(llmStatus?.usage?.totals.inferenceCount)} inferences
              </span>
              <span className="muted tiny">
                Updated {formatUsageTimestamp(llmStatus?.usage?.updatedAt)}
              </span>
            </div>
          </div>
          <div className="pillRow" style={{ marginTop: 0 }}>
            <span className="pill pill-good">
              Input {formatMetricCount(llmStatus?.usage?.totals.inputTokens)} tokens
            </span>
            <span className="pill pill-good">
              Output {formatMetricCount(llmStatus?.usage?.totals.outputTokens)} tokens
            </span>
            <span className="pill pill-neutral">
              Total {formatMetricCount(llmStatus?.usage?.totals.totalTokens)} tokens
            </span>
            <span className="pill pill-neutral">
              Structured {formatMetricCount(llmStatus?.usage?.totals.structuredCount)}
            </span>
            <span className="pill pill-neutral">
              Repairs {formatMetricCount(llmStatus?.usage?.totals.repairCount)}
            </span>
          </div>
          <div className="grid2" style={{ marginTop: 12 }}>
            <div className="control">
              <label className="muted tiny">Selected model usage</label>
              <p className="muted tiny" style={{ margin: "4px 0 0" }}>
                {(llmStatus?.usage?.current.backend ?? selectedLlmBackend) || "unknown"} •{" "}
                {llmStatus?.usage?.current.modelId || llmModelDraft || "unknown model"}
              </p>
              <div className="pillRow">
                <span className="pill pill-neutral">
                  {formatMetricCount(llmStatus?.usage?.current.inferenceCount)} inferences
                </span>
                <span className="pill pill-neutral">
                  {formatMetricCount(llmStatus?.usage?.current.inputTokens)} in
                </span>
                <span className="pill pill-neutral">
                  {formatMetricCount(llmStatus?.usage?.current.outputTokens)} out
                </span>
              </div>
              <p className="muted tiny" style={{ margin: "6px 0 0" }}>
                Last used {formatUsageTimestamp(llmStatus?.usage?.current.lastUsedAt)}
              </p>
            </div>
            <div className="control">
              <label className="muted tiny">Last recorded request</label>
              {llmStatus?.usage?.lastRequest ? (
                <>
                  <p className="muted tiny" style={{ margin: "4px 0 0" }}>
                    {llmStatus.usage.lastRequest.backend ?? "unknown"} •{" "}
                    {llmStatus.usage.lastRequest.modelId ?? "unknown model"} •{" "}
                    {llmStatus.usage.lastRequest.operation ?? "chat"}
                  </p>
                  <div className="pillRow">
                    <span className="pill pill-neutral">
                      {formatMetricCount(llmStatus.usage.lastRequest.inputTokens)} in
                    </span>
                    <span className="pill pill-neutral">
                      {formatMetricCount(llmStatus.usage.lastRequest.outputTokens)} out
                    </span>
                    <span className="pill pill-neutral">
                      {formatMetricCount(llmStatus.usage.lastRequest.totalTokens)} total
                    </span>
                  </div>
                  <p className="muted tiny" style={{ margin: "6px 0 0" }}>
                    {formatUsageTimestamp(llmStatus.usage.lastRequest.at)}
                  </p>
                </>
              ) : (
                <p className="muted tiny" style={{ margin: "4px 0 0" }}>
                  No AI usage recorded yet on this machine.
                </p>
              )}
            </div>
          </div>
        </div>
        <div className="grid2">
          <div className="control">
            <label className="muted tiny" htmlFor={compact ? "ai-backend-compact" : "ai-backend-prominent"}>
              Backend
            </label>
            <select
              id={compact ? "ai-backend-compact" : "ai-backend-prominent"}
              className="dateInput"
              value={llmBackendDraft}
              onChange={(e) => setLlmBackendDraft(e.target.value)}
              disabled={llmSaving || !llmStatus || visibleBackendOptions(llmStatus.availableBackends ?? []).length <= 1}
            >
              {visibleBackendOptions(llmStatus?.availableBackends ?? []).map((option) => (
                <option key={option.id} value={option.id} disabled={option.available === false}>
                  {option.label}
                  {option.available === false ? " (unavailable)" : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="control">
            <label className="muted tiny" htmlFor={compact ? "ai-model-compact" : "ai-model-prominent"}>
              Model
            </label>
            <select
              id={compact ? "ai-model-compact" : "ai-model-prominent"}
              className="dateInput"
              value={llmModelDraft}
              onChange={(e) => setLlmModelDraft(e.target.value)}
              disabled={llmSaving || !llmStatus}
            >
              {modelOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="control">
          <label className="muted tiny" htmlFor={compact ? "ai-device-compact" : "ai-device-prominent"}>
            Device {llmUsesRemoteDevice ? "(managed by backend)" : "(local runtime)"}
          </label>
          <select
            id={compact ? "ai-device-compact" : "ai-device-prominent"}
            className="dateInput"
            value={llmDeviceDraft}
            onChange={(e) => setLlmDeviceDraft(e.target.value)}
            disabled={llmSaving || !llmStatus || llmUsesRemoteDevice}
          >
            {(llmStatus?.availableDevices ?? []).map((option) => (
              <option key={option.id} value={option.id} disabled={option.available === false}>
                {option.label}{option.available === false ? " (unavailable)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="adminRow">
          <span className="muted tiny">
            {selectedLlmBackend === CODEX_BACKEND_ID
              ? `Codex model: ${llmStatus?.codex.model ?? "unknown"}`
              : "AI functions disabled"}
          </span>
          <div className="adminRowRight">
            <button className="button buttonSmall" type="button" onClick={saveLlmSettings} disabled={llmSaving || !llmSettingsChanged}>
              {llmSaving ? "Saving…" : "Apply"}
            </button>
            <button className="button buttonSmall" type="button" onClick={loadLlmSettings} disabled={llmSaving}>
              Refresh
            </button>
          </div>
        </div>
        {llmError ? <p className="pill pill-warn">{llmError}</p> : null}
        {llmNotice ? <p className="pill">{llmNotice}</p> : null}
      </div>
    </section>
  );
}
