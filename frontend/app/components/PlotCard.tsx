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
              return {
                ...baseLayout,
                autosize: true,
                height,
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)",
                font: { color: "#e8ecf2" },
                template: "plotly_dark",
                margin: { l: 48, r: 18, t: 56, b: 46 }
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
