"use client";

type Tone = "good" | "warn" | "neutral";

export type StatusPill = {
  key?: string;
  label: string;
  tone?: Tone;
  title?: string;
};

export function StatusPills({ items }: { items: StatusPill[] }) {
  return (
    <div className="status-row">
      {items
        .filter((item) => item.label)
        .map((item, index) => {
          const toneClass = item.tone ? ` pill-${item.tone}` : "";
          return (
            <span
              key={item.key ?? `${item.label}-${index}`}
              className={`pill${toneClass}`}
              title={item.title}
            >
              {item.label}
            </span>
          );
        })}
    </div>
  );
}
