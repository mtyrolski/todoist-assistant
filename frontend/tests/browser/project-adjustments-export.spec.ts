import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("exports saved manual and automatic project assignments for Android", async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ json: { status: "ok", configured: true } }));
  await page.route("**/api/admin/project_adjustments**", (route) => route.fulfill({ json: {
    files: ["projects.py"], selectedFile: "projects.py",
    mappings: { Old: "Work", Shared: "Personal" },
    automaticMappings: { Child: "Work", Shared: "Work" },
    archivedParentProjects: ["Archive"], activeRootProjects: ["Work", "Personal"],
    archivedRootProjects: ["Old", "Archive"], archivedProjects: ["Old", "Child", "Archive"],
    sourceProjects: ["Old", "Child", "Archive"], unmappedSourceProjects: ["Archive"],
  } }));
  await page.goto("/project-adjustments");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export saved mappings for Android" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("todoist-project-adjustments.json");
  expect(JSON.parse(await readFile(await download.path(), "utf8"))).toEqual({
    format: "todoist-assistant-project-adjustments-v1",
    mappings: { Old: "Work", Child: "Work", Shared: "Personal" },
    archivedParents: ["Archive"],
  });
});
