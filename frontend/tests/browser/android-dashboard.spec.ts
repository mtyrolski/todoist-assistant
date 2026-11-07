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
          { id: "work", name: "Work", parentId: "", rootName: "Work", color: "blue", archived: false, createdAt: "2026-09-01", lastEventAt: "2026-11-02", archivedAt: "", weeklyCounts: { 7: 10, 8: 3 } },
          { id: "old", name: "Reopened", parentId: "work", rootName: "Work", color: "blue", archived: false, createdAt: "2026-09-01", lastEventAt: "2026-10-01", archivedAt: "2025-01-01", weeklyCounts: { 7: 1 } },
          { id: "old-two", name: "Reopened", parentId: "work", rootName: "Work", color: "blue", archived: false, createdAt: "2026-09-02", lastEventAt: "2026-10-01", archivedAt: "", weeklyCounts: { 7: 1 } },
        ],
        taskCounts: [{ date: "2026-11-01", total: 2, p1: 1, p2: 1, p3: 0, p4: 0 }, { date: "2026-11-02", total: 3, p1: 2, p2: 1, p3: 0, p4: 0 }],
      };
      (model as typeof model & { plotData: typeof plotData }).plotData = plotData;
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
    window.Todoist = {
      ready: send,
      command: (name: string, argument: string) => {
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
          const { mappings, archivedParents } = JSON.parse(argument);
          (model as typeof model & { adjustments: unknown }).adjustments = { mappings, archivedParents };
          sessionStorage.setItem("test-saved-adjustments", JSON.stringify({ mappings, archivedParents }));
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

test("many project labels stay outside both plots in portrait and landscape", async ({ page }) => {
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
      const chart = card.locator(".js-plotly-plot");
      await expect(legend.getByRole("button")).toHaveCount(15);
      await expect(chart).toBeVisible();
      const [legendBox, chartBox] = await Promise.all([legend.boundingBox(), chart.boundingBox()]);
      expect(legendBox!.y + legendBox!.height).toBeLessThanOrEqual(chartBox!.y);
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
  const project = card.getByRole("button", { name: "Long project name 0 with research and planning" });
  await project.click();
  await expect(project).toHaveAttribute("aria-pressed", "false");
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
    .toEqual(["legendonly", "legendonly", "legendonly"]);
  await project.click();
  await expect(project).toHaveAttribute("aria-pressed", "true");
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

test("privacy information and bundled licenses are readable in Control Panel", async ({ page }) => {
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await page.getByText("Privacy & app info", { exact: true }).click();
  await expect(page.getByText("Version 0.4.1 · Preview", { exact: true })).toBeVisible();
  await expect(page.getByText(/Not affiliated with or endorsed by Doist/)).toBeVisible();
  await page.getByRole("button", { name: "Open-source licenses", exact: true }).click();
  await expect(page.locator("pre")).toContainText("SIL OPEN FONT LICENSE");
});

test("first sync explains the current stage and can be cancelled", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("todoist-state", {
    detail: { model: null, demo: false, syncing: true, message: "Loading active tasks · 200 loaded" },
  })));
  const status = page.getByRole("status");
  await expect(status).toContainText("Syncing with Todoist");
  await expect(status).toContainText("Loading active tasks · 200 loaded");
  await expect(status).toContainText("first sync loads your available history");
  await expect(page.getByRole("button", { name: "Cancel sync" })).toBeVisible();
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
  const timeline = section("Timeline").locator(".js-plotly-plot");
  await expect(timeline).toBeVisible();
  await expect.poll(() => timeline.evaluate((node) => (node as HTMLElement & { data: { y: string[] }[] }).data[0].y.filter((name) => name.includes("Reopened")))).toEqual(["Work / Reopened", "Work / Reopened (2)"]);
  await page.evaluate(() => window.dispatchEvent(new Event("test-history-gap")));
  await expect(page.getByText("History is incomplete; earlier periods may change as sync continues.")).toBeVisible();
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
  await manager.getByLabel("Group under").selectOption("Personal");
  await manager.getByRole("button", { name: "Assign to group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").mappings)).toEqual({ Old: "Personal", Missing: "Gone", Conflict: "Other" });
  await manager.getByRole("button", { name: "Make its own group" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").archivedParents)).toEqual(["Legacy", "Conflict", "Old"]);
  await manager.getByRole("button", { name: "Use automatic grouping" }).click();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test-saved-adjustments") ?? "{}").archivedParents)).toEqual(["Legacy", "Conflict"]);
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
  await expect(manager.getByText(/file rules win when both places define the same project/)).toBeVisible();
  await manager.getByRole("button", { name: "Choose desktop export" }).click();
  expect(await page.evaluate(() => sessionStorage.getItem("test-import-requested"))).toBe("yes");
});

test("project names do not collide with JavaScript properties or the aggregate", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new Event("test-special-names")));
  const section = page.locator("section.card").filter({ has: page.getByRole("heading", { name: "Completed tasks", exact: true }) });
  const chart = section.locator(".js-plotly-plot");
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
