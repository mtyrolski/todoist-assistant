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
    const preferences = JSON.parse(
      sessionStorage.getItem("test-preferences") ?? "null",
    ) ?? {
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
      window.dispatchEvent(
        new CustomEvent("todoist-state", { detail: structuredClone(state) }),
      );
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
        sessionStorage.setItem(
          "test-preferences",
          JSON.stringify(state.preferences),
        );
        setTimeout(send, 0);
        return json;
      },
    };
  });
  await page.goto("/android");
  await page
    .getByRole("button", { name: "Explore a demo", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Back to my data", exact: true }),
  ).toBeVisible();
});

test("Android uses desktop Plotly cards and keeps actual/forecast colors together", async ({
  page,
}) => {
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
  await expect(
    page.getByText(/undone completions this week|SAVED ON THIS DEVICE/),
  ).toHaveCount(0);
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

test("project filters and search survive a page recreation", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  const query = page.getByRole("searchbox");
  await query.fill("release");
  await expect(
    page.getByText("Review the release checklist", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Filter task priority", { exact: true })
    .selectOption("4");
  await expect(
    page.getByText("No tasks match.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(query).toHaveValue("release");
  await expect(
    page.getByText("No tasks match.", { exact: true }),
  ).toBeVisible();
});

test("Android reuses the validated control panel and saves disabled monitoring", async ({
  page,
}) => {
  await page
    .getByRole("button", { name: "Control Panel", exact: true })
    .click();
  await page
    .getByLabel("Enable attention monitoring", { exact: true })
    .uncheck();
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(
    page.locator("#dashboard-settings").getByRole("status"),
  ).toContainText("Settings saved");
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByText("Monitoring paused", { exact: true }),
  ).toBeVisible();
});
