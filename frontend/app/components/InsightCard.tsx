"use client";

import { InfoTip } from "./InfoTip";

export type InsightItem = {
  title: string;
  value: string;
  detail?: string;
  color?: string | null;
};

export function InsightCard({ item, help }: { item: InsightItem; help?: string }) {
  return (
    <section className="stat insight">
      <div className="statTop">
        <div className="statTitleRow">
          <p className="muted tiny">{item.title}</p>
          {help ? <InfoTip label={`About ${item.title}`} content={help} /> : null}
        </div>
        {item.color ? <span className="swatch" style={{ background: item.color }} /> : null}
      </div>
      <p className="statValue insightValue">{item.value}</p>
      {item.detail ? <p className="muted tiny">{item.detail}</p> : null}
    </section>
  );
}
