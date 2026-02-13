"use client";

import dynamic from "next/dynamic";
import type { PlotParams } from "react-plotly.js";
import type { ComponentType } from "react";
import { InfoTip } from "./InfoTip";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as unknown as ComponentType<PlotParams>;

export type PlotlyFigure = {
  data: unknown[];
  layout?: Record<string, unknown>;
  frames?: unknown[];
};

export function PlotCard({
  title,
  figure,
  help,
  height = 420
}: {
  title: string;
  figure: PlotlyFigure | null | undefined;
  help?: string;
  height?: number;
}) {
  return (
    <section className="card">
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>{title}</h2>
          {help ? <InfoTip label={`About ${title}`} content={help} /> : null}
        </div>
      </header>
      <div className="cardBody" style={{ height }}>
        {!figure ? (
          <div className="skeleton" />
        ) : (
          <Plot
            data={figure.data as PlotParams["data"]}
            layout={(() => {
              const { title: _title, ...baseLayout } = figure.layout ?? {};
              const layoutRecord = baseLayout as Record<string, unknown>;
              const margin = (layoutRecord.margin ?? {}) as Record<string, unknown>;
              const xaxis = (layoutRecord.xaxis ?? {}) as Record<string, unknown>;
              const yaxis = (layoutRecord.yaxis ?? {}) as Record<string, unknown>;
              const legend = (layoutRecord.legend ?? {}) as Record<string, unknown>;

              const toNumber = (value: unknown, fallback: number): number =>
                typeof value === "number" && Number.isFinite(value) ? value : fallback;

              const withTitleStandoff = (
                axis: Record<string, unknown>,
                standoff: number
              ): Record<string, unknown> => {
                const axisTitle = axis.title;
                if (typeof axisTitle === "string") {
                  return { ...axis, automargin: true, title: { text: axisTitle, standoff } };
                }
                if (axisTitle && typeof axisTitle === "object") {
                  return {
                    ...axis,
                    automargin: true,
                    title: { ...(axisTitle as Record<string, unknown>), standoff }
                  };
                }
                return { ...axis, automargin: true };
              };

              return {
                ...baseLayout,
                autosize: true,
                height,
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)",
                font: { color: "#e8ecf2" },
                template: "plotly_dark",
                margin: {
                  l: Math.max(56, toNumber(margin.l, 56)),
                  r: Math.max(24, toNumber(margin.r, 24)),
                  t: Math.max(76, toNumber(margin.t, 76)),
                  b: Math.max(58, toNumber(margin.b, 58))
                },
                xaxis: withTitleStandoff(xaxis, 18),
                yaxis: withTitleStandoff(yaxis, 16),
                legend: {
                  ...legend,
                  tracegroupgap: Math.max(12, toNumber(legend.tracegroupgap, 12))
                }
              };
            })()}
            config={{
              displayModeBar: false,
              responsive: true,
              scrollZoom: false
            }}
            useResizeHandler
            style={{ width: "100%", height: "100%" }}
          />
        )}
      </div>
    </section>
  );
}
