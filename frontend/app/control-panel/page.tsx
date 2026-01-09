"use client";

import { AdminPanel } from "../components/AdminPanel";
import { LlmBreakdownStatus } from "../components/LlmBreakdownStatus";
import { ServiceMonitor } from "../components/ServiceMonitor";
import { LoadingBar } from "../components/LoadingBar";
import { useApiHealth, useDashboardStatus, useLlmBreakdownProgress, useSyncLabel } from "../lib/dashboardHooks";

export default function ControlPanelPage() {
  const { health, loadingHealth, error } = useApiHealth();
  const { status, loadingStatus, refreshStatus } = useDashboardStatus();
  const { progress, loading, refresh } = useLlmBreakdownProgress();
  const { label: syncLabel, title: syncTitle } = useSyncLabel(status);

  return (
    <>
      <LoadingBar active={loadingStatus || loading} />
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Control Panel</p>
          <h1>Operations & Monitoring</h1>
          <p className="lede">Run automations, inspect logs, and keep track of service health in one place.</p>
          <div className="status-row">
            <span className={`pill ${health?.status === "ok" ? "pill-good" : "pill-warn"}`}>
              {loadingHealth ? "Checking API..." : health?.status === "ok" ? "API online" : "API offline"}
            </span>
            {health?.version ? <span className="pill pill-neutral">v{health.version}</span> : null}
            <span className="pill pill-neutral" title={syncTitle}>
              {syncLabel}
            </span>
            {error ? <span className="pill pill-warn">{error}</span> : null}
          </div>
        </div>
      </header>

      <section className="grid2">
        <div className="stack">
          <AdminPanel
            onAfterMutation={() => {
              refreshStatus();
              refresh();
            }}
          />
        </div>
        <div className="stack">
          <LlmBreakdownStatus progress={progress} loading={loading} onRefresh={refresh} />
          <ServiceMonitor services={status?.services ?? null} onRefresh={refreshStatus} />
        </div>
      </section>
    </>
  );
}
