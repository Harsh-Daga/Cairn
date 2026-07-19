import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const response = await request.get("/api/health", { timeout: 2_000 });
  expect(response.ok(), "The required seeded Cairn server must be healthy").toBe(true);
});

test("@cross-browser overview loads and shows title", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1.page-title")).toHaveText("Overview");
});

test("@cross-browser custom time range is URL-backed and sent as explicit half-open bounds", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Custom" }).click();
  await page.getByRole("textbox", { name: "Start", exact: true }).fill("2026-07-01T00:00");
  await page.getByRole("textbox", { name: "End", exact: true }).fill("2026-07-18T00:00");
  await page.getByRole("textbox", { name: "IANA timezone", exact: true }).fill("Asia/Kolkata");
  const response = page.waitForResponse((candidate) => {
    const url = new URL(candidate.url());
    return (
      url.pathname === "/api/overview" &&
      url.searchParams.get("start") === "2026-07-01T00:00" &&
      url.searchParams.get("end") === "2026-07-18T00:00" &&
      url.searchParams.get("timezone") === "Asia/Kolkata"
    );
  });
  await page.getByRole("button", { name: "Apply" }).click();
  expect((await response).ok()).toBe(true);
  await expect(page).toHaveURL(/start=2026-07-01T00%3A00/);
  await expect(page).toHaveURL(/tz=Asia%2FKolkata/);
});

test("navigate overview to sessions via sidebar link", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1.page-title")).toHaveText("Overview");

  await page.getByRole("link", { name: "Sessions", exact: true }).click();
  await expect(page).toHaveURL(/\/sessions$/);
  await expect(page.locator("h1.page-title")).toHaveText("Sessions");
});

test("overview answers money, quality, shields, and cause evidence", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "What this window cost, and what success cost" }),
  ).toBeVisible();
  await expect(page.getByText(/independent facts, not one trust score/)).toBeVisible();
  for (const shield of ["Verification", "Scope", "Privacy", "Resource"]) {
    await expect(page.getByRole("heading", { name: `${shield} shield` })).toBeVisible();
  }
  await expect(page.getByText("Completion claims", { exact: true })).toBeVisible();
  await expect(page.getByText("Decayed rules", { exact: true })).toBeVisible();
  const evidence = page.getByRole("button", { name: /Evidence \(/ }).first();
  await expect(evidence).toBeVisible();
  await evidence.click();
  const panel = page.getByRole("dialog", { name: /evidence$/i });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/not guaranteed savings/)).toBeVisible();
  await panel.getByRole("button", { name: "Close" }).click();
});

