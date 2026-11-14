import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 412, height: 915 });
  await page.addInitScript(() => {
    const model = {
      syncedAt: "2026-11-02T10:00:00Z",
      weekStart: "2026-11-02",
      weeks: [30, 34, 40, 38, 42, 41, 45, 45, 3],
      priorities: [0, 1, 0, 1],
      forecast: 40,
      forecastAvailable: true,
      historyAvailable: true,
      historyWarning: "",
      weeklyProjects: [30, 34, 40, 38, 42, 41, 45, 45, 3].map((total) => ({
        Work: Math.ceil(total * 0.6),
        Personal: total - Math.ceil(total * 0.6),
      })),
      projectForecasts: { Work: 25, Personal: 15 },
      projectColors: { Work: "blue", Personal: "violet" },
      projects: [
        { id: "work", path: "Work" },
        { id: "life", path: "Personal" },
      ],
      tasks: [
        {
          id: "a",
          projectId: "work",
          project: "Work",
          content: "Review the release checklist",
          priority: 3,
          due: "2026-11-03",
          deadline: "",
          labels: ["next"],
        },
        {
          id: "b",
          projectId: "life",
          project: "Personal",
          content: "Go for a walk",
          priority: 1,
          due: "",
          deadline: "",
          labels: [],
        },
      ],
      activity: [
        {
          id: "e",
          kind: "uncompleted",
          content: "Reopened a milestone",
          project: "Work",
          date: "2026-11-02T09:00:00Z",
        },
      ],
    };
    const preferences = JSON.parse(sessionStorage.getItem("test-preferences") ?? "null") ?? {
      rules: {
        enabled: true,
        fire: true,
        priority: true,
        due: true,
        deadline: true,
        priorities: [4, 3],
        fireLabels: "fire",
        priorityMin: 1,
        dueDays: 0,
        dueMin: 1,
        deadlineDays: 0,
        deadlineMin: 1,
      },
      settings: null,
      labels: ["fire", "next"],
    };
    const state = {
      version: "0.4.1",
      preview: true,
      loading: false,
      syncing: false,
      connected: false,
      demo: Boolean(sessionStorage.getItem("test-demo")),
      message: "",
      model: null as typeof model | null,
      preferences,
      alert: { enabled: preferences.rules.enabled, level: 1, matches: 1 },
    };
    if (state.demo) state.model = model;
    const send = () =>
      window.dispatchEvent(new CustomEvent("todoist-state", { detail: structuredClone(state) }));
    window.addEventListener("test-empty-activity", () => {
      model.activity = [];
      send();
    });
    window.addEventListener("test-large-task-account", () => {
      model.projects = Array.from({ length: 20 }, (_, project) => ({ id: `large-${project}`, path: `Large project ${project}` }));
      model.tasks = Array.from({ length: 2000 }, (_, index) => ({
        id: `task-${index}`, projectId: `large-${Math.floor(index / 100)}`, project: `Large project ${Math.floor(index / 100)}`,
        content: `Task ${index}`, priority: 1, due: "", deadline: "", labels: [],
      }));
      send();
    });
    window.addEventListener("test-large-lifespans", () => {
      const data = (model as typeof model & { plotData: { lifespans: { completedAt: string; seconds: number }[] } }).plotData;
      data.lifespans = Array.from({ length: 2000 }, (_, index) => ({ completedAt: "2026-10-01", seconds: index + 1 }));
      model.tasks.push({ id: "large-history-marker", projectId: "work", project: "Work", content: "Marker", priority: 1, due: "", deadline: "", labels: [] });
      send();
    });
    window.addEventListener("test-activity-freshness", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = model as typeof model & { activitySyncedAt: string; activityTotal: number; plotData: { historyComplete: boolean } };
      data.activitySyncedAt = "2026-11-02T08:00:00Z";
      data.activityTotal = 250;
      data.plotData.historyComplete = false;
      model.syncedAt = "2026-11-02T10:00:00Z";
      model.historyWarning = "Older activity could not be refreshed.";
      state.demo = false;
      state.connected = true;
      send();
    });
    window.addEventListener("test-activity-unavailable", () => {
      model.historyAvailable = false;
      model.activity = [];
      model.historyWarning = "Activity access was denied.";
      state.demo = false;
      state.connected = true;
      send();
    });
    window.addEventListener("test-habits", () => {
      window.dispatchEvent(new Event("test-analysis"));
      (model as typeof model & { habitTracker: unknown }).habitTracker = {
        weekBeg: "2026-10-19", weekEnd: "2026-10-25", trackedCount: 1,
        totals: { weeklyCompleted: 4, weeklyRescheduled: 2, allTimeCompleted: 8, allTimeRescheduled: 2 },
        items: [{ taskId: "habit", name: "Take a walk", projectName: "Personal", weeklyCompleted: 4, weeklyRescheduled: 2, allTimeCompleted: 8, allTimeRescheduled: 2, reliability: 80 }],
        history: [{ label: "2026-10-19 to 2026-10-25", completed: 4, rescheduled: 2 }],
      };
      (model as typeof model & { plotData: { historyComplete: boolean } }).plotData.historyComplete = false;
      send();
    });
    window.addEventListener("test-many-projects", () => {
      for (let i = 0; i < 12; i++) {
        const name = `Long project name ${i} with research and planning`;
        model.weeklyProjects.forEach((week) => {
          (week as Record<string, number>)[name] = i + 1;
        });
        (model.projectForecasts as Record<string, number>)[name] = i + 1;
        (model.projectColors as Record<string, string>)[name] = "blue";
      }
      send();
    });
    window.addEventListener("test-long-history", () => {
      model.weeks.unshift(...Array(20).fill(10));
      model.weeklyProjects.unshift(...Array.from({ length: 20 }, () => ({ Work: 6, Personal: 4, Historic: 1 })));
      send();
    });
    window.addEventListener("test-analysis", () => {
      delete (model as typeof model & { activitySyncedAt?: string }).activitySyncedAt;
      const makeDay = (date: string, completed: number, added: number) => ({
        date, effectiveCompletions: completed,
        counts: { added, completed, uncompleted: 0, updated: 0, deleted: 0, rescheduled: 0 },
        projects: { Work: completed },
        hours: Array.from({ length: 24 }, (_, hour) => hour === 10 ? added + completed : 0),
      });
      const plotData = {
        historyComplete: true, historyStart: "2026-09-01", historyAsOf: "2026-11-02",
        dailyActivity: [makeDay("2026-09-30", 2, 7), makeDay("2026-10-01", 4, 0), makeDay("2026-10-12", 1, 7), makeDay("2026-10-19", 1, 0), makeDay("2026-10-26", 1, 0), makeDay("2026-11-02", 3, 0)],
        lifespans: [{ completedAt: "2026-10-01", seconds: 60 }, { completedAt: "2026-10-02", seconds: 86400 }],
        hierarchy: [
          { id: "work", name: "Work", parentId: "", rootName: "Work", color: "blue", archived: false, createdAt: "2026-09-01", lastEventAt: "2026-11-02", archivedAt: "", openTasks: 1, dailyCompletions: [{date: "2026-10-01", count: 4}, {date: "2026-11-02", count: 3}], dailyEvents: [{date: "2026-10-01", count: 4}, {date: "2026-10-02", count: 1}, {date: "2026-11-02", count: 3}], weeklyCounts: { 7: 10, 8: 3 } },
          { id: "old", name: "Reopened", parentId: "work", rootName: "Work", color: "blue", archived: false, createdAt: "2026-09-01", lastEventAt: "2026-10-01", archivedAt: "2025-01-01", weeklyCounts: { 7: 1 } },
          { id: "old-two", name: "Reopened", parentId: "work", rootName: "Work", color: "blue", archived: false, createdAt: "2026-09-02", lastEventAt: "2026-10-01", archivedAt: "", weeklyCounts: { 7: 1 } },
        ],
        taskCounts: [{ date: "2026-11-01", total: 2, p1: 1, p2: 1, p3: 0, p4: 0 }, { date: "2026-11-02", total: 3, p1: 2, p2: 1, p3: 0, p4: 0 }],
      };
      (model as typeof model & { plotData: typeof plotData }).plotData = plotData;
      send();
    });
    window.addEventListener("test-timeline-large", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = (model as typeof model & { plotData: { hierarchy: Record<string, unknown>[] } }).plotData;
      const work = data.hierarchy[0];
      work.dailyEvents = Array.from({ length: 90 }, (_, i) => ({ date: new Date(Date.UTC(2026, 0, i + 1)).toISOString().slice(0, 10), count: 1 }));
      work.dailyCompletions = work.dailyEvents;
      for (let i = 0; i < 25; i++) data.hierarchy.push({ id: `p${i}`, name: `Project ${i}`, rootName: `Project ${i}`, parentId: "", archived: i === 0, createdAt: "2026-01-01", lastEventAt: "", archivedAt: "", dailyEvents: [], dailyCompletions: [], weeklyCounts: {} });
      data.hierarchy.push({ id: "unknown", name: "Unknown project", rootName: "Unknown project", parentId: "", archived: false, metadataKnown: false, createdAt: "", lastEventAt: "", archivedAt: "", dailyEvents: [], dailyCompletions: [], weeklyCounts: {} });
      model.tasks.push({ id: "child", parentId: "a", projectId: "work", project: "Work", content: "A subtask", priority: 1, due: "", deadline: "", labels: [] } as typeof model.tasks[number]);
      send();
    });
    window.addEventListener("test-history-gap", () => {
      const data = (model as typeof model & { plotData: { historyComplete: boolean; historyStart: string; historyAsOf: string } }).plotData;
      data.historyComplete = false;
      data.historyStart = "2026-10-10";
      data.historyAsOf = "2026-10-20";
      send();
    });
    window.addEventListener("test-history-stale", () => {
      const data = (model as typeof model & { plotData: { historyComplete: boolean; historyAsOf: string } }).plotData;
      data.historyComplete = true;
      data.historyAsOf = "2026-10-10";
      send();
    });
    window.addEventListener("test-current-week-partial", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = (model as typeof model & { plotData: { historyComplete: boolean; historyStart: string; historyAsOf: string }; activitySyncedAt: string });
      data.plotData.historyComplete = false;
      data.plotData.historyStart = "2026-11-03";
      data.plotData.historyAsOf = "2026-11-03";
      data.activitySyncedAt = "2026-11-03T10:00:00Z";
      model.syncedAt = "2026-11-03T10:00:00Z";
      send();
    });
    window.addEventListener("test-stale-same-day", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = (model as typeof model & { plotData: { historyAsOf: string }; activitySyncedAt: string });
      data.plotData.historyAsOf = "2026-11-03";
      data.activitySyncedAt = "2026-11-03T08:00:00Z";
      model.syncedAt = "2026-11-03T10:00:00Z";
      send();
    });
    window.addEventListener("test-long-pace", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = (model as typeof model & { plotData: { dailyActivity: { date: string; effectiveCompletions: number; counts: Record<string, number>; hours: number[]; projects: Record<string, number> }[] } }).plotData;
      data.dailyActivity.unshift({ date: "2026-09-01", effectiveCompletions: 1, counts: { completed: 1 }, hours: Array(24).fill(0), projects: { Work: 1 } });
      send();
    });
    window.addEventListener("test-empty-account", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = (model as typeof model & { plotData: { historyComplete: boolean; historyStart: string; historyAsOf: string; dailyActivity: unknown[]; taskCounts: unknown[]; hierarchy: unknown[]; lifespans: unknown[] }; activitySyncedAt: string });
      data.plotData = { historyComplete: true, historyStart: "2026-11-02", historyAsOf: "2026-11-03", dailyActivity: [], taskCounts: [], hierarchy: [], lifespans: [] };
      data.activitySyncedAt = "2026-11-03T10:00:00Z";
      model.syncedAt = "2026-11-03T10:00:00Z";
      model.activity = [];
      model.projects = [];
      model.tasks = [];
      model.weeks = model.weeks.map(() => 0);
      model.weeklyProjects = model.weeklyProjects.map(() => ({} as { Work: number; Personal: number }));
      send();
    });
    window.addEventListener("test-special-names", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = (model as typeof model & { plotData: { dailyActivity: { date: string; effectiveCompletions: number; projects: Record<string, number>; counts: Record<string, number>; hours: number[] }[] } }).plotData;
      data.dailyActivity = [
        { date: "2026-10-01", effectiveCompletions: 7, projects: JSON.parse('{"constructor":2,"__proto__":1,"All projects":4}'), counts: { completed: 7 }, hours: Array(24).fill(0) },
        { date: "2026-11-02", effectiveCompletions: 3, projects: { Work: 3 }, counts: { completed: 3 }, hours: Array(24).fill(0) },
      ];
      model.weeklyProjects[7] = JSON.parse('{"constructor":2,"__proto__":1,"All projects":4}');
      model.weeks[7] = 7;
      model.weeklyProjects[8] = { Work: 3, Personal: 0 };
      model.weeks[8] = 3;
      send();
    });
    window.addEventListener("test-grouping-account", () => {
      window.dispatchEvent(new Event("test-analysis"));
      const data = (model as typeof model & { plotData: { hierarchy: Record<string, unknown>[] }; adjustments: unknown });
      for (const id of ["one", "two"]) data.plotData.hierarchy.push({ id, name: "Old", rootName: "Work", parentId: "", archived: true, createdAt: "2026-09-01", lastEventAt: "2026-10-01", archivedAt: "2026-10-01", weeklyCounts: {} });
      data.plotData.hierarchy.push({ id: "life", name: "Personal", rootName: "Personal", parentId: "", archived: false, createdAt: "2026-09-01", lastEventAt: "2026-10-01", archivedAt: "", weeklyCounts: {} });
      data.adjustments = { mappings: { Old: "Work", Missing: "Gone", Conflict: "Other" }, archivedParents: ["Legacy", "Conflict"] };
      state.demo = false;
      state.connected = true;
      state.model = model;
      send();
    });
    window.addEventListener("test-grouping-search", () => {
      window.dispatchEvent(new Event("test-grouping-account"));
      const data = (model as typeof model & { plotData: { hierarchy: Record<string, unknown>[] } }).plotData;
      data.hierarchy.push(
        { id: "old-source", name: "Łódź archive", previousNames: ["Stary zeszyt"], rootName: "Łódź archive", parentId: "", archived: true, weeklyCounts: {} },
        { id: "old-child", name: "Archived child", rootName: "Łódź archive", parentId: "old-source", archived: true, weeklyCounts: {} },
        { id: "indirect-child", name: "Indirect child", rootName: "Łódź archive", parentId: "", archived: true, weeklyCounts: {} },
        { id: "old-parent", name: "Zażółć Parent", previousNames: ["Dawny dział"], rootName: "Work", parentId: "work", archived: true, weeklyCounts: {} },
        { id: "shared-a", name: "Shared parent", rootName: "Shared parent · shared-a", parentId: "", archived: true, weeklyCounts: {} },
        { id: "shared-b", name: "Shared parent", rootName: "Shared parent · shared-b", parentId: "", archived: true, weeklyCounts: {} },
      );
      send();
    });
    window.addEventListener("test-grouping-missing-id", () => {
      window.dispatchEvent(new Event("test-grouping-account"));
      (model as typeof model & { adjustments: unknown }).adjustments = {
        mappings: { Old: "Work" }, archivedParents: [],
        projectMappings: { one: { targetId: "missing-parent", targetName: "Personal" } },
      };
      send();
    });
    window.addEventListener("test-grouping-renamed-parent", () => {
      window.dispatchEvent(new Event("test-grouping-account"));
      (model as typeof model & { adjustments: unknown }).adjustments = {
        mappings: { Old: "Work" }, archivedParents: [],
        projectMappings: { one: { targetId: "life", targetName: "Earlier name" } },
      };
      send();
    });
    window.Todoist = {
      ready: send,
      command: (name: string, argument: string) => {
        if (name === "close") sessionStorage.setItem("test-close", "yes");
        if (name === "demo") {
          state.demo = true;
          state.model = model;
          sessionStorage.setItem("test-demo", "1");
        }
        if (name === "account") {
          state.demo = false;
          state.model = null;
          sessionStorage.removeItem("test-demo");
        }
        if (name === "save-adjustments" && state.model) {
          const { mappings, archivedParents, projectMappings } = JSON.parse(argument);
          (model as typeof model & { adjustments: unknown }).adjustments = { mappings, archivedParents, projectMappings };
          sessionStorage.setItem("test-saved-adjustments", JSON.stringify({ mappings, archivedParents, projectMappings }));
          state.message = "Project adjustments saved.";
        }
        if (name === "import-adjustments") sessionStorage.setItem("test-import-requested", "yes");
        send();
      },
      getSettings: () => JSON.stringify(state.preferences),
      saveSettings: (json: string) => {
        const value = JSON.parse(json);
        state.preferences = { ...state.preferences, ...value };
        state.alert.enabled = value.rules.enabled;
        sessionStorage.setItem("test-preferences", JSON.stringify(state.preferences));
        setTimeout(send, 0);
        return json;
      },
    };
  });
  await page.goto("/android");
  await page.getByRole("button", { name: "Explore a demo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Back to my data", exact: true })).toBeVisible();
});

