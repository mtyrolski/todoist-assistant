const { test } = require("node:test");
const assert = require("node:assert/strict");
const { parseWebViewBounds, waitForWebViewBounds, waitForRotation } = require("./device/webview-bounds.cjs");

const pkg = "com.todoistassistant";
const node = (className, packageName, bounds, text = "") =>
  `<node text="${text}" bounds="${bounds}" package="${packageName}" class="${className}"/>`;
const dump = (rotation, ...children) => `<hierarchy rotation="${rotation}">${children.join("")}</hierarchy>`;
const webView = (packageName, bounds) => node("android.webkit.WebView", packageName, bounds);
const noDelay = { attempts: 4, interval: 0, sleep: async () => {} };

test("parses only a nonempty WebView belonging to the app", () => {
  const xml = dump(0, webView("other.app", "[0,0][800,1200]"), webView(pkg, "[0,0][0,0]"), webView(pkg, "[0,24][400,800]"));
  assert.deepEqual(parseWebViewBounds(xml, pkg), { x: 0, y: 24, width: 400, height: 776 });
  assert.equal(parseWebViewBounds(dump(0, webView("other.app", "[0,0][400,800]")), pkg), null);
  assert.equal(parseWebViewBounds("", pkg), null);
});

test("waits for a fresh, matching hierarchy and bounds its attempts", async () => {
  const dumps = ["", dump(0, webView("other.app", "[0,0][400,800]")), dump(0, webView(pkg, "[0,24][400,800]"))];
  let reads = 0;
  const bounds = await waitForWebViewBounds(async () => dumps[reads++], pkg, noDelay);
  assert.equal(reads, 3);
  assert.deepEqual(bounds, { x: 0, y: 24, width: 400, height: 776 });

  reads = 0;
  await assert.rejects(
    waitForWebViewBounds(async () => { reads++; return dump(1, node("android.view.View", "system.ui", "[0,0][400,800]", "private account text")); }, pkg, noDelay),
    (error) => /after 4 hierarchy dumps/.test(error.message) && /rotation=1/.test(error.message) && !error.message.includes("private account text"),
  );
  assert.equal(reads, 4);
});

test("waits for the physical portrait rotation and propagates shell failures", async () => {
  const dumps = ["", dump(1), dump(0)];
  let reads = 0;
  assert.equal(await waitForRotation(async () => dumps[reads++], 0, noDelay), 0);
  assert.equal(reads, 3);
  await assert.rejects(waitForRotation(async () => dump(1), 0, { ...noDelay, attempts: 2 }), /rotation=1/);
  await assert.rejects(waitForWebViewBounds(async () => { throw new Error("adb unavailable"); }, pkg, noDelay), /adb unavailable/);
});
