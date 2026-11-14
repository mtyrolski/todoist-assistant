import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const rules = {
      enabled: true, fire: true, priority: true, due: true, deadline: true,
      fireLabels: "fire", priorities: [4, 3], priorityMin: 1,
      dueDays: 0, dueMin: 1, deadlineDays: 0, deadlineMin: 1,
    };
    const preferences = { rules, settings: null, labels: ["fire"] };
    const week = Array(9).fill(3);
    const longName = "A project with a deliberately long name and an unbroken suffix " + "x".repeat(80);
    const model = {
      syncedAt: "2026-11-02T10:00:00Z", weekStart: "2026-11-02", weeks: week,
      priorities: [1, 0, 0, 0], forecast: 3, forecastAvailable: false,
      historyAvailable: true, historyWarning: "", weeklyProjects: week.map(() => ({ Work: 3 })),
      projectForecasts: {}, projectColors: {}, projects: [{ id: "p", path: longName }],
      tasks: [{ id: "t", projectId: "p", project: longName, content: longName,
        priority: 4, due: "", deadline: "", labels: [] }],
      activity: [{ id: "a", kind: "completed", content: longName, project: longName, date: "2026-11-01T12:00:00Z" }],
    };
    const state = { connected: true, demo: false, loading: false, syncing: false,
      message: "", model, preferences, alert: { enabled: true, level: 0, matches: 0 } };
    window.addEventListener("test-many-chart-lines", () => {
      for (let i = 0; i < 12; i++)
        for (const counts of model.weeklyProjects) (counts as Record<string, number>)[i === 10 ? "Łódź Research 10" : `Research ${i}`] = i + 1;
      window.dispatchEvent(new CustomEvent("todoist-state", { detail: structuredClone(state) }));
    });
    window.Todoist = {
      ready: () => window.dispatchEvent(new CustomEvent("todoist-state", { detail: state })),
      command: () => {},
      getSettings: () => JSON.stringify(preferences),
      saveSettings: (value) => value,
    };
  });
  await page.goto("/android");
  await expect(page.getByRole("heading", { name: "Dashboard", exact: true })).toBeVisible();
});

test("compact, normal and tablet layouts keep controls within the viewport", async ({ page }, testInfo) => {
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 900 });
    for (const scale of [1, 2]) {
      for (const tab of ["Overview", "Projects", "Activity", "Control Panel"]) {
        await page.getByRole("navigation", { name: "Dashboard sections" }).getByRole("button", { name: tab, exact: true }).click();
        // Browser proxy for Android WebView textZoom: double each computed font size
        // without scaling the viewport or control geometry. A device test is still needed.
        const overflow = await page.evaluate((factor) => {
          const nodes = [...document.querySelectorAll<HTMLElement | SVGElement>(".androidPage, .androidPage *")];
          for (const node of nodes) {
            const original = node.getAttribute("data-test-original-font");
            if (original !== null) {
              if (original) node.style.fontSize = original;
              else node.style.removeProperty("font-size");
              node.removeAttribute("data-test-original-font");
            }
          }
          if (factor !== 1) {
            const sizes = nodes.map((node) => parseFloat(getComputedStyle(node).fontSize));
            nodes.forEach((node, index) => {
              if (!Number.isFinite(sizes[index])) return;
              node.setAttribute("data-test-original-font", node.style.fontSize);
              node.style.setProperty("font-size", `${sizes[index] * factor}px`, "important");
            });
          }
          const viewport = document.documentElement.clientWidth;
          return [...document.querySelectorAll<HTMLElement>(".androidPage button, .androidPage input, .androidPage select, .androidPage summary")]
            .filter((node) => node.getClientRects().length && getComputedStyle(node).visibility !== "hidden")
            .map((node) => ({ name: node.getAttribute("aria-label") || node.textContent?.trim() || node.tagName,
              left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right,
              clipped: node.tagName === "BUTTON" && (node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1) }))
            .filter((node) => node.left < -1 || node.right > viewport + 1 || node.clipped);
        }, scale);
        expect(overflow, `${tab}, ${width}px, text scale ${scale}`).toEqual([]);
      }
    }
    await page.screenshot({ path: testInfo.outputPath(`android-${width}.png`) });
  }
});

test("primary controls have accessible names, touch targets and keyboard focus", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const nav = page.getByRole("navigation", { name: "Dashboard sections" });
  const activity = nav.getByRole("button", { name: "Activity", exact: true });
  await activity.focus();
  expect(await activity.evaluate((node) => getComputedStyle(node).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Activity", exact: true })).toBeVisible();
  const undersized = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>(".androidPage button, .androidPage select, .androidPage input:not([type=checkbox]), .androidPage summary")]
    .filter((node) => node.getClientRects().length && getComputedStyle(node).visibility !== "hidden")
    .map((node) => ({ name: node.getAttribute("aria-label") || node.textContent?.trim(), width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height }))
    .filter((node) => node.width < 47 || node.height < 47));
  expect(undersized).toEqual([]);
  await expect(page.getByRole("searchbox", { name: "Search tasks, projects or activity" })).toBeVisible();
});

test("bundled font supports Polish text without a Google Fonts connection", async ({ page }) => {
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.reload();
  const fonts = await page.evaluate(async () => {
    const latin = await document.fonts.load('400 16px "Space Grotesk"', "Todometry");
    const polish = await document.fonts.load('700 16px "Space Grotesk"', "ąćęłńóśźż");
    return {
      family: getComputedStyle(document.documentElement).fontFamily,
      latin: latin.map((font) => font.status),
      polish: polish.map((font) => font.status),
    };
  });
  expect(fonts.family).toContain("Space Grotesk");
  expect(fonts.latin).toContain("loaded");
  expect(fonts.polish).toContain("loaded");
});

