import { expect, test } from "@playwright/test";

test("the history calendar selects whole periods and individual days", async ({ page }) => {
  await page.goto("/history");
  const from = page.getByLabel("From date");
  const to = page.getByLabel("To date");
  const load = page.getByRole("button", { name: "Load charts" });

  await expect(load).toBeDisabled();
  await page.getByRole("combobox", { name: "Year", exact: true }).selectOption("2024");
  await page.getByRole("combobox", { name: "Month", exact: true }).selectOption({ label: "February" });
  await expect(page.getByRole("table", { name: "February 2024" })).toBeVisible();

  await page.getByRole("button", { name: "Thursday, February 29, 2024" }).click();
  await expect(from).toHaveValue("2024-02-29");
  await expect(to).toHaveValue("2024-02-29");
  await expect(load).toBeEnabled();

  await page.getByRole("button", { name: "Select week of Feb 26, 2024" }).click();
  await expect(from).toHaveValue("2024-02-26");
  await expect(to).toHaveValue("2024-03-03");

  await page.getByRole("button", { name: "Select month" }).click();
  await expect(from).toHaveValue("2024-02-01");
  await expect(to).toHaveValue("2024-02-29");

  await page.getByRole("button", { name: "Select year" }).click();
  await expect(from).toHaveValue("2024-01-01");
  await expect(to).toHaveValue("2024-12-31");
  await from.fill("2010-01-01");
  await expect(load).toBeDisabled();
  await expect(page.getByText("Choose a range of up to 260 weeks.")).toBeVisible();
});