test("large projects render task rows incrementally and search all tasks", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-large-task-account")));
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(page.getByText("2000 of 2000 active tasks")).toBeVisible();
  await expect(page.locator(".mobileProject .mobileTask")).toHaveCount(0);
  const project = page.locator(".mobileProject").filter({ hasText: "Large project 0" });
  await project.locator("summary").click();
  await expect(project.locator(".mobileTask")).toHaveCount(20);
  await project.getByRole("button", { name: "Show more tasks" }).click();
  await expect(project.locator(".mobileTask")).toHaveCount(40);
  await page.getByRole("searchbox").fill("Task 1999");
  await expect(page.getByText("1 of 2000 active tasks")).toBeVisible();
  await expect(page.getByText("Task 1999", { exact: true })).toBeVisible();
  await page.getByRole("searchbox").fill("");
  await expect(page.getByText("2000 of 2000 active tasks")).toBeVisible();
  await expect(project.locator(".mobileTask")).toHaveCount(40);
});

test("a large history update appears in the chart after returning to Overview", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await page.evaluate(() => window.dispatchEvent(new Event("test-large-lifespans")));
  await expect(page.getByText("3 of 3 active tasks")).toBeVisible();
  await expect(page.getByRole("region", { name: "Task Lifespans: Time to Completion" })).toHaveCount(0);
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  const lifespan = page.getByRole("region", { name: "Task Lifespans: Time to Completion" });
  await lifespan.scrollIntoViewIfNeeded();
  const plot = lifespan.locator(".js-plotly-plot");
  await expect(plot).toBeVisible();
  await expect.poll(() => plot.evaluate((node) =>
    (node as HTMLElement & { data: { x: number[] }[] }).data[0].x.reduce((a, b) => a + b, 0),
  )).toBe(2000);
});

