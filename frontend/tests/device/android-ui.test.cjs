const { test, before, beforeEach, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { _android, expect: playwrightExpect } = require("playwright/test");
const expect = playwrightExpect.configure({ timeout: 15000 });

const pkg = "com.todoistassistant";
const screenshots = `frontend/test-results/device/${process.env.ANDROID_SERIAL ?? "emulator"}`;
let device, page;
before(async () => {
  const devices = await _android.devices({ port: Number(process.env.ANDROID_ADB_SERVER_PORT || 5037) });
  const emulators = devices.filter((candidate) =>
    candidate.serial().startsWith("emulator-"),
  );
  device = process.env.ANDROID_SERIAL
    ? emulators.find(
        (candidate) => candidate.serial() === process.env.ANDROID_SERIAL,
      )
    : emulators[0];
  await Promise.all(
    devices
      .filter((candidate) => candidate !== device)
      .map((candidate) => candidate.close()),
  );
  assert.ok(
    device?.serial().startsWith("emulator-"),
    "Use a dedicated emulator: these tests clear app data",
  );
  fs.mkdirSync(screenshots, { recursive: true });
  device.setDefaultTimeout(60000);
  await device.shell("svc wifi disable");
  await device.shell("svc data disable");
});
beforeEach(async () => {
  await device.shell(`am force-stop ${pkg}`);
  await device.shell(`pm clear ${pkg}`);
  await device.shell("settings put system accelerometer_rotation 0");
  await device.shell("settings put system user_rotation 0");
  await device.shell("settings put secure show_ime_with_hard_keyboard 1");
  const created = device.waitForEvent("webview", {
    predicate: (view) => view.pkg() === pkg,
  });
  await device.shell(`am start -n ${pkg}/.MainActivity`);
  page = await (await created).page();
  await page.waitForFunction(() => Array.from(document.querySelectorAll("button")).some((button) => button.textContent.trim() === "Explore a demo"), null, { timeout: 120000 });
  await page.evaluate(() => Array.from(document.querySelectorAll("button")).find((button) => button.textContent.trim() === "Explore a demo").click());
  await page.waitForFunction(() => Array.from(document.querySelectorAll("button")).some((button) => button.textContent.trim() === "Back to my data"), null, { timeout: 120000 });
});

test("project timeline filters and switches projects offline on the device", async () => {
  await page.waitForFunction(() => document.querySelector('[aria-label="Project Timeline"] button'));
  await page.evaluate(() => document.querySelector('[aria-label="Project Timeline"] button').click());
  await page.waitForFunction(() => document.querySelector('[data-project-id="product"]'));
  await page.evaluate(() => document.querySelector('[data-project-id="product"]').click());
  await page.waitForFunction(() => document.querySelector('[aria-label="Project activity by day"] time'));
  const date = await page.evaluate(() => document.querySelector('[aria-label="Project activity by day"] time').dateTime);
  await page.evaluate((day) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    for (const label of ["Timeline start date", "Timeline end date"]) {
      const input = document.querySelector(`input[aria-label="${label}"]`);
      setter.call(input, day);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }, date);
  await page.waitForFunction(() => document.querySelectorAll('[aria-label="Project activity by day"] li').length === 1);
  await page.evaluate(() => document.querySelector('[data-project-id="life"]').click());
  await page.waitForFunction(() => document.querySelector('[data-project-id="life"]').getAttribute("aria-pressed") === "true");
  assert.equal(await page.evaluate(() => document.querySelector('input[aria-label="Timeline start date"]').value), date);
  await page.evaluate(() => document.querySelector('[data-project-id="product"]').click());
  await page.waitForFunction(() => document.querySelector('[data-project-id="product"]').getAttribute("aria-pressed") === "true");
  assert.equal(await page.evaluate(() => document.querySelectorAll('[aria-label="Project activity by day"] li').length), 1);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "Timeline must fit the screen without horizontal overflow");
});
after(async () => {
  if (!device) return;
  await device.shell("svc wifi enable");
  await device.shell("svc data enable");
  await device.shell("settings put system user_rotation 0");
  await device.close();
});

test("bundled desktop charts and fonts work offline without saving demo account data", async () => {
  const chart = page.locator(".js-plotly-plot").first();
  await expect(chart).toBeVisible({ timeout: 30000 });
  await page.waitForFunction(() => document.fonts.status === "loaded");
  const bounds = await chart.boundingBox();
  const viewportHeight = await page.evaluate(() => visualViewport.height);
  const visibleHeight = Math.max(0, Math.min(viewportHeight, bounds.y + bounds.height) - Math.max(0, bounds.y));
  assert.ok(visibleHeight >= bounds.height * 0.4, "At least 40% of the chart should be visible on the first screen");
  const traces = await chart.evaluate((node) => node.data);
  const actual = traces.filter((trace) => trace.mode === "markers");
  const forecast = traces.filter(
    (trace) => trace.mode === "lines+markers" && trace.line.dash === "dash",
  );
  assert.equal(
    actual[0].y[0],
    actual.slice(1).reduce((sum, trace) => sum + trace.y[0], 0),
  );
  assert.equal(
    forecast[0].y[1],
    forecast.slice(1).reduce((sum, trace) => sum + trace.y[1], 0),
  );
  for (const trace of actual) {
    assert.equal(
      trace.marker.color,
      forecast.find((f) => f.legendgroup === trace.legendgroup).marker.color,
    );
  }
  const files = (await device.shell(`run-as ${pkg} ls files`)).toString();
  assert.ok(!files.includes("dashboard-v1.json"));
  await page.screenshot({
    path: `${screenshots}/overview.png`,
  });
  await chart.evaluate((node) =>
    node.scrollIntoView({ block: "center", behavior: "instant" }),
  );
  const scroll = await page.evaluate(() => scrollY);
  const point = await page.evaluate(() => ({
    x: Math.round((innerWidth * devicePixelRatio) / 2),
    y: Math.round(innerHeight * devicePixelRatio * 0.6),
  }));
  await device.shell(
    `input touchscreen swipe ${point.x} ${point.y} ${point.x} ${point.y - 500} 200`,
  );
  await expect
    .poll(() => page.evaluate(() => scrollY))
    .toBeGreaterThan(scroll + 30);
});

test("search results remain usable with the keyboard and survive rotation", async () => {
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  const search = page.getByRole("searchbox");
  const height = await page.evaluate(() => visualViewport.height);
  await search.click();
  await search.fill("release");
  await expect(
    page.getByText("Review the release checklist · 4", { exact: true }),
  ).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => visualViewport.height))
    .toBeLessThan(height);
  await page.screenshot({ path: `${screenshots}/keyboard.png` });
  await page
    .getByLabel("Filter task priority", { exact: true })
    .selectOption("4");
  await expect(
    page.getByText("No tasks match.", { exact: true }),
  ).toBeVisible();
  const recreated = page.context().waitForEvent("page");
  await device.shell("settings put system user_rotation 1");
  page = await recreated;
  await expect(page.getByRole("searchbox")).toHaveValue("release");
  await expect(
    page.getByText("No tasks match.", { exact: true }),
  ).toBeVisible();
});

test("shared control panel persists alert rules and rejects an empty token", async () => {
  await page
    .getByRole("button", { name: "Control Panel", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Connect and sync", exact: true })
    .click();
  await expect(page.locator(".androidPage [role=alert]")).toHaveText(
    "Enter your Todoist API token.",
  );
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
  await page.reload();
  await expect(
    page.getByText("Monitoring paused", { exact: true }),
  ).toBeVisible();
});