test("overview deep-link targets open the exact insight and experiment", async ({
  page,
  request,
}) => {
  const insightsResponse = await request.get("/api/insights");
  expect(insightsResponse.ok()).toBe(true);
  const insights = (await insightsResponse.json()).insights as Array<{ insight_id: string }>;
  expect(insights.length).toBeGreaterThan(0);
  await page.goto(`/insights?insight=${encodeURIComponent(insights[0].insight_id)}`);
  await expect(page.getByRole("button", { name: "Copy fix" })).toBeVisible();

  const experimentsResponse = await request.get("/api/experiments");
  expect(experimentsResponse.ok()).toBe(true);
  const experiments = (await experimentsResponse.json()).experiments as Array<{
    experiment_id: string;
  }>;
  expect(experiments.length).toBeGreaterThan(0);
  await page.goto(`/optimize?experiment=${encodeURIComponent(experiments[0].experiment_id)}`);
  await expect(page.getByRole("button", { name: "Hide diff" })).toBeVisible();
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

test("sessions typed filters, accessible chips, and multi-session summary", async ({ page }) => {
  await page.goto("/sessions");
  const filter = page.getByRole("combobox", { name: "Session filter" });
  await filter.fill("cost:>0");
  await filter.press("Enter");
  await expect(page).toHaveURL(/q=cost%3A%3E0/);
  await expect(page.getByRole("button", { name: "Remove filter cost:>0" })).toBeVisible();
  expect(await page.locator("[data-trace-row]").count()).toBeLessThan(50);

  const selections = page.getByRole("checkbox", { name: /for compare/ });
  await expect(selections.nth(2)).toBeVisible();
  for (let index = 0; index < 3; index += 1) await selections.nth(index).check();
  await page.getByRole("button", { name: "Summarize selected (3)" }).click();
  await expect(page.getByRole("region", { name: "Selected session summary" })).toContainText(
    "Descriptive totals only",
  );

  await filter.fill("claim:unsupported");
  await filter.press("Enter");
  await expect(page.getByRole("alert")).toContainText(/not available yet/);
  await expect(page.locator("[data-trace-row]")).toHaveCount(0);
});

test("session diff shows validity, signed metrics, evidence, and aligned spans", async ({
  page,
}) => {
  await page.goto("/sessions");
  const selections = page.getByRole("checkbox", { name: /for compare/ });
  await selections.nth(0).check();
  await selections.nth(1).check();
  await page.getByRole("button", { name: "Compare selected (2)" }).click();

  await expect(page).toHaveURL(/\/sessions\/diff\?a=.*&b=.*/);
  await expect(page.getByRole("region", { name: "Comparison validity" })).toContainText(
    /descriptive associations/i,
  );
  for (const metric of [
    "Cost delta",
    "Tokens delta",
    "Waste delta",
    "Quality delta",
    "Duration delta",
  ]) {
    await expect(page.getByText(metric, { exact: true })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "What changed" })).toContainText(
    /no causal attribution/i,
  );
  await expect(page.getByRole("region", { name: "Aligned session timeline" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open session A" }).first()).toBeVisible();
});

test("@cross-browser session detail time mode toggle", async ({ page, request }) => {
  const traces = await request.get("/api/traces?limit=1");
  expect(traces.ok(), "The seeded trace API must be available").toBe(true);
  const body = await traces.json();
  const traceId = body.traces?.[0]?.trace_id as string | undefined;
  expect(traceId, "The deterministic E2E seed must contain a trace").toBeTruthy();
  const detail = await request.get(`/api/traces/${traceId!}`);
  expect(detail.ok()).toBe(true);
  const detailBody = await detail.json();
  const spanId = detailBody.spans?.[0]?.span_id as string | undefined;
  expect(spanId, "The deterministic E2E trace must contain a span").toBeTruthy();

  await page.goto(`/sessions/${traceId!}`);
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Sessions");
  await page.getByRole("button", { name: "Token mode" }).click();
  await expect(page).toHaveURL(/(?:\?|&)mode=time(?:&|$)/);
  await page.locator(`[data-span-id="${spanId!}"]`).click();
  await expect(page.getByRole("dialog", { name: "Span inspector" })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`(?:\\?|&)span=${encodeURIComponent(spanId!)}(?:&|$)`));
  await expect(page.getByRole("tab", { name: "Links" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Time mode" })).toBeVisible();
  for (const shield of ["verification", "scope", "privacy", "resource"]) {
    await expect(page.getByRole("heading", { name: `${shield} shield` })).toBeVisible();
  }

  await page.getByRole("tab", { name: "transcript" }).click();
  await expect(page).toHaveURL(/(?:\?|&)tab=transcript(?:&|$)/);
  await expect(page.getByRole("region", { name: "Session transcript" })).toBeVisible();

  await page.getByRole("tab", { name: "receipt" }).click();
  await expect(page.getByRole("region", { name: "Verification receipt" })).toContainText(
    "Debt components",
  );
  await expect(
    page.getByText(/cannot prove validation occurred after the final relevant edit/i),
  ).toBeVisible();

  await page.getByRole("tab", { name: "postmortem" }).click();
  await expect(page.getByRole("region", { name: "Session post-mortem" })).toContainText(
    /recorded localization from the diagnose cascade/i,
  );

  await page.getByRole("tab", { name: "investigate" }).click();
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
  await page.getByRole("button", { name: "4×" }).click();
  await expect(page.getByRole("button", { name: "4×" })).toHaveAttribute("aria-pressed", "true");
});

test("context ledger answers composition without inventing cache savings", async ({ page }) => {
  await page.goto("/context");
  await expect(page.locator("h1.page-title")).toHaveText("Context");
  await expect(page.getByRole("heading", { name: "Where your tokens go" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top re-billed blocks" })).toBeVisible();
  await expect(page.getByText("Unavailable").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Interpretation limits" })).toBeVisible();
  await expect(
    page.getByText(/not a partition of input tokens|provider-specific measured billing/i).first(),
  ).toBeVisible();
});

test("insights ledger ranks findings and opens evidence panel", async ({ page }) => {
  await page.goto("/insights");
  await expect(page.locator("h1.page-title")).toHaveText("Insights");
  const empty = page.getByText("No insights yet");
  if (await empty.isVisible()) {
    await expect(empty).toBeVisible();
    return;
  }
  await expect(page.getByRole("heading", { name: "Ranked findings under evidence" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Insights view mode" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Interpretation limits" })).toBeVisible();
  await page.locator("article.card").first().getByRole("button").first().click();
  await expect(page.getByText(/producer|fix|Evidence/i).first()).toBeVisible();
});

test("quality ledger separates process score from verification evidence", async ({ page }) => {
  await page.goto("/quality");
  await expect(page.locator("h1.page-title")).toHaveText("Quality");
  const empty = page.getByText("Outcomes not captured yet");
  if (await empty.isVisible()) {
    await expect(empty).toBeVisible();
    return;
  }
  await expect(
    page.getByRole("heading", { name: "Process quality vs task evidence" }),
  ).toBeVisible();
  await expect(page.getByText("Unavailable").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Interpretation limits" })).toBeVisible();
  await expect(page.getByText(/process-quality|unsupported/i).first()).toBeVisible();
});

test("compare ledger withholds winners without sufficient samples", async ({ page }) => {
  await page.goto("/compare");
  await expect(page.locator("h1.page-title")).toHaveText("Compare");
  await expect(
    page.getByRole("heading", { name: "Difficulty-aware agent performance" }),
  ).toBeVisible();
  await expect(
    page.getByText(/No leaderboard winner declared|Declared winner/i).first(),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Interpretation limits" })).toBeVisible();
  await expect(
    page.getByText(/descriptive|insufficient samples|minimum sample/i).first(),
  ).toBeVisible();
});

test("shell go shortcuts, palette preferences, and active route stay in sync", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1.page-title")).toHaveText("Overview");
  expect(await page.evaluate(() => document.activeElement?.tagName)).toBe("BODY");
  await page.keyboard.press("KeyG");
  await page.keyboard.press("KeyC");
  await expect(page).toHaveURL(/\/context$/);
  await expect(page.getByRole("link", { name: "Context" }).first()).toHaveAttribute(
    "aria-current",
    "page",
  );

  await page.keyboard.press("/");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  const search = palette.getByRole("textbox", { name: "Search pages and actions" });
  await search.fill("theme light");
  await palette.getByRole("button", { name: "Use light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("workspace request failure produces a persistent local-server state", async ({ page }) => {
  await page.route("**/api/workspace", (route) => route.abort("connectionrefused"));
  await page.goto("/");
  await expect(page.getByText("Local server disconnected")).toBeVisible();
});

test("clean workspace shows the complete local-first setup journey", async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
  await page.route("**/api/workspace", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        workspace_id: "clean-e2e",
        root_path: "/tmp/cairn-clean-e2e",
        name: "cairn-clean-e2e",
        adapters: [],
        health: {
          trace_count: 0,
          insight_count: 0,
          fts_available: false,
          adapter_warnings: [],
          human_label_agreement: { labeled_sessions: 0, agreements: 0, rate: null },
        },
        gauge: null,
      }),
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "No local agent logs found" })).toBeVisible();
  await expect(page.getByText("/tmp/cairn-clean-e2e/.cairn/cairn.db")).toBeVisible();
  await page.getByRole("button", { name: "View setup guide" }).click();
  await expect(page.getByText(/never edits agent or MCP configuration/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Load deterministic demo" })).toBeVisible();
});

test("selected-range empty state expands without re-importing data", async ({ page }) => {
  await page.route("**/api/overview?*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.kpis = {
      ...body.kpis,
      traces: 0,
      input_tokens: 0,
      output_tokens: 0,
      waste_tokens: 0,
      cost: 0,
    };
    await route.fulfill({ response, json: body });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "No sessions in this time range" })).toBeVisible();
  const expanded = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/overview" && url.searchParams.get("preset") === "90d";
  });
  await page.getByRole("button", { name: "Show 90 days" }).click();
  await expanded;
  await expect(page).toHaveURL(/range=90d/);
});

test("demo workspace provides an explicit path back to real data", async ({ page }) => {
  await page.route("**/api/workspace", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.root_path = "/home/local/.cairn-demo";
    await route.fulfill({ response, json: body });
  });
  await page.goto("/");
  await expect(page.getByText("Deterministic demo workspace")).toBeVisible();
  await expect(page.getByText(/cairn ui --workspace \/path\/to\/your-repo/)).toBeVisible();
});

const ROUTES = [
  ["/", "Overview"],
  ["/sessions", "Sessions"],
  ["/sessions/diff", "Session diff"],
  ["/context", "Context"],
  ["/tools", "Tools"],
  ["/files", "Files"],
  ["/compare", "Compare"],
  ["/agents", "Agents"],
  ["/behavior", "Behavior"],
  ["/quality", "Quality"],
  ["/insights", "Insights"],
  ["/optimize", "Optimize"],
  ["/guard", "Guard"],
  ["/live", "Live"],
  ["/search", "Search"],
  ["/settings", "Settings"],
  ["/recap", "Weekly recap"],
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
  await expect(page.getByText(/hits? · page/)).toBeVisible();
  await expect(page.getByText("bounded compatibility scan")).toBeVisible();
  await expect(page.getByRole("region", { name: "Recent local searches" })).toContainText(
    "tool:read",
  );
  const results = page.locator("[data-search-index]");
  await results.first().focus();
  await page.keyboard.press("j");
  await expect(results.nth(1)).toBeFocused();
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

test("theme is applied before React and persists explicit preference", async ({ page }) => {
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("cairn-theme-test-seeded")) {
      localStorage.setItem(
        "cairn-ui",
        JSON.stringify({ state: { themePreference: "light" }, version: 1 }),
      );
      sessionStorage.setItem("cairn-theme-test-seeded", "1");
    }
  });
  await page.goto("/settings");
  await page.getByRole("tab", { name: "appearance" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("button", { name: "light", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await page.getByRole("button", { name: "dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await page.getByRole("tab", { name: "appearance" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("system theme follows operating-system color-scheme changes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme-preference", "system");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
