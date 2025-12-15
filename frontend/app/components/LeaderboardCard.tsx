"use client";

export type LeaderboardItem = {
  name: string;
  events: number;
  prevEvents: number;
  deltaPercent: number | null;
  color: string;
};

export function LeaderboardCard({ items }: { items: LeaderboardItem[] | null | undefined }) {
  const max = Math.max(1, ...(items?.map((it) => it.events) ?? [1]));
  if (!items) return <div className="skeleton" style={{ minHeight: 220 }} />;
  return (
    <div className="leaderboard">
      {items.map((it) => (
        <div key={it.name} className="leaderRow">
          <div className="leaderMeta">
            <div className="leaderName">
              <span className="swatch" style={{ background: it.color }} />
              <span className="truncate">{it.name}</span>
            </div>
            <div className="leaderNumbers">
              <span className="mono">{it.events}</span>
              <span
                className={`pill pill-${
                  it.deltaPercent === null ? "neutral" : it.deltaPercent >= 0 ? "good" : "warn"
                }`}
              >
                {it.deltaPercent === null ? "∞" : `${it.deltaPercent > 0 ? "+" : ""}${it.deltaPercent}%`}
              </span>
            </div>
          </div>
          <div className="leaderBar">
            <div
              className="leaderFill"
              style={{
                width: `${Math.round((it.events / max) * 100)}%`,
                background: `linear-gradient(90deg, ${it.color}, rgba(255,255,255,0.18))`
              }}
            />
          </div>
          <p className="muted tiny">
            Prev: <span className="mono">{it.prevEvents}</span>
          </p>
        </div>
      ))}
    </div>
  );
}
