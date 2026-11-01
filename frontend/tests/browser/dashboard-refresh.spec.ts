import { expect, test } from "@playwright/test";

const home = {
  range: { beg: "2026-10-26", end: "2026-11-01", granularity: "W", weeks: 12 },
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
  await expect(page.getByText("349", { exact: true })).toBeVisible();
  await expect(page.getByText("Activity history is from saved data.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Temporarily offline. Showing the last loaded view.", { exact: true })).toBeVisible();
  await expect(page.getByText("349", { exact: true })).toBeVisible();
});

test("a background sync updates the visible counts when it finishes", async ({ page }) => {
  let reads = 0;
  await page.route("**/api/dashboard/home?**", (route) => {
    reads++;
    const updated = reads > 1;
    return route.fulfill({ json: {
      ...home, refreshing: !updated,
      metrics: { ...home.metrics, items: [{ ...home.metrics.items[0], value: updated ? 350 : 349 }] }
    } });
  });
  await page.goto("/");
  await expect(page.getByText("349", { exact: true })).toBeVisible();
  await expect(page.getByText("350", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Syncing in the background…", { exact: true })).toHaveCount(0);
});
