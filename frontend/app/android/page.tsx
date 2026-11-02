"use client";

import { useEffect, useMemo, useState } from "react";
import { DashboardSettings } from "../components/DashboardSettings";
import { LeaderboardCard } from "../components/LeaderboardCard";
import { LoadingBar } from "../components/LoadingBar";
import { MobileAbout } from "../components/MobileAbout";
import { PlotCard } from "../components/PlotCard";
import { StatCard } from "../components/StatCard";
import { PLOT_HELP } from "../lib/dashboardCopy";
import {
  command,
  completionFigure,
  mobileSettings,
  mobileSettingsRequest,
  projectColor,
  weekDate,
} from "../lib/mobile";
import type { MobileState } from "../lib/mobile";

const TABS = ["Overview", "Projects", "Activity", "Control Panel"] as const;
type Tab = (typeof TABS)[number];
const INITIAL_UI = {
  tab: "Overview" as Tab,
  query: "",
  priority: 0,
  range: 8,
  week: 7,
};

export default function AndroidDashboard() {
  const [state, setState] = useState<MobileState | null>(null);
  const [ui, setUi] = useState(INITIAL_UI);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [persist, setPersist] = useState(false);
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("todoist-ui") ?? "null");
      if (saved) setUi({ ...INITIAL_UI, ...saved });
    } catch {
      /* Start with defaults. */
    }
    setPersist(true);
    const receive = (event: Event) =>
      setState((previous) => ({
        ...previous,
        ...(event as CustomEvent<MobileState>).detail,
      }));
    const fail = (event: Event) =>
      setError(String((event as CustomEvent<string>).detail));
    window.addEventListener("todoist-state", receive);
    window.addEventListener("todoist-error", fail);
    if (window.Todoist) window.Todoist.ready();
    else setError("Open this dashboard in the Android app.");
    return () => {
      window.removeEventListener("todoist-state", receive);
      window.removeEventListener("todoist-error", fail);
    };
  }, []);
  useEffect(() => {
    if (persist) localStorage.setItem("todoist-ui", JSON.stringify(ui));
  }, [ui, persist]);
  useEffect(() => {
    const back = () =>
      ui.tab === "Overview"
        ? command("close")
        : setUi((current) => ({ ...current, tab: "Overview" }));
    window.addEventListener("todoist-back", back);
    return () => window.removeEventListener("todoist-back", back);
  }, [ui.tab]);
  const patch = (value: Partial<typeof ui>) =>
    setUi((current) => ({ ...current, ...value }));
  const model = state?.model;
  const settings = state?.preferences
    ? mobileSettings(state.preferences)
    : null;
  const eventsKey = JSON.stringify(settings?.plotEvents ?? []);
  const figures = useMemo(
    () =>
      model
        ? [false, true].map((cumulative) =>
            completionFigure(
              model,
              ui.range,
              JSON.parse(eventsKey),
              cumulative,
            ),
          )
        : [],
    [model, ui.range, eventsKey],
  );
  const busy = state?.loading || state?.syncing;
  const matches =
    model?.tasks.filter(
      (task) =>
        (!ui.priority || task.priority === ui.priority) &&
        `${task.content} ${task.project} ${task.labels.join(" ")}`
          .toLowerCase()
          .includes(ui.query.trim().toLowerCase()),
    ) ?? [];
  const counts = model?.weeklyProjects[ui.week] ?? {};
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const leaderboard = model
    ? Object.entries(counts)
        .map(([name, completed]) => ({
          name,
          completed,
          percentOfCompleted: total ? (100 * completed) / total : 0,
          color: projectColor(model, name),
        }))
        .sort((a, b) => b.completed - a.completed)
    : [];
  const alert = state?.alert;
  const alertTitle = !alert?.enabled
    ? "Monitoring paused"
    : alert.level === 2
      ? "Urgent attention needed"
      : alert.level === 1
        ? "Attention needed"
        : "All clear";
  const connect = () => {
    if (!token.trim()) {
      setError("Enter your Todoist API token.");
      return;
    }
    setError("");
    command("sync", token.trim());
    setToken("");
  };
  const disconnect = () => {
    if (
      window.confirm(
        "Disconnect and remove this account's saved data from the phone?",
      )
    ) {
      command("disconnect");
      localStorage.removeItem("todoist-ui");
      setUi(INITIAL_UI);
    }
  };

  return (
    <>
      <LoadingBar active={Boolean(busy)} />
      <header className="topbar">
        <div>
          <p className="eyebrow">Todoist Assistant</p>
          <h1>{ui.tab === "Overview" ? "Dashboard" : ui.tab}</h1>
          <div className="statusPills">
            {state?.demo && <span className="pill pill-neutral">Demo</span>}
            {model && (
              <span className="muted tiny">
                {new Date(model.syncedAt).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
          </div>
        </div>
        <div className="controls">
          {state?.demo && (
            <button
              className="button buttonSmall buttonGhost"
              onClick={() => command("account")}
            >
              Back to my data
            </button>
          )}
          {state?.connected && !state.demo && (
            <button
              className="button buttonSmall"
              onClick={() => command("sync")}
              disabled={busy}
            >
              Refresh
            </button>
          )}
          {state?.syncing && (
            <button
              className="button buttonSmall buttonGhost"
              onClick={() => command("cancel")}
            >
              Cancel sync
            </button>
          )}
        </div>
      </header>
      <nav className="segmented mobileNav" aria-label="Dashboard sections">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`seg ${ui.tab === tab ? "segActive" : ""}`}
            aria-current={ui.tab === tab ? "page" : undefined}
            onClick={() => {
              patch({ tab, query: "", priority: 0 });
              setError("");
            }}
          >
            {tab}
          </button>
        ))}
      </nav>
      {error && (
        <p className="pill pill-warn" role="alert">
          {error}
        </p>
      )}
      {state?.message && !state.demo && (
        <p
          className={`tiny ${state.syncing ? "muted" : "mobileNotice"}`}
          role="status"
        >
          {state.message}
        </p>
      )}
      {!state && !error && <p className="muted">Opening dashboard…</p>}

      {state && (!model || ui.tab === "Control Panel") && (
        <section className="card">
          <header className="cardHeader">
            <h2>Todoist account</h2>
            {state.connected && (
              <span className="pill pill-good">Connected</span>
            )}
          </header>
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              connect();
            }}
          >
            <label className="control">
              API token
              <input
                type="password"
                className="textInput"
                autoComplete="off"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                disabled={busy}
              />
            </label>
            <div className="controls">
              <button
                className="button buttonSmall"
                type="submit"
                disabled={busy}
              >
                Connect and sync
              </button>
              {!state.demo && (
                <button
                  className="button buttonSmall buttonGhost"
                  type="button"
                  onClick={() => command("demo")}
                  disabled={busy}
                >
                  Explore a demo
                </button>
              )}
              {state.connected && (
                <button
                  className="button buttonSmall buttonGhost"
                  type="button"
                  onClick={disconnect}
                  disabled={busy}
                >
                  Disconnect
                </button>
              )}
            </div>
          </form>
        </section>
      )}
      {state && ui.tab === "Control Panel" && (
        <>
          <DashboardSettings
            request={mobileSettingsRequest}
            onAfterMutation={() => setError("")}
          />
          <MobileAbout version={state.version} preview={state.preview} />
        </>
      )}

      {model && ui.tab === "Overview" && (
        <>
          <div className="statsRow mobileStats">
            {model.historyAvailable ? (
              <StatCard
                name="This week"
                value={model.weeks[8]}
                deltaPercent={null}
                inverseDelta={false}
                currentPeriod={model.weekStart}
                previousPeriod={weekDate(model.weekStart, -1)}
                comparison={false}
              />
            ) : (
              <section className="stat">
                <p className="muted">Completed this week</p>
                <p>History unavailable</p>
              </section>
            )}
            <section className="stat mobileUrgency" data-level={alert?.level}>
              <div className="statTop">
                <p className="muted">Urgency</p>
              </div>
              <p className="statValue">{alert?.matches ?? 0}</p>
              <button
                className="mobileRuleLink"
                onClick={() => patch({ tab: "Control Panel" })}
              >
                {alertTitle}
              </button>
              <p className="muted tiny">
                {model.tasks.length} active tasks · P1 {model.priorities[0]} ·
                P2 {model.priorities[1]}
              </p>
            </section>
          </div>
          {!model.historyAvailable ? (
            <p className="pill pill-warn">
              Completion history unavailable. {model.historyWarning}
            </p>
          ) : (
            <>
              {model.historyWarning && (
                <p className="pill pill-warn">{model.historyWarning}</p>
              )}
              <div className="controls mobilePlotControls">
                <label className="control">
                  <span className="muted tiny">Range</span>
                  <select
                    className="select"
                    value={ui.range}
                    onChange={(event) =>
                      patch({ range: Number(event.target.value) })
                    }
                  >
                    <option value={4}>Last 4 weeks</option>
                    <option value={8}>Last 8 weeks</option>
                  </select>
                </label>
                {model.forecastAvailable && (
                  <span className="pill pill-neutral">
                    Forecast: {model.forecast}
                  </span>
                )}
              </div>
              <PlotCard
                title="Completed tasks"
                figure={figures[0]}
                height={340}
                compact
                help={PLOT_HELP.completedTasksPeriodically}
              />
              <section className="card">
                <header className="cardHeader">
                  <h2>Project contributions</h2>
                  <select
                    aria-label="Contribution week"
                    className="select"
                    value={ui.week}
                    onChange={(event) =>
                      patch({ week: Number(event.target.value) })
                    }
                  >
                    {model.weeks.map((_, i) => (
                      <option key={i} value={i}>
                        {i === 8
                          ? "This week"
                          : i === 7
                            ? "Last completed week"
                            : weekDate(model.weekStart, i - 8)}
                      </option>
                    ))}
                  </select>
                </header>
                {leaderboard.length ? (
                  <LeaderboardCard items={leaderboard} />
                ) : (
                  <p className="muted">No completions in this week.</p>
                )}
              </section>
              <PlotCard
                title="Cumulative completions"
                figure={figures[1]}
                height={320}
                compact
              />
            </>
          )}
        </>
      )}

      {model && (ui.tab === "Projects" || ui.tab === "Activity") && (
        <div className="controls mobileSearch">
          <label className="control">
            <span className="muted tiny">Search</span>
            <input
              className="textInput"
              type="search"
              aria-label="Search tasks, projects or activity"
              placeholder={
                ui.tab === "Projects"
                  ? "Tasks, projects, labels"
                  : "Recent activity"
              }
              value={ui.query}
              onChange={(event) => patch({ query: event.target.value })}
            />
          </label>
          {ui.tab === "Projects" && (
            <label className="control">
              <span className="muted tiny">Priority</span>
              <select
                className="select"
                aria-label="Filter task priority"
                value={ui.priority}
                onChange={(event) =>
                  patch({ priority: Number(event.target.value) })
                }
              >
                <option value={0}>All</option>
                {[4, 3, 2, 1].map((value) => (
                  <option key={value} value={value}>
                    P{5 - value}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}
      {model && ui.tab === "Projects" && (
        <>
          <p className="muted tiny">
            {matches.length} of {model.tasks.length} active tasks
          </p>
          {model.projects.map((project) => {
            const tasks = matches.filter(
              (task) => task.projectId === project.id,
            );
            if (!tasks.length && (ui.query || ui.priority)) return null;
            return (
              <details
                key={project.id}
                className="card mobileProject"
                open={Boolean(ui.query || ui.priority)}
              >
                <summary>
                  <span>{project.path}</span>
                  <span className="pill pill-neutral">{tasks.length}</span>
                </summary>
                {tasks.length ? (
                  tasks.map((task) => (
                    <article className="mobileTask" key={task.id}>
                      <div>
                        <strong>{task.content}</strong>
                        <p className="muted tiny">
                          {[
                            task.due,
                            ...task.labels.map((label) => `#${label}`),
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                        {task.deadline && (
                          <p className="muted tiny">
                            Deadline: {task.deadline}
                          </p>
                        )}
                      </div>
                      <span
                        className={`pill pill-${task.priority === 4 ? "warn" : "neutral"}`}
                      >
                        P{5 - task.priority}
                      </span>
                    </article>
                  ))
                ) : (
                  <p className="muted tiny">No active tasks.</p>
                )}
              </details>
            );
          })}
          {!matches.length && (ui.query || ui.priority) && (
            <p className="muted">No tasks match.</p>
          )}
        </>
      )}
      {model && ui.tab === "Activity" && (
        <section className="card">
          <header className="cardHeader">
            <h2>Recent activity</h2>
          </header>
          {model.activity
            .filter((event) =>
              `${event.kind === "uncompleted" ? "undone" : event.kind} ${event.content} ${event.project}`
                .toLowerCase()
                .includes(ui.query.trim().toLowerCase()),
            )
            .map((event) => (
              <article className="mobileTask" key={event.id}>
                <div>
                  <strong>{event.content || event.project}</strong>
                  <p className="muted tiny">
                    {event.project} · {new Date(event.date).toLocaleString()}
                  </p>
                </div>
                <span className="pill pill-neutral">
                  {event.kind === "uncompleted" ? "Undone" : event.kind}
                </span>
              </article>
            ))}
        </section>
      )}
    </>
  );
}
