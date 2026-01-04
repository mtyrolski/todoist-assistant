"use client";

import { InfoTip } from "./InfoTip";

export type ServiceStatus = {
  name: string;
  status: "ok" | "warn" | "neutral";
  detail: unknown;
};

const SERVICE_HELP = `**Service Monitor**
Health checks for local services and caches.

- Status shows whether a service is healthy.
- Detail contains the latest check output.`;

function statusLabel(status: ServiceStatus["status"]): string {
  if (status === "ok") return "Healthy";
  if (status === "warn") return "Attention";
  return "Unknown";
}

export function ServiceMonitor({
  services,
  onRefresh
}: {
  services: ServiceStatus[] | null;
  onRefresh: () => void;
}) {
  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>Service Monitor</h2>
          <InfoTip label="About service monitor" content={SERVICE_HELP} />
        </div>
        <button className="button buttonSmall" onClick={onRefresh} type="button">
          Refresh
        </button>
      </header>
      <div className="list">
        {!services ? (
          <div className="skeleton" style={{ minHeight: 140 }} />
        ) : (
          services.map((svc) => (
            <div key={svc.name} className="row">
              <div className={`dot dot-${svc.status}`} />
              <div className="rowMain">
                <p className="rowTitle">{svc.name}</p>
                <p className="muted tiny">{statusLabel(svc.status)}</p>
              </div>
              <pre className="rowDetail">{typeof svc.detail === "string" ? svc.detail : JSON.stringify(svc.detail)}</pre>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