test("first connection can be retried without retyping a token", async ({ page }) => {
  await page.getByRole("button", { name: "Back to my data", exact: true }).click();
  await page.evaluate(() => {
    const bridge = window.Todoist;
    if (!bridge) throw new Error("Missing Android bridge");
    const original = bridge.command;
    bridge.command = (name, argument) => {
      if (name !== "sync") return original(name, argument);
      sessionStorage.setItem("attempts", String(Number(sessionStorage.getItem("attempts")) + 1));
      window.dispatchEvent(new CustomEvent("todoist-state", { detail: { syncing: false, message: "No network connection." } }));
    };
  });
  const token = page.getByLabel("API token");
  await token.fill("private-test-token");
  await page.getByRole("button", { name: "Connect and sync" }).click();
  await expect(page.getByText("No network connection.")).toBeVisible();
  await expect(token).toHaveValue("private-test-token");
  await page.getByRole("button", { name: "Connect and sync" }).click();
  expect(await page.evaluate(() => sessionStorage.getItem("attempts"))).toBe("2");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", {
    detail: { connected: true, syncing: false, message: "Sync complete. Your history is available offline." },
  })));
  await expect(token).toHaveValue("");
  await expect(page.getByText("Account saved")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry sync" })).toBeVisible();
});

test("empty activity is described separately from unavailable history", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-empty-activity")));
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText("No activity in the available history.")).toBeVisible();
});

test("activity reports saved scope, freshness and incomplete history while sync fails", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-activity-freshness")));
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText(/Activity last synchronized/)).toContainText("out of date");
  await expect(page.getByText(/Earlier activity history is incomplete/)).toBeVisible();
  await expect(page.getByText("Older activity could not be refreshed.")).toBeVisible();
  await expect(page.getByText("Showing the latest 1 of 250 saved events. Search covers these recent events only.")).toBeVisible();
  const search = page.getByRole("searchbox", { name: "Search tasks, projects or activity" });
  await search.fill("not a recent record");
  await expect(page.getByText("No recent activity matches your search; older saved events are not searched.")).toBeVisible();
  await search.fill("uncompleted");
  await expect(page.getByText("Reopened a milestone")).toBeVisible();
  await search.fill("undone");
  await expect(page.getByText("Reopened a milestone")).toBeVisible();
  await search.fill("reopened");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", { detail: { syncing: true, message: "Updating activity" } })));
  await expect(page.getByText("Showing saved activity while synchronization is in progress.")).toBeVisible();
  await expect(search).toHaveValue("reopened");
  await expect(page.getByText("Reopened a milestone")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", { detail: { syncing: false, message: "No network connection. Saved history is unchanged." } })));
  await expect(page.getByText("No network connection. Saved history is unchanged.")).toBeVisible();
  await expect(page.getByText("Reopened a milestone")).toBeVisible();
  await expect(search).toHaveValue("reopened");
  await page.setViewportSize({ width: 320, height: 700 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test("unavailable activity is not represented as an empty account", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-activity-unavailable")));
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText("Activity history is unavailable. Activity access was denied.")).toBeVisible();
  await expect(page.getByText("No activity in the available history.")).toHaveCount(0);
});

test("habit tracker labels recorded counts and hides unavailable activity metrics", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-habits")));
  const habits = page.getByRole("region", { name: "Habit tracker" });
  await expect(habits).toContainText("last full week 2026-10-19 to 2026-10-25");
  await expect(habits).toContainText("Habit history is incomplete or out of date");
  await expect(habits).toContainText("4 recorded completions");
  await expect(habits).toContainText("2 recorded reschedules");
  await expect(habits).toContainText("80% reliability");
  await expect(habits).toContainText("not a measure of goal adherence");
  await habits.getByText("Recorded weekly history").click();
  await expect(habits).toContainText("2026-10-19 to 2026-10-25 · 4 completed · 2 rescheduled");
  await page.evaluate(() => window.dispatchEvent(new Event("test-activity-unavailable")));
  await expect(habits).toContainText("Habit activity is unavailable");
  await expect(habits).not.toContainText("4 recorded completions");
});

test("an empty account distinguishes no activity from unavailable history", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-03T12:00:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("test-empty-account")));
  await expect(page.getByText("No activity found in the history stored on this device.")).toBeVisible();
  await expect(page.getByText("Totals use activity returned by Todoist; older history may be limited by your plan.")).toBeVisible();
  await expect(page.locator(".mobileStats .stat").first()).toContainText("This week");
  await expect(page.locator(".mobileStats .stat").first()).toContainText("0");
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(page.getByText("No projects are available on this device.")).toBeVisible();
});

test("partial and stale history never presents unavailable weeks as zero", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-03T12:00:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("test-current-week-partial")));
  await expect(page.locator(".mobileStats .stat").first()).toContainText("This week (partial)");
  await expect(page.getByText("History is unavailable for this week.")).toBeVisible();
  await page.getByLabel("Contribution week").selectOption("8");
  await expect(page.getByText("This week has partial history.")).toBeVisible();
  await page.evaluate(() => {
    window.dispatchEvent(new Event("test-analysis"));
    window.dispatchEvent(new Event("test-history-stale"));
  });
  await expect(page.locator(".mobileStats .stat").first()).toContainText("Current week unavailable");
  await expect(page.getByText(/Activity is out of date/)).toBeVisible();
  await expect(page.getByText("History is unavailable for this week.")).toBeVisible();
});

test("activity lagging a same-day task refresh is marked stale", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-03T12:00:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("test-stale-same-day")));
  await expect(page.getByText(/Activity is out of date/)).toBeVisible();
  await expect(page.locator(".mobileStats .stat").first()).toContainText("This week (partial)");
});

