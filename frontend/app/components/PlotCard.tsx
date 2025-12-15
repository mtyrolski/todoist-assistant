"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

type PlotProps = ComponentProps<typeof Plot>;

export type PlotlyFigure = {
  data: unknown[];
  layout?: Record<string, unknown>;
  frames?: unknown[];
};

export function PlotCard({
  title,
  figure,
  height = 420
}: {
  title: string;
  figure: PlotlyFigure | null | undefined;
  height?: number;
}) {
  return (
    <section className="card">
      <header className="cardHeader">
        <h2>{title}</h2>
      </header>
      <div className="cardBody" style={{ height }}>
        {!figure ? (
          <div className="skeleton" />
        ) : (
          <Plot
            data={figure.data as PlotProps["data"]}
            layout={{
              ...(figure.layout ?? {}),
              autosize: true,
              height,
              paper_bgcolor: "rgba(0,0,0,0)",
              plot_bgcolor: "rgba(0,0,0,0)",
              font: { color: "#e8ecf2" },
              margin: { l: 48, r: 18, t: 56, b: 46 }
            }}
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
