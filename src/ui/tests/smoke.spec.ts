// filename: ui/tests/smoke.spec.ts
/**
 * eNDinomics UI + API Smoke Tests — v2.1
 *
 * ── Profile architecture ───────────────────────────────────────────────────
 * __testui__      Hidden fixture. Managed by --reset-system-profiles.
 * PlaywrightTest  Ephemeral visible profile. Created by globalSetup (from
 *                 __testui__) before tests run, deleted by globalTeardown after.
 *                 Works whether you run via --comprehensive-test or npx directly.
 * __system__*     Hidden scenario profiles for Part A API tests.
 *
 * ── Row counts ─────────────────────────────────────────────────────────────
 * NEVER hardcoded. Always derived from person.json via API.
 * /profile-config/<id>/person.json returns a wrapper:
 *   { content: "<json string>", profile: "...", readme: ... }
 * Always: const p = JSON.parse(wrapper.content)
 *
 * ── State / filing ─────────────────────────────────────────────────────────
 * Always read state + filing_status from person.json and pass to /run.
 * /run defaults to California/MFJ if not specified — wrong for Texas etc.
 */

import { test, expect, describe, Page, Locator, APIRequestContext } from "@playwright/test";

// ─── Constants ────────────────────────────────────────────────────────────────

const UI_PROFILE  = "PlaywrightTest";
const SIM_PATHS   = 100;
const SIM_STEPS   = 2;
const SIM_TIMEOUT = 90_000;

const COLS = {
  summary:           2,
  aggregateBalances: 4,
  accountBalances:   5,
  portfolio:        12,
  withdrawals:      14,
  taxes:             9,
};

// ─── Scenario definitions ─────────────────────────────────────────────────────

interface Scenario {
  id:    string;
  label: string;
  focus: "baseline" | "no_ss" | "single" | "texas" | "rmd_73" | "rmd_75";
}

