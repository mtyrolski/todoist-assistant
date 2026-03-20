"use client";

import { InfoTip } from "./InfoTip";

function formatDelta(deltaPercent: number | null): string {
  if (deltaPercent === null) return "N/A";
  const sign = deltaPercent > 0 ? "+" : "";
  return `${sign}${deltaPercent}%`;
}

export function StatCard({
  name,
  value,
  deltaPercent,
  inverseDelta,
  currentPeriod,
  previousPeriod,
  currentLabel = "Current",
  previousLabel = "Previous",
  help
}: {
  name: string;
  value: number;
  deltaPercent: number | null;
  inverseDelta: boolean;
  currentPeriod: string;
  previousPeriod: string;
  currentLabel?: string;
  previousLabel?: string;
  help?: string;
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
        <div className="statTitleRow">
          <p className="muted">{name}</p>
          {help ? <InfoTip label={`About ${name}`} content={help} /> : null}
        </div>
        <span className={`pill pill-${deltaTone} statDeltaPill`}>{formatDelta(deltaPercent)}</span>
      </div>
      <p className="statValue">{value.toLocaleString()}</p>
      <div className="statPeriods">
        <div className="statPeriodBlock">
          <p className="muted tiny">{currentLabel}</p>
          <p className="tiny">{currentPeriod}</p>
        </div>
        <div className="statPeriodBlock">
          <p className="muted tiny">{previousLabel}</p>
          <p className="tiny">{previousPeriod}</p>
        </div>
      </div>
    </section>
  );
}