test("an old snapshot does not label its previous week as this week", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-10T12:00:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  await expect(page.locator(".mobileStats .stat").first()).toContainText("Current week unavailable");
  await expect(page.getByText(/Activity is out of date/)).toBeVisible();
  await expect(page.getByLabel("Contribution week").locator("option[value='8']")).toHaveText("Snapshot week");
});

test("pace filters stay selected if an interrupted refresh leaves insufficient history", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-03T12:00:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("test-long-pace")));
  const select = page.getByLabel("Weekly pace comparison");
  await expect(select.locator("option[value='6']")).toBeEnabled();
  await select.selectOption("6");
  await page.evaluate(() => window.dispatchEvent(new Event("test-history-gap")));
  await expect(select).toHaveValue("6");
  await expect(select.locator("option[value='6']")).toHaveAttribute("disabled", "");
  await expect(page.getByText("The selected 6-week baseline is unavailable for the current history.")).toBeVisible();
});

test.describe("local date changes", () => {
  test.use({ timezoneId: "America/New_York" });

  test("updates current-week labels at local midnight while the dashboard stays open", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-11-09T04:59:50Z") });
    await page.reload();
    await page.evaluate(() => {
      const bridge = window.Todoist;
      if (!bridge) throw new Error("Missing Android bridge");
      const command = bridge.command;
      bridge.command = (name, argument) => {
        if (name === "refresh-clock") sessionStorage.setItem("clock-refresh", "yes");
        command(name, argument);
      };
    });
    await expect(page.locator(".mobileStats .stat").first()).not.toContainText("Current week unavailable");
    await page.clock.fastForward(20_000);
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("clock-refresh"))).toBe("yes");
    await expect(page.locator(".mobileStats .stat").first()).toContainText("Current week unavailable");
    await expect(page.getByLabel("Contribution week").locator("option[value='8']")).toHaveText("Snapshot week");
  });
});

test("a sync update keeps the current navigation and task filters", async ({ page }) => {
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  const search = page.getByRole("searchbox", { name: "Search tasks, projects or activity" });
  const priority = page.getByLabel("Filter task priority");
  await search.fill("release");
  await priority.selectOption("3");
  await expect(page.getByText("Review the release checklist")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", {
    detail: { syncing: true, message: "Refreshing" },
  })));
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  await expect(page.getByRole("button", { name: "Projects", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(search).toHaveValue("release");
  await expect(priority).toHaveValue("3");
  await expect(page.getByText("Review the release checklist")).toBeVisible();
});

test("tab changes preserve separate searches, priority and expanded projects", async ({ page }) => {
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  const search = page.getByRole("searchbox");
  await search.fill("release");
  await page.getByLabel("Filter task priority").selectOption("3");
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(search).toHaveValue("release");
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(search).toHaveValue("");
  await search.fill("undone");
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(search).toHaveValue("release");
  await expect(page.getByLabel("Filter task priority")).toHaveValue("3");
  await search.fill("");
  await page.getByLabel("Filter task priority").selectOption("0");
  const project = page.locator(".mobileProject").filter({ hasText: "Work" });
  await project.locator("summary").click();
  await expect(project).toHaveAttribute("open", "");
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("todoist-ui") ?? "{}").openProjects)).toContain("work");
  await page.reload();
  await expect(project).toHaveAttribute("open", "");
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(search).toHaveValue("undone");
});

test("timeline choices survive recreation and rapid back closes each level", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  const timeline = page.getByRole("region", { name: "Project Timeline", exact: true });
  await timeline.getByRole("button", { name: "Show", exact: true }).click();
  await timeline.getByLabel("Timeline start date").fill("2026-10-01");
  await timeline.getByLabel("Timeline end date").fill("2026-10-02");
  await timeline.locator('[data-project-id="work"]').click();
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("todoist-ui") ?? "{}").timelineProject)).toBe("work");
  await page.reload();
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  await expect(timeline.getByLabel("Timeline start date")).toHaveValue("2026-10-01");
  await expect(timeline.getByLabel("Timeline end date")).toHaveValue("2026-10-02");
  await expect(timeline.locator('[data-project-id="work"]')).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await page.evaluate(() => {
    for (let i = 0; i < 3; i++) window.dispatchEvent(new Event("todoist-back"));
  });
  await expect(page.getByRole("button", { name: "Overview", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(timeline.getByRole("button", { name: "Show", exact: true })).toHaveAttribute("aria-expanded", "false");
  expect(await page.evaluate(() => sessionStorage.getItem("test-close"))).toBeNull();
  await page.evaluate(() => window.dispatchEvent(new Event("todoist-back")));
  expect(await page.evaluate(() => sessionStorage.getItem("test-close"))).toBe("yes");
});

test("invalid saved view preferences are isolated until the user changes the view", async ({ page }) => {
  const raw = JSON.stringify({ tab: "Projects", query: null, priority: [], range: 8 });
  await page.addInitScript((value) => localStorage.setItem("todoist-ui", value), raw);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Search tasks, projects or activity" })).toHaveValue("");
  await expect(page.getByText(/Some saved view preferences are invalid/)).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("todoist-ui"))).toBe(raw);
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByText(/Some saved view preferences are invalid/)).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("todoist-ui") ?? "{}").tab)).toBe("Activity");
});

test("an out-of-range saved week cannot crash dashboard restoration", async ({ page }) => {
  const raw = JSON.stringify({ week: -Number.MAX_SAFE_INTEGER });
  await page.evaluate((value) => localStorage.setItem("todoist-ui", value), raw);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.reload();
  await expect(page.getByRole("button", { name: "Back to my data", exact: true })).toBeVisible();
  await expect(page.getByText(/Some saved view preferences are invalid/)).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("todoist-ui"))).toBe(raw);
  expect(errors).toEqual([]);
});

test("restores an older selected week when history becomes available", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-long-history")));
  const week = page.getByLabel("Contribution week");
  await week.selectOption("-11");
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("todoist-ui") ?? "{}").week)).toBe(-11);
  await page.reload();
  await expect(page.getByText("History is unavailable for this week.")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("test-long-history")));
  await expect(week).toHaveValue("-11");
});

