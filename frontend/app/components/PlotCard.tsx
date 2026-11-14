"use client";

import type { PlotParams } from "react-plotly.js";
import { Plot } from "./Plot";
import type { ReactNode } from "react";
import { InfoTip } from "./InfoTip";

export type PlotlyFigure = {
  data: unknown[];
  layout?: Record<string, unknown>;
  frames?: unknown[];
};

export function PlotCard({
  title,
  figure,
  help,
  actions,
  legendContent,
  height = 420,
  interactive = false,
  compact = false
}: {
  title: string;
  figure: PlotlyFigure | null | undefined;
  help?: string;
  actions?: ReactNode;
  legendContent?: ReactNode;
  height?: number | string;
  interactive?: boolean;
  compact?: boolean;
}) {
  const numericHeight = typeof height === "number" ? height : undefined;
  const fillHeight = typeof height === "string" && !numericHeight;

  return (
    <section
      className={`card${legendContent ? " cardWithLegend" : ""}${fillHeight ? " cardFillHeight" : ""}`}
      aria-label={title}
      style={fillHeight ? { height: "100%", minHeight: 0 } : undefined}
    >
      <header className="cardHeader">
        <div className="cardTitleRow">
          <h2>{title}</h2>
          {help ? <InfoTip label={`About ${title}`} content={help} /> : null}
        </div>
        {actions}
      </header>
      {legendContent}
      <div
        className={`cardBody${fillHeight ? " cardBodyFill" : ""}`}
        style={numericHeight ? { height: numericHeight } : fillHeight ? { minHeight: 0 } : undefined}
      >
        {!figure ? (
          <div className="skeleton" role="status" aria-label={`Loading ${title}`} />
        ) : (
          <Plot
            data={figure.data as PlotParams["data"]}
            layout={(() => {
              const { title: _title, height: _height, ...baseLayout } = figure.layout ?? {};
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
                // On touch screens Plotly's default comparison hover can stack
                // multiple labels over the axis and drag-to-zoom steals scrolling.
                ...(compact ? { hovermode: "closest", dragmode: false } : {}),
                ...(numericHeight ? { height: numericHeight } : {}),
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)",
                font: { ...(layoutRecord.font as Record<string, unknown> ?? {}), color: "#e8ecf2" },
                template: "plotly_dark",
                margin: {
                  l: Math.max(compact ? 32 : 56, toNumber(margin.l, compact ? 32 : 56)),
                  r: Math.max(compact ? 12 : 24, toNumber(margin.r, compact ? 12 : 24)),
                  t: Math.max(compact ? (legendContent ? 12 : 48) : 76, toNumber(margin.t, compact ? (legendContent ? 12 : 48) : 76)),
                  b: Math.max(compact ? 36 : 58, toNumber(margin.b, compact ? 36 : 58))
                },
                xaxis: withTitleStandoff(compact ? { showgrid: false, ...xaxis, ...(Array.isArray(xaxis.categoryarray) ? { tickangle: 0 } : {}) } : xaxis, 18),
                yaxis: withTitleStandoff(compact ? { showgrid: false, ...yaxis } : yaxis, 16),
                legend: {
                  ...legend,
                  tracegroupgap: Math.max(12, toNumber(legend.tracegroupgap, 12))
                }
              };
            })()}
            config={{
              displayModeBar: interactive ? "hover" : false,
              displaylogo: false,
              responsive: true,
              scrollZoom: interactive,
              doubleClick: interactive ? "reset+autosize" : false
            }}
            useResizeHandler
            style={{ width: "100%", height: "100%" }}
          />
        )}
      </div>
    </section>
  );
}
