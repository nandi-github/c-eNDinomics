// filename: ui/playwright.config.ts
/**
 * Playwright configuration for eNDinomics UI smoke tests.
 *
 * Assumes the FastAPI server is already running on localhost:8000.
 * Start it before running tests:
 *   cd src && ./vcleanbld_ui
 *
 * Run tests (both work):
 *   cd src && python3 -B test_flags.py --comprehensive-test   ← recommended
 *   cd src/ui && npx playwright test                          ← standalone, globalSetup creates PlaywrightTest
 *
 * Run with visible browser (debugging):
 *   cd src/ui && npx playwright test --headed
 *
 * Run a single test file:
 *   cd src/ui && npx playwright test tests/smoke.spec.ts
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  globalSetup:    require.resolve("./tests/global-setup"),
  globalTeardown: require.resolve("./tests/global-teardown"),
  fullyParallel: false,       // run sequentially — tests share server state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],

  use: {
    baseURL: "http://localhost:8000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Do NOT start a webServer here — the FastAPI server must already be running.
});