test("unavailable view storage does not prevent startup", async ({ page }) => {
  await page.addInitScript(() => {
    const getItem = Storage.prototype.getItem;
    Storage.prototype.getItem = function (key) {
      if (key === "todoist-ui") throw new DOMException("Storage unavailable", "SecurityError");
      return getItem.call(this, key);
    };
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.reload();
  await expect(page.getByText("View preferences could not be saved on this device.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Back to my data", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("malformed dashboard settings fall back to usable defaults", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.evaluate(() => {
    const bridge = window.Todoist;
    if (!bridge) throw new Error("Missing Android bridge");
    const preferences = JSON.parse(bridge.getSettings());
    preferences.settings = { fireLabels: 42, warnPriorityThresholds: "bad", plotEvents: [null] };
    bridge.getSettings = () => JSON.stringify(preferences);
    window.dispatchEvent(new CustomEvent("todoist-state", { detail: { preferences } }));
  });
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dashboard settings" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Enable attention monitoring" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("settings reflect native alert rules when saved copies disagree", async ({ page }) => {
  await page.evaluate(() => {
    const bridge = window.Todoist;
    if (!bridge) throw new Error("Missing Android bridge");
    const preferences = JSON.parse(bridge.getSettings());
    preferences.rules = { ...preferences.rules, enabled: false, fireLabels: "retained", priorities: [2], dueDays: 3 };
    preferences.settings = {
      enabled: true,
      fireLabels: ["wrong"],
      warnPriorityThresholds: [3],
      warnDueWithinDays: 42,
      warnPriorityMinCount: "invalid",
      plotEvents: [null, { date: "2026-11-02", label: "Milestone", color: "#123456" }],
    };
    bridge.getSettings = () => JSON.stringify(preferences);
    window.dispatchEvent(new CustomEvent("todoist-state", { detail: { preferences } }));
  });
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Enable attention monitoring" })).not.toBeChecked();
  await expect(page.getByRole("button", { name: "retained", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "P3", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Due within days", { exact: true })).toHaveValue("3");
  await expect(page.getByLabel("Minimum priority matches", { exact: true })).toHaveValue("1");
  await expect(page.getByLabel("Label", { exact: true })).toHaveValue("Milestone");
});

test("unreadable saved history can be explicitly disconnected", async ({ page }) => {
  await page.getByRole("button", { name: "Back to my data", exact: true }).click();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", {
    detail: { connected: false, savedHistory: true, message: "Saved credentials or history could not be opened." },
  })));
  await expect(page.getByRole("button", { name: "Disconnect", exact: true })).toBeVisible();
});

test("the dashboard remains usable when UI preferences cannot be saved", async ({ page }) => {
  await page.getByRole("button", { name: "Back to my data", exact: true }).click();
  await page.addInitScript(() => {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key === "todoist-ui") throw new DOMException("Storage unavailable", "QuotaExceededError");
      return setItem.call(this, key, value);
    };
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await page.reload();
  await expect(page.getByRole("heading", { name: "Todoist account" })).toBeVisible();
  await expect(page.getByText("View preferences could not be saved on this device.")).toBeVisible();
  await page.getByRole("button", { name: "Explore a demo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Back to my data", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Recent activity" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("an older WebView keeps navigation usable when charts are unsupported", async ({ page }) => {
  await page.addInitScript(() => {
    const supports = CSS.supports.bind(CSS);
    CSS.supports = ((...args: [string, string?]) =>
      args[0] === "selector(:focus-visible)" ? false :
        args[1] === undefined ? supports(args[0]) : supports(args[0], args[1])) as typeof CSS.supports;
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.reload();
  await expect(page.getByText("Charts require an updated Android System WebView or browser.").first()).toBeVisible();
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByText("Charts require an updated Android System WebView or browser.").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("many projects start with a readable total and an accessible line selector", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-many-projects")));
  for (const size of [
    { width: 412, height: 915 },
    { width: 915, height: 412 },
  ]) {
    await page.setViewportSize(size);
    for (const title of ["Completed tasks", "Cumulative completions"]) {
      const card = page
        .locator("section.card")
        .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
      const legend = card.locator(".mobilePlotLegend");
      const selector = card.locator(".mobilePlotLegendDisclosure");
      const chart = card.locator(".js-plotly-plot");
      await expect(selector.locator("summary")).toContainText("1 of 15 shown");
      await expect(selector).not.toHaveAttribute("open");
      await expect(chart).toBeVisible({ timeout: 30000 });
      const [summaryBox, chartBox] = await Promise.all([selector.locator("summary").boundingBox(), chart.boundingBox()]);
      expect(chartBox!.y - (summaryBox!.y + summaryBox!.height)).toBeLessThan(30);
      await selector.locator("summary").click();
      await expect(legend.getByRole("button")).toHaveCount(15);
      await expect(chart).toBeVisible();
      const legendBox = await legend.boundingBox();
      expect(legendBox!.height).toBeLessThanOrEqual(156);
      await selector.locator("summary").click();
      const overflow = await page.evaluate(() =>
        [...document.querySelectorAll("body *")]
          .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
          .slice(0, 12)
          .map(
            (element) => `${element.tagName}.${element.className}: ${element.getBoundingClientRect().right}`,
          ),
      );
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
        JSON.stringify(overflow),
      ).toBeLessThanOrEqual(size.width);
    }
  }
  const card = page
    .locator("section.card")
    .filter({ has: page.getByRole("heading", { name: "Completed tasks", exact: true }) });
  await page.mouse.move(0, 0);
  await card.getByRole("button", { name: "About Completed tasks" }).focus();
  await expect(card.locator(".infoTipPanel")).toHaveCSS("opacity", "1");
  // The help panel can overlap the start of cardBody, especially in landscape.
  // Click the visible heading instead of forcing a click through the panel.
  await card.getByRole("heading", { name: "Completed tasks", exact: true }).click();
  await expect(card.locator(".infoTipPanel")).toHaveCSS("opacity", "0");
  await card.locator(".mobilePlotLegendDisclosure summary").click();
  const project = card.getByRole("button", { name: "Long project name 0 with research and planning" });
  await expect(project).toHaveAttribute("aria-pressed", "false");
  await project.click();
  await expect(project).toHaveAttribute("aria-pressed", "true");
  await expect(card.locator(".mobilePlotLegendDisclosure summary")).toContainText("2 of 15 shown");
  await expect
    .poll(() =>
      card
        .locator(".js-plotly-plot")
        .evaluate((node) =>
          (node as HTMLElement & { data: { legendgroup: string; visible: string }[] }).data
            .filter((trace) => trace.legendgroup === "Long project name 0 with research and planning")
            .map((trace) => trace.visible),
        ),
    )
    .toEqual([true, true, true]);
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await card.locator(".mobilePlotLegendDisclosure summary").click();
  await expect(project).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => card.locator(".js-plotly-plot").evaluate((node) =>
    (node as HTMLElement & { data: { legendgroup: string; visible: string }[] }).data
      .filter((trace) => trace.legendgroup === "Long project name 0 with research and planning")
      .map((trace) => trace.visible),
  )).toEqual([true, true, true]);
  const bounds = await card.locator(".js-plotly-plot").boundingBox();
  expect(bounds!.width).toBeGreaterThan(0);
  expect(bounds!.width).toBeLessThanOrEqual(await page.evaluate(() => innerWidth));
  await project.click();
  await expect(project).toHaveAttribute("aria-pressed", "false");
});

test("mobile chart hover shows one value and duration labels fit a narrow phone", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  await page.setViewportSize({ width: 320, height: 900 });
  const pace = page.getByRole("region", { name: "Weekly Completion Trend" });
  await pace.evaluate((node) => node.scrollIntoView());
  const chart = pace.locator(".js-plotly-plot");
  await expect(chart).toBeVisible();
  const point = chart.locator(".scatterlayer .trace .points path").first();
  await expect(point).toBeAttached();
  await point.hover({ force: true });
  await expect(chart.locator(".hoverlayer .hovertext")).toHaveCount(1);
  const lifespan = page.getByRole("region", { name: "Task Lifespans: Time to Completion" });
  await lifespan.evaluate((node) => node.scrollIntoView());
  const plot = lifespan.locator(".js-plotly-plot");
  await expect(plot).toBeVisible();
  const clipped = await plot.evaluate((node) => {
    const bounds = node.closest(".cardBody")!.getBoundingClientRect();
    return [...node.querySelectorAll<SVGTextElement>(".xaxislayer-above text, .yaxislayer-above text")]
      .filter((text) => text.textContent?.trim())
      .filter((text) => { const rect = text.getBoundingClientRect(); return rect.left < bounds.left - 1 || rect.right > bounds.right + 1 || rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1; })
      .map((text) => text.textContent);
  });
  expect(clipped).toEqual([]);
  await expect(plot.locator(".yaxislayer-above text").getByText("Under 1 min", { exact: true })).toBeVisible();
  const ticks = await plot.locator(".xaxislayer-above text").allTextContents();
  expect(ticks.length).toBeGreaterThan(1);
  expect(new Set(ticks).size).toBe(ticks.length);
  expect(ticks.every((tick) => Number.isInteger(Number(tick.replaceAll(",", ""))))).toBe(true);
});

test("Android uses desktop Plotly cards and keeps actual/forecast colors together", async ({ page }) => {
  const chart = page.locator(".js-plotly-plot").first();
  await expect(chart).toBeVisible({ timeout: 30000 });
  const traces = await chart.evaluate(
    (node) =>
      (
        node as HTMLElement & {
          data: {
            legendgroup: string;
            mode: string;
            marker: { color: string };
            y: number[];
          }[];
        }
      ).data,
  );
  for (const name of ["All projects", "Work", "Personal"]) {
    const group = traces.filter((trace) => trace.legendgroup === name);
    expect(new Set(group.map((trace) => trace.marker.color)).size).toBe(1);
    expect(group).toHaveLength(3);
  }
  expect(traces[0].y).toHaveLength(7);
  expect(traces[1].y[1]).toBe(40);
  expect(traces[2].y[0]).toBe(3);
  await expect(page.getByText(/undone completions this week|SAVED ON THIS DEVICE/)).toHaveCount(0);
  const size = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(size.document).toBeLessThanOrEqual(size.viewport);
  await page.screenshot({
    path: "test-results/android-overview.png",
    fullPage: true,
  });
});

test("project filters and search survive a page recreation", async ({ page }) => {
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  const query = page.getByRole("searchbox");
  await query.fill("release");
  await expect(page.getByText("Review the release checklist", { exact: true })).toBeVisible();
  await page.getByLabel("Filter task priority", { exact: true }).selectOption("4");
  await expect(page.getByText("No tasks match.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(query).toHaveValue("release");
  await expect(page.getByText("No tasks match.", { exact: true })).toBeVisible();
});

test("Android reuses the validated control panel and saves disabled monitoring", async ({ page }) => {
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await page.getByLabel("Enable attention monitoring", { exact: true }).uncheck();
  await page.getByRole("button", { name: "Save settings", exact: true }).click();
  await expect(page.locator("#dashboard-settings").getByRole("status")).toContainText("Settings saved");
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByText("Monitoring paused", { exact: true })).toBeVisible();
});

test("an unsaved control panel draft survives switching tabs", async ({ page }) => {
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const enabled = page.getByLabel("Enable attention monitoring", { exact: true });
  await enabled.uncheck();
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await expect(enabled).not.toBeChecked();
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Save settings", exact: true }).click();
  await expect(page.locator("#dashboard-settings").getByRole("status")).toContainText("Settings saved");
});

test("privacy information and bundled licenses are readable in Control Panel", async ({ page }) => {
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await page.getByText("Privacy & app info", { exact: true }).click();
  await expect(page.getByText("Version 0.4.1 · Preview", { exact: true })).toBeVisible();
  await expect(page.getByText(/Not affiliated with or endorsed by Doist/)).toBeVisible();
  const open = page.getByRole("button", { name: "Open-source licenses", exact: true });
  await expect(open).toHaveAttribute("aria-expanded", "false");
  await open.click();
  await expect(page.locator("pre")).toContainText("SIL OPEN FONT LICENSE");
  const close = page.getByRole("button", { name: "Hide licenses", exact: true });
  await expect(close).toHaveAttribute("aria-expanded", "true");
  await close.click();
  await expect(page.locator("pre")).toBeHidden();
  await expect(open).toHaveAttribute("aria-expanded", "false");
});

test("first sync explains the current stage and can be cancelled", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", {
    detail: { model: null, demo: false, syncing: true, message: "Loading active tasks · 200 loaded" },
  })));
  const status = page.getByRole("status");
  await expect(status).toContainText("Syncing with Todoist");
  await expect(status).toContainText("Loading active tasks · 200 loaded");
  await expect(status).toContainText("History is saved periodically");
  await expect(page.getByRole("button", { name: "Cancel sync" })).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", {
    detail: { model: null, demo: false, syncing: true, message: "History 4/43 · 2024-02-01 to 2024-03-01 · ~5 min remaining" },
  })));
  await expect(status).toContainText("History 4/43 · 2024-02-01 to 2024-03-01 · ~5 min remaining");
});

