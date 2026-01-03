"use client";

type LlmBreakdownResult = {
  task_id?: string;
  content?: string;
  status?: string;
  created_count?: number;
  error?: string | null;
  depth?: number;
};

export type LlmBreakdownProgress = {
  active: boolean;
  status: string;
  runId: string | null;
  startedAt: string | null;
  updatedAt: string | null;
  tasksTotal: number;
  tasksCompleted: number;
  tasksFailed: number;
  tasksPending: number;
  current: { task_id?: string; content?: string; label?: string; depth?: number } | null;
  error?: string | null;
  recent?: LlmBreakdownResult[];
};

function statusBadge(progress: LlmBreakdownProgress | null): { label: string; tone: "ok" | "warn" | "neutral" } {
  if (!progress) return { label: "Unknown", tone: "neutral" };
  if (progress.status === "failed") return { label: "Failed", tone: "warn" };
  if (progress.active) return { label: "Running", tone: "ok" };
  if (progress.status === "completed") return { label: "Completed", tone: "ok" };
  return { label: "Idle", tone: "neutral" };
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replace("T", " ");
}

export function LlmBreakdownStatus({
  progress,
  loading,
  onRefresh
}: {
  progress: LlmBreakdownProgress | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const badge = statusBadge(progress);
  const total = progress?.tasksTotal ?? 0;
  const completed = progress?.tasksCompleted ?? 0;
  const failed = progress?.tasksFailed ?? 0;
  const pending = progress?.tasksPending ?? 0;
  const ratio = total > 0 ? Math.min(1, completed / total) : 0;
  const current = progress?.current;
  const recent = progress?.recent ?? [];

  return (
    <section className="card">
      <header className="cardHeader">
        <h2>LLM Breakdown Queue</h2>
        <button className="button buttonSmall" type="button" onClick={onRefresh} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      {!progress ? (
        <div className="skeleton" style={{ minHeight: 160 }} />
      ) : (
        <div className="list">
          <div className="row">
            <div className={`dot dot-${badge.tone}`} />
            <div className="rowMain">
              <p className="rowTitle">{badge.label}</p>
              <p className="muted tiny">
                {completed}/{total} completed • {pending} pending • {failed} failed
              </p>
            </div>
            <p className="rowDetail">Updated {formatTimestamp(progress.updatedAt)}</p>
          </div>

          <div className="leaderBar" aria-hidden>
            <div className="leaderFill" style={{ width: `${Math.round(ratio * 100)}%`, background: "var(--ok)" }} />
          </div>

          {progress.error ? <p className="muted tiny">Error: {progress.error}</p> : null}

          <div className="row">
            <div className="dot dot-neutral" />
            <div className="rowMain">
              <p className="rowTitle">Current task</p>
              <p className="muted tiny">
                {current?.content ?? "No task running"}
                {typeof current?.depth === "number" ? ` (depth ${current.depth})` : ""}
              </p>
            </div>
            <p className="rowDetail">{current?.label ?? "—"}</p>
          </div>

          {recent.length ? (
            <div className="row">
              <div className="dot dot-neutral" />
              <div className="rowMain">
                <p className="rowTitle">Recent tasks</p>
                <p className="muted tiny">
                  {recent
                    .map((item) => {
                      const status = item.status ?? "done";
                      const content = item.content ?? "Untitled";
                      return `${content} (${status})`;
                    })
                    .join(" • ")}
                </p>
              </div>
              <p className="rowDetail">Run {progress.runId ?? "—"}</p>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
