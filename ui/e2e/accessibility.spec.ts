import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const ROUTES = [
  "/",
  "/sessions",
  "/sessions/diff",
  "/sessions/468fa2ec-1a52-505a-8aa7-35bdad2b9ccf",
  "/context",
  "/tools",
  "/files",
  "/compare",
  "/agents",
  "/behavior",
  "/quality",
  "/insights",
  "/optimize",
  "/guard",
  "/live",
  "/search",
  "/settings",
  "/recap",
] as const;

for (const theme of ["dark", "light"] as const) {
  for (const route of ROUTES) {
    test(`${route} has no automated accessibility violations in ${theme}`, async ({ page }) => {
      await page.addInitScript((preference) => {
        localStorage.setItem(
          "cairn-ui",
          JSON.stringify({ state: { themePreference: preference }, version: 1 }),
        );
      }, theme);
      await page.goto(route);
      await page.locator("main").waitFor();
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });
  }
}

test("skip link reaches main content and dialogs trap and restore focus", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await skip.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const trigger = page.getByRole("button", { name: "Open command palette" });
  await trigger.focus();
  await page.keyboard.press("ControlOrMeta+KeyK");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Search pages and actions" })).toBeFocused();
  for (let index = 0; index < 20; index += 1) await page.keyboard.press("Tab");
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBeTruthy();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("waterfall selection supports j/k and arrow-key traversal", async ({ page }) => {
  await page.goto("/sessions/468fa2ec-1a52-505a-8aa7-35bdad2b9ccf");
  const rows = page.locator("[data-span-id]");
  await rows.first().focus();
  await page.keyboard.press("j");
  await expect(rows.nth(1)).toBeFocused();
  await page.keyboard.press("ArrowUp");
  await expect(rows.first()).toBeFocused();
});

test("primary page reflows at 320 CSS pixels and 200 percent zoom", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/sessions");
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Search" })).toBeVisible();
});

test("reduced motion disables nonessential running animations", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.locator("h1.page-title")).toHaveText("Overview");
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(
    true,
  );
  expect(
    await page.evaluate(
      () =>
        document.getAnimations().filter((animation) => animation.playState === "running").length,
    ),
  ).toBe(0);
});

test("forced colors preserves visible focus and structural boundaries", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active" });
  await page.goto("/");
  await expect(page.locator("h1.page-title")).toHaveText("Overview");
  expect(await page.evaluate(() => matchMedia("(forced-colors: active)").matches)).toBe(true);
  const sessions = page.getByRole("link", { name: "Sessions" }).first();
  await sessions.focus();
  await expect(sessions).toBeFocused();
  const focusStyle = await sessions.evaluate((element) => {
    const style = getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });
  expect(focusStyle.outlineStyle).not.toBe("none");
  expect(Number.parseFloat(focusStyle.outlineWidth)).toBeGreaterThanOrEqual(3);
  await expect(page.locator(".card").first()).toHaveCSS("border-top-style", "solid");
});

test("touch input reaches every mobile route without pointer-only controls", async ({
  browser,
}) => {
  const context = await browser.newContext({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.goto("/");
  const dock = page.getByRole("navigation", { name: "Mobile navigation" });
  await expect(dock).toBeVisible();
  const links = dock.getByRole("link");
  await expect(links).toHaveCount(15);
  const sessions = dock.getByRole("link", { name: "Sessions" });
  const box = await sessions.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  await sessions.tap();
  await expect(page).toHaveURL(/\/sessions$/);
  await expect(page.locator("h1.page-title")).toHaveText("Sessions");
  await context.close();
});
