import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.CAIRN_E2E_BASE_URL ?? "http://127.0.0.1:8787";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  webServer: process.env.CAIRN_E2E_BASE_URL
    ? undefined
    : {
        command:
          "cd .. && uv run python scripts/build_ui.py build && uv run python scripts/e2e_server.py",
        url: `${baseURL}/api/health`,
        reuseExistingServer: false,
        timeout: 120_000,
      },
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      grep: /@cross-browser/,
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      grep: /@cross-browser/,
      use: { ...devices["Desktop Safari"] },
    },
  ],
});
