// filename: ui/tests/global-teardown.ts
/**
 * Playwright globalTeardown — runs once after all tests complete.
 * Deletes PlaywrightTest so it doesn't clutter the UI dropdown.
 */
import { request } from "@playwright/test";

const BASE_URL   = process.env.PW_BASE_URL ?? "http://localhost:8000";
const PW_PROFILE = "PlaywrightTest";

async function teardown() {
  const ctx = await request.newContext({ baseURL: BASE_URL });
  await ctx.post("/profiles/delete", {
    data: { profile: PW_PROFILE },
  }).catch(() => {});
  console.log(`[globalTeardown] ${PW_PROFILE} deleted ✅`);
  await ctx.dispose();
}

export default teardown;
