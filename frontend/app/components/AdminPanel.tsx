"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { InfoTip } from "./InfoTip";
import {
  clearAdminApiToken,
  clearAdminTimezone,
  getAdminApiTokenStatus,
  getAdminTimezoneStatus,
  saveAdminApiToken,
  saveAdminTimezone,
  type AdminApiTokenStatus,
  type AdminTimezoneStatus
} from "../lib/adminApi";

type ApiTokenStatus = AdminApiTokenStatus;
type TimezoneStatus = AdminTimezoneStatus;

const ADMIN_HELP = `**Dashboard Admin**
Update your local Todoist API token and timezone.`;

export function AdminPanel({ onAfterMutation }: { onAfterMutation: () => void }) {
  const [tokenStatus, setTokenStatus] = useState<ApiTokenStatus | null>(null);
  const [tokenDraft, setTokenDraft] = useState<string>("");
  const [tokenSaving, setTokenSaving] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenNotice, setTokenNotice] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [timezoneStatus, setTimezoneStatus] = useState<TimezoneStatus | null>(null);
  const [timezoneDraft, setTimezoneDraft] = useState<string>("");
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [timezoneError, setTimezoneError] = useState<string | null>(null);
  const [timezoneNotice, setTimezoneNotice] = useState<string | null>(null);

  const loadApiToken = async () => {
    try {
      setTokenStatus(await getAdminApiTokenStatus());
    } catch {
      setTokenStatus(null);
    }
  };

  const loadTimezone = async () => {
    try {
      const payload = await getAdminTimezoneStatus();
      setTimezoneStatus(payload);
      setTimezoneDraft(payload.override ?? "");
    } catch {
      setTimezoneStatus(null);
    }
  };

  useEffect(() => {
    loadApiToken();
  }, []);

  useEffect(() => {
    loadTimezone();
  }, []);

  const saveApiToken = async () => {
    if (!tokenDraft.trim()) {
      setTokenError("Paste your Todoist API token.");
      return;
    }
    try {
      setTokenSaving(true);
      setTokenError(null);
      setTokenNotice(null);
      const payload = await saveAdminApiToken(tokenDraft.trim());
      setTokenStatus(payload);
      setTokenDraft("");
      setTokenNotice("API token saved and validated.");
      onAfterMutation();
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "Failed to save token");
    } finally {
      setTokenSaving(false);
    }
  };

  const clearApiToken = async () => {
    try {
      setTokenSaving(true);
      setTokenError(null);
      setTokenNotice(null);
      const payload = await clearAdminApiToken();
      setTokenStatus(payload);
      setTokenNotice("API token removed.");
      onAfterMutation();
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "Failed to clear token");
    } finally {
      setTokenSaving(false);
    }
  };

  const saveTimezone = async () => {
    if (!timezoneDraft.trim()) {
      setTimezoneError("Provide an IANA timezone (example: Europe/Warsaw).");
      return;
    }
    try {
      setTimezoneSaving(true);
      setTimezoneError(null);
      setTimezoneNotice(null);
      const payload = await saveAdminTimezone(timezoneDraft.trim());
      setTimezoneStatus(payload);
      setTimezoneDraft(payload.override ?? "");
      setTimezoneNotice("Timezone override saved.");
      onAfterMutation();
    } catch (e) {
      setTimezoneError(e instanceof Error ? e.message : "Failed to save timezone");
    } finally {
      setTimezoneSaving(false);
    }
  };

  const clearTimezone = async () => {
    try {
      setTimezoneSaving(true);
      setTimezoneError(null);
      setTimezoneNotice(null);
      const payload = await clearAdminTimezone();
      setTimezoneStatus(payload);
      setTimezoneDraft("");
      setTimezoneNotice("Timezone override removed (using system timezone).");
      onAfterMutation();
    } catch (e) {
      setTimezoneError(e instanceof Error ? e.message : "Failed to clear timezone");
    } finally {
      setTimezoneSaving(false);
    }
  };

  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Dashboard Admin</h2>
          <InfoTip label="About dashboard admin" content={ADMIN_HELP} />
        </div>
        <Link className="button buttonSmall buttonGhost" href="/live-logs">Open Live Logs</Link>
      </header>
      <div className="stack">
          <div className="card cardInner">
            <header className="cardHeader">
              <h3>Todoist API Token</h3>
            </header>
            <div className="stack">
              <p className="muted tiny" style={{ margin: 0 }}>
                Paste your Todoist API token to enable the dashboard. Find it in Todoist: Settings → Integrations → Developer.
              </p>
              <div className="adminRow">
                <span className={`pill ${tokenStatus?.configured ? "pill-good" : "pill-warn"}`}>
                  {tokenStatus?.configured ? `Configured (${tokenStatus.masked})` : "Missing token"}
                </span>
                {tokenStatus?.envPath ? (
                  <span className="muted tiny" style={{ marginLeft: 8 }}>
                    {tokenStatus.envPath}
                  </span>
                ) : null}
              </div>
              <div className="control">
                <label className="muted tiny" htmlFor="api-token-input">
                  API token
                </label>
                <input
                  id="api-token-input"
                  className="dateInput"
                  type={showToken ? "text" : "password"}
                  placeholder="Paste token here"
                  value={tokenDraft}
                  onChange={(e) => setTokenDraft(e.target.value)}
                />
              </div>
              <div className="adminRow">
                <div className="adminRowRight">
                  <label className="muted tiny" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input type="checkbox" checked={showToken} onChange={(e) => setShowToken(e.target.checked)} />
                    Show
                  </label>
                  <button className="button buttonSmall" type="button" onClick={saveApiToken} disabled={tokenSaving}>
                    {tokenSaving ? "Saving…" : "Save token"}
                  </button>
                  <button className="button buttonSmall" type="button" onClick={clearApiToken} disabled={tokenSaving}>
                    Clear token
                  </button>
                  <button className="button buttonSmall" type="button" onClick={loadApiToken} disabled={tokenSaving}>
                    Refresh
                  </button>
                </div>
              </div>
              {tokenError ? <p className="pill pill-warn">{tokenError}</p> : null}
              {tokenNotice ? <p className="pill pill-good">{tokenNotice}</p> : null}
            </div>
          </div>

          <div className="card cardInner">
            <header className="cardHeader">
              <h3>Timezone Override</h3>
            </header>
            <div className="stack">
              <p className="muted tiny" style={{ margin: 0 }}>
                The app uses system timezone by default. Set an IANA timezone in .env to override it.
              </p>
              <div className="adminRow">
                <span className={`pill ${timezoneStatus?.source === "env" ? "pill-good" : "pill"}`}>
                  {timezoneStatus ? `${timezoneStatus.timezone} (${timezoneStatus.source})` : "Timezone unavailable"}
                </span>
                {timezoneStatus?.envPath ? (
                  <span className="muted tiny" style={{ marginLeft: 8 }}>
                    {timezoneStatus.envPath}
                  </span>
                ) : null}
              </div>
              {timezoneStatus && !timezoneStatus.overrideValid ? (
                <p className="pill pill-warn">
                  Invalid override in .env ({timezoneStatus.invalidOverride}). Falling back to system timezone.
                </p>
              ) : null}
              <div className="adminRow">
                <span className="muted tiny">
                  System timezone: {timezoneStatus?.system ?? "unknown"}
                </span>
              </div>
              <div className="control">
                <label className="muted tiny" htmlFor="timezone-input">
                  Timezone (IANA name)
                </label>
                <input
                  id="timezone-input"
                  className="dateInput"
                  type="text"
                  placeholder="Europe/Warsaw"
                  value={timezoneDraft}
                  onChange={(e) => setTimezoneDraft(e.target.value)}
                />
              </div>
              <div className="adminRow">
                <div className="adminRowRight">
                  <button className="button buttonSmall" type="button" onClick={saveTimezone} disabled={timezoneSaving}>
                    {timezoneSaving ? "Saving…" : "Save timezone"}
                  </button>
                  <button className="button buttonSmall" type="button" onClick={clearTimezone} disabled={timezoneSaving}>
                    Use system timezone
                  </button>
                  <button className="button buttonSmall" type="button" onClick={loadTimezone} disabled={timezoneSaving}>
                    Refresh
                  </button>
                </div>
              </div>
              {timezoneError ? <p className="pill pill-warn">{timezoneError}</p> : null}
              {timezoneNotice ? <p className="pill pill-good">{timezoneNotice}</p> : null}
            </div>
          </div>
        </div>
    </section>
  );
}
