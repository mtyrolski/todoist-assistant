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
    window.Todoist = {
      ready: send,
      command: (name: string) => {
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
  await expect(status).toContainText("first sync loads about 12 weeks");
  await expect(page.getByRole("button", { name: "Cancel sync" })).toBeVisible();
});
