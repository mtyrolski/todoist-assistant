import { expect, test } from "@playwright/test";

const home = {
  range: { beg: "2026-10-26", end: "2026-11-01", mode: "rolling", granularity: "W", weeks: 12 },
  metrics: {
    items: [{ name: "Completed Tasks", value: 349, deltaPercent: null, inverseDelta: false }],
    currentPeriod: "This week", previousPeriod: "Last week"
  },
  badges: { p1: 0, p2: 0, p3: 0, p4: 0 },
  figures: {}, insights: { items: [] }, refreshedAt: "2026-11-01T12:00:00Z"
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ json: {
    configured: true, valid: true, status: "ok", services: [],
    apiCache: { lastRefresh: null }, activityCache: null
  } }));
});

test("a failed refresh keeps the last loaded counts and explains their status", async ({ page }) => {
  await page.route("**/api/dashboard/home?**", (route) => {
    if (new URL(route.request().url()).searchParams.get("refresh") === "true") {
      return route.fulfill({ status: 500, json: { detail: "Temporarily offline" } });
    }
    return route.fulfill({ json: { ...home, refreshWarning: "Activity history is from saved data." } });
  });
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: /multiplication/i })).toHaveCount(0);
  await expect(page.getByText("349", { exact: true })).toBeVisible();
  await expect(page.getByText("Activity history is from saved data.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Temporarily offline. Showing the last loaded view.", { exact: true })).toBeVisible();
  await expect(page.getByText("349", { exact: true })).toBeVisible();
});

