"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

type TokenStatus = {
  configured: boolean;
  masked?: string;
  labelsCount?: number | null;
  valid?: boolean;
  detail?: string;
};

type TokenGateState = { setupActive: boolean; tokenReady: boolean };

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error("Invalid API response");
  }
}

export function TokenGate({ children }: { children: ReactNode | ((state: TokenGateState) => ReactNode) }) {
  const [status, setStatus] = useState<TokenStatus | null>(null);
  const [ready, setReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tokenDraft, setTokenDraft] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = async () => {
    setChecking(true);
    setError(null);
    try {
      const response = await fetch("/api/admin/api_token");
      const payload = await readJson<TokenStatus>(response);
      if (!response.ok) throw new Error(payload.detail ?? "Failed to load token status");
      setStatus(payload);
      if (!payload.configured) {
        setReady(false);
        return;
      }
      const validationResponse = await fetch("/api/admin/api_token/validate", { method: "POST" });
      const validation = await readJson<TokenStatus>(validationResponse);
      if (!validationResponse.ok) throw new Error(validation.detail ?? "Token validation failed");
      setStatus((previous) => ({ ...previous, ...validation }));
      setReady(Boolean(validation.valid));
      if (!validation.valid) setError(validation.detail ?? "Token validation failed");
    } catch (cause) {
      setReady(false);
      setError(cause instanceof Error ? cause.message : "Failed to check API token");
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    void refreshStatus();
  }, []);

  const saveToken = async () => {
    if (!tokenDraft.trim()) {
      setError("Paste your Todoist API token.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/admin/api_token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: tokenDraft.trim(), validate: true })
      });
      const payload = await readJson<TokenStatus>(response);
      if (!response.ok) throw new Error(payload.detail ?? "Failed to save token");
      setStatus(payload);
      setTokenDraft("");
      setReady(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to save token");
    } finally {
      setSaving(false);
    }
  };

  const setupActive = !ready;
  const renderedChildren = typeof children === "function" ? children({ setupActive, tokenReady: ready }) : children;

  return (
    <>
      {renderedChildren}
      {setupActive ? (
        <div className="setupOverlay" role="dialog" aria-modal="true" aria-live="polite">
          <div className="setupPanel">
            <header className="setupHeader">
              <p className="eyebrow">Quick setup</p>
              <h2>Connect Todoist</h2>
              <p className="muted">Validate your API token to load local activity and plots.</p>
              {status?.masked ? <span className="pill">{status.masked}</span> : null}
            </header>
            <section className="card setupStep">
              <div className="control">
                <label className="muted tiny" htmlFor="token-gate-input">API token</label>
                <div className="tokenGateInputRow">
                  <input
                    id="token-gate-input"
                    className="textInput"
                    type={showToken ? "text" : "password"}
                    placeholder="Paste token here"
                    value={tokenDraft}
                    onChange={(event) => setTokenDraft(event.target.value)}
                    disabled={saving || checking}
                  />
                  <button className="button buttonSmall buttonGhost" type="button" onClick={() => setShowToken((value) => !value)}>
                    {showToken ? "Hide" : "Show"}
                  </button>
                </div>
              </div>
              <div className="tokenGateActions">
                <button className="button buttonSmall" type="button" onClick={saveToken} disabled={saving || checking}>
                  {saving ? "Validating…" : "Validate & Save"}
                </button>
                <button className="button buttonSmall buttonGhost" type="button" onClick={refreshStatus} disabled={saving || checking}>
                  {checking ? "Checking…" : "Re-check token"}
                </button>
              </div>
              {error ? <p className="pill pill-warn">{error}</p> : null}
            </section>
          </div>
        </div>
      ) : null}
    </>
  );
}
