const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { _android, expect: baseExpect } = require("playwright/test");
const { isMissingAndroidSelector } = require("./webview-bounds.cjs");
const expect = baseExpect.configure({ timeout: 20000 });

const pkg = "com.todoistassistant.preview";
let device;
before(async () => {
  const devices = await _android.devices({ port: Number(process.env.ANDROID_ADB_SERVER_PORT || 5037) });
  device = devices.find(
    (d) =>
      d.serial().startsWith("emulator-") &&
      (!process.env.ANDROID_SERIAL || d.serial() === process.env.ANDROID_SERIAL),
  );
  await Promise.all(devices.filter((d) => d !== device).map((d) => d.close()));
  assert.ok(device, "Use a dedicated emulator: this test clears Preview data");
  device.setDefaultTimeout(45000);
  await device.shell(`am force-stop ${pkg}`);
  await device.shell(`pm clear ${pkg}`);
  await device.shell("svc wifi disable");
  await device.shell("svc data disable");
  await device.shell("settings put system accelerometer_rotation 0");
  await device.shell("settings put system user_rotation 0");
  await device.shell("settings put secure show_ime_with_hard_keyboard 1");
  await device.shell(`am start -n ${pkg}/com.todoistassistant.MainActivity`);
});
after(async () => {
  if (!device) return;
  await device.shell("svc wifi enable");
  await device.shell("svc data enable");
  await device.shell("settings put system user_rotation 0");
  await device.shell("am force-stop com.microsoft.playwright.androiddriver");
  await device.close();
});
const text = (value) => ({ text: value, pkg });
async function info(selector) {
  try {
    return await device.info(selector);
  } catch (error) {
    if (isMissingAndroidSelector(error)) return null;
    throw error;
  }
}
async function wait(selector) {
  await expect.poll(async () => Boolean((await info(selector))?.enabled), {
    message: `Expected accessible Preview element ${JSON.stringify(selector)}`,
  }).toBe(true);
}
async function tap(selector) {
  await wait(selector);
  await device.tap(selector);
}
async function swipePage(direction) {
  const { bounds } = await device.info({ clazz: "android.webkit.WebView", pkg });
  const x = Math.round(bounds.x + bounds.width * 0.95);
  const top = Math.round(bounds.y + bounds.height * 0.24);
  const bottom = Math.round(bounds.y + bounds.height * 0.84);
  await device.input.swipe(
    { x, y: direction === "down" ? bottom : top },
    [{ x, y: direction === "down" ? top : bottom }],
    80,
  );
}
async function scrollTo(label, direction = "down") {
  for (let attempt = 0; attempt < 8; attempt++) {
    if ((await info(text(label)))?.enabled) return;
    await swipePage(direction);
  }
  await wait(text(label));
}

test("optimized release works offline with search, keyboard, rotation and production debugging disabled", async (t) => {
  assert.match((await device.shell(`run-as ${pkg} id 2>&1`)).toString(), /not debuggable/);
  await tap(text("Explore a demo"));
  await wait(text("Back to my data"));
  await scrollTo("Weekly Completion Trend");
  if (process.env.ANDROID_PLOT_SCREENSHOT) {
    await swipePage("down");
    await device.screenshot({ path: process.env.ANDROID_PLOT_SCREENSHOT });
  }
  await scrollTo("Task Lifespans: Time to Completion");
  await scrollTo("Project Hierarchy");
  await scrollTo("Completed tasks");
  // A heading can appear at the bottom of a smaller screen before its
  // legend enters the accessibility tree. Bring the legend into view too.
  await scrollTo("All projects");
  await scrollTo("Projects", "up");
  await tap(text("Projects"));
  await tap({ clazz: "android.widget.EditText", pkg });
  await device.fill({ clazz: "android.widget.EditText", pkg }, "release");
  await expect
    .poll(async () => (await device.shell("dumpsys input_method")).toString())
    .toMatch(/mInputShown=true/);
  await device.input.press("Back");
  await wait(text("10 of 40 active tasks"));
  await device.shell("settings put system user_rotation 1");
  await expect
    .poll(async () => {
      const node = await info({ clazz: "android.webkit.WebView", pkg });
      return Boolean(node && node.bounds.width > node.bounds.height);
    })
    .toBe(true);
  // Capture the dedicated emulator's demo screen before interacting further,
  // so an inaccessible result after rotation can be diagnosed from CI artifacts.
  const screenshots = `frontend/test-results/device/${process.env.ANDROID_SERIAL ?? "emulator"}`;
  try {
    fs.mkdirSync(screenshots, { recursive: true });
    await device.screenshot({ path: `${screenshots}/preview-search-landscape.png` });
  } catch (error) {
    t.diagnostic(`Could not capture demo screenshot: ${error instanceof Error ? error.name : "unknown error"}`);
  }
  // The resized viewport may hide the result below the search controls. Return
  // to navigation and scroll down only when the exact result isn't accessible.
  if (!(await info(text("10 of 40 active tasks")))?.enabled) {
    await scrollTo("Projects", "up");
    await scrollTo("10 of 40 active tasks");
  }
  await wait(text("10 of 40 active tasks"));
  await device.shell("settings put system user_rotation 0");
  await expect
    .poll(async () => {
      const node = await info({ clazz: "android.webkit.WebView", pkg });
      return Boolean(node && node.bounds.height > node.bounds.width);
    })
    .toBe(true);
  // After rotation the scroll offset can differ by viewport and font scale.
  // Keep swiping until navigation is actually accessible, as above for Projects.
  await scrollTo("Activity", "up");
  await tap(text("Activity"));
  await wait(text("Recent activity"));
  await device.input.press("Back");
  await wait(text("Dashboard"));
  const pid = (await device.shell(`pidof ${pkg}`)).toString().trim();
  assert.ok(pid, "Release must remain running");
  const debugOs = (await device.shell("getprop ro.debuggable")).toString().trim();
  if (process.env.ANDROID_REQUIRE_PRODUCTION_OS === "1") assert.equal(debugOs, "0");
  if (debugOs === "1") {
    // Chromium forces inspection on userdebug OS images regardless of the app setting.
    t.diagnostic("WebView inspection is checked on the Android 16 production image.");
  } else {
    const sockets = (await device.shell("cat /proc/net/unix")).toString();
    assert.ok(!sockets.includes(`webview_devtools_remote_${pid}`), "WebView inspection must be disabled");
  }
});