test("all history is selectable without changing the current week", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-long-history")));
  const chart = page.locator(".js-plotly-plot").first();
  await expect(chart).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("button", { name: "Historic", exact: true })).toHaveCount(0);
  await page.getByLabel("Range").selectOption("0");
  await expect(page.getByRole("button", { name: "Historic", exact: true })).toHaveCount(2);
  await expect.poll(() => chart.evaluate((node) =>
    (node as HTMLElement & { data: { y: number[] }[] }).data[0].y.length,
  )).toBe(28);
  await expect(page.getByLabel("Contribution week")).toHaveValue("7");
  const values = await chart.evaluate((node) =>
    (node as HTMLElement & { data: { y: number[] }[] }).data.slice(0, 3).map((trace) => trace.y),
  );
  expect(values[0][0]).toBe(10);
  expect(values[2][0]).toBe(3);
});

test("mobile exposes desktop plots with calendar-accurate totals and respects partial coverage", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  for (const title of ["Weekly Completion Trend", "Task Lifespans: Time to Completion", "Project Hierarchy", "Heatmap of Events by Day and Hour", "Events Over Time", "Active Tasks by Priority"]) {
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  }
  const section = (title: string) => page.locator("section.card").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(section("Events Over Time").locator(".js-plotly-plot")).toHaveCount(0);
  await section("Events Over Time").scrollIntoViewIfNeeded();
  const events = section("Events Over Time").locator(".js-plotly-plot");
  await expect(events).toBeVisible({ timeout: 30000 });
  await expect.poll(() => events.evaluate((node) => (node as HTMLElement & { data: { y: number[] }[] }).data[0].y[0])).toBe(7);
  for (const size of [{ width: 412, height: 915 }, { width: 915, height: 412 }]) {
    await page.setViewportSize(size);
    await section("Events Over Time").scrollIntoViewIfNeeded();
    await expect(events).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(size.width);
    const info = section("Events Over Time").getByRole("button", { name: "About Events Over Time" });
    await info.focus();
    const tooltip = section("Events Over Time").getByRole("tooltip");
    await expect(tooltip).toBeVisible();
    const bounds = await tooltip.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(size.width);
    await info.press("Escape");
  }
  await page.setViewportSize({ width: 412, height: 915 });
  await page.getByRole("combobox", { name: "Period", exact: true }).selectOption("month");
  const completed = section("Completed tasks").locator(".js-plotly-plot");
  await expect.poll(() => completed.evaluate((node) => (node as HTMLElement & { data: { y: number[] }[] }).data[0].y)).toEqual([2, 7, 3]);
  await expect(page.getByText("Calendar periods show actual completions; the current period is still in progress.")).toBeVisible();
  await page.getByRole("combobox", { name: "Period", exact: true }).selectOption("quarter");
  await expect.poll(() => completed.evaluate((node) => (node as HTMLElement & { data: { y: number[] }[] }).data[0].y)).toEqual([2, 10]);
  await page.getByRole("button", { name: "Show", exact: true }).click();
  const timeline = page.getByRole("region", { name: "Project Timeline", exact: true });
  await expect(timeline.locator('[data-project-id="old"]')).toBeVisible();
  await expect(timeline.locator('[data-project-id="old-two"]')).toBeVisible();
  await timeline.locator('[data-project-id="work"]').click();
  await expect(timeline.getByRole("region", { name: "Selected project timeline" })).toContainText("7 recorded completions");
  await page.evaluate(() => window.dispatchEvent(new Event("test-history-gap")));
  await expect(page.getByText("History is incomplete; earlier periods may change or be omitted as sync continues.")).toBeVisible();
  await expect.poll(() => events.evaluate((node) => (node as HTMLElement & { data: { x: string[]; y: number[] }[] }).data[0].x[0])).toBe("2026-10-12");
  await expect.poll(() => events.evaluate((node) => (node as HTMLElement & { data: { x: string[]; y: number[] }[] }).data[0].y[0])).toBe(7);
  await expect.poll(() => events.evaluate((node) => (node as HTMLElement & { data: { x: string[] }[] }).data[0].x.at(-1))).toBe("2026-10-20");
  await page.evaluate(() => window.dispatchEvent(new Event("test-history-stale")));
  await page.getByRole("combobox", { name: "Range", exact: true }).selectOption("4");
  await page.getByRole("combobox", { name: "Period", exact: true }).selectOption("month");
  await expect.poll(() => completed.evaluate((node) => (node as HTMLElement & { data: unknown[] }).data.length)).toBe(0);
});

