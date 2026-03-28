"use client";

import { useEffect, useState } from "react";

type LogSource = {
  id: string;
  label: string;
  kind: string;
  description: string;
  path: string;
  available: boolean;
  inspectOnly: boolean;
  size: number | null;
  mtime: string | null;
};

type LogsResponse = {
  inspectOnly: boolean;
  sources: LogSource[];
};

type LogReadResponse = {
  source: string;
  label: string;
  category: string;
  description: string;
  path: string;
  available: boolean;
  inspectOnly: boolean;
  size: number;
  mtime: string;
  content: string;
  page: number;
  perPage: number;
  totalPages: number;
  totalLines: number;
};

function preferredSourceId(sources: LogSource[], current: string): string {
  if (current && sources.some((source) => source.id === current)) {
    return current;
  }
  const available = sources.find((source) => source.available);
  return available?.id ?? sources[0]?.id ?? "";
}

async function fetchLogSources(): Promise<LogsResponse> {
  const res = await fetch("/api/runtime/logs");
  const payload = (await res.json()) as LogsResponse;
  if (!res.ok) {
    throw new Error("Failed to load runtime log sources");
  }
  return payload;
}

async function fetchLogRead(source: string, page: number, lines: number): Promise<LogReadResponse> {
  const qs = new URLSearchParams({
    source,
    tail_lines: String(lines),
    page: String(page)
  });
  const res = await fetch(`/api/runtime/logs/read?${qs.toString()}`);
  const payload = (await res.json()) as LogReadResponse & { detail?: string };
  if (!res.ok) {
    throw new Error(payload.detail ?? "Failed to read runtime log");
  }
  return payload;
}

function formatSize(size: number | null): string {
  if (size === null) return "Unavailable";
  if (size < 1024) return `${size} B`;
  return `${Math.round(size / 1024)} KB`;
}

