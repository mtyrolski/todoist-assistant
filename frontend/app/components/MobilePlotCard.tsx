"use client";

import { useMemo, useRef, useState } from "react";
import { PlotCard, type PlotlyFigure } from "./PlotCard";

type Trace = { name: string; legendgroup: string; showlegend?: boolean; marker: { color: string } };

export function MobilePlotCard({
  title,
  figure,
  help,
  height,
  hiddenByTitle,
}: {
  title: string;
  figure: PlotlyFigure;
  help?: string;
  height: number;
  hiddenByTitle: Map<string, Set<string>>;
}) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(hiddenByTitle.get(title)));
  const currentHidden = useRef(hidden);
  currentHidden.current = hidden;
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
            onClick={() => {
              const next = new Set(currentHidden.current);
              if (next.has(trace.legendgroup)) next.delete(trace.legendgroup);
              else next.add(trace.legendgroup);
              currentHidden.current = next;
              hiddenByTitle.set(title, next);
              setHidden(next);
            }}
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
