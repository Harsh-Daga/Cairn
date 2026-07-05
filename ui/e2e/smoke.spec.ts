import { test, expect, type APIRequestContext } from "@playwright/test";

async function serverAvailable(request: APIRequestContext): Promise<boolean> {
  try {
    const res = await request.get("/api/health", { timeout: 2_000 });
    return res.ok();
  } catch {
    return false;
  }
}

test.beforeEach(async ({ request }, testInfo) => {
  if (!(await serverAvailable(request))) {
    testInfo.skip(true, "Cairn server not running at http://127.0.0.1:8787");
  }
});

test("overview loads and shows title", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1.page-title")).toHaveText("Overview");
});

test("navigate overview to sessions via sidebar link", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1.page-title")).toHaveText("Overview");

  await page.getByRole("link", { name: "Sessions" }).click();
  await expect(page).toHaveURL(/\/sessions$/);
  await expect(page.locator("h1.page-title")).toHaveText("Sessions");
});

test("insights page loads", async ({ page }) => {
  await page.goto("/insights");
  await expect(page.locator("h1.page-title")).toHaveText("Insights");
});
