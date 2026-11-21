"use client";

import { useMemo, useRef, useState } from "react";
import { normalizeSearch } from "../lib/mobile";
import { PlotCard, type PlotlyFigure } from "./PlotCard";

type Trace = { name: string; legendgroup: string; showlegend?: boolean; marker: { color: string }; mode?: string; x?: unknown[] };

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
  const traces = figure.data as Trace[];
  const entries = useMemo(() => traces.filter((trace) => trace.showlegend !== false), [traces]);
  // A total plus many project lines becomes unreadable on a phone. Start with
  // the total visible, while keeping every project available in the selector.
  const defaultHidden = useMemo<Set<string>>(() => {
    if (entries.length > 5 && entries.some((trace) => trace.legendgroup === "All projects")) {
      return new Set(entries.filter((trace) => trace.legendgroup !== "All projects").map((trace) => trace.legendgroup));
    }
    return new Set();
  }, [entries]);
  const [customized, setCustomized] = useState(() => hiddenByTitle.has(title));
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(hiddenByTitle.get(title)));
  const [query, setQuery] = useState("");
  const selectedHidden = customized ? hidden : defaultHidden;
  const normalizedQuery = normalizeSearch(query);
  const filteredEntries = entries.filter((trace) => normalizeSearch(trace.name).includes(normalizedQuery));
  const currentHidden = useRef(selectedHidden);
  currentHidden.current = selectedHidden;
  const displayed = useMemo(
    () => ({
      ...figure,
      data: traces.map((trace) => ({
        ...trace,
        // Dense markers merge into a solid blob on long histories; the line and
        // individual hover values remain available, as do separate endpoints.
        ...(trace.mode === "lines+markers" && Array.isArray(trace.x) && trace.x.length > 20 ? { mode: "lines" } : {}),
        visible: selectedHidden.has(trace.legendgroup) ? "legendonly" : true,
      })),
    }),
    [figure, traces, selectedHidden],
  );
  const legendItems = (
    <>
      {entries.length > 8 && <input className="select" type="search" aria-label={`Search ${title} lines`} placeholder="Search lines" value={query} onChange={(event) => setQuery(event.target.value)} />}
      <div className="mobilePlotLegend" aria-label={`${title} projects`}>
      {filteredEntries.map((trace) => (
          <button
            type="button"
            key={trace.legendgroup}
            aria-pressed={!selectedHidden.has(trace.legendgroup)}
            onClick={() => {
              const next = new Set(currentHidden.current);
              if (next.has(trace.legendgroup)) next.delete(trace.legendgroup);
              else next.add(trace.legendgroup);
              currentHidden.current = next;
              hiddenByTitle.set(title, next);
              setHidden(next);
              setCustomized(true);
            }}
          >
            <i aria-hidden="true" style={{ backgroundColor: trace.marker.color }} />
            <span>{trace.name}</span>
          </button>
        ))}
      </div>
      {query.trim() && !filteredEntries.length && <p className="muted tiny">No matching lines.</p>}
    </>
  );
  const legend = entries.length > 5 ? (
    <details className="mobilePlotLegendDisclosure">
      <summary>{entries.some((trace) => trace.legendgroup === "All projects") && !selectedHidden.has("All projects") ? "All projects total" : "Lines"} · {entries.filter((trace) => !selectedHidden.has(trace.legendgroup)).length} of {entries.length} shown</summary>
      {legendItems}
    </details>
  ) : legendItems;
  return (
    <PlotCard title={title} figure={displayed} help={help} height={height} compact legendContent={legend} />
  );
}
