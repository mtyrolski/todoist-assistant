"use client";

import { AdminPanel } from "../components/AdminPanel";
import { DashboardSettings } from "../components/DashboardSettings";
import { LlmBreakdownStatus } from "../components/LlmBreakdownStatus";
import { LlmRuntimeSettings } from "../components/LlmRuntimeSettings";
import { LoadingBar } from "../components/LoadingBar";
import { ObserverControl } from "../components/ObserverControl";
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
        lede="Run automations, tune settings, and keep track of service health."
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
          <LlmRuntimeSettings
            onAfterMutation={() => {
              refreshStatus();
              refresh();
            }}
          />
          <DashboardSettings
            onAfterMutation={() => {
              refreshStatus();
            }}
          />
          <ObserverControl
            onAfterMutation={() => {
              refreshStatus();
              refresh();
            }}
          />
          <LlmBreakdownStatus progress={progress} loading={loading} onRefresh={refresh} />
          <ServiceMonitor
            services={status?.services ?? null}
            configurableItems={status?.configurableItems}
            onRefresh={refreshStatus}
          />
        </div>
      </section>
    </>
  );
}
