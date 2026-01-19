"use client";

import { AdminPanel } from "../components/AdminPanel";
import { LlmBreakdownStatus } from "../components/LlmBreakdownStatus";
import { LoadingBar } from "../components/LoadingBar";
import { PageHeader } from "../components/PageHeader";
import { ServiceMonitor } from "../components/ServiceMonitor";
import { StatusPills } from "../components/StatusPills";
import { useApiHealth, useDashboardStatus, useLlmBreakdownProgress, useSyncLabel } from "../lib/dashboardHooks";

export default function ControlPanelPage() {
  const { health, loadingHealth, error } = useApiHealth();
  const { status, loadingStatus, refreshStatus } = useDashboardStatus();
  const { progress, loading, refresh } = useLlmBreakdownProgress();
  const { label: syncLabel, title: syncTitle } = useSyncLabel(status);
  const healthLabel = loadingHealth ? "Checking API..." : health?.status === "ok" ? "API online" : "API offline";
  const healthTone = health?.status === "ok" ? "good" : "warn";

  return (
    <>
      <LoadingBar active={loadingStatus || loading} />
      <PageHeader
        eyebrow="Control Panel"
        title="Operations & Monitoring"
        lede="Run automations, inspect logs, and keep track of service health in one place."
      >
        <StatusPills
          items={[
            { label: healthLabel, tone: healthTone },
            { label: health?.version ? `v${health.version}` : "", tone: "neutral" },
            { label: syncLabel, tone: "neutral", title: syncTitle },
            { label: error ?? "", tone: "warn" }
          ]}
        />
      </PageHeader>

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
