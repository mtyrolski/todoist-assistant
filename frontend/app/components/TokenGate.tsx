"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";

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

export function TokenGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<ApiTokenStatus | null>(null);
  const [validation, setValidation] = useState<TokenValidation | null>(null);
  const [checking, setChecking] = useState(true);
  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenNotice, setTokenNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showToken, setShowToken] = useState(false);

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
      const payload = await readJson<ApiTokenStatus & { detail?: string }>(res);
      if (!res.ok) throw new Error(payload.detail ?? "Failed to save token");
      setStatus(payload);
      setValidation({ configured: true, valid: true });
      setTokenDraft("");
      setTokenNotice("API token saved and validated.");
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

  if (ready) {
    return <>{children}</>;
  }

  return (
    <section className="card tokenGate">
      <div className="cardHeader">
        <div className="cardTitleRow">
          <h2>Connect Todoist</h2>
        </div>
        <span className={`pill ${status?.configured ? "pill-warn" : "pill-neutral"}`}>
          {status?.configured ? `Token found (${status.masked})` : "Token required"}
        </span>
      </div>
      <p className="muted">
        Paste your Todoist API token to unlock the dashboard. Find it in Todoist: Settings → Integrations → Developer.
      </p>
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
          <button className="button buttonSmall buttonGhost" type="button" onClick={validateExisting} disabled={saving || checking}>
            Re-check token
          </button>
        ) : null}
        <button className="button buttonSmall buttonGhost" type="button" onClick={refreshStatus} disabled={saving || checking}>
          {checking ? "Checking…" : "Refresh"}
        </button>
      </div>
      {tokenError ? <p className="pill pill-warn">{tokenError}</p> : null}
      {tokenNotice ? <p className="pill">{tokenNotice}</p> : null}
    </section>
  );
}
