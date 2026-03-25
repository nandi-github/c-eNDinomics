// filename: ui/tests/global-setup.ts
/**
 * Playwright globalSetup — runs once before any test.
 * Creates PlaywrightTest by cloning __testui__.
 * This makes `npx playwright test` work standalone without needing
 * the test harness (python3 test_flags.py --comprehensive-test) to
 * create the profile first.
 */
import { request } from "@playwright/test";

const BASE_URL    = process.env.PW_BASE_URL ?? "http://localhost:8000";
const PW_PROFILE  = "PlaywrightTest";
const SRC_PROFILE = "__testui__";

async function setup() {
  const ctx = await request.newContext({ baseURL: BASE_URL });

  // Delete any leftover from a previous run
  await ctx.post("/profiles/delete", {
    data: { profile: PW_PROFILE },
  }).catch(() => {});

  // Clone __testui__ → PlaywrightTest
  const res = await ctx.post("/profiles/create", {
    data: { name: PW_PROFILE, source: SRC_PROFILE },
  });

  if (!res.ok()) {
    const body = await res.text();
    throw new Error(
      `globalSetup: failed to create ${PW_PROFILE} from ${SRC_PROFILE}.\n` +
      `Status ${res.status()}: ${body}\n` +
      `Ensure the server is running and --reset-system-profiles has been run.`
    );
  }

  console.log(`[globalSetup] ${PW_PROFILE} created from ${SRC_PROFILE} ✅`);
  await ctx.dispose();
}

export default setup;
