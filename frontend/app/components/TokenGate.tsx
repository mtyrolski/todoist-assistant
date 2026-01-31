"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { ProjectAdjustmentsBoard } from "./ProjectAdjustmentsBoard";

const SETUP_COMPLETE_KEY = "todoist-assistant.setupComplete";

type ApiTokenStatus = {
  configured: boolean;
  masked: string;
  envPath?: string;
};

type TokenValidation = {
  configured: boolean;
  valid: boolean;
  detail?: string;
  masked?: string;
  labelsCount?: number | null;
};

type TokenGateState = {
  setupActive: boolean;
  setupComplete: boolean;
  tokenReady: boolean;
};

async function readJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error("Invalid JSON response");
  }
}

export function TokenGate({
  children
}: {
  children: ReactNode | ((state: TokenGateState) => ReactNode);
}) {
  const [status, setStatus] = useState<ApiTokenStatus | null>(null);
  const [validation, setValidation] = useState<TokenValidation | null>(null);
  const [checking, setChecking] = useState(true);
  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenNotice, setTokenNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [setupComplete, setSetupComplete] = useState(false);
  const [currentStep, setCurrentStep] = useState<1 | 2>(1);

  const refreshStatus = async () => {
    setChecking(true);
    setTokenError(null);
    try {
      const res = await fetch("/api/admin/api_token");
      const payload = await readJson<ApiTokenStatus>(res);
      if (!res.ok) throw new Error("Failed to load token status");
      setStatus(payload);
      if (payload.configured) {
        const vres = await fetch("/api/admin/api_token/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" }
        });
        const vpayload = await readJson<TokenValidation>(vres);
        if (!vres.ok) throw new Error(vpayload.detail ?? "Token validation failed");
        setValidation(vpayload);
        if (!vpayload.valid) {
          setTokenError(vpayload.detail ?? "API token validation failed.");
        }
      } else {
        setValidation({ configured: false, valid: false });
      }
    } catch (e) {
      setValidation({ configured: false, valid: false });
      setTokenError(e instanceof Error ? e.message : "Failed to check API token.");
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    refreshStatus();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(SETUP_COMPLETE_KEY) === "1";
    setSetupComplete(stored);
  }, []);

  const saveToken = async () => {
    if (!tokenDraft.trim()) {
      setTokenError("Paste your Todoist API token.");
      return;
    }
    try {
      setSaving(true);
      setTokenError(null);
      setTokenNotice(null);
      const res = await fetch("/api/admin/api_token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: tokenDraft.trim(), validate: true })
      });
      const payload = await readJson<ApiTokenStatus & { detail?: string; labelsCount?: number | null }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to save token");
      setStatus(payload);
      setValidation({ configured: true, valid: true, labelsCount: payload.labelsCount ?? null });
      setTokenDraft("");
      setTokenNotice("API token saved and validated.");
      if (typeof window !== "undefined") {
        window.localStorage.removeItem("todoist-assistant.firstSyncComplete");
      }
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "Failed to save token");
    } finally {
      setSaving(false);
    }
  };

  const validateExisting = async () => {
    try {
      setSaving(true);
      setTokenError(null);
      setTokenNotice(null);
      const res = await fetch("/api/admin/api_token/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const payload = await readJson<TokenValidation & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Token validation failed");
      setValidation(payload);
      if (!payload.valid) {
        throw new Error(payload.detail ?? "API token validation failed.");
      }
      setTokenNotice("API token validated.");
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "Token validation failed");
    } finally {
      setSaving(false);
    }
  };

  const ready = Boolean(validation?.valid);
  const setupActive = !setupComplete || !ready;

  useEffect(() => {
    if (!ready) {
      setCurrentStep(1);
      return;
    }
    if (!setupComplete) {
      setCurrentStep(2);
    }
  }, [ready, setupComplete]);

  const finishSetup = () => {
    setSetupComplete(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SETUP_COMPLETE_KEY, "1");
    }
  };

  const connectionSummary = useMemo(() => {
    if (ready) {
      if (typeof validation?.labelsCount === "number") {
        return `Connected • ${validation.labelsCount} labels found`;
      }
      return "Connected • token validated";
    }
    if (checking) return "Checking connection…";
    if (status?.configured) return "Token found • needs validation";
    return "Token required to continue";
  }, [ready, validation?.labelsCount, checking, status?.configured]);

  const renderedChildren =
    typeof children === "function"
      ? (children as (state: TokenGateState) => ReactNode)({
          setupActive,
          setupComplete,
          tokenReady: ready
        })
      : children;

  return (
    <>
      {renderedChildren}
      {setupActive ? (
        <div className="setupOverlay" role="dialog" aria-modal="true" aria-live="polite">
          <div className="setupPanel">
            <header className="setupHeader">
              <div>
                <p className="eyebrow">Quick setup</p>
                <h2>Connect Todoist and confirm project mapping</h2>
                <p className="muted" style={{ margin: "6px 0 0" }}>
                  We&apos;ll validate your API token and let you confirm project adjustments. You can always change these
                  later in the Control Panel.
                </p>
              </div>
              <div className="setupStatusRow">
                <span className={`pill ${ready ? "pill-good" : status?.configured ? "pill-warn" : "pill-neutral"}`}>
                  {ready ? "Token validated" : status?.configured ? "Token found" : "Token required"}
                </span>
                {status?.masked ? <span className="pill">{status.masked}</span> : null}
                {typeof validation?.labelsCount === "number" ? (
                  <span className="pill">Labels: {validation.labelsCount}</span>
                ) : null}
              </div>
              <p className="muted tiny" style={{ margin: 0 }}>
                {connectionSummary}
              </p>
            </header>

            {currentStep === 1 ? (
              <section className="card setupStep">
                <div className="setupStepHeader">
                  <span className="setupStepBadge">1</span>
                  <div>
                    <h3>Set your Todoist API token</h3>
                    <p className="muted tiny" style={{ margin: 0 }}>
                      Can be changed later in Control Panel → Settings.
                    </p>
                  </div>
                </div>
                <div className="control">
                  <label className="muted tiny" htmlFor="token-gate-input">
                    API token
                  </label>
                  <div className="tokenGateInputRow">
                    <input
                      id="token-gate-input"
                      className="textInput"
                      type={showToken ? "text" : "password"}
                      placeholder="Paste token here"
                      value={tokenDraft}
                      onChange={(e) => setTokenDraft(e.target.value)}
                      disabled={saving || checking}
                    />
                    <button
                      className="button buttonSmall buttonGhost"
                      type="button"
                      onClick={() => setShowToken((prev) => !prev)}
                      disabled={saving || checking}
                    >
                      {showToken ? "Hide" : "Show"}
                    </button>
                  </div>
                </div>
                <div className="tokenGateActions">
                  <button className="button buttonSmall" type="button" onClick={saveToken} disabled={saving || checking}>
                    {saving ? "Validating…" : "Validate & Save"}
                  </button>
                  {status?.configured ? (
                    <button
                      className="button buttonSmall buttonGhost"
                      type="button"
                      onClick={validateExisting}
                      disabled={saving || checking}
                    >
                      Re-check token
                    </button>
                  ) : null}
                  <button
                    className="button buttonSmall buttonGhost"
                    type="button"
                    onClick={refreshStatus}
                    disabled={saving || checking}
                  >
                    {checking ? "Checking…" : "Refresh"}
                  </button>
                  <button
                    className="button buttonSmall buttonGhost"
                    type="button"
                    onClick={() => setCurrentStep(2)}
                    disabled={!ready || saving || checking}
                  >
                    Continue
                  </button>
                </div>
                {tokenError ? <p className="pill pill-warn">{tokenError}</p> : null}
                {tokenNotice ? <p className="pill">{tokenNotice}</p> : null}
              </section>
            ) : (
              <section className="card setupStep">
                <div className="setupStepHeader">
                  <span className="setupStepBadge">2</span>
                  <div>
                    <h3>Project adjustments</h3>
                    <p className="muted tiny" style={{ margin: 0 }}>
                      Can be changed later in Control Panel → Project Adjustments.
                    </p>
                  </div>
                </div>
                <ProjectAdjustmentsBoard variant="embedded" showWhenEmpty onAfterSave={refreshStatus} />
                <div className="setupStepActions">
                  <button className="button buttonSmall buttonGhost" type="button" onClick={() => setCurrentStep(1)}>
                    Back
                  </button>
                  <button className="button buttonSmall" type="button" onClick={finishSetup}>
                    Finish setup
                  </button>
                </div>
              </section>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
