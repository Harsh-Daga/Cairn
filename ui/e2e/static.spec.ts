import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { expect, test } from "@playwright/test";

const root = fileURLToPath(new URL("../../", import.meta.url));
const output = resolve(root, "ui/test-results/static-export");
const indexUrl = pathToFileURL(resolve(output, "index.html")).href;

test.beforeAll(() => {
  execFileSync(
    "uv",
    ["run", "python", "scripts/prepare_e2e_static.py", "ui/test-results/static-export"],
    { cwd: root, stdio: "inherit" },
  );
});

test("@cross-browser static snapshot opens directly from file URL", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto(indexUrl);
  await page.waitForTimeout(250);
  expect(errors, "The file snapshot must start without browser errors").toEqual([]);
  await expect(page.locator("h1.page-title")).toHaveText("Overview");
  await expect(page.getByText(/Read-only scrubbed snapshot/)).toBeVisible();
  await expect(page.getByText("Completion claims", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Custom" })).toHaveCount(0);
  await expect(page.getByText(/custom ranges/)).toBeVisible();
  await page.getByRole("link", { name: "Sessions", exact: true }).click();
  await expect(page.locator("h1.page-title")).toHaveText("Sessions");
  await expect(page.locator("[data-trace-row]").first()).toBeVisible();
  const selections = page.getByRole("checkbox", { name: /for compare/ });
  await selections.nth(0).check();
  await selections.nth(1).check();
  await page.getByRole("button", { name: "Compare selected (2)" }).click();
  await expect(page.locator("h1.page-title")).toHaveText("Session diff");
  await expect(page.getByRole("region", { name: "Comparison validity" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Aligned session timeline" })).toBeVisible();
  await page.goto(`${indexUrl}#/recap`);
  await expect(page.locator("h1.page-title")).toHaveText("Weekly recap");
  await expect(page.getByText(/seven local days/i)).toBeVisible();
  expect(errors).toEqual([]);
});
