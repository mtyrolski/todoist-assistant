import { expect, test } from "@playwright/test";

const initial = {
  enabled: true, dangerOnFireLabel: true, warnOnPriority: true, warnOnDue: true, warnOnDeadline: true,
  fireLabel: "fire", fireLabels: ["fire"], warnPriorityThresholds: [4, 3],
  warnPriorityMinCount: 1, warnDueWithinDays: 0, warnDueMinCount: 1,
  warnDeadlineWithinDays: 0, warnDeadlineMinCount: 1, plotEvents: [], configPath: "configs/dashboard.yaml"
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ json: {
    configured: true, valid: true, status: "ok", services: [], logs: [], files: [],
    apiCache: { lastRefresh: null }, activityCache: null,
    labels: [{ name: "fire" }, { name: "next" }], timezone: "Europe/Warsaw", source: "system", settings: initial
  } }));
});

test("empty numeric input blocks saving; valid changes and empty selections survive reload", async ({ page }) => {
  let settings = structuredClone(initial);
  let writes = 0;
  await page.route("**/api/admin/dashboard/settings", async (route) => {
    if (route.request().method() === "PUT") { writes++; settings = { ...settings, ...route.request().postDataJSON() }; }
    await route.fulfill({ json: { settings } });
  });
  await page.goto("/control-panel");
  const panel = page.locator("#dashboard-settings");
  await expect(panel.getByRole("button", { name: "P1", exact: true })).toHaveAttribute("aria-pressed", "true");
  await panel.getByRole("button", { name: "P1", exact: true }).click();
  await panel.getByRole("button", { name: "fire", exact: true }).click();
  const minimum = panel.getByLabel("Minimum priority matches", { exact: true });
  await minimum.fill("");
  await panel.getByRole("button", { name: "Save settings", exact: true }).click();
  expect(writes).toBe(0);
  await expect(minimum).toHaveValue("");
  await minimum.fill("2");
  await panel.getByRole("button", { name: "Save settings", exact: true }).click();
  await expect(panel.getByRole("status")).toContainText("Settings saved");
  expect(writes).toBe(1);
  expect(settings.warnPriorityThresholds).toEqual([3]);
  expect(settings.fireLabels).toEqual([]);
  await page.reload();
  await expect(panel.getByRole("button", { name: "fire", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(panel.getByLabel("Minimum priority matches", { exact: true })).toHaveValue("2");
});

test("server failures keep the draft and show the actual error", async ({ page }) => {
  await page.route("**/api/admin/dashboard/settings", (route) => route.request().method() === "PUT"
    ? route.fulfill({ status: 500, json: { detail: "Configuration directory is not writable" } })
    : route.fulfill({ json: { settings: initial } }));
  await page.goto("/control-panel");
  const panel = page.locator("#dashboard-settings");
  await panel.getByLabel("Minimum priority matches", { exact: true }).fill("5");
  await panel.getByRole("button", { name: "Save settings", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Configuration directory is not writable");
  await expect(panel.getByLabel("Minimum priority matches", { exact: true })).toHaveValue("5");
  await expect(panel.getByText("Unsaved changes", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Discard changes", exact: true }).click();
  await expect(panel.getByLabel("Minimum priority matches", { exact: true })).toHaveValue("1");
});

test("failed initial load cannot overwrite settings with defaults", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/admin/dashboard/settings", (route) => {
    if (route.request().method() === "PUT") writes++;
    return route.fulfill({ status: 500, json: { detail: "Settings unavailable" } });
  });
  await page.goto("/control-panel");
  const panel = page.locator("#dashboard-settings");
  await expect(panel.getByRole("alert")).toContainText("Settings unavailable");
  await expect(panel.getByRole("button", { name: "Save settings", exact: true })).toHaveCount(0);
  expect(writes).toBe(0);
});

test("mobile labels and priorities use touch toggles", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/control-panel");
  const panel = page.locator("#dashboard-settings");
  await panel.getByRole("button", { name: "P2", exact: true }).click();
  await expect(panel.getByRole("button", { name: "P2", exact: true })).toHaveAttribute("aria-pressed", "false");
  await panel.getByLabel("Add a fire label by name").fill("hot");
  await panel.getByRole("button", { name: "Add label", exact: true }).click();
  await expect(panel.getByRole("button", { name: "hot", exact: true })).toHaveAttribute("aria-pressed", "true");
});
