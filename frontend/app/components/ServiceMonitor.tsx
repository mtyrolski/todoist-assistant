"use client";

export type ServiceStatus = {
  name: string;
  status: "ok" | "warn" | "neutral";
  detail: unknown;
};

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
        <h2>Service Monitor</h2>
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