test("a background sync updates the visible counts when it finishes", async ({ page }) => {
  let reads = 0;
  let followupMode: string | null = null;
  await page.route("**/api/dashboard/home?**", (route) => {
    reads++;
    const updated = reads > 1;
    if (updated) followupMode = new URL(route.request().url()).searchParams.get("cached_only");
    return route.fulfill({ json: {
      ...home, refreshing: !updated,
      metrics: { ...home.metrics, items: [{ ...home.metrics.items[0], value: updated ? 350 : 349 }] }
    } });
  });
  await page.goto("/");
  await expect(page.getByText("349", { exact: true })).toBeVisible();
  await expect(page.getByText("Refreshing dashboard data")).toHaveCount(0);
  await expect(page.getByText("350", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Syncing in the background…", { exact: true })).toHaveCount(0);
  expect(followupMode).toBe("true");
});

test("Autoscale survives a background sync and a new period resets the chart", async ({ page }) => {
  const initialRange = ["2026-10-01", "2026-11-01"];
  const syncedRange = ["2026-10-02", "2026-11-02"];
  const selectedRange = ["2026-05-04", "2026-11-02"];
  let finishSync!: () => void;
  const sync = new Promise<void>((resolve) => { finishSync = resolve; });

  await page.route("**/api/dashboard/home?**", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    const selected = params.get("weeks") === "26";
    const refreshed = params.get("cached_only") === "true";
    if (refreshed) await sync;
    const range = selected ? selectedRange : refreshed ? syncedRange : initialRange;
    return route.fulfill({ json: {
      ...home,
      refreshing: !refreshed,
      range: { ...home.range, weeks: selected ? 26 : 12, beg: range[0], end: range[1] },
      figures: {
        completedTasksPeriodically: {
          data: [{
            type: "scatter",
            mode: "lines",
            x: ["2024-06-01", "2026-06-01", "2026-10-26"],
            y: [1, 2, refreshed ? 4 : 3]
          }],
          layout: { xaxis: { type: "date", range } }
        }
      }
    } });
  });
  const chart = page.getByRole("region", { name: "Periodically Completed Tasks Per Project", exact: true });
  const plot = chart.locator(".js-plotly-plot");
  const chartState = () => plot.evaluateAll(([node]) => {
    const graph = node as (HTMLElement & {
      data?: { y: number[] }[];
      _fullLayout?: { xaxis: { autorange: boolean; range: string[] } };
    }) | undefined;
    const axis = graph?._fullLayout?.xaxis;
    if (!axis) return null;
    return {
      auto: axis.autorange,
      range: axis.range.map((date) => date.slice(0, 10)),
      lastCount: graph?.data?.[0]?.y.at(-1)
    };
  });

  try {
    const backgroundRead = page.waitForRequest((request) =>
      request.url().includes("/api/dashboard/home?") &&
      new URL(request.url()).searchParams.get("cached_only") === "true"
    );
    await page.goto("/");
    await backgroundRead;
    const autoscale = chart.locator('[data-title="Autoscale"]');
    await expect(autoscale).toBeAttached();
    await plot.hover();
    await expect.poll(chartState).toMatchObject({ auto: false, range: initialRange, lastCount: 3 });
    await autoscale.click();
    await expect.poll(chartState).toMatchObject({ auto: true, lastCount: 3 });
    const expandedRange = (await chartState())!.range;
    expect(Date.parse(expandedRange[0])).toBeLessThanOrEqual(Date.UTC(2024, 5, 1));

    finishSync();
    await expect.poll(chartState).toMatchObject({ auto: true, range: expandedRange, lastCount: 4 });

    await page.getByLabel("Range", { exact: true }).selectOption("26");
    await expect.poll(chartState).toMatchObject({ auto: false, range: selectedRange, lastCount: 4 });
  } finally {
    finishSync();
  }
});

test("idle Overview keeps its snapshot when time passes and the window regains focus", async ({ page }) => {
  await page.clock.install();
  let reads = 0;
  await page.route("**/api/dashboard/home?**", (route) => {
    reads++;
    return route.fulfill({ json: home });
  });
  await page.goto("/");
  await expect(page.getByText("349", { exact: true })).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.clock.fastForward(65_000);
  await expect(page.getByText("349", { exact: true })).toBeVisible();
  expect(reads).toBe(1);
});

test("hierarchy playback requests the range used by the displayed dashboard", async ({ page }) => {
  const figure = { data: [], layout: {} };
  const playbackRequests: URLSearchParams[] = [];
  const historyRequests: URLSearchParams[] = [];
  await page.route("**/api/dashboard/home?**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const custom = params.has("beg") && params.has("end");
    if (custom) historyRequests.push(params);
    return route.fulfill({ json: {
      ...home,
      range: { ...home.range, mode: custom ? "custom" : "rolling", beg: params.get("beg") ?? home.range.beg, end: params.get("end") ?? home.range.end },
      figures: { activeProjectHierarchy: figure }
    } });
  });
  await page.route("**/api/dashboard/hierarchy-playback?**", (route) => {
    playbackRequests.push(new URL(route.request().url()).searchParams);
    return route.fulfill({ json: { frames: [{ date: "2026-11-01", figure }] } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Play history" }).click();
  await expect.poll(() => playbackRequests.length).toBe(1);
  expect(playbackRequests[0].get("weeks")).toBe("12");
  expect(playbackRequests[0].has("beg")).toBe(false);

  await page.getByRole("link", { name: /Activity History/ }).first().click();
  await page.getByLabel("From date").fill("2026-10-01");
  await page.getByLabel("To date").fill("2026-10-15");
  expect(historyRequests).toHaveLength(0);
  await page.getByRole("button", { name: "Load charts" }).click();
  await expect(page.getByRole("heading", { name: "2026-10-01 → 2026-10-15" })).toBeVisible();
  expect(historyRequests).toHaveLength(1);
  expect(historyRequests[0].get("cached_only")).toBe("true");
  await page.getByRole("button", { name: "Play history" }).click();
  await expect.poll(() => playbackRequests.length).toBe(2);
  expect(playbackRequests[1].get("beg")).toBe("2026-10-01");
  expect(playbackRequests[1].get("end")).toBe("2026-10-15");
  expect(playbackRequests[1].has("weeks")).toBe(false);
  expect(playbackRequests[1].get("cached_only")).toBe("true");
});
