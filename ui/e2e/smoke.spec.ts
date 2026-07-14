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
    testInfo.skip(true, "Cairn server is not available at the configured E2E base URL");
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

test("sessions saved view round-trip", async ({ page }) => {
  await page.goto("/sessions");
  await expect(page.locator("h1.page-title")).toHaveText("Sessions");

  await page.getByRole("button", { name: "cursor" }).click();
  await page.getByPlaceholder("Save view as…").fill("E2E cursor");
  await page.getByRole("button", { name: "Save view" }).click();
  await expect(page.getByRole("button", { name: "E2E cursor", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Default" }).click();
  await page.getByRole("button", { name: "E2E cursor", exact: true }).click();
  await expect(page.getByRole("button", { name: "cursor", exact: true })).toHaveClass(
    /border-copper/,
  );
});

test("session detail time mode toggle", async ({ page, request }) => {
  const traces = await request.get("/api/traces?limit=1");
  test.skip(!traces.ok(), "No traces available");
  const body = await traces.json();
  const traceId = body.traces?.[0]?.trace_id as string | undefined;
  test.skip(!traceId, "No traces available");

  await page.goto(`/sessions/${traceId}`);
  await page.getByRole("button", { name: "Token mode" }).click();
  await expect(page).toHaveURL(/\?mode=time/);
  await expect(page.getByRole("button", { name: "Time mode" })).toBeVisible();
});

const ROUTES = [
  ["/", "Overview"],
  ["/sessions", "Sessions"],
  ["/sessions/diff", "Session diff"],
  ["/context", "Context"],
  ["/agents", "Agents"],
  ["/behavior", "Behavior"],
  ["/quality", "Quality"],
  ["/insights", "Insights"],
  ["/optimize", "Optimize"],
  ["/live", "Live"],
  ["/search", "Search"],
  ["/settings", "Settings"],
] as const;

for (const [route, title] of ROUTES) {
  test(`${title} route renders`, async ({ page }) => {
    await page.goto(route);
    await expect(page.locator("h1.page-title")).toHaveText(title);
  });
}

test("search operators return real span matches", async ({ page }) => {
  await page.goto("/search");
  await page.getByRole("button", { name: "tool:read" }).click();
  await expect(page.getByText(/hit(s)?$/)).toBeVisible();
});

test("sessions table fits a phone viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/sessions");
  await expect(page.locator("h1.page-title")).toHaveText("Sessions");
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
