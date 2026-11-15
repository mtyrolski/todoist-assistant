const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function nodes(xml) {
  return (xml.match(/<node\b[^>]*>/g) ?? []).map((node) => ({
    className: node.match(/\bclass="([^"]*)"/)?.[1] ?? "",
    packageName: node.match(/\bpackage="([^"]*)"/)?.[1] ?? "",
    bounds: node.match(/\bbounds="\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"/)?.slice(1).map(Number),
  }));
}

function parseWebViewBounds(xml, packageName) {
  for (const node of nodes(xml)) {
    if (node.className !== "android.webkit.WebView" || node.packageName !== packageName || !node.bounds) continue;
    const [left, top, right, bottom] = node.bounds;
    if (right > left && bottom > top) return { x: left, y: top, width: right - left, height: bottom - top };
  }
  return null;
}

async function waitForHierarchy(readDump, description, select, { attempts = 8, interval = 500, sleep = delay } = {}) {
  let xml = "";
  for (let attempt = 0; attempt < attempts; attempt++) {
    xml = await readDump();
    const result = select(xml);
    if (result !== null) return result;
    if (attempt + 1 < attempts) await sleep(interval);
  }
  // Do not include node text or content descriptions: they can contain account data.
  const summary = nodes(xml).slice(0, 20).map(({ className, packageName: name, bounds }) => ({ className, packageName: name, bounds }));
  const rotation = xml.match(/<hierarchy\b[^>]*\brotation="([0-3])"/)?.[1] ?? "unknown";
  throw new Error(`${description} after ${attempts} hierarchy dumps; rotation=${rotation}: ${JSON.stringify(summary)}`);
}

function waitForWebViewBounds(readDump, packageName, options) {
  return waitForHierarchy(readDump, `No visible WebView for ${packageName}`, (xml) => parseWebViewBounds(xml, packageName), options);
}

function waitForRotation(readDump, rotation, options) {
  return waitForHierarchy(readDump, `Device did not reach rotation ${rotation}`, (xml) => {
    const found = xml.match(/<hierarchy\b[^>]*\brotation="([0-3])"/)?.[1];
    return found === String(rotation) ? rotation : null;
  }, options);
}

module.exports = { parseWebViewBounds, waitForWebViewBounds, waitForRotation };
