const { test, before, beforeEach, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { _android, expect: playwrightExpect } = require("playwright/test");
const expect = playwrightExpect.configure({ timeout: 15000 });

const pkg = "com.todoistassistant";
const screenshots = `frontend/test-results/device/${process.env.ANDROID_SERIAL ?? "emulator"}`;
let device, page;
async function webViewBounds() {
  // Query the Android accessibility hierarchy without starting Playwright's
  // long-running instrumentation driver, which otherwise outlives this suite.
  const xml = (await device.shell("uiautomator dump /sdcard/todometry-window.xml >/dev/null && cat /sdcard/todometry-window.xml")).toString();
  const node = xml.match(/<node\b(?=[^>]*class="android\.webkit\.WebView")(?=[^>]*package="com\.todoistassistant")([^>]*)>/)?.[1];
  const bounds = node?.match(/bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);
  if (!bounds) return null;
  const [, left, top, right, bottom] = bounds.map(Number);
  return { x: left, y: top, width: right - left, height: bottom - top };
}
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

test("navigation and timeline survive rotation and process recreation", async () => {
  const clickTab = (name) => page.evaluate((label) => Array.from(document.querySelectorAll('nav[aria-label="Dashboard sections"] button')).find((button) => button.textContent.trim() === label).click(), name);
  await clickTab("Control Panel");
  await page.waitForFunction(() => document.querySelector('#dashboard-settings input[type="checkbox"]'));
  const originalRule = await page.evaluate(() => {
    const checkbox = document.querySelector('#dashboard-settings input[type="checkbox"]');
    const checked = checkbox.checked;
    checkbox.click();
    return checked;
  });
  await page.waitForFunction(() => localStorage.getItem("todometry-android-dashboard-settings-draft") !== null);
  await clickTab("Projects");
  await page.waitForFunction(() => document.querySelector('input[aria-label="Search tasks, projects or activity"]'));
  await page.evaluate(() => {
    const input = document.querySelector('input[aria-label="Search tasks, projects or activity"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "release");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForFunction(() => document.querySelector('input[aria-label="Search tasks, projects or activity"]').value === "release");
  await clickTab("Projects");
  assert.equal(await page.evaluate(() => document.querySelector('input[aria-label="Search tasks, projects or activity"]').value), "release");
  await clickTab("Activity");
  await clickTab("Projects");
  assert.equal(await page.evaluate(() => document.querySelector('input[aria-label="Search tasks, projects or activity"]').value), "release");
  await clickTab("Overview");
  await page.evaluate(() => document.querySelector('[aria-label="Project Timeline"] button').click());
  await page.waitForFunction(() => document.querySelector('[data-project-id="product"]'));
  await page.evaluate(() => document.querySelector('[data-project-id="product"]').click());
  await page.waitForFunction(() => document.querySelector('[aria-label="Selected project timeline"]'));
  await page.waitForFunction(() => JSON.parse(localStorage.getItem("todoist-ui") || "{}").timelineProject === "product");
  await page.screenshot({ path: `${screenshots}/navigation-portrait.png` });

  const rotated = page.context().waitForEvent("page", { timeout: 120000 });
  await device.shell("settings put system user_rotation 1");
  page = await rotated;
  await page.waitForFunction(() => document.querySelector('[aria-label="Selected project timeline"]'), null, { timeout: 120000 });
  assert.equal(await page.evaluate(() => document.querySelector('[data-project-id="product"]').getAttribute("aria-pressed")), "true");
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.screenshot({ path: `${screenshots}/navigation-landscape.png` });

  await device.shell(`am force-stop ${pkg}`);
  const recreated = device.waitForEvent("webview", { predicate: (view) => view.pkg() === pkg });
  await device.shell(`am start -n ${pkg}/.MainActivity`);
  page = await (await recreated).page();
  await page.waitForFunction(() => Array.from(document.querySelectorAll("button")).some((button) => button.textContent.trim() === "Explore a demo"), null, { timeout: 120000 });
  await page.evaluate(() => Array.from(document.querySelectorAll("button")).find((button) => button.textContent.trim() === "Explore a demo").click());
  await page.waitForFunction(() => document.querySelector('[aria-label="Selected project timeline"]'), null, { timeout: 120000 });
  assert.equal(await page.evaluate(() => document.querySelector('[data-project-id="product"]').getAttribute("aria-pressed")), "true");
  await clickTab("Control Panel");
  await page.waitForFunction(() => document.querySelector('#dashboard-settings input[type="checkbox"]'));
  assert.equal(await page.evaluate(() => document.querySelector('#dashboard-settings input[type="checkbox"]').checked), !originalRule);
  assert.ok(await page.evaluate(() => document.querySelector("#dashboard-settings").innerText.includes("Unsaved changes")));
  await clickTab("Overview");
  await device.shell("input keyevent KEYCODE_BACK");
  await page.waitForFunction(() => !document.querySelector('[aria-label="Selected project timeline"]'));
  assert.equal(await page.evaluate(() => document.querySelector('[aria-label="Project Timeline"] button').textContent.trim()), "Hide");
  await device.shell("input keyevent KEYCODE_BACK");
  await page.waitForFunction(() => document.querySelector('[aria-label="Project Timeline"] button').textContent.trim() === "Show");
});

test("larger system text and appearance keep Android navigation usable", async () => {
  const original = (await device.shell("settings get system font_scale")).toString().trim();
  assert.match(original, /^(null|\d+(\.\d+)?)$/);
  // CI already runs at 1.3; writing the same value does not recreate the Activity.
  const largeScale = Number(original) === 1.3 ? "1.5" : "1.3";
  const night = (await device.shell("cmd uimode night")).toString().trim().match(/^Night mode: (yes|no|auto)$/);
  assert.ok(night, "The emulator must report its system appearance");
  try {
    const recreated = page.context().waitForEvent("page", { timeout: 120000 });
    await device.shell(`settings put system font_scale ${largeScale}`);
    page = await recreated;
    assert.equal(Number((await device.shell("settings get system font_scale")).toString().trim()), Number(largeScale));
    await page.waitForFunction(() => Array.from(document.querySelectorAll("button")).some((button) => button.textContent.trim() === "Back to my data"), null, { timeout: 120000 });
    const layout = await page.evaluate(() => {
      const nav = document.querySelector('nav[aria-label="Dashboard sections"]');
      const buttons = Array.from(nav.querySelectorAll("button")).map((button) => {
        const rect = button.getBoundingClientRect();
        return { left: rect.left, right: rect.right, width: rect.width, height: rect.height };
      });
      return { width: innerWidth, overflow: document.documentElement.scrollWidth, buttons };
    });
    assert.ok(layout.overflow <= layout.width + 1, "Large text must not overflow the screen");
    assert.ok(layout.buttons.every((button) => button.left >= -1 && button.right <= layout.width + 1 && button.width >= 48 && button.height >= 48), "Navigation controls remain visible and touchable");
    await page.screenshot({ path: `${screenshots}/navigation-large-text.png` });
    await page.evaluate(() => Array.from(document.querySelectorAll('nav[aria-label="Dashboard sections"] button')).find((button) => button.textContent.trim() === "Activity").click());
    await page.waitForFunction(() => document.querySelector("h1")?.textContent === "Activity");
    const beforeColours = await page.evaluate(() => [getComputedStyle(document.documentElement).getPropertyValue("--bg"), getComputedStyle(document.documentElement).getPropertyValue("--text")]);
    const appearance = page.context().waitForEvent("page", { timeout: 120000 });
    await device.shell(`cmd uimode night ${night[1] === "yes" ? "no" : "yes"}`);
    page = await appearance;
    await page.waitForFunction(() => document.querySelector("h1")?.textContent === "Activity", null, { timeout: 120000 });
    assert.deepEqual(await page.evaluate(() => [getComputedStyle(document.documentElement).getPropertyValue("--bg"), getComputedStyle(document.documentElement).getPropertyValue("--text")]), beforeColours);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: `${screenshots}/navigation-alternate-appearance.png` });
  } finally {
    await device.shell(`cmd uimode night ${night[1]}`);
    if (original === "null") await device.shell("settings delete system font_scale");
    else await device.shell(`settings put system font_scale ${original}`);
  }
});

test("Android Back dismisses the keyboard before leaving search", async () => {
  await page.evaluate(() => Array.from(document.querySelectorAll('nav[aria-label="Dashboard sections"] button')).find((button) => button.textContent.trim() === "Projects").click());
  await page.waitForFunction(() => document.querySelector('input[aria-label="Search tasks, projects or activity"]'));
  await page.evaluate(() => document.querySelector('input[aria-label="Search tasks, projects or activity"]').scrollIntoView({ block: "center", behavior: "instant" }));
  const box = await page.evaluate(() => {
    const rect = document.querySelector('input[aria-label="Search tasks, projects or activity"]').getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, scale: devicePixelRatio, height: visualViewport.height };
  });
  const bounds = await webViewBounds();
  assert.ok(bounds, "The Android accessibility hierarchy must include the WebView");
  const x = Math.round(bounds.x + box.x * box.scale);
  const y = Math.round(bounds.y + box.y * box.scale);
  await device.shell(`input tap ${x} ${y}`);
  let shown = false;
  for (let attempt = 0; attempt < 20 && !shown; attempt++) {
    shown = /mInputShown=true/.test((await device.shell("dumpsys input_method")).toString());
    if (!shown) await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.ok(shown, "The system keyboard should open after touching search");
  await page.waitForFunction((height) => visualViewport.height < height - 30, box.height, { timeout: 30000 });
  await page.screenshot({ path: `${screenshots}/keyboard-insets.png` });
  await device.shell("input keyevent KEYCODE_BACK");
  await page.waitForFunction((height) => visualViewport.height >= height - 2, box.height, { timeout: 30000 });
  assert.equal(await page.evaluate(() => document.querySelector("h1").textContent), "Projects");
});
after(async () => {
  if (!device) return;
  console.log("Restoring emulator network and rotation settings");
  await device.shell("svc wifi enable");
  await device.shell("svc data enable");
  await device.shell("settings put system user_rotation 0");
  console.log("Stopping the Android test driver and closing the device");
  await device.shell("am force-stop com.microsoft.playwright.androiddriver");
  await device.close();
  console.log("Android device cleanup complete");
}, { timeout: 90000 });

test("bundled desktop charts and fonts work offline without saving demo account data", async () => {
  // Deferred overview cards can render ahead of this one depending on scroll.
  const chart = page.locator(".card").filter({ has: page.getByRole("heading", { name: "Completed tasks", exact: true }) }).locator(".js-plotly-plot");
  await expect(chart).toBeVisible({ timeout: 30000 });
  await page.waitForFunction(() => document.fonts.status === "loaded");
  await chart.evaluate((node) => node.scrollIntoView({ block: "center", behavior: "instant" }));
  const bounds = await chart.boundingBox();
  const { viewportHeight, viewportWidth } = await page.evaluate(() => ({ viewportHeight: visualViewport.height, viewportWidth: visualViewport.width }));
  const visibleHeight = Math.max(0, Math.min(viewportHeight, bounds.y + bounds.height) - Math.max(0, bounds.y));
  assert.ok(visibleHeight >= Math.min(bounds.height, viewportHeight) * 0.8, "The chart should be readable when scrolled into view");
  assert.ok(bounds.x >= -1 && bounds.x + bounds.width <= viewportWidth + 1, "The chart must fit the phone width");
  const traces = await chart.evaluate((node) => node.data);
  const actual = traces.filter((trace) => trace.mode === "markers");
  const forecast = traces.filter(
    (trace) => trace.mode === "lines+markers" && trace.line.dash === "dash",
  );
  assert.ok(actual.length > 0, "The completion chart must show actual data");
  assert.ok(forecast.length > 0, "The completion chart must show the demo forecast");
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
  const context = page.context();
  // Depending on the Android version and keyboard state, rotation may either
  // keep the WebView or recreate it. Both paths must preserve the search.
  const onPage = (created) => { page = created; };
  context.on("page", onPage);
  try {
    await device.shell("settings put system user_rotation 1");
    await expect.poll(async () => {
      const bounds = await webViewBounds();
      return Boolean(bounds && bounds.width > bounds.height);
    }, { timeout: 120000 }).toBe(true);
    await expect.poll(async () => {
      const candidate = page;
      if (candidate.isClosed()) return null;
      try {
        const search = candidate.getByRole("searchbox");
        const priority = candidate.getByLabel("Filter task priority", { exact: true });
        if (await search.count() !== 1 || await priority.count() !== 1) return null;
        return {
          search: await search.inputValue(),
          priority: await priority.inputValue(),
          empty: await candidate.getByText("No tasks match.", { exact: true }).isVisible(),
        };
      } catch (error) {
        if (candidate.isClosed() || /Execution context was destroyed|navigation/i.test(String(error))) return null;
        throw error;
      }
    }, { timeout: 120000 }).toEqual({ search: "release", priority: "4", empty: true });
  } catch (error) {
    const [rotation, window, keyboard] = await Promise.all([
      device.shell("settings get system user_rotation"),
      device.shell("dumpsys window displays"),
      device.shell("dumpsys input_method"),
    ]);
    console.error("Rotation diagnostics:", {
      requestedRotation: rotation.toString().trim(),
      display: window.toString().split("\n").filter((line) => /mRotation|mCurrentFocus/.test(line)).join(" "),
      inputShown: /mInputShown=true/.test(keyboard.toString()),
      openPages: context.pages().length,
    });
    throw error;
  } finally {
    context.off("page", onPage);
  }
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
