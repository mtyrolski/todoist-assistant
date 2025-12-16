"use client";

export type InsightItem = {
  title: string;
  value: string;
  detail?: string;
  color?: string | null;
};

export function InsightCard({ item }: { item: InsightItem }) {
  return (
    <section className="stat insight">
      <div className="statTop">
        <p className="muted tiny">{item.title}</p>
        {item.color ? <span className="swatch" style={{ background: item.color }} /> : null}
      </div>
      <p className="statValue insightValue">{item.value}</p>
      {item.detail ? <p className="muted tiny">{item.detail}</p> : null}
    </section>
  );
}

