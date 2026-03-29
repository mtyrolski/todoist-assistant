"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type LlmOption = {
  id: string;
  label: string;
  available?: boolean;
  selected?: boolean;
};

type LlmSettingsStatus = {
  backend: string;
  backendLabel: string;
  device: string;
  deviceLabel: string;
  localModelId: string;
  localModelOptions: LlmOption[];
  availableBackends: LlmOption[];
  availableDevices: LlmOption[];
  openai: {
    configured: boolean;
    keyName?: string | null;
    model?: string | null;
    modelOptions: LlmOption[];
  };
  triton: {
    configured: boolean;
    healthy?: boolean;
    baseUrl?: string;
    modelName?: string;
    modelId?: string;
    modelOptions: LlmOption[];
  };
  envPath?: string;
  enabled?: boolean;
  loading?: boolean;
  reloadedRequired?: boolean;
};

export function LlmRuntimeSettings({
  onAfterMutation,
  compact = false
}: {
  onAfterMutation?: () => void;
  compact?: boolean;
}) {
  const [llmStatus, setLlmStatus] = useState<LlmSettingsStatus | null>(null);
  const [llmBackendDraft, setLlmBackendDraft] = useState("transformers_local");
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
      setLlmBackendDraft(payload.backend);
      setLlmDeviceDraft(payload.device);
      setLlmModelDraft(
        payload.backend === "openai"
          ? payload.openai.model ?? ""
          : payload.backend === "triton_local"
            ? payload.triton.modelId ?? ""
            : payload.localModelId
      );
    } catch (e) {
      setLlmStatus(null);
      setLlmError(e instanceof Error ? e.message : "Failed to load LLM settings");
    }
  }, []);

  useEffect(() => {
    loadLlmSettings();
  }, [loadLlmSettings]);

  const selectedLlmBackend = llmBackendDraft || llmStatus?.backend || "transformers_local";
  const llmUsesRemoteDevice = selectedLlmBackend === "openai" || selectedLlmBackend === "triton_local";
  const modelOptions = useMemo(() => {
    if (!llmStatus) return [];
    if (selectedLlmBackend === "openai") return llmStatus.openai.modelOptions;
    if (selectedLlmBackend === "triton_local") return llmStatus.triton.modelOptions;
    return llmStatus.localModelOptions;
  }, [llmStatus, selectedLlmBackend]);

  useEffect(() => {
    if (!llmStatus) return;
    setLlmModelDraft(
      selectedLlmBackend === "openai"
        ? llmStatus.openai.model ?? ""
        : selectedLlmBackend === "triton_local"
          ? llmStatus.triton.modelId ?? ""
          : llmStatus.localModelId
    );
  }, [llmStatus, selectedLlmBackend]);

  const llmSettingsChanged = useMemo(() => {
    if (!llmStatus) return false;
    const currentModel =
      llmBackendDraft === "openai"
        ? llmStatus.openai.model ?? ""
        : llmBackendDraft === "triton_local"
          ? llmStatus.triton.modelId ?? ""
          : llmStatus.localModelId;
    return (
      llmBackendDraft !== llmStatus.backend ||
      llmDeviceDraft !== llmStatus.device ||
      llmModelDraft !== currentModel
    );
  }, [llmBackendDraft, llmDeviceDraft, llmModelDraft, llmStatus]);

  const currentSummary = useMemo(() => {
    if (!llmStatus) return "LLM settings unavailable";
    if (llmStatus.backend === "openai") return `OpenAI • ${llmStatus.openai.model ?? "unknown model"}`;
    if (llmStatus.backend === "triton_local") return `Triton • ${llmStatus.triton.modelId ?? "unknown model"}`;
    return `Local Transformers • ${llmStatus.localModelId}`;
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
          backend: llmBackendDraft,
          device: llmDeviceDraft,
          localModelId: llmBackendDraft === "transformers_local" ? llmModelDraft : llmStatus?.localModelId,
          openaiModel: llmBackendDraft === "openai" ? llmModelDraft : llmStatus?.openai.model,
          tritonModelId: llmBackendDraft === "triton_local" ? llmModelDraft : llmStatus?.triton.modelId
        })
      });
      const payload = (await res.json()) as LlmSettingsStatus & { detail?: string };
      if (!res.ok) {
        throw new Error(payload.detail ?? "Failed to save LLM settings");
      }
      setLlmStatus(payload);
      setLlmBackendDraft(payload.backend);
      setLlmDeviceDraft(payload.device);
      setLlmModelDraft(
        payload.backend === "openai"
          ? payload.openai.model ?? ""
          : payload.backend === "triton_local"
            ? payload.triton.modelId ?? ""
            : payload.localModelId
      );
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
            Pick the backend and actual model used under the hood. This controls the dashboard chat runtime and related AI flows.
          </p>
        </div>
      </header>
      <div className="stack">
        <div className="adminRow">
          <span className="pill pill-beta">{currentSummary}</span>
          {llmStatus?.envPath ? <span className="muted tiny">{llmStatus.envPath}</span> : null}
        </div>
        <div className="grid2">
          <div className="control">
            <label className="muted tiny" htmlFor={compact ? "llm-backend-compact" : "llm-backend-prominent"}>
              Backend
            </label>
            <select
              id={compact ? "llm-backend-compact" : "llm-backend-prominent"}
              className="dateInput"
              value={llmBackendDraft}
              onChange={(e) => setLlmBackendDraft(e.target.value)}
              disabled={llmSaving || !llmStatus}
            >
              {(llmStatus?.availableBackends ?? []).map((option) => (
                <option key={option.id} value={option.id} disabled={option.available === false}>
                  {option.label}{option.available === false ? " (unavailable)" : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="control">
            <label className="muted tiny" htmlFor={compact ? "llm-model-compact" : "llm-model-prominent"}>
              Model
            </label>
            <select
              id={compact ? "llm-model-compact" : "llm-model-prominent"}
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
          <label className="muted tiny" htmlFor={compact ? "llm-device-compact" : "llm-device-prominent"}>
            Device {llmUsesRemoteDevice ? "(managed by backend)" : "(local runtime)"}
          </label>
          <select
            id={compact ? "llm-device-compact" : "llm-device-prominent"}
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
            {selectedLlmBackend === "openai"
              ? `OpenAI key: ${llmStatus?.openai.keyName ?? "default"}`
              : selectedLlmBackend === "triton_local"
                ? `Triton endpoint: ${llmStatus?.triton.baseUrl ?? "unknown"}`
                : `Local device: ${llmStatus?.deviceLabel ?? llmDeviceDraft}`}
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
