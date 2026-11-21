const { test } = require("node:test");
const assert = require("node:assert/strict");
const { displayRotation, isMissingAndroidSelector, readAndroidInfo, waitForWebViewBounds } = require("./device/webview-bounds.cjs");

test("uses the Android selector to obtain nonempty WebView bounds", async () => {
  const selector = { clazz: "android.webkit.WebView", pkg: "com.todoistassistant" };
  const bounds = { x: 0, y: 24, width: 400, height: 776 };
  const calls = [];
  const device = {
    wait: async (value, options) => calls.push(["wait", value, options]),
    info: async (value) => { calls.push(["info", value]); return { bounds }; },
  };
  assert.deepEqual(await waitForWebViewBounds(device, selector.pkg, 100), bounds);
  assert.deepEqual(calls, [["wait", selector, { timeout: 100 }], ["info", selector]]);
});

test("rejects missing bounds, ADB errors and a stuck info request", async () => {
  const wait = async () => {};
  await assert.rejects(waitForWebViewBounds({ wait, info: async () => ({ bounds: { x: 0, y: 0, width: 0, height: 1 } }) }, "app", 100), /invalid or empty/);
  await assert.rejects(waitForWebViewBounds({ wait, info: async () => { throw new Error("ADB unavailable"); } }, "app", 100), /ADB unavailable/);
  await assert.rejects(waitForWebViewBounds({ wait, info: async () => new Promise(() => {}) }, "app", 5), /Timed out reading WebView bounds/);
  await assert.rejects(waitForWebViewBounds({ wait: async () => { throw new Error("selector timeout"); } }, "app", 100), /selector timeout/);
});

test("reads only numeric physical display rotation from window diagnostics", () => {
  const dump = "overrideConfig={ mRotation=ROTATION_90 }\n    mRotation=1 mDeferredRotationPauseCount=0\n";
  assert.equal(displayRotation(dump), 1);
  assert.equal(displayRotation("    mRotation=0 mDeferredRotationPauseCount=0"), 0);
  assert.equal(displayRotation("overrideConfig={ mRotation=ROTATION_90 }"), null);
});

test("only treats the Android driver's missing selector error as absent", () => {
  const missing = new Error("androidDevice.info: java.lang.NullPointerException: Attempt to invoke virtual method 'java.lang.String androidx.test.uiautomator.UiObject2.getClassName()' on a null object reference");
  assert.equal(isMissingAndroidSelector(missing), true);
  assert.equal(isMissingAndroidSelector(new Error("androidDevice.info: ADB device offline")), false);
  assert.equal(isMissingAndroidSelector(new Error("java.lang.NullPointerException: driver crashed")), false);
});

test("retries a stale accessibility lookup after rotation without hiding driver failures", async () => {
  const selector = { clazz: "android.webkit.WebView", pkg: "preview" };
  let calls = 0;
  const device = { info: async (actual) => {
    assert.deepEqual(actual, selector);
    if (++calls === 1) throw new Error("androidDevice.info: androidx.test.uiautomator.StaleObjectException");
    return { bounds: { width: 800, height: 400 } };
  } };
  assert.equal(await readAndroidInfo(device, selector), null);
  assert.deepEqual(await readAndroidInfo(device, selector), { bounds: { width: 800, height: 400 } });
  await assert.rejects(readAndroidInfo({ info: async () => { throw new Error("androidDevice.info: ADB device offline"); } }, selector), /ADB device offline/);
  await assert.rejects(readAndroidInfo({ info: async () => { throw new Error("androidDevice.tap: androidx.test.uiautomator.StaleObjectException"); } }, selector), /androidDevice.tap/);
});