test("project groupings can be edited, promoted, imported, and kept when names are missing", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-account")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByLabel("Find an archived project").fill("Old");
  await manager.getByRole("combobox", { name: /^Archived project/ }).selectOption("Old");
  await expect(manager.getByText(/2 projects share this name/)).toBeVisible();
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  await manager.getByLabel("Specific project", { exact: true }).selectOption("one");
  await manager.getByLabel("Group under").selectOption("Personal");
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings)).toEqual({ one: { targetId: "life", targetName: "Personal" } });
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").mappings)).toEqual({ Old: "Work", Missing: "Gone", Conflict: "Other" });
  await manager.getByRole("button", { name: "Make its own group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings.one.targetId)).toBe("one");
  await manager.getByRole("button", { name: "Remove individual rule" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings)).toEqual({});
  await manager.getByLabel("Find an archived project").fill("");
  await manager.getByRole("combobox", { name: /^Archived project/ }).selectOption("Missing");
  await expect(manager.getByText(/not in the current project list/)).toBeVisible();
  await expect(manager.getByLabel("Group under")).toHaveValue("Gone");
  await manager.getByText("Saved groupings", { exact: false }).click();
  await expect(manager.getByText("Conflict → Other (own group takes priority when archived)")).toBeVisible();
  await manager.getByRole("button", { name: "Remove own group for Legacy" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").archivedParents)).toEqual(["Conflict"]);
  await manager.getByText("Project not listed?").click();
  await manager.getByLabel("Project name", { exact: true }).fill("Reopened");
  await manager.getByRole("button", { name: "Use project name" }).click();
  await expect(manager.getByText(/active subproject follows its Todoist parent/)).toBeVisible();
  await manager.getByLabel("Group under").selectOption("Personal");
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  await expect(manager.getByRole("button", { name: "Make its own group" })).toBeDisabled();
  await manager.getByLabel("Project name", { exact: true }).fill("Absent archive");
  await manager.getByRole("button", { name: "Use project name" }).click();
  await manager.getByText("Group not listed?").click();
  await manager.getByLabel("Group name", { exact: true }).fill("Absent group");
  await manager.getByRole("button", { name: "Use group name" }).click();
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").mappings["Absent archive"])).toBe("Absent group");
  await manager.getByLabel("Project name", { exact: true }).fill("__proto__");
  await manager.getByRole("button", { name: "Use project name" }).click();
  await manager.getByLabel("Group under").selectOption("Personal");
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").mappings["__proto__"])).toBe("Personal");
  await manager.getByText("Import groupings from your computer").click();
  await expect(manager.getByText(/individual project rules take priority and are kept unless the file contains the same project IDs/)).toBeVisible();
  await manager.getByRole("button", { name: "Choose desktop export" }).click();
  expect(await page.evaluate(() => sessionStorage.getItem("test-import-requested"))).toBe("yes");
});

test("archived projects and parents can be searched and assigned", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-search")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByLabel("Find an archived project").fill("lodz");
  const source = manager.getByRole("combobox", { name: /^Archived project/ });
  await expect(source.locator("option")).toHaveCount(2);
  await source.selectOption("Łódź archive");
  await expect(manager.getByText("Current grouping: No parent recorded; shown under its own name")).toBeVisible();
  await expect(manager.getByLabel("Specific project", { exact: true })).toHaveValue("old-source");
  await manager.getByLabel("Find a parent project").fill("indirect child");
  const parent = manager.getByLabel("Group under");
  await parent.selectOption("Indirect child");
  await expect(manager.getByText(/would create a grouping loop/)).toBeVisible();
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  await parent.selectOption("");
  await manager.getByLabel("Find a parent project").fill("archived child");
  await parent.selectOption("Archived child");
  await expect(manager.getByText(/would create a grouping loop/)).toBeVisible();
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  await parent.selectOption("");
  await manager.getByLabel("Find a parent project").fill("zazolc");
  await expect(parent.locator("option")).toHaveCount(2);
  await expect(parent.locator('option[value="Zażółć Parent"]')).toHaveText("Zażółć Parent (archived)");
  await parent.selectOption("Zażółć Parent");
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings["old-source"])).toEqual({ targetId: "old-parent", targetName: "Zażółć Parent" });
  await manager.getByLabel("Find a parent project").fill("missing term");
  await expect(manager.getByText("No parent projects match this search.")).toBeVisible();
  await expect(parent).toHaveValue("Zażółć Parent");
  await manager.getByLabel("Find an archived project").fill("missing term");
  await expect(manager.getByText("No archived projects match this search.")).toBeVisible();
  await expect(source).toHaveValue("Łódź archive");
});

test("duplicate project and parent names require an explicit id", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-search")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByRole("combobox", { name: /^Archived project/ }).selectOption("Old");
  await expect(manager.getByRole("button", { name: "Make its own group" })).toBeDisabled();
  const source = manager.getByLabel("Specific project", { exact: true });
  await source.selectOption("one");
  await manager.getByLabel("Group under").selectOption("Shared parent");
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  const parent = manager.getByLabel("Specific parent project");
  await expect(parent.locator('option[value="shared-b"]')).toContainText("archived");
  await parent.selectOption("shared-b");
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings)).toEqual({ one: { targetId: "shared-b", targetName: "Shared parent" } });
  await source.selectOption("two");
  await manager.getByLabel("Group under").selectOption("Shared parent");
  await manager.getByLabel("Specific parent project").selectOption("shared-a");
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings)).toEqual({ one: { targetId: "shared-b", targetName: "Shared parent" }, two: { targetId: "shared-a", targetName: "Shared parent" } });
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").mappings.Old)).toBe("Work");
});

test("projects can be found by an earlier name without automatically assigning them", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-search")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByLabel("Find an archived project").fill("stary zeszyt");
  const source = manager.getByRole("combobox", { name: /^Archived project/ });
  await expect(source.locator('option[value="Łódź archive"]')).toContainText("formerly Stary zeszyt");
  await source.selectOption("Łódź archive");
  await expect(manager.getByLabel("Specific project", { exact: true })).toHaveValue("old-source");
  await manager.getByLabel("Find a parent project").fill("dawny dzial");
  const parent = manager.getByLabel("Group under");
  await expect(parent.locator('option[value="Zażółć Parent"]')).toContainText("formerly Dawny dział");
  expect(await page.evaluate(() => sessionStorage.getItem("test-saved-adjustments"))).toBeNull();
  await parent.selectOption("Zażółć Parent");
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings["old-source"])).toEqual({ targetId: "old-parent", targetName: "Zażółć Parent" });
});

test("a missing saved parent id is not replaced by another project of the same name", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-missing-id")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByRole("combobox", { name: /^Archived project/ }).selectOption("Old");
  await manager.getByLabel("Specific project", { exact: true }).selectOption("one");
  await expect(manager.getByText(/saved parent is missing from synced projects/)).toBeVisible();
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  expect(await page.evaluate(() => sessionStorage.getItem("test-saved-adjustments"))).toBeNull();
  await manager.getByRole("button", { name: "Remove individual rule" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").projectMappings)).toEqual({});
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").mappings.Old)).toBe("Work");
});

test("an id-based grouping follows the current name of a renamed parent", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-renamed-parent")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByRole("combobox", { name: /^Archived project/ }).selectOption("Old");
  await manager.getByLabel("Specific project", { exact: true }).selectOption("one");
  await expect(manager.getByText("Current grouping: Personal (this project)")).toBeVisible();
  await expect(manager.getByLabel("Group under")).toHaveValue("Personal");
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  await expect(manager.getByText(/Removing the individual rule restores the saved name rule/)).toBeVisible();
});

test("grouping editor draft survives recreation without applying changes", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-account")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByLabel("Find an archived project").fill("Old");
  await manager.getByRole("combobox", { name: /^Archived project/ }).selectOption("Old");
  await manager.getByLabel("Group under").selectOption("Personal");
  await manager.getByText("Project not listed?").click();
  await manager.getByLabel("Project name", { exact: true }).fill("Unlisted project");
  await manager.getByText("Group not listed?").click();
  await manager.getByLabel("Group name", { exact: true }).fill("Unlisted group");
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("todoist-ui") ?? "{}").groupingDraft?.target)).toBe("Personal");
  await page.reload();
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-account")));
  await expect(manager.getByLabel("Find an archived project")).toHaveValue("Old");
  await expect(manager.getByRole("combobox", { name: /^Archived project/ })).toHaveValue("Old");
  await expect(manager.getByLabel("Group under")).toHaveValue("Personal");
  await manager.getByText("Project not listed?").click();
  await expect(manager.getByLabel("Project name", { exact: true })).toHaveValue("Unlisted project");
  await manager.getByText("Group not listed?").click();
  await expect(manager.getByLabel("Group name", { exact: true })).toHaveValue("Unlisted group");
  expect(await page.evaluate(() => sessionStorage.getItem("test-saved-adjustments"))).toBeNull();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("todoist-ui") ?? "{}").groupingDraft?.source)).toBe("");
});

