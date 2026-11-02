"use client";

import { useMemo, useState } from "react";
import { PlotCard, type PlotlyFigure } from "./PlotCard";

type Trace = { name: string; legendgroup: string; showlegend?: boolean; marker: { color: string } };

export function MobilePlotCard({
  title,
  figure,
  help,
  height,
}: {
  title: string;
  figure: PlotlyFigure;
  help?: string;
  height: number;
}) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const traces = figure.data as Trace[];
  const displayed = useMemo(
    () => ({
      ...figure,
      data: traces.map((trace) => ({
        ...trace,
        visible: hidden.has(trace.legendgroup) ? "legendonly" : true,
      })),
    }),
    [figure, traces, hidden],
  );
  const legend = (
    <div className="mobilePlotLegend" aria-label={`${title} projects`}>
      {traces
        .filter((trace) => trace.showlegend !== false)
        .map((trace) => (
          <button
            type="button"
            key={trace.legendgroup}
            aria-pressed={!hidden.has(trace.legendgroup)}
            onClick={() =>
              setHidden((previous) => {
                const next = new Set(previous);
                if (next.has(trace.legendgroup)) next.delete(trace.legendgroup);
                else next.add(trace.legendgroup);
                return next;
              })
            }
          >
            <i aria-hidden="true" style={{ backgroundColor: trace.marker.color }} />
            <span>{trace.name}</span>
          </button>
        ))}
    </div>
  );
  return (
    <PlotCard title={title} figure={displayed} help={help} height={height} compact legendContent={legend} />
  );
}
