"use client";

function formatDelta(deltaPercent: number | null): string {
  if (deltaPercent === null) return "∞";
  const sign = deltaPercent > 0 ? "+" : "";
  return `${sign}${deltaPercent}%`;
}

export function StatCard({
  name,
  value,
  deltaPercent,
  inverseDelta,
  currentPeriod,
  previousPeriod
}: {
  name: string;
  value: number;
  deltaPercent: number | null;
  inverseDelta: boolean;
  currentPeriod: string;
  previousPeriod: string;
}) {
  const isUp = (deltaPercent ?? 0) > 0;
  const isDown = (deltaPercent ?? 0) < 0;
  const deltaTone = (() => {
    if (deltaPercent === null) return "neutral";
    if (!inverseDelta) {
      if (isUp) return "good";
      if (isDown) return "warn";
      return "neutral";
    }
    if (isUp) return "warn";
    if (isDown) return "good";
    return "neutral";
  })();

  return (
    <section className="stat">
      <div className="statTop">
        <p className="muted">{name}</p>
        <span className={`pill pill-${deltaTone}`}>{formatDelta(deltaPercent)}</span>
      </div>
      <p className="statValue">{value.toLocaleString()}</p>
      <div className="statPeriods">
        <div>
          <p className="muted tiny">Current</p>
          <p className="tiny">{currentPeriod}</p>
        </div>
        <div>
          <p className="muted tiny">Previous</p>
          <p className="tiny">{previousPeriod}</p>
        </div>
      </div>
    </section>
  );
}