test("a specific source and parent selection survives recreation without saving", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-search")));
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const manager = page.getByRole("region", { name: "Project grouping" });
  await manager.getByRole("combobox", { name: /^Archived project/ }).selectOption("Old");
  await manager.getByLabel("Specific project", { exact: true }).selectOption("one");
  await manager.getByLabel("Find a parent project").fill("shared");
  await manager.getByLabel("Group under").selectOption("Shared parent");
  await manager.getByLabel("Specific parent project").selectOption("shared-b");
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("todoist-ui") ?? "{}").groupingDraft?.targetId)).toBe("shared-b");
  await page.reload();
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-search")));
  await expect(manager.getByRole("combobox", { name: /^Archived project/ })).toHaveValue("Old");
  await expect(manager.getByLabel("Specific project", { exact: true })).toHaveValue("one");
  await expect(manager.getByLabel("Find a parent project")).toHaveValue("shared");
  await expect(manager.getByLabel("Group under")).toHaveValue("Shared parent");
  await expect(manager.getByLabel("Specific parent project")).toHaveValue("shared-b");
  expect(await page.evaluate(() => sessionStorage.getItem("test-saved-adjustments"))).toBeNull();
});

test("an older grouping draft without ids remains readable", async ({ page }) => {
  await page.evaluate(() => localStorage.setItem("todoist-ui", JSON.stringify({ tab: "Control Panel", groupingDraft: { search: "Old", source: "Old", target: "Personal", customSource: "", customTarget: "" } })));
  await page.reload();
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-account")));
  const manager = page.getByRole("region", { name: "Project grouping" });
  await expect(manager.getByLabel("Find an archived project")).toHaveValue("Old");
  await expect(manager.getByLabel("Group under")).toHaveValue("Personal");
  await expect(manager.getByLabel("Specific project", { exact: true })).toHaveValue("");
  await expect(page.getByText(/Some saved view preferences are invalid/)).toHaveCount(0);
});

test("a stale project id in a draft cannot be applied to a different project", async ({ page }) => {
  await page.evaluate(() => localStorage.setItem("todoist-ui", JSON.stringify({ tab: "Control Panel", groupingDraft: { search: "", source: "Old", target: "Personal", customSource: "", customTarget: "", sourceId: "removed", targetId: "", targetSearch: "" } })));
  await page.reload();
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-account")));
  const manager = page.getByRole("region", { name: "Project grouping" });
  await expect(manager.getByText(/selected project ID is no longer in the synced projects/)).toBeVisible();
  await expect(manager.getByRole("button", { name: "Assign to group" })).toBeDisabled();
  expect(await page.evaluate(() => sessionStorage.getItem("test-saved-adjustments"))).toBeNull();
});

test("invalid stored grouping draft is ignored without overwriting it", async ({ page }) => {
  const raw = JSON.stringify({ tab: "Control Panel", groupingDraft: { source: ["bad"] } });
  await page.evaluate((value) => localStorage.setItem("todoist-ui", value), raw);
  await page.reload();
  await expect(page.getByText(/Some saved view preferences are invalid/)).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("todoist-ui"))).toBe(raw);
  await page.evaluate(() => window.dispatchEvent(new Event("test-grouping-account")));
  await expect(page.getByRole("region", { name: "Project grouping" }).getByRole("combobox", { name: /^Archived project/ })).toHaveValue("");
});

test("project names do not collide with JavaScript properties or the aggregate", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-special-names")));
  const section = page.locator("section.card").filter({ has: page.getByRole("heading", { name: "Completed tasks", exact: true }) });
  const chart = section.locator(".js-plotly-plot");
  await expect(chart).toBeVisible({ timeout: 30000 });
  const traces = () => chart.evaluate((node) => (node as HTMLElement & { data: { name: string; legendgroup: string; y: number[]; showlegend?: boolean }[] }).data);
  await expect.poll(async () => (await traces()).filter((trace) => trace.legendgroup === "All projects").length).toBe(3);
  await expect.poll(async () => (await traces()).filter((trace) => trace.legendgroup === "project:All projects").length).toBe(3);
  expect((await traces()).find((trace) => trace.legendgroup === "project:All projects")!.name).toBe("All projects (project)");
  await page.getByRole("combobox", { name: "Period", exact: true }).selectOption("month");
  await expect.poll(async () => (await traces()).find((trace) => trace.legendgroup === "All projects")?.y).toEqual([7, 3]);
  expect((await traces()).find((trace) => trace.legendgroup === "project:All projects")?.y).toEqual([4, 0]);
  expect((await traces()).find((trace) => trace.legendgroup === "constructor")?.y).toEqual([2, 0]);
  expect((await traces()).find((trace) => trace.legendgroup === "__proto__")?.y).toEqual([1, 0]);
});


test("timeline filters inclusive dates and keeps selection separate for duplicate names", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  const timeline = page.getByRole("region", { name: "Project Timeline", exact: true });
  await timeline.getByRole("button", { name: "Show", exact: true }).click();
  await timeline.getByLabel("Timeline start date").fill("2026-10-01");
  await timeline.getByLabel("Timeline end date").fill("2026-10-02");
  await timeline.locator('[data-project-id="work"]').click();
  const details = timeline.getByRole("region", { name: "Selected project timeline" });
  await expect(details).toContainText("4 recorded completions");
  await expect(details).toContainText("5 recorded activity events");
  await expect(details).toContainText("2026-10-01");
  await expect(details).toContainText("2026-10-02");
  await expect(details).not.toContainText("2026-11-02");
  await expect(timeline.locator('[data-project-id="old"]')).toContainText("ID old");
  await expect(timeline.locator('[data-project-id="old-two"]')).toContainText("ID old-two");
  await timeline.locator('[data-project-id="old"]').click();
  await expect(timeline.locator('[data-project-id="old"]')).toHaveAttribute("aria-pressed", "true");
  await timeline.locator('[data-project-id="old-two"]').click();
  await expect(timeline.locator('[data-project-id="old-two"]')).toHaveAttribute("aria-pressed", "true");
  await expect(timeline.getByLabel("Timeline start date")).toHaveValue("2026-10-01");
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(timeline.locator('[data-project-id="old-two"]')).toHaveAttribute("aria-pressed", "true");
  await expect(timeline.getByLabel("Timeline start date")).toHaveValue("2026-10-01");
  await expect(timeline.getByLabel("Timeline end date")).toHaveValue("2026-10-02");
  await timeline.getByLabel("Timeline end date").fill("2026-09-01");
  await expect(timeline.getByRole("alert")).toContainText("start date must not be after");
  await page.setViewportSize({ width: 320, height: 700 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test("timeline distinguishes unavailable project history from an empty range", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-analysis")));
  const timeline = page.getByRole("region", { name: "Project Timeline", exact: true });
  await timeline.getByRole("button", { name: "Show", exact: true }).click();
  await page.evaluate(() => window.dispatchEvent(new Event("test-history-gap")));
  await expect(timeline).toContainText("missing dates are not confirmed as inactive");
  await timeline.locator('[data-project-id="work"]').click();
  await timeline.getByLabel("Timeline start date").fill("2025-01-01");
  await timeline.getByLabel("Timeline end date").fill("2025-02-01");
  await expect(timeline).toContainText("No recorded activity in this range; history is incomplete");
});


test("large timeline paginates and shows subtask parents", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-timeline-large")));
  const timeline = page.getByRole("region", { name: "Project Timeline", exact: true });
  await timeline.getByRole("button", { name: "Show", exact: true }).click();
  await expect(timeline.locator('[data-project-id]')).toHaveCount(20);
  await timeline.getByRole("button", { name: "Show more projects" }).click();
  await expect(timeline.locator('[data-project-id]')).toHaveCount(29);
  await expect(timeline.locator('[data-project-id="unknown"]')).toContainText("Status unavailable");
  await timeline.locator('[data-project-id="unknown"]').click();
  await expect(timeline.getByRole("region", { name: "Selected project timeline" })).toContainText("Project status is unknown");
  await timeline.locator('[data-project-id="work"]').click();
  const details = timeline.getByRole("region", { name: "Selected project timeline" });
  await expect(details).toContainText("90 recorded completions");
  await expect(details).toContainText("Subtask of Review the release checklist");
  await expect(details.getByRole("list", { name: "Project activity by day" }).locator("li")).toHaveCount(30);
  await details.getByRole("button", { name: "Show more activity" }).click();
  await expect(details.getByRole("list", { name: "Project activity by day" }).locator("li")).toHaveCount(60);
});