test("compact completion chart keeps axis labels within its card", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  const chart = page.locator(".js-plotly-plot").first();
  await expect(chart).toBeVisible();
  const clipped = await chart.evaluate((plot) => {
    const bounds = plot.closest(".cardBody")!.getBoundingClientRect();
    return [...plot.querySelectorAll<SVGTextElement>(".xaxislayer-above text, .yaxislayer-above text")]
      .filter((text) => text.textContent?.trim())
      .map((text) => ({ text: text.textContent, rect: text.getBoundingClientRect() }))
      .filter(({ rect }) => rect.left < bounds.left - 1 || rect.right > bounds.right + 1 || rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1)
      .map(({ text }) => text);
  });
  expect(clipped).toEqual([]);
});

test("a long chart legend can be searched without losing selected lines", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.evaluate(() => window.dispatchEvent(new Event("test-many-chart-lines")));
  const chart = page.getByRole("region", { name: "Completed tasks", exact: true });
  await chart.locator("summary").click();
  const search = chart.getByRole("searchbox", { name: "Search Completed tasks lines" });
  await search.fill("lodz research 10");
  const line = chart.getByRole("button", { name: "Łódź Research 10", exact: true });
  await expect(line).toBeVisible();
  await expect(chart.getByRole("button", { name: "Research 11", exact: true })).toHaveCount(0);
  await line.click();
  await expect(line).toHaveAttribute("aria-pressed", "true");
  await search.fill("nothing matches");
  await expect(chart.getByText("No matching lines.")).toBeVisible();
  await search.fill("lodz research 10");
  await expect(line).toHaveAttribute("aria-pressed", "true");
  await search.press("Tab");
  await expect(line).toBeFocused();

  const scrollBefore = await page.evaluate(() => window.scrollY);
  const cumulative = page.getByRole("region", { name: "Cumulative completions", exact: true });
  await cumulative.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(scrollBefore);
  await cumulative.locator("summary").click();
  const otherSearch = cumulative.getByRole("searchbox", { name: "Search Cumulative completions lines" });
  await expect(otherSearch).toHaveValue("");
  await otherSearch.fill("lodz research 10");
  await expect(cumulative.getByRole("button", { name: "Łódź Research 10", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(search).toHaveValue("lodz research 10");
});

test("both system appearances retain readable colours and reduced motion", async ({ page }) => {
  const colours: string[][] = [];
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    colours.push(await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      return [style.getPropertyValue("--bg").trim(), style.getPropertyValue("--text").trim(), style.getPropertyValue("--muted").trim()];
    }));
    expect(await page.locator(".androidPage .button").first().evaluate((node) => parseFloat(getComputedStyle(node).transitionDuration))).toBeLessThan(0.001);
  }
  expect(colours[0]).toEqual(colours[1]);
  const luminance = (hex: string) => {
    const rgb = [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16) / 255)
      .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  for (const colour of colours[0].slice(1))
    expect((luminance(colour) + 0.05) / (luminance(colours[0][0]) + 0.05)).toBeGreaterThanOrEqual(4.5);
});

test("unsaved Android settings survive recreation and are cleared on save or disconnect", async ({ page }) => {
  const key = "todometry-android-dashboard-settings-draft";
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  const monitoring = page.getByLabel("Enable attention monitoring");
  await monitoring.uncheck();
  await expect.poll(() => page.evaluate((name) => localStorage.getItem(name), key)).not.toBeNull();
  await page.reload();
  await expect(monitoring).not.toBeChecked();
  await expect(page.getByText("Unsaved settings restored. Save to apply them.")).toBeVisible();
  await page.getByRole("button", { name: "Save settings", exact: true }).click();
  await expect.poll(() => page.evaluate((name) => localStorage.getItem(name), key)).toBeNull();
  await monitoring.check();
  await expect.poll(() => page.evaluate((name) => localStorage.getItem(name), key)).not.toBeNull();
  await page.evaluate(() => { delete window.Todoist; });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect.poll(() => page.evaluate((name) => localStorage.getItem(name), key)).toBeNull();
});

test("a stale or corrupt Android settings draft is preserved until explicitly discarded", async ({ page }) => {
  const key = "todometry-android-dashboard-settings-draft";
  const raw = '{"base":"stale","draft":{}}';
  await page.evaluate(([name, value]) => localStorage.setItem(name, value), [key, raw]);
  await page.getByRole("button", { name: "Control Panel", exact: true }).click();
  await expect(page.getByText(/stored settings draft is invalid or based on older settings/)).toBeVisible();
  await expect(page.getByLabel("Enable attention monitoring")).toBeChecked();
  expect(await page.evaluate((name) => localStorage.getItem(name), key)).toBe(raw);
  await page.getByLabel("Enable attention monitoring").uncheck();
  await page.getByRole("button", { name: "Save settings", exact: true }).click();
  expect(await page.evaluate((name) => localStorage.getItem(name), key)).toBe(raw);
  await page.getByRole("button", { name: "Discard stored draft" }).click();
  await expect.poll(() => page.evaluate((name) => localStorage.getItem(name), key)).toBeNull();
});
