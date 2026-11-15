// Read just the WebView node; full-tree dumps were killed in CI.
async function waitForWebViewBounds(device, packageName, timeout = 20000) {
  const selector = { clazz: "android.webkit.WebView", pkg: packageName };
  await device.wait(selector, { timeout });
  let timer;
  try {
    // Playwright's AndroidDevice.info has no timeout of its own.
    const result = await Promise.race([
      device.info(selector),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("Timed out reading WebView bounds")), timeout);
      }),
    ]);
    const bounds = result?.bounds;
    if (!bounds || ![bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isFinite) || bounds.width <= 0 || bounds.height <= 0) {
      throw new Error("WebView bounds are invalid or empty");
    }
    return bounds;
  } finally {
    clearTimeout(timer);
  }
}

function displayRotation(dump) {
  // mRotation is the physical display rotation, unlike a viewport reduced by
  // the on-screen keyboard. Ignore symbolic mRotation=ROTATION_... values.
  const match = dump.match(/^\s*mRotation=([0-3])\b/m);
  return match ? Number(match[1]) : null;
}

function isMissingAndroidSelector(error) {
  // Playwright's Android driver calls getClassName() on the result of findObject().
  // A missing node produces this specific null-reference error; driver/ADB errors
  // must remain visible instead of being treated as an absent element.
  return error instanceof Error && /java\.lang\.NullPointerException:.*androidx\.test\.uiautomator\.UiObject2\.getClassName\(\).*null object reference/s.test(error.message);
}

module.exports = { displayRotation, isMissingAndroidSelector, waitForWebViewBounds };