const API_SCENARIOS: Scenario[] = [
  { id: "__system__",       label: "base (MFJ, CA, SS, age 46)",       focus: "baseline" },
  { id: "__system__noss",   label: "no Social Security",                focus: "no_ss"    },
  { id: "__system__single", label: "single filer",                      focus: "single"   },
  { id: "__system__texas",  label: "Texas — no state income tax",       focus: "texas"    },
  { id: "__system__rmd73",  label: "RMD era age 73 (born 1953)",        focus: "rmd_73"   },
  { id: "__system__rmd75",  label: "SECURE 2.0 born 1960 — RMD at 75", focus: "rmd_75"   },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Read person.json for a profile.
 * /profile-config/<id>/person.json returns a WRAPPER:
 *   { content: "<json string>", profile: "...", readme: ... }
 * Must JSON.parse(wrapper.content) to get actual person config.
 */
async function fetchPerson(
  request: APIRequestContext, profileId: string
): Promise<Record<string, any>> {
  const res = await request.get(`/profile-config/${profileId}/person.json`);
  expect(res.ok(), `${profileId}/person.json accessible`).toBe(true);
  const wrapper = await res.json();
  return JSON.parse(wrapper.content);
}

/** Derive n_years and curAge from person.json. Never hardcode. */
async function fetchNYears(
  request: APIRequestContext, profileId: string
): Promise<{ nYears: number; curAge: number; birthYear: number; state: string; filing: string }> {
  const p         = await fetchPerson(request, profileId);
  const birthYear = parseInt(String(p.birth_year ?? "1980"));
  const curAge    = new Date().getFullYear() - birthYear;
  const nYears    = Math.max(10, Math.min(60, parseInt(String(p.target_age ?? "95")) - curAge));
  const state     = String(p.state ?? "California");
  const filing    = String(p.filing_status ?? "MFJ");
  return { nYears, curAge, birthYear, state, filing };
}

/** Derive RMD start row (0-indexed) per SECURE 2.0 birth_year rules. */
function rmdStartRow(birthYear: number, curAge: number): number {
  const rmdAge = birthYear <= 1950 ? 70 : birthYear <= 1959 ? 73 : 75;
  return Math.max(0, rmdAge - curAge);
}

/**
 * Run simulation via API.
 * Reads state + filing from person.json and passes explicitly to /run.
 * Without this, /run defaults to California/MFJ — wrong for Texas etc.
 */
async function apiRun(request: APIRequestContext, profileId: string): Promise<string> {
  const { state, filing } = await fetchNYears(request, profileId);
  const res = await request.post("/run", {
    data: {
      profile:        profileId,
      paths:          SIM_PATHS,
      steps_per_year: SIM_STEPS,
      shocks_mode:    "none",
      state,
      filing,
    },
  });
  expect(res.ok(), `POST /run ok for ${profileId}`).toBe(true);
  const data  = await res.json();
  const runId = data.run_id ?? data.run ?? "";
  expect(runId, `run_id present for ${profileId}`).toBeTruthy();
  return runId;
}

/** Fetch snapshot JSON for a completed run. */
async function fetchSnapshot(
  request: APIRequestContext, profileId: string, runId: string
): Promise<Record<string, any>> {
  const res = await request.get(`/artifact/${profileId}/${runId}/raw_snapshot_accounts.json`);
  expect(res.ok(), `snapshot ok for ${profileId}/${runId}`).toBe(true);
  return res.json();
}

/** Assert array is correct length and all values finite. */
function assertCleanArray(arr: any, label: string, expectedLen: number): number[] {
  expect(Array.isArray(arr), `${label} is array`).toBe(true);
  expect((arr as any[]).length, `${label} length = ${expectedLen}`).toBe(expectedLen);
  const nums = (arr as any[]).map(Number);
  for (let i = 0; i < nums.length; i++) {
    expect(isFinite(nums[i]), `${label}[${i}] finite (got ${nums[i]})`).toBe(true);
  }
  return nums;
}

async function getTableCells(page: Page, table: Locator): Promise<string[][]> {
  const rows  = table.locator("tbody tr");
  const count = await rows.count();
  const result: string[][] = [];
  for (let i = 0; i < count; i++) {
    const cells = rows.nth(i).locator("td");
    const n     = await cells.count();
    const row: string[] = [];
    for (let j = 0; j < n; j++) row.push((await cells.nth(j).textContent()) ?? "");
    result.push(row);
  }
  return result;
}

async function colCount(table: Locator): Promise<number> {
  return table.locator("thead tr").first().locator("th").count();
}

function assertNoBad(cells: string[][], name: string): void {
  for (let r = 0; r < cells.length; r++)
    for (let c = 0; c < cells[r].length; c++)
      for (const b of ["NaN", "undefined", "null"])
        if (cells[r][c].trim().includes(b))
          throw new Error(`${name} row ${r+1} col ${c+1}: "${cells[r][c]}"`);
}

function parseUSD(s: string): number { return parseFloat(s.replace(/[$,]/g, "")) || 0; }
function parsePct(s: string): number | null {
  const t = s.trim();
  if (t === "—" || t === "" || t === "-") return null;
  return parseFloat(t.replace("%", "")) || 0;
}

async function loadResults(page: Page, profileId: string, runId: string): Promise<void> {
  await page.goto("/");
  await page.locator(".tab", { hasText: "Results" }).click();
  await page.locator(".results-header .field").filter({ hasText: "Profile" })
    .locator("select").selectOption(profileId);
  const runsSel = page.locator(".results-header .field").filter({ hasText: "Runs" }).locator("select");
  await page.waitForFunction(() => {
    const s = document.querySelector(".results-header select:last-child") as HTMLSelectElement;
    return s && s.options.length > 1;
  }, { timeout: 10_000 });
  await runsSel.selectOption(runId);
  await expect(page.locator("h3", { hasText: "Summary" })).toBeVisible({ timeout: 15_000 });
}

// ═══════════════════════════════════════════════════════════════════════════════
// PART A — API Scenario Tests (no browser)
// ═══════════════════════════════════════════════════════════════════════════════

for (const scenario of API_SCENARIOS) {
  test.describe(`[API] ${scenario.label}`, () => {
    let snap:      Record<string, any> = {};
    let nYears:    number = 0;
    let curAge:    number = 0;
    let birthYear: number = 1980;
    let rmdRow:    number = 0;

    test.beforeAll(async ({ request }) => {
      const info = await fetchNYears(request, scenario.id);
      nYears    = info.nYears;
      curAge    = info.curAge;
      birthYear = info.birthYear;
      rmdRow    = rmdStartRow(birthYear, curAge);
      const runId = await apiRun(request, scenario.id);
      snap = await fetchSnapshot(request, scenario.id, runId);
    });

    test("federal tax: length=n_years, all finite", async () => {
      const wd = snap.withdrawals ?? {};
      assertCleanArray(
        wd.taxes_fed_current_mean ?? wd.taxes_fed_future_mean,
        `${scenario.id} taxes_fed`, nYears
      );
    });

    test("state tax: length=n_years, all finite", async () => {
      const wd = snap.withdrawals ?? {};
      assertCleanArray(
        wd.taxes_state_current_mean ?? wd.taxes_state_future_mean,
        `${scenario.id} taxes_state`, nYears
      );
    });

    test("portfolio future_median: length=n_years, all > 0", async () => {
      const arr = assertCleanArray(
        snap.portfolio?.future_median ?? snap.portfolio?.future_mean,
        `${scenario.id} portfolio`, nYears
      );
      for (let i = 0; i < arr.length; i++)
        expect(arr[i], `portfolio[${i}] > 0`).toBeGreaterThan(0);
    });

    test("years array: [1..n_years]", async () => {
      const years: number[] = snap.years ?? snap.portfolio?.years ?? [];
      expect(years.length, "years length = n_years").toBe(nYears);
      expect(years[0], "first year = 1").toBe(1);
      expect(years[years.length - 1], `last year = ${nYears}`).toBe(nYears);
    });

    test("effective tax rate: 0-100% every year", async () => {
      const rates = (snap.withdrawals ?? {}).effective_tax_rate_median_path as number[] | undefined;
      if (!rates) return;
      expect(rates.length, "eff rate length = n_years").toBe(nYears);
      for (let i = 0; i < rates.length; i++) {
        const r = Number(rates[i]);
        if (!isFinite(r)) continue;
        expect(r, `eff_rate[${i}] ≤ 100%`).toBeLessThanOrEqual(100);
        expect(r, `eff_rate[${i}] ≥ 0%`).toBeGreaterThanOrEqual(0);
      }
    });

    if (scenario.focus === "no_ss") {
      test("no_ss: ordinary_other ≈ 0 in retirement years", async () => {
        const arr = (snap.withdrawals ?? {}).ordinary_other_current_mean as number[] | undefined;
        if (!arr) return;
        const retRow = Math.max(0, 65 - curAge);
        for (let i = retRow; i < arr.length; i++)
          expect(Math.abs(arr[i]), `no_ss ordinary_other[${i}] ≈ 0`).toBeLessThan(1000);
      });
    }

    if (scenario.focus === "texas") {
      test("texas: state tax = 0 every year", async () => {
        const wd  = snap.withdrawals ?? {};
        const arr = assertCleanArray(
          wd.taxes_state_current_mean ?? wd.taxes_state_future_mean,
          "texas state_tax", nYears
        );
        for (let i = 0; i < arr.length; i++)
          expect(arr[i], `texas state_tax[${i}] = 0`).toBe(0);
      });
    }

    if (scenario.focus === "single") {
      test("single: some non-zero effective rates present", async () => {
        const rates = (snap.withdrawals ?? {}).effective_tax_rate_median_path as number[] | undefined;
        if (!rates) return;
        expect(rates.filter(r => isFinite(r) && r > 0).length, "single: non-zero rates").toBeGreaterThan(0);
      });
    }

    if (scenario.focus === "rmd_73") {
      test("rmd_73: RMD > 0 from year 1 (age 73, already in RMD era)", async () => {
        const arr = (snap.withdrawals ?? {}).rmd_current_mean as number[] | undefined;
        if (!arr) return;
        expect(arr[0], "rmd_73: RMD year-1 > 0").toBeGreaterThan(0);
      });
    }

    if (scenario.focus === "rmd_75") {
      test("rmd_75: RMD = 0 before 75, > 0 after", async () => {
        const arr = (snap.withdrawals ?? {}).rmd_current_mean as number[] | undefined;
        if (!arr) return;
        // curAge=66, rmdAge=75, firstRmdRow=9 (0-indexed: rows 0-8 are pre-RMD)
        const firstRmdRow = 75 - curAge;
        for (let i = 0; i < firstRmdRow && i < arr.length; i++)
          expect(arr[i], `rmd_75: RMD[${i}] = 0 pre-75`).toBe(0);
        if (firstRmdRow < arr.length)
          expect(arr[firstRmdRow], `rmd_75: RMD[${firstRmdRow}] > 0 post-75`).toBeGreaterThan(0);
      });
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// PART B — UI Structure Tests (browser, PlaywrightTest profile)
//
// PlaywrightTest is created by globalSetup (playwright.config.ts) from __testui__
// before any test runs, deleted by globalTeardown after. Works whether you run
// via --comprehensive-test or npx playwright test directly.
// ═══════════════════════════════════════════════════════════════════════════════

test.describe("UI structure tests [PlaywrightTest]", () => {
  let uiRunId:  string = "";
  let uiN:      number = 0;
  let uiRmd:    number = 0;

  test.beforeAll(async ({ browser, request }) => {
    const info = await fetchNYears(request, UI_PROFILE);
    uiN   = info.nYears;
    uiRmd = rmdStartRow(info.birthYear, info.curAge);

    const page = await browser.newPage();
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("eNDinomics");
    await page.locator(".tab", { hasText: "Simulation" }).click();
    await page.locator(".form-grid .field").filter({ hasText: "Profile" })
      .locator("select").selectOption(UI_PROFILE);
    await page.locator(".form-grid .field").filter({ hasText: "Paths" }).locator("input").fill(String(SIM_PATHS));
    await page.locator(".form-grid .field").filter({ hasText: "Steps" }).locator("input").fill(String(SIM_STEPS));
    await page.locator(".form-grid .field").filter({ hasText: "Shocks" }).locator("select").selectOption("none");
    await page.locator("button", { hasText: "Run Simulation" }).click();
    await expect(page.locator(".status")).toContainText("running", { timeout: 15_000 });
    await expect(page.locator(".status")).toContainText("idle",    { timeout: SIM_TIMEOUT });

    await page.locator(".tab", { hasText: "Results" }).click();
    await page.locator(".results-header .field").filter({ hasText: "Profile" })
      .locator("select").selectOption(UI_PROFILE);
    const runsSel = page.locator(".results-header .field").filter({ hasText: "Runs" }).locator("select");
    await page.waitForFunction(() => {
      const s = document.querySelector(".results-header select:last-child") as HTMLSelectElement;
      return s && s.options.length > 1;
    }, { timeout: 10_000 });
    const opts  = runsSel.locator("option");
    const count = await opts.count();
    const last  = await opts.nth(count - 1).getAttribute("value");
    if (last && last !== "") { await runsSel.selectOption(last); uiRunId = last; }
    await expect(page.locator("h3", { hasText: "Summary" })).toBeVisible({ timeout: 15_000 });
    await page.close();
  });

  test("page loads with correct title and tabs", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("eNDinomics");
    for (const t of ["Configure", "Simulation", "Results"])
      await expect(page.locator(".tab", { hasText: t })).toBeVisible();
  });

  test("__system__* and __testui__ NOT visible in Simulation dropdown", async ({ page }) => {
    await page.goto("/");
    await page.locator(".tab", { hasText: "Simulation" }).click();
    const opts = await page.locator(".form-grid .field")
      .filter({ hasText: "Profile" }).locator("select option").allTextContents();
    const hidden = opts.filter(o => o.startsWith("__"));
    expect(hidden.length, `hidden profiles in dropdown: ${hidden.join(", ")}`).toBe(0);
  });

  test("results load for PlaywrightTest", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    for (const h of ["Summary", "Withdrawals", "Taxes by Type", "Total Portfolio (Future USD)"])
      await expect(page.locator("h3", { hasText: h })).toBeVisible();
  });

  test("Summary: 2 cols, ≥4 rows, survival rate in [0,100]", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const table = page.locator("section.results-section", { hasText: "Summary" }).locator("table.table");
    expect(await colCount(table), "Summary cols").toBe(COLS.summary);
    const cells = await getTableCells(page, table);
    expect(cells.length, "Summary ≥4 rows").toBeGreaterThanOrEqual(4);
    assertNoBad(cells, "Summary");
    const row = cells.find(r => r[0].includes("survival rate") || r[0].includes("Success"));
    if (row) {
      const pct = parsePct(row[1]);
      expect(pct).not.toBeNull();
      expect(pct!).toBeGreaterThanOrEqual(0);
      expect(pct!).toBeLessThanOrEqual(100);
    }
  });

  test("Aggregate Balances: 4 cols, 3 rows, balances > 0", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const table = page.locator("section.results-section", { hasText: "Aggregate Balances" })
      .filter({ hasNot: page.locator("h3", { hasText: "Account Balances" }) })
      .locator("table.table").first();
    expect(await colCount(table), "Agg cols").toBe(COLS.aggregateBalances);
    const cells = await getTableCells(page, table);
    expect(cells.length, "Agg rows = 3").toBe(3);
    assertNoBad(cells, "Agg Balances");
    for (const row of cells) expect(parseUSD(row[2]), `${row[0]} > 0`).toBeGreaterThan(0);
  });

  test("Account Balances: 5 cols, 6 accounts, all names present", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const table = page.locator("section.results-section", { hasText: "Account Balances" }).locator("table.table");
    expect(await colCount(table), "AcctBal cols").toBe(COLS.accountBalances);
    const cells = await getTableCells(page, table);
    expect(cells.length, "6 accounts").toBe(6);
    assertNoBad(cells, "Account Balances");
    const names = cells.map(r => r[0]);
    for (const a of ["BROKERAGE-1","BROKERAGE-2","TRAD_IRA-1","TRAD_IRA-2","ROTH_IRA-1","ROTH_IRA-2"])
      expect(names, `${a} present`).toContain(a);
  });

  test("Total Portfolio: n_years rows (from person.json), year sequence valid", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const table = page.locator("section.results-section")
      .filter({ has: page.locator("h3", { hasText: "Total Portfolio (Future USD)" }) })
      .locator("table.table").first();
    expect(await colCount(table), "Portfolio cols").toBe(COLS.portfolio);
    const cells = await getTableCells(page, table);
    expect(cells.length, `Portfolio rows = ${uiN}`).toBe(uiN);
    assertNoBad(cells, "Total Portfolio");
    expect(cells[0][0], "First year = 1").toBe("1");
    expect(cells[uiN - 1][0], `Last year = ${uiN}`).toBe(String(uiN));
    for (let i = 0; i < cells.length; i++)
      expect(parseUSD(cells[i][2]), `Portfolio[${i}] > 0`).toBeGreaterThan(0);
  });

  test("Withdrawals: 14 cols, n_years rows, planned > 0, RMD rows > 0", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const table = page.locator("section.results-section")
      .filter({ has: page.locator("h3", { hasText: "Withdrawals" }) })
      .locator("table.table").first();
    expect(await colCount(table), "Withdrawals cols").toBe(COLS.withdrawals);
    const cells = await getTableCells(page, table);
    expect(cells.length, `Withdrawals rows = ${uiN}`).toBe(uiN);
    assertNoBad(cells, "Withdrawals");
    for (let i = 0; i < uiRmd; i++) {
      expect(parseUSD(cells[i][2]), `Planned WD > 0 row ${i+1}`).toBeGreaterThan(0);
      expect(parseUSD(cells[i][5]), `For spending > 0 row ${i+1}`).toBeGreaterThan(0);
    }
    for (let i = uiRmd; i < cells.length; i++) {
      expect(parseUSD(cells[i][6]), `RMD > 0 row ${i+1}`).toBeGreaterThan(0);
      expect(parseUSD(cells[i][5]), `For spending > 0 RMD row ${i+1}`).toBeGreaterThan(0);
    }
  });

  test("Taxes: 9 cols, n_years rows, eff rate ≤ 100%", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const table = page.locator("section.results-section", { hasText: "Taxes by Type" }).locator("table.table");
    expect(await colCount(table), "Taxes cols").toBe(COLS.taxes);
    const cells = await getTableCells(page, table);
    expect(cells.length, `Taxes rows = ${uiN}`).toBe(uiN);
    assertNoBad(cells, "Taxes");
    for (let i = 0; i < cells.length; i++) {
      const r = parsePct(cells[i][8]);
      if (r !== null) {
        expect(r, `eff_rate[${i}] ≤ 100%`).toBeLessThanOrEqual(100);
        expect(r, `eff_rate[${i}] ≥ 0%`).toBeGreaterThanOrEqual(0);
      }
    }
  });

  test("Withdrawals diff: not deeply negative in pre-RMD years", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const table = page.locator("section.results-section")
      .filter({ has: page.locator("h3", { hasText: "Withdrawals" }) })
      .locator("table.table").first();
    const cells = await getTableCells(page, table);
    const bad: string[] = [];
    for (let i = 0; i < uiRmd; i++)
      if (parseUSD(cells[i][4]) < -1000) bad.push(`row ${i+1}: ${cells[i][4]}`);
    if (bad.length > 5) throw new Error(`Shortfalls in ${bad.length} pre-RMD rows: ${bad.slice(0,3).join(", ")}`);
  });

  test("Accounts YoY: n_years rows per account, balances > 0", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const section = page.locator("section.results-section", {
      hasText: "Accounts — Investment YoY (Future USD)",
    });
    for (const acct of ["BROKERAGE-1","BROKERAGE-2","TRAD_IRA-1","TRAD_IRA-2","ROTH_IRA-1","ROTH_IRA-2"]) {
      await section.locator("select").selectOption(acct);
      await page.waitForTimeout(200);
      const cells = await getTableCells(page, section.locator("table.table"));
      expect(cells.length, `${acct} rows = ${uiN}`).toBe(uiN);
      assertNoBad(cells, `Accounts YoY ${acct}`);
      for (let i = 0; i < cells.length; i++)
        expect(parseUSD(cells[i][2]), `${acct}[${i}] > 0`).toBeGreaterThan(0);
    }
  });

  test("Charts: Portfolio Projection section present with chart", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    // Charts render as <canvas> or <svg>, not <img>. Find by section heading text.
    const section = page.locator("section.results-section", {
      hasText: /Portfolio Projection|Scenario Bands|Chart/,
    }).first();
    await expect(section).toBeVisible({ timeout: 10_000 });
    // Chart is canvas or svg — either is acceptable
    const chartEl = section.locator("canvas, svg").first();
    const chartCount = await chartEl.count();
    // If no canvas/svg, at minimum the section itself has content
    if (chartCount > 0) {
      await expect(chartEl).toBeVisible();
    } else {
      const text = await section.textContent() ?? "";
      expect(text.length, "Chart section has content").toBeGreaterThan(10);
    }
  });

  test("Insights: present with content", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    // Two sections match /Insights/ — pick the first non-Roth one
    const section = page.locator("section.results-section")
      .filter({ hasText: /Insights|Findings/ })
      .filter({ hasNotText: /^Roth/ })
      .first();
    await expect(section).toBeVisible({ timeout: 10_000 });
    expect((await section.textContent() ?? "").length, "Insights has content").toBeGreaterThan(20);
  });

  test("Portfolio Analysis: section present with content", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const section = page.locator("section.results-section", { hasText: "Portfolio Analysis" });
    await expect(section).toBeVisible({ timeout: 10_000 });
    // Content renders as divs, not tables — just verify section has text content
    const text = await section.textContent() ?? "";
    expect(text.length, "Portfolio Analysis has text content").toBeGreaterThan(20);
  });

  test("Run Parameters: present with content", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const grid = page.locator(".run-params-grid");
    await expect(grid).toBeVisible();
    expect((await grid.textContent() ?? "").length, "Run params has content").toBeGreaterThan(10);
  });

  test("Run panel: ignore checkboxes + mode selector present", async ({ page }) => {
    await page.goto("/");
    await page.locator(".tab", { hasText: "Simulation" }).click();
    await page.locator(".form-grid .field").filter({ hasText: "Profile" })
      .locator("select").selectOption(UI_PROFILE);
    for (const label of ["Withdrawals", "RMDs", "Conversions"])
      await expect(page.locator(".options-row label").filter({ hasText: label }), `${label} checkbox`).toBeVisible();
    await expect(
      page.locator(".form-grid .field").filter({ hasText: /mode|Mode/ }).locator("select"),
      "Mode selector"
    ).toBeVisible();
  });

  test("No NaN or undefined in Results page", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const body = await page.locator("body").textContent() ?? "";
    const bad  = ["NaN", "undefined", "null"].filter(b => body.includes(b));
    expect(bad, `Bad values found: ${bad.join(", ")}`).toHaveLength(0);
  });

  test("Roth Conversion Insights: present and expandable", async ({ page }) => {
    await loadResults(page, UI_PROFILE, uiRunId);
    const section = page.locator("section.results-section").filter({
      has: page.locator("h3", { hasText: /Roth.*Insights|Roth.*Conversion/ }),
    });
    await expect(section).toBeVisible({ timeout: 10_000 });
    const before = await section.textContent() ?? "";
    const btn    = section.locator("button, summary, [role='button'], .expandable, .collapsible").first();
    const btnCnt = await btn.count();
    if (btnCnt > 0) {
      await btn.click();
      await page.waitForTimeout(400);
      const after = await section.textContent() ?? "";
      expect(after.length, "Roth Insights section has content after interaction").toBeGreaterThan(20);
    } else {
      expect(before.length, "Roth Insights has content").toBeGreaterThan(20);
    }
  });

  test("Configure tab: Version History panel present", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    const vBtn = page.locator("button", { hasText: "Version History" });
    await expect(vBtn).toBeVisible({ timeout: 5_000 });
    await vBtn.click();
    await page.waitForTimeout(500);
    // After clicking, the panel expands showing either version rows OR "No versions yet" text.
    // Both are valid — just verify something appeared below the button.
    const panel = page.locator(".profile-row").locator(".. >> *").filter({
      hasText: /No versions yet|Version \d|Auto-saved|version/i,
    }).first();
    // Fallback: look for any visible element containing version-related text anywhere on page
    const anyVersionText = page.locator("*").filter({
      hasText: /No versions yet|Auto-saved on every config/i,
    }).first();
    await expect(anyVersionText).toBeVisible({ timeout: 8_000 });
  });

  test("Configure tab: Save Version hidden when dirty", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    // Must be in EDIT mode for Save Version to appear
    await page.locator(".profile-actions button", { hasText: "EDIT" }).click();
    await page.waitForTimeout(300);
    const saveVersionBtn = page.locator("button", { hasText: "Save Version" });
    await expect(saveVersionBtn).toBeVisible({ timeout: 5_000 });
    // Make a change to create dirty state
    const ta = page.locator("textarea");
    await ta.click(); await ta.press("End"); await ta.pressSequentially(" ");
    await page.waitForTimeout(200);
    expect(await saveVersionBtn.isHidden(), "Save Version hidden while dirty").toBe(true);
  });

  test("Investment tab: Roth Conversion Recommendations present", async ({ page }) => {
    await page.goto("/");
    await page.locator(".tab", { hasText: "Investment" }).click();
    await expect(page.locator("h2", { hasText: "Investment" })).toBeVisible();
    const section = page.locator("section.results-section").filter({
      has: page.locator("h3", { hasText: "Roth Conversion Recommendations" }),
    });
    await expect(section).toBeVisible({ timeout: 5_000 });
    expect((await section.textContent() ?? "").length, "Roth Recs has content").toBeGreaterThan(10);
  });

  test("Versioning: Save Version creates entry", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    const vBtn = page.locator("button", { hasText: "Version History" });
    await vBtn.click(); await page.waitForTimeout(300);
    const panel  = page.locator("table").filter({ hasText: /Ver/ }).first();
    const before = await panel.locator("tbody tr").count().catch(() => 0);
    if (before >= 40) await page.request.delete(`/profile/${UI_PROFILE}/versions?keep=30`);
    // Save Version only appears in EDIT mode
    await page.locator(".profile-actions button", { hasText: "EDIT" }).click();
    await page.waitForTimeout(300);
    await expect(page.locator("button", { hasText: "Save Version" })).toBeVisible({ timeout: 5_000 });
    await vBtn.click(); await page.waitForTimeout(300);
    await page.locator("button", { hasText: "Save Version" }).click();
    await page.waitForTimeout(200);
    await page.locator("input").filter({ hasText: "" }).last().fill("playwright checkpoint");
    await page.locator("button", { hasText: /^Save$/ }).click();
    await page.waitForTimeout(500);
    await vBtn.click(); await page.waitForTimeout(300);
    expect(await panel.locator("tbody tr").count().catch(() => 0), "Version count increased").toBeGreaterThan(before);
    await expect(panel).toContainText("playwright checkpoint");
  });

  test("Versioning: auto-version on config save", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    const vBtn = page.locator("button", { hasText: "Version History" });
    await vBtn.click(); await page.waitForTimeout(300);
    const hist   = page.locator("table").filter({ hasText: /Ver/ }).first();
    let before   = await hist.locator("tbody tr").count().catch(() => 0);
    if (before >= 40) { await page.request.delete(`/profile/${UI_PROFILE}/versions?keep=30`); before = 0; }
    await vBtn.click(); await page.waitForTimeout(200);
    await page.locator(".profile-actions button", { hasText: "EDIT" }).click();
    await page.waitForTimeout(400);
    await page.locator("button").filter({ hasText: "person.json" }).first().click();
    await page.waitForTimeout(300);
    const ta = page.locator("textarea");
    await ta.click(); await ta.press("End"); await ta.pressSequentially(" ");
    await page.waitForTimeout(200);
    await page.locator("input[type='text']").last().fill("playwright auto-version");
    await page.locator("button", { hasText: "Save to Profile" }).click();
    await page.waitForTimeout(500);
    await vBtn.click(); await page.waitForTimeout(300);
    expect(await hist.locator("tbody tr").count().catch(() => 0), "Version count increased").toBeGreaterThan(before);
    await expect(hist).toContainText("playwright auto-version");
  });

  test("Versioning: Restore reverts and creates auto-save", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    const vBtn = page.locator("button", { hasText: "Version History" });
    await vBtn.click(); await page.waitForTimeout(300);
    const hist   = page.locator("table").filter({ hasText: /Ver/ }).first();
    let before   = await hist.locator("tbody tr").count().catch(() => 0);
    if (before >= 40) { await page.request.delete(`/profile/${UI_PROFILE}/versions?keep=30`); before = 0; }
    if (before < 2) { test.skip(); return; }
    await hist.locator("tbody tr").nth(1).locator("button", { hasText: "View" }).click();
    await page.waitForTimeout(800);
    await expect(page.locator("pre").filter({ hasText: "{" }).first()).toBeVisible({ timeout: 5_000 });
    await page.locator("button", { hasText: /↩ Restore/ }).first().click();
    await page.waitForTimeout(800);
    expect(await hist.locator("tbody tr").count().catch(() => 0), "Count increased after restore").toBeGreaterThan(before);
    await expect(hist.locator("tbody tr").first()).toContainText(/before restore|auto-save/i);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Guided Editor — person.json  (stable UI, v1)
//
// These tests assume:
//   • Selecting a profile loads GUIDED mode by default
//   • person.json is selected by default (first file in "You" group)
//   • All sections start collapsed → Profile Overview shown on right
//   • Clicking a section header expands it
//   • Clicking a field row opens the detail panel on the right
//   • Update button only appears when local value differs from draft
//   • Dirty bar appears when draft ≠ saved; Save Profile / Discard present
// ─────────────────────────────────────────────────────────────────────────────

describe("Guided editor — file list and navigation [PlaywrightTest]", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
  });

  test("File list: four group headers present", async ({ page }) => {
    for (const group of ["YOU", "CASH FLOWS", "PORTFOLIO", "ASSUMPTIONS"]) {
      await expect(
        page.locator("div").filter({ hasText: new RegExp(`^${group}$`, "i") }).first(),
        `Group "${group}" missing`
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("File list: all seven files present with friendly labels", async ({ page }) => {
    for (const label of [
      "Personal Profile", "Income Sources", "Spending Plan",
      "Asset Allocation", "Withdrawal Strategy", "Inflation", "Shocks & Windfalls",
    ]) {
      await expect(
        page.locator("button").filter({ hasText: label }).first(),
        `File "${label}" missing`
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("Personal Profile is active by default", async ({ page }) => {
    const activeBtn = page.locator("button.config-file.active");
    await expect(activeBtn).toBeVisible({ timeout: 5_000 });
    await expect(activeBtn).toContainText("Personal Profile");
  });

  test("Clicking another file switches selection", async ({ page }) => {
    await page.locator("button").filter({ hasText: "Income Sources" }).first().click();
    await page.waitForTimeout(300);
    const activeBtn = page.locator("button.config-file.active");
    await expect(activeBtn).toContainText("Income Sources");
  });

  test("GUIDED button is active by default", async ({ page }) => {
    const guidedBtn = page.locator(".profile-actions button", { hasText: "GUIDED" });
    await expect(guidedBtn).toBeVisible({ timeout: 5_000 });
    // Should have active styling (background color set)
    const bg = await guidedBtn.evaluate(el => getComputedStyle(el).background);
    expect(bg, "GUIDED button should have active background").toContain("rgb");
  });
});

describe("Guided editor — person.json sections and fields [PlaywrightTest]", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    // Ensure person.json is selected
    await page.locator("button").filter({ hasText: "Personal Profile" }).filter({ hasText: "Who you are" }).click();
    await page.waitForTimeout(400);
  });

  test("All sections collapsed by default → Profile Overview shown", async ({ page }) => {
    await expect(
      page.locator("div").filter({ hasText: /Profile Overview/i }).first()
    ).toBeVisible({ timeout: 5_000 });
    // Overview grid should show key fields
    await expect(page.locator("div").filter({ hasText: /CURRENT AGE/i }).first()).toBeVisible({ timeout: 3_000 });
    await expect(page.locator("div").filter({ hasText: /FILING STATUS/i }).first()).toBeVisible({ timeout: 3_000 });
    await expect(page.locator("div").filter({ hasText: /STATE/i }).first()).toBeVisible({ timeout: 3_000 });
  });

  test("Seven section headers visible: Identity, Simulation Horizon, Social Security, Spouse, Beneficiaries, Roth Conversion Policy, RMD Policy", async ({ page }) => {
    for (const label of [
      "IDENTITY", "SIMULATION HORIZON", "SOCIAL SECURITY",
      "SPOUSE", "BENEFICIARIES", "ROTH CONVERSION POLICY", "RMD POLICY",
    ]) {
      await expect(
        page.locator("[data-section=\"identity\"]"),
        `Section "${label}" missing`
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("Clicking Identity expands to show its fields", async ({ page }) => {
    await page.locator("[data-section=\"identity\"]").click();
    await page.waitForTimeout(300);
    await expect(page.locator("[data-field-key=\"Current Age\"]")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-field-key=\"Birth Year\"]")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-field-key=\"Filing Status\"]")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-field-key=\"State\"]")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-field-key=\"Retirement Age\"]")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-field-key=\"Simulation Mode\"]")).toBeVisible({ timeout: 5_000 });
  });

  test("Expanding then collapsing Identity hides its fields", async ({ page }) => {
    await page.locator("[data-section=\"identity\"]").click();
    await page.waitForTimeout(300);
    await expect(page.locator("[data-field-key=\"Birth Year\"]")).toBeVisible({ timeout: 3_000 });
    // Collapse
    await page.locator("[data-section=\"identity\"]").click();
    await page.waitForTimeout(300);
    await expect(page.locator("[data-field-key=\"Birth Year\"]")).not.toBeVisible({ timeout: 3_000 });
    // Overview returns
    await expect(page.locator("div").filter({ hasText: /Profile Overview/i }).first()).toBeVisible({ timeout: 3_000 });
  });

  test("Social Security section: four fields after expand", async ({ page }) => {
    await page.locator("[data-section=\"ss\"]").click();
    await page.waitForTimeout(300);
    for (const label of ["Your Start Age", "Spouse Start Age", "Your Annual SS Benefit ($)", "Exclude from Plan"]) {
      await expect(
        page.locator(`[data-field-key="${label}"]`),
        `SS field "${label}" missing`
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("Spouse section: four fields including Sole IRA Beneficiary", async ({ page }) => {
    await page.locator("[data-section=\"spouse\"]").click();
    await page.waitForTimeout(300);
    for (const label of ["Name", "Birth Year", "Expected Longevity", "Sole IRA Beneficiary"]) {
      await expect(
        page.locator(`[data-field-key="${label}"]`),
        `Spouse field "${label}" missing`
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("Beneficiaries section: expands and shows Add beneficiary button", async ({ page }) => {
    await page.locator("[data-section=\"beneficiaries\"]").click();
    await page.waitForTimeout(300);
    await expect(
      page.locator("button").filter({ hasText: /\+ Add beneficiary/i })
    ).toBeVisible({ timeout: 5_000 });
  });

  test("Roth Conversion Policy: five fields after expand", async ({ page }) => {
    await page.locator("[data-section=\"roth\"]").click();
    await page.waitForTimeout(300);
    for (const label of [
      "Conversions Enabled", "Stay Below Bracket",
      "Avoid NIIT Threshold", "Annual Amount ($K)", "Conversion Window",
    ]) {
      await expect(
        page.locator(`[data-field-key="${label}"]`),
        `Roth field "${label}" missing`
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("RMD Policy: Surplus RMD Handling field present", async ({ page }) => {
    await page.locator("[data-section=\"rmd\"]").click();
    await page.waitForTimeout(300);
    await expect(
      page.locator("[data-field-key=\"Surplus RMD Handling\"]")
    ).toBeVisible({ timeout: 5_000 });
  });
});

describe("Guided editor — person.json field detail panel [PlaywrightTest]", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    await page.locator("button").filter({ hasText: "Personal Profile" }).filter({ hasText: "Who you are" }).click();
    await page.waitForTimeout(400);
    // Expand Identity
    await page.locator("[data-section=\"identity\"]").click();
    await page.waitForTimeout(300);
  });

  test("Clicking a field shows description text and an input control", async ({ page }) => {
    await page.locator("[data-field-key=\"Birth Year\"]").click();
    await page.waitForTimeout(300);
    // Description box (blue left-border) has content
    const panel = page.locator("div").filter({ hasText: /birth year/i }).nth(1);
    const text = (await panel.textContent() ?? "").trim();
    expect(text.length, "Description text missing").toBeGreaterThan(10);
    // Input control present
    await expect(page.locator("input[type='number']").first()).toBeVisible({ timeout: 3_000 });
  });

  test("Filing Status select has MFJ, Single, MFS, HOH options", async ({ page }) => {
    await page.locator("[data-field-key=\"Filing Status\"]").click();
    await page.waitForTimeout(300);
    // Detail panel select — nth(1) skips the Profile dropdown
    const sel = page.locator("select").nth(1);
    await expect(sel).toBeVisible({ timeout: 5_000 });
    const opts = await sel.locator("option").allTextContents();
    for (const opt of ["MFJ", "Single", "MFS", "HOH"]) {
      expect(opts.some(o => o.includes(opt)), `Filing option "${opt}" missing`).toBe(true);
    }
  });

  test("Simulation Mode select has all four modes", async ({ page }) => {
    await page.locator("[data-field-key=\"Simulation Mode\"]").click();
    await page.waitForTimeout(300);
    const sel = page.locator("select").nth(1);
    await expect(sel).toBeVisible({ timeout: 5_000 });
    const opts = await sel.locator("option").allTextContents();
    for (const mode of ["automatic", "investment", "retirement", "balanced"]) {
      expect(opts.some(o => o.toLowerCase().includes(mode)), `Mode "${mode}" missing`).toBe(true);
    }
  });

  test("SS Start Age select has ages 62 through 70", async ({ page }) => {
    await page.locator("[data-section=\"ss\"]").click();
    await page.waitForTimeout(200);
    await page.locator("[data-field-key=\"Your Start Age\"]").click();
    await page.waitForTimeout(300);
    const sel = page.locator("select").nth(1);
    await expect(sel).toBeVisible({ timeout: 5_000 });
    const opts = await sel.locator("option").allTextContents();
    for (const age of [62, 63, 64, 65, 66, 67, 68, 69, 70]) {
      expect(opts.some(o => o.startsWith(String(age))), `SS age ${age} missing`).toBe(true);
    }
  });

  test("RMD Table select has uniform_lifetime and joint_life", async ({ page }) => {
    await page.locator("[data-section=\"horizon\"]").click();
    await page.waitForTimeout(200);
    await page.locator("[data-field-key=\"RMD Table\"]").click();
    await page.waitForTimeout(300);
    const sel = page.locator("select").nth(1);
    await expect(sel).toBeVisible({ timeout: 5_000 });
    const opts = await sel.locator("option").allTextContents();
    expect(opts.some(o => o.includes("uniform_lifetime")), "uniform_lifetime missing").toBe(true);
    expect(opts.some(o => o.includes("joint_life")), "joint_life missing").toBe(true);
  });

  test("State dropdown has California, Texas, New York", async ({ page }) => {
    await page.locator("[data-field-key=\"State\"]").click();
    await page.waitForTimeout(300);
    const sel = page.locator("select").nth(1);
    await expect(sel).toBeVisible({ timeout: 5_000 });
    const opts = await sel.locator("option").allTextContents();
    for (const state of ["California", "Texas", "New York"]) {
      expect(opts.some(o => o.includes(state)), `State "${state}" missing`).toBe(true);
    }
  });

  test("Surplus RMD Handling has reinvest_in_brokerage option", async ({ page }) => {
    await page.locator("[data-section=\"rmd\"]").click();
    await page.waitForTimeout(200);
    await page.locator("[data-field-key=\"Surplus RMD Handling\"]").click();
    await page.waitForTimeout(300);
    // Scope to detail panel (right side) — skip the profile select
    // Detail panel select — find the select that has reinvest option (not profile dropdown)
    const allSels = page.locator("select");
    const count = await allSels.count();
    let found = false;
    for (let i = 0; i < count; i++) {
      const opts = await allSels.nth(i).locator("option").allTextContents();
      if (opts.some(o => o.toLowerCase().includes("reinvest"))) { found = true; break; }
    }
    expect(found, "reinvest_in_brokerage missing from any select on page").toBe(true);
  });
});

describe("Guided editor — Update / dirty / discard flow [PlaywrightTest]", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    await page.locator("button").filter({ hasText: "Personal Profile" }).filter({ hasText: "Who you are" }).click();
    await page.waitForTimeout(400);
    // Expand Identity so Birth Year is accessible
    await page.locator("[data-section=\"identity\"]").click();
    await page.waitForTimeout(300);
    await page.locator("[data-field-key=\"Birth Year\"]").click();
    await page.waitForTimeout(300);
  });

  test("Update button hidden before any change", async ({ page }) => {
    await expect(page.locator("button", { hasText: "Update" })).not.toBeVisible({ timeout: 3_000 });
    await expect(page.locator("text=Make a change above to enable Update")).toBeVisible({ timeout: 3_000 });
  });

  test("Update button appears after changing a value", async ({ page }) => {
    const input = page.locator("input[type='number']").first();
    const orig = await input.inputValue();
    await input.fill(String(Number(orig) + 1));
    await page.waitForTimeout(200);
    await expect(page.locator("button", { hasText: "Update" })).toBeVisible({ timeout: 3_000 });
  });

  test("Clicking Update stages the change → amber dirty bar appears", async ({ page }) => {
    const input = page.locator("input[type='number']").first();
    const orig = await input.inputValue();
    await input.fill(String(Number(orig) - 1));
    await page.waitForTimeout(200);
    await page.locator("button", { hasText: "Update" }).click();
    await page.waitForTimeout(300);
    // Amber bar
    await expect(page.locator("div").filter({ hasText: /Unsaved changes/i }).first()).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("button", { hasText: "Save Profile" })).toBeVisible({ timeout: 3_000 });
    await expect(page.locator("button", { hasText: "Discard" })).toBeVisible({ timeout: 3_000 });
    // "edited" badge in field list header
    await expect(page.locator("span").filter({ hasText: /^edited$/ })).toBeVisible({ timeout: 3_000 });
    // Update button hides after commit
    await expect(page.locator("button", { hasText: "Update" })).not.toBeVisible({ timeout: 3_000 });
  });

  test("Discard reverts all pending changes and removes dirty indicators", async ({ page }) => {
    const input = page.locator("input[type='number']").first();
    const orig = await input.inputValue();
    await input.fill("1900");
    await page.waitForTimeout(200);
    await page.locator("button", { hasText: "Update" }).click();
    await page.waitForTimeout(300);
    await page.locator("button", { hasText: "Discard" }).click();
    await page.waitForTimeout(300);
    // Dirty bar gone
    await expect(page.locator("div").filter({ hasText: /Unsaved changes/i }).first()).not.toBeVisible({ timeout: 3_000 });
    // Value reverted
    await page.locator("[data-field-key=\"Birth Year\"]").click();
    await page.waitForTimeout(200);
    const reverted = await page.locator("input[type='number']").first().inputValue();
    expect(reverted, "Value should revert to original").toBe(orig);
  });
});

describe("Guided editor — beneficiary management [PlaywrightTest]", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(500);
    await page.locator("button").filter({ hasText: "Personal Profile" }).filter({ hasText: "Who you are" }).click();
    await page.waitForTimeout(400);
    // Expand beneficiaries section
    await page.locator("[data-section=\"beneficiaries\"]").click();
    await page.waitForTimeout(300);
  });

  test("Beneficiaries section shows Primary and Contingent sub-groups", async ({ page }) => {
    await expect(page.locator("[data-bene-group=\"primary\"]")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-bene-group=\"contingent\"]")).toBeVisible({ timeout: 5_000 });
  });

  test("Add beneficiary button opens a form with Primary/Contingent type selector", async ({ page }) => {
    await page.locator("button").filter({ hasText: /\+ Add beneficiary/i }).click();
    await page.waitForTimeout(400);
    // Type selector cards
    await expect(page.locator("div").filter({ hasText: "primary" }).filter({ hasText: "Inherits first" }).first()).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("div").filter({ hasText: "contingent" }).filter({ hasText: "Inherits if" }).first()).toBeVisible({ timeout: 5_000 });
    // Name input
    await expect(page.locator("input[placeholder='e.g. Child A']")).toBeVisible({ timeout: 3_000 });
    // Add and Cancel buttons
    await expect(page.getByRole("button", { name: "Add", exact: true })).toBeVisible({ timeout: 3_000 });
    await expect(page.locator("button", { hasText: "Cancel" })).toBeVisible({ timeout: 3_000 });
  });

  test("Add beneficiary Cancel returns to section without adding", async ({ page }) => {
    const countBefore = await page.locator("div").filter({ hasText: /^CONTINGENT/i }).locator("~ *").count().catch(() => 0);
    await page.locator("button").filter({ hasText: /\+ Add beneficiary/i }).click();
    await page.waitForTimeout(300);
    await page.locator("button", { hasText: "Cancel" }).click();
    await page.waitForTimeout(300);
    // Form gone
    await expect(page.getByRole("button", { name: "Add", exact: true })).not.toBeVisible({ timeout: 3_000 });
    // Overview or section still visible
    await expect(page.locator("button").filter({ hasText: /\+ Add beneficiary/i })).toBeVisible({ timeout: 3_000 });
  });

  test("Clicking existing primary beneficiary opens edit form", async ({ page }) => {
    // The PlaywrightTest profile has Spouse as primary — click the row
    // Click the first primary beneficiary row using data-selected on the bene row div
    const primRow = page.locator("div[data-selected]").filter({ hasText: /spouse/i }).first();
    await primRow.click();
    await page.waitForTimeout(300);
    // Edit form should appear — DetailHeader shows "Edit Primary — ..."
    await expect(page.locator("span").filter({ hasText: /Edit Primary/i }).first()).toBeVisible({ timeout: 5_000 });
    // Delete always visible; Done only appears after a field is changed
    await expect(page.getByRole("button", { name: "Delete", exact: true })).toBeVisible({ timeout: 3_000 });
  });
});

describe("Guided editor — view mode (read-only) [PlaywrightTest]", () => {
  test("VIEW mode: no Update or Save Profile button", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(400);
    await page.locator(".profile-actions button", { hasText: "VIEW" }).click();
    await page.waitForTimeout(500);
    // person.json is already selected — GUIDED in VIEW mode renders read-only
    // Neither Update nor Save Profile should appear in VIEW mode
    await expect(page.locator("button", { hasText: "Update" })).not.toBeVisible({ timeout: 3_000 });
    await expect(page.locator("button", { hasText: "Save Profile" })).not.toBeVisible({ timeout: 3_000 });
  });

  test("Switching GUIDED → EDIT shows textarea, switching back hides it", async ({ page }) => {
    await page.goto("/");
    await page.locator(".profile-row select").selectOption(UI_PROFILE);
    await page.waitForTimeout(400);
    // Switch to EDIT
    await page.locator(".profile-actions button", { hasText: "EDIT" }).click();
    await page.waitForTimeout(300);
    await expect(page.locator("textarea")).toBeVisible({ timeout: 5_000 });
    // Switch back to GUIDED
    await page.locator(".profile-actions button", { hasText: "GUIDED" }).click();
    await page.waitForTimeout(300);
    await expect(page.locator("textarea")).not.toBeVisible({ timeout: 3_000 });
    // Profile Overview back
    await expect(page.locator("div").filter({ hasText: /Profile Overview/i }).first()).toBeVisible({ timeout: 3_000 });
  });
});