export function LogInspector() {
  const [sources, setSources] = useState<LogSource[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>("");
  const [logRead, setLogRead] = useState<LogReadResponse | null>(null);
  const [lines, setLines] = useState<number>(120);
  const [page, setPage] = useState<number>(1);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [loadingSources, setLoadingSources] = useState<boolean>(true);
  const [loadingLog, setLoadingLog] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        setLoadingSources(true);
        const payload = await fetchLogSources();
        if (!active) return;
        setSources(payload.sources);
        setSelectedSource((current) => preferredSourceId(payload.sources, current));
        setError(null);
      } catch (err) {
        if (!active) return;
        setSources([]);
        setSelectedSource("");
        setError(err instanceof Error ? err.message : "Failed to load runtime log sources");
      } finally {
        if (active) {
          setLoadingSources(false);
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedSource) {
      setLogRead(null);
      return;
    }
    let active = true;
    const load = async () => {
      try {
        setLoadingLog(true);
        const payload = await fetchLogRead(selectedSource, page, lines);
        if (!active) return;
        setLogRead(payload);
        setError(null);
      } catch (err) {
        if (!active) return;
        setLogRead(null);
        setError(err instanceof Error ? err.message : "Failed to read runtime log");
      } finally {
        if (active) {
          setLoadingLog(false);
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [selectedSource, page, lines]);

  useEffect(() => {
    if (!autoRefresh || !selectedSource) return undefined;
    const timer = window.setInterval(() => {
      void fetchLogSources()
        .then((payload) => {
          setSources(payload.sources);
          setSelectedSource((current) => preferredSourceId(payload.sources, current));
        })
        .catch(() => undefined);
      void fetchLogRead(selectedSource, page, lines)
        .then((payload) => {
          setLogRead(payload);
        })
        .catch(() => undefined);
    }, 4000);
    return () => {
      window.clearInterval(timer);
    };
  }, [autoRefresh, selectedSource, page, lines]);

  const selectedMeta = sources.find((source) => source.id === selectedSource) ?? null;

  const refreshNow = async () => {
    try {
      setLoadingSources(true);
      setLoadingLog(true);
      const payload = await fetchLogSources();
      setSources(payload.sources);
      const nextSource = preferredSourceId(payload.sources, selectedSource);
      setSelectedSource(nextSource);
      if (nextSource) {
        const nextLog = await fetchLogRead(nextSource, page, lines);
        setLogRead(nextLog);
      } else {
        setLogRead(null);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh runtime logs");
    } finally {
      setLoadingSources(false);
      setLoadingLog(false);
    }
  };

  return (
    <section className="logInspectorLayout">
      <div className="card logInspectorRail">
        <div className="logInspectorRailHeader">
          <div>
            <p className="muted tiny">Inspectable sources</p>
            <h2 className="logInspectorSectionTitle">Runtime logs</h2>
          </div>
          <span className="pill pill-neutral">Read-only</span>
        </div>
        <p className="muted tiny">
          Only explicitly allowlisted runtime logs are exposed here. No file editing, upload, or path browsing.
        </p>
        <div className="list">
          {sources.map((source) => (
            <button
              key={source.id}
              className={`row rowCompact rowButton logSourceButton${selectedSource === source.id ? " rowActive" : ""}${source.available ? "" : " logSourceButtonDisabled"}`}
              onClick={() => {
                setSelectedSource(source.id);
                setPage(1);
              }}
              type="button"
            >
              <div className={`dot ${source.available ? "dot-ok" : "dot-neutral"}`} />
              <div className="rowMain">
                <p className="rowTitle">{source.label}</p>
                <p className="muted tiny">{source.description}</p>
              </div>
              <div className="logSourceMeta">
                <span className="pill pill-neutral">{source.kind}</span>
                <span className="muted tiny">{source.available ? formatSize(source.size) : "Unavailable"}</span>
              </div>
            </button>
          ))}
          {!loadingSources && sources.length === 0 ? (
            <p className="muted tiny" style={{ margin: 0 }}>
              No runtime log sources were configured.
            </p>
          ) : null}
        </div>
      </div>

      <div className="card logInspectorViewer">
        <div className="logInspectorViewerHeader">
          <div>
            <p className="muted tiny">Inspection only</p>
            <h2 className="logInspectorSectionTitle">
              {selectedMeta?.label ?? "Select a runtime log"}
            </h2>
            <p className="muted tiny">
              {selectedMeta?.description ?? "Choose a runtime source to inspect its live output."}
            </p>
          </div>
          <div className="logInspectorViewerActions">
            <label className="logInspectorToggle">
              <input
                checked={autoRefresh}
                onChange={(event) => setAutoRefresh(event.target.checked)}
                type="checkbox"
              />
              Auto-refresh
            </label>
            <button className="button buttonSmall" onClick={() => void refreshNow()} type="button">
              Refresh
            </button>
          </div>
        </div>

        {error ? <p className="pill pill-warn">{error}</p> : null}

        <div className="logInspectorToolbar">
          <div className="control" style={{ margin: 0 }}>
            <label className="muted tiny" htmlFor="log-lines">
              Lines per page
            </label>
            <input
              id="log-lines"
              className="dateInput"
              max={2000}
              min={20}
              onChange={(event) => {
                setLines(Number(event.target.value));
                setPage(1);
              }}
              type="number"
              value={lines}
            />
          </div>
          <div className="logInspectorMetaPanel">
            <p className="muted tiny">
              Source path: <code>{selectedMeta?.path ?? "n/a"}</code>
            </p>
            <p className="muted tiny">
              {selectedMeta?.available
                ? `Updated ${selectedMeta.mtime ?? "unknown"}`
                : "Waiting for this service to produce a log file."}
            </p>
          </div>
        </div>

        {!selectedSource ? (
          <div className="logInspectorEmpty">
            <p className="muted tiny">No runtime log source selected.</p>
          </div>
        ) : !selectedMeta?.available ? (
          <div className="logInspectorEmpty">
            <p className="muted tiny">
              This source is allowlisted, but no log file exists yet for the current dashboard run.
            </p>
          </div>
        ) : !logRead ? (
          <div className="skeleton" style={{ minHeight: 320 }} />
        ) : (
          <div className="stack" style={{ gap: 14 }}>
            <div className="adminRow">
              <p className="muted tiny" style={{ margin: 0 }}>
                {logRead.path} • {formatSize(logRead.size)} • {logRead.totalLines} lines total
              </p>
              <div className="adminRowRight">
                <button
                  className="button buttonSmall"
                  disabled={loadingLog || logRead.page <= 1}
                  onClick={() => setPage(1)}
                  type="button"
                >
                  First
                </button>
                <button
                  className="button buttonSmall"
                  disabled={loadingLog || logRead.page <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Prev
                </button>
                <span className="muted tiny">
                  Page {logRead.page} / {logRead.totalPages}
                </span>
                <button
                  className="button buttonSmall"
                  disabled={loadingLog || logRead.page >= logRead.totalPages}
                  onClick={() => setPage((current) => Math.min(logRead.totalPages, current + 1))}
                  type="button"
                >
                  Next
                </button>
                <button
                  className="button buttonSmall"
                  disabled={loadingLog || logRead.page >= logRead.totalPages}
                  onClick={() => setPage(logRead.totalPages)}
                  type="button"
                >
                  Last
                </button>
              </div>
            </div>
            <pre className="codeBlock logInspectorOutput">
              {loadingLog ? "Refreshing log output..." : logRead.content || "(empty)"}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}
