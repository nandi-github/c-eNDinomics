// filename: ui/playwright.config.ts
/**
 * Playwright configuration for eNDinomics UI smoke tests.
 *
 * Assumes the FastAPI server is already running on localhost:8000.
 * Start it before running tests:
 *   cd root/src && source venv/bin/activate && uvicorn api:app --reload
 *
 * Run tests:
 *   cd root/src/ui && npx playwright test
 *
 * Run with UI (headed, for debugging):
 *   cd root/src/ui && npx playwright test --headed
 *
 * Run a single test file:
 *   cd root/src/ui && npx playwright test tests/smoke.spec.ts
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
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
  // See run-ui-tests.sh for a wrapper that handles server startup.
});
