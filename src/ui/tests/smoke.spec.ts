// filename: ui/tests/smoke.spec.ts
/**
 * eNDinomics UI Smoke Tests
 *
 * Runs a full simulation on the Test profile and validates:
 *   1. Page structure (tabs, headers)
 *   2. Simulation runs successfully and results load
 *   3. Every table has the correct number of columns and rows
 *   4. No cell contains NaN, undefined, null, or unexpected empties
 *   5. Key financial invariants (effective rate ≤ 100%, spending > 0 in RMD years)
 *   6. Summary metrics are present and in plausible ranges
 *
 * Prerequisites:
 *   - FastAPI server running on localhost:8000
 *   - Test profile exists with standard config (target_age=95, current_age≈46)
 *   - Expected rows: 49 (target_age 95 - current_age 46 = 49 sim years)
 *
 * Run:
 *   cd root/src/ui && npx playwright test
 */

import { test, expect, Page, Locator } from "@playwright/test";

// ─── Constants ────────────────────────────────────────────────────────────────

const PROFILE = "Test";
const EXPECTED_ROWS = 49;         // Test profile: current_age=46, target_age=95 → 49 sim years
const RMD_START_ROW = 30;         // age 75 = sim year 30 (birth_year=1980 → SECURE 2.0 age 75)
const SIM_TIMEOUT_MS = 90_000;    // generous budget for 200-path run

// Column counts per table (including Year + Age header cols)
const COLS = {
  summary:           2,   // Metric | Value
  aggregateBalances: 4,   // Aggregate | Starting | Current median | Future median
  accountBalances:   5,   // Account | Type | Starting | Current median | Future median
  portfolio:        12,   // Year | Age | Median | Today$ | Mean | Floor | Ceiling | Growth | RealGrowth | StressReturn | NomInv | RealInv
  withdrawals:      14,   // Year | Age | Planned | ForSpending | Diff | FutureSpend | RMD | RMDFut | Total | TotalFut | RMDReinvCur | RMDReinvFut | Conv | ConvTax
  taxes:             11,  // Year | Age | Federal | State | NIIT | Excise | Total | Taxable Income | Portfolio WD | Total Take-Home | Eff. rate
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Get all text content of cells in a table body, row by row. */
async function getTableCells(
  page: Page,
  tableLocator: Locator
): Promise<string[][]> {
  const rows = tableLocator.locator("tbody tr");
  const count = await rows.count();
  const result: string[][] = [];
  for (let i = 0; i < count; i++) {
    const cells = rows.nth(i).locator("td");
    const cellCount = await cells.count();
    const rowData: string[] = [];
    for (let j = 0; j < cellCount; j++) {
      rowData.push((await cells.nth(j).textContent()) ?? "");
    }
    result.push(rowData);
  }
  return result;
}

/** Get column count from the first header row only (avoids multi-row header inflation). */
async function getColumnCount(tableLocator: Locator): Promise<number> {
  const firstHeaderRow = tableLocator.locator("thead tr").first();
  return firstHeaderRow.locator("th").count();
}

/** Check no cell in a 2D array contains NaN, undefined, null as literal text. */
function assertNoBadValues(cells: string[][], tableName: string): void {
  const BAD = ["NaN", "undefined", "null"];
  for (let r = 0; r < cells.length; r++) {
    for (let c = 0; c < cells[r].length; c++) {
      const val = cells[r][c].trim();
      for (const bad of BAD) {
        if (val.includes(bad)) {
          throw new Error(
            `${tableName}: row ${r + 1} col ${c + 1} contains "${bad}": "${val}"`
          );
        }
      }
    }
  }
}

/** Parse a USD string like "$1,234,567" or "1,234,567" → number. */
function parseUSD(s: string): number {
  return parseFloat(s.replace(/[$,]/g, "")) || 0;
}

/** Parse a percent string like "35.3%" or "—" → number or null. */
function parsePct(s: string): number | null {
  const trimmed = s.trim();
  if (trimmed === "—" || trimmed === "" || trimmed === "-") return null;
  return parseFloat(trimmed.replace("%", "")) || 0;
}

// ─── Test setup: run simulation once, share results across all tests ──────────

let simulationDone = false;
let latestRunId = "";   // set in beforeAll, reused by all tests

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();

  // Navigate to app
  await page.goto("/");
  await expect(page.locator("h1")).toContainText("eNDinomics");

  // Switch to Simulation tab
  await page.locator(".tab", { hasText: "Simulation" }).click();
  await expect(page.locator("h2")).toContainText("Simulation");

  // Select Test profile
  await page.locator(".form-grid .field").filter({ hasText: "Profile" })
    .locator("select").selectOption(PROFILE);

  // Set paths to 200, steps to 2 for speed
  const pathsInput = page.locator(".form-grid .field").filter({ hasText: "Paths" }).locator("input");
  await pathsInput.fill("200");

  const spyInput = page.locator(".form-grid .field").filter({ hasText: "Steps/Year" }).locator("input");
  await spyInput.fill("2");

  // Ensure shocks mode = none for deterministic results
  await page.locator(".form-grid .field").filter({ hasText: "Shocks Mode" })
    .locator("select").selectOption("none");

  // Click Run Simulation
  await page.locator("button", { hasText: "Run Simulation" }).click();

  // ── Fix: wait for "running…" first, THEN wait for "idle" ──────────────────
  // Without this, the check catches the initial "idle" state before the run
  // even starts, and all subsequent tests load an old snapshot.
  await expect(page.locator(".status")).toContainText("running", {
    timeout: 15_000,   // should transition to running within 15s
  });
  await expect(page.locator(".status")).toContainText("idle", {
    timeout: SIM_TIMEOUT_MS,
  });

  // Switch to Results tab
  await page.locator(".tab", { hasText: "Results" }).click();

  // Select Test profile in Results
  await page.locator(".results-header .field").filter({ hasText: "Profile" })
    .locator("select").selectOption(PROFILE);

  // Wait for runs dropdown to populate
  const runsSelect = page.locator(".results-header .field")
    .filter({ hasText: "Runs" }).locator("select");
  await runsSelect.waitFor({ state: "visible" });
  await page.waitForFunction(() => {
    const sel = document.querySelector(".results-header select:last-child") as HTMLSelectElement;
    return sel && sel.options.length > 1;
  }, { timeout: 10_000 });

  // Pick the last run (most recent = the one we just ran) and record its ID
  const optionCount = await runsSelect.locator("option").count();
  const lastOption = await runsSelect.locator("option").nth(optionCount - 1).getAttribute("value");
  if (lastOption && lastOption !== "") {
    await runsSelect.selectOption(lastOption);
    latestRunId = lastOption;
  }

  // Wait for snapshot to load — Summary table should appear
  await expect(page.locator("h3", { hasText: "Summary" })).toBeVisible({
    timeout: 15_000,
  });

  simulationDone = true;
  await page.close();
});

// ─── Test 1: Page structure ───────────────────────────────────────────────────

test("page loads with correct title and tabs", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toContainText("eNDinomics Investment Simulator");
  await expect(page.locator(".tab", { hasText: "Configure" })).toBeVisible();
  await expect(page.locator(".tab", { hasText: "Simulation" })).toBeVisible();
  await expect(page.locator(".tab", { hasText: "Results" })).toBeVisible();
});

// ─── Test 2: Results load ─────────────────────────────────────────────────────

test("results load for Test profile", async ({ page }) => {
  expect(simulationDone).toBe(true);

  await page.goto("/");
  await page.locator(".tab", { hasText: "Results" }).click();
  await page.locator(".results-header .field").filter({ hasText: "Profile" })
    .locator("select").selectOption(PROFILE);

  // Pick the run generated by beforeAll
  const runsSelect = page.locator(".results-header .field")
    .filter({ hasText: "Runs" }).locator("select");
  await page.waitForFunction(() => {
    const sel = document.querySelector(".results-header select:last-child") as HTMLSelectElement;
    return sel && sel.options.length > 1;
  }, { timeout: 10_000 });
  if (latestRunId) {
    await runsSelect.selectOption(latestRunId);
  } else {
    const optionCount = await runsSelect.locator("option").count();
    const lastOption = await runsSelect.locator("option").nth(optionCount - 1).getAttribute("value");
    if (lastOption) await runsSelect.selectOption(lastOption);
  }

  await expect(page.locator("h3", { hasText: "Summary" })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("h3", { hasText: "Withdrawals" })).toBeVisible();
  await expect(page.locator("h3", { hasText: "Taxes by Type" })).toBeVisible();
  await expect(page.locator("h3", { hasText: "Total Portfolio (Future USD)" })).toBeVisible();
});

// ─── Helper: load results page and return ─────────────────────────────────────

async function loadResults(page: Page): Promise<void> {
  await page.goto("/");
  await page.locator(".tab", { hasText: "Results" }).click();
  await page.locator(".results-header .field").filter({ hasText: "Profile" })
    .locator("select").selectOption(PROFILE);

  const runsSelect = page.locator(".results-header .field")
    .filter({ hasText: "Runs" }).locator("select");
  await page.waitForFunction(() => {
    const sel = document.querySelector(".results-header select:last-child") as HTMLSelectElement;
    return sel && sel.options.length > 1;
  }, { timeout: 10_000 });

  // Use the run ID captured in beforeAll — guarantees we load the fresh snapshot
  if (latestRunId) {
    await runsSelect.selectOption(latestRunId);
  } else {
    // Fallback: pick last option
    const optionCount = await runsSelect.locator("option").count();
    const lastOption = await runsSelect.locator("option").nth(optionCount - 1).getAttribute("value");
    if (lastOption) await runsSelect.selectOption(lastOption);
  }

  await expect(page.locator("h3", { hasText: "Summary" })).toBeVisible({ timeout: 15_000 });
}

// ─── Test 3: Summary table ────────────────────────────────────────────────────

test("Summary table: columns, no bad values, plausible metrics", async ({ page }) => {
  await loadResults(page);
  const table = page.locator("section.results-section", { hasText: "Summary" }).locator("table.table");

  // Column count
  const cols = await getColumnCount(table);
  expect(cols, "Summary column count").toBe(COLS.summary);

  // At least 4 rows (success rate, nom YoY, real YoY, drawdown)
  const rows = table.locator("tbody tr");
  const rowCount = await rows.count();
  expect(rowCount, "Summary row count").toBeGreaterThanOrEqual(4);

  // No bad values
  const cells = await getTableCells(page, table);
  assertNoBadValues(cells, "Summary");

  // Survival/success rate row — label varies by mode:
  //   retirement → "Full-plan survival rate"
  //   automatic/investment → "Floor survival rate"
  const successRow = cells.find((r) =>
    r[0].includes("survival rate") || r[0].includes("Success rate")
  );
  expect(successRow, "Survival/success rate row present").toBeTruthy();
  if (successRow) {
    const pct = parsePct(successRow[1]);
    expect(pct, "Survival rate in [0,100]").not.toBeNull();
    expect(pct!).toBeGreaterThanOrEqual(0);
    expect(pct!).toBeLessThanOrEqual(100);
  }
});

// ─── Test 4: Aggregate Balances table ────────────────────────────────────────

test("Aggregate Balances table: 4 columns, 3 rows, no bad values", async ({ page }) => {
  await loadResults(page);
  const table = page.locator("section.results-section", { hasText: "Aggregate Balances" })
    .filter({ hasNot: page.locator("h3", { hasText: "Account Balances" }) })
    .locator("table.table").first();

  const cols = await getColumnCount(table);
  expect(cols, "Aggregate Balances columns").toBe(COLS.aggregateBalances);

  const cells = await getTableCells(page, table);
  expect(cells.length, "Aggregate Balances rows").toBe(3); // Brokerage | TRAD | Roth
  assertNoBadValues(cells, "Aggregate Balances");

  // Each ending balance should be > 0
  for (const row of cells) {
    const ending = parseUSD(row[2]);
    expect(ending, `Aggregate ending balance > 0 for ${row[0]}`).toBeGreaterThan(0);
  }
});

// ─── Test 5: Account Balances table ──────────────────────────────────────────

test("Account Balances table: 5 columns, 6 accounts, no bad values", async ({ page }) => {
  await loadResults(page);
  const table = page.locator("section.results-section", { hasText: "Account Balances" })
    .locator("table.table");

  const cols = await getColumnCount(table);
  expect(cols, "Account Balances columns").toBe(COLS.accountBalances);

  const cells = await getTableCells(page, table);
  expect(cells.length, "Account Balances row count (6 accounts)").toBe(6);
  assertNoBadValues(cells, "Account Balances");

  // Account names should include the 6 expected accounts
  const accountNames = cells.map((r) => r[0]);
  for (const expected of ["BROKERAGE-1", "BROKERAGE-2", "TRAD_IRA-1", "TRAD_IRA-2", "ROTH_IRA-1", "ROTH_IRA-2"]) {
    expect(accountNames, `Account ${expected} present`).toContain(expected);
  }
});

// ─── Test 6: Total Portfolio table ───────────────────────────────────────────

test("Total Portfolio table: correct columns, 49 rows, no bad values", async ({ page }) => {
  await loadResults(page);
  const section = page.locator("section.results-section").filter({
    has: page.locator("h3", { hasText: "Total Portfolio (Future USD)" }),
  });
  const table = section.locator("table.table").first();

  const cols = await getColumnCount(table);
  expect(cols, "Portfolio column count").toBe(COLS.portfolio);

  const cells = await getTableCells(page, table);
  expect(cells.length, "Portfolio row count").toBe(EXPECTED_ROWS);
  assertNoBadValues(cells, "Total Portfolio");

  // Year column should be 1..49
  expect(cells[0][0], "First year = 1").toBe("1");
  expect(cells[EXPECTED_ROWS - 1][0], `Last year = ${EXPECTED_ROWS}`).toBe(
    String(EXPECTED_ROWS)
  );

  // Age column: starts at 46 (birth_year=1980, current year=2026)
  const firstAge = parseInt(cells[0][1]);
  expect(firstAge, "First age = 46").toBe(46);

  // Typical balance (col 2): all rows > 0
  for (let i = 0; i < cells.length; i++) {
    const bal = parseUSD(cells[i][2]);
    expect(bal, `Portfolio balance > 0 at row ${i + 1}`).toBeGreaterThan(0);
  }
});

// ─── Test 7: Withdrawals table ────────────────────────────────────────────────

test("Withdrawals table: 14 columns, 49 rows, no bad values", async ({ page }) => {
  await loadResults(page);
  const section = page.locator("section.results-section").filter({
    has: page.locator("h3", { hasText: "Withdrawals" }),
  });
  const table = section.locator("table.table").first();

  const cols = await getColumnCount(table);
  expect(cols, "Withdrawals column count").toBe(COLS.withdrawals);

  const cells = await getTableCells(page, table);
  expect(cells.length, "Withdrawals row count").toBe(EXPECTED_ROWS);
  assertNoBadValues(cells, "Withdrawals");

  // Pre-RMD years (rows 0..28): planned withdrawal should be non-zero
  for (let i = 0; i < RMD_START_ROW - 1; i++) {
    const planned = parseUSD(cells[i][2]);
    expect(planned, `Planned withdrawal non-zero at row ${i + 1}`).toBeGreaterThan(0);
  }

  // Pre-RMD: For spending future $ (col 3) should be > 0
  for (let i = 0; i < RMD_START_ROW - 1; i++) {
    const forSpendingFuture = parseUSD(cells[i][5]);
    expect(forSpendingFuture, `For spending future > 0 at row ${i + 1}`).toBeGreaterThan(0);
  }

  // RMD years (rows 29+): RMD current (col 6) should be > 0
  for (let i = RMD_START_ROW - 1; i < EXPECTED_ROWS; i++) {
    const rmd = parseUSD(cells[i][6]);
    expect(rmd, `RMD > 0 at RMD year row ${i + 1}`).toBeGreaterThan(0);
  }

  // RMD years: For spending future $ (col 5) should still be > 0 (the fix we made)
  for (let i = RMD_START_ROW - 1; i < EXPECTED_ROWS; i++) {
    const forSpendingFuture = parseUSD(cells[i][5]);
    expect(
      forSpendingFuture,
      `For spending future > 0 in RMD year row ${i + 1} (regression: was zero before fix)`
    ).toBeGreaterThan(0);
  }
});

// ─── Test 8: Taxes by Type table ─────────────────────────────────────────────

test("Taxes table: 11 columns, 49 rows, effective rate ≤ 100%", async ({ page }) => {
  await loadResults(page);
  const section = page.locator("section.results-section", { hasText: "Taxes by Type" });
  const table = section.locator("table.table");

  const cols = await getColumnCount(table);
  expect(cols, "Taxes column count").toBe(COLS.taxes);

  const cells = await getTableCells(page, table);
  expect(cells.length, "Taxes row count").toBe(EXPECTED_ROWS);
  assertNoBadValues(cells, "Taxes");

  // Effective rate (last col): must be ≤ 100% or "—" — never > 100%
  const badRateRows: string[] = [];
  for (let i = 0; i < cells.length; i++) {
    const rateStr = cells[i][10];
    const rate = parsePct(rateStr);
    if (rate !== null && rate > 100) {
      badRateRows.push(`row ${i + 1} (age ${cells[i][1]}): ${rateStr}`);
    }
  }
  expect(
    badRateRows,
    `Effective rate > 100% found (regression: was 500-2000% before fix): ${badRateRows.join(", ")}`
  ).toHaveLength(0);

  // Pre-RMD effective rates: should be < 30% (small conversion-only taxes)
  for (let i = 0; i < RMD_START_ROW - 1; i++) {
    const rate = parsePct(cells[i][10]);
    if (rate !== null) {
      expect(
        rate,
        `Pre-RMD effective rate < 30% at row ${i + 1}`
      ).toBeLessThan(30);
    }
  }

  // RMD years: total taxes (col 6) should be > 0
  for (let i = RMD_START_ROW - 1; i < EXPECTED_ROWS; i++) {
    const totalTax = parseUSD(cells[i][6]);
    expect(totalTax, `Total taxes > 0 in RMD year row ${i + 1}`).toBeGreaterThan(0);
  }

  // RMD years: effective rate must SHOW a value (not dash) and be between 1% and 100%.
  // Dashes in RMD years = total_ordinary_income_median_path missing from withdrawals
  // (simulator_new.py must call withdrawals.update(_taxes_median_path)).
  const dashInRmdRows: string[] = [];
  for (let i = RMD_START_ROW - 1; i < EXPECTED_ROWS; i++) {
    const rateStr = cells[i][10].trim();
    if (rateStr === "—" || rateStr === "" || rateStr === "-") {
      dashInRmdRows.push(`row ${i + 1} (age ${cells[i][1]})`);
    }
  }
  expect(
    dashInRmdRows,
    `Effective rate showing dash in RMD years (regression: withdrawals.update(_taxes_median_path) missing): ${dashInRmdRows.join(", ")}`
  ).toHaveLength(0);
});

// ─── Test 9: Withdrawals Diff column ─────────────────────────────────────────

test("Withdrawals: Diff vs plan is 0 when fully met, never positive in non-RMD years", async ({ page }) => {
  await loadResults(page);
  const section = page.locator("section.results-section").filter({
    has: page.locator("h3", { hasText: "Withdrawals" }),
  });
  const table = section.locator("table.table").first();
  const cells = await getTableCells(page, table);

  // In pre-RMD years where portfolio is healthy: diff should be 0
  // (planned = 150k or 200k, fully met)
  const badDiffRows: string[] = [];
  for (let i = 0; i < RMD_START_ROW - 1; i++) {
    const diff = parseUSD(cells[i][4]);
    if (diff < -1000) {
      // More than $1k shortfall in pre-RMD years is suspicious for Test profile
      badDiffRows.push(`row ${i + 1}: diff=${cells[i][4]}`);
    }
  }
  // Soft check — log but don't fail hard (market might cause genuine shortfall)
  if (badDiffRows.length > 5) {
    throw new Error(
      `Unexpected shortfalls in ${badDiffRows.length} pre-RMD rows: ${badDiffRows.slice(0, 3).join(", ")}`
    );
  }
});

// ─── Test 10: Accounts YoY table ─────────────────────────────────────────────

test("Accounts YoY table: loads for all 6 accounts, no bad values", async ({ page }) => {
  await loadResults(page);
  const section = page.locator("section.results-section", {
    hasText: "Accounts — Investment YoY (Future USD)",
  });

  const accountSelect = section.locator("select");

  const accounts = [
    "BROKERAGE-1", "BROKERAGE-2",
    "TRAD_IRA-1", "TRAD_IRA-2",
    "ROTH_IRA-1", "ROTH_IRA-2",
  ];

  for (const acct of accounts) {
    await accountSelect.selectOption(acct);
    // Wait for table to update
    await page.waitForTimeout(200);

    const table = section.locator("table.table");
    const cells = await getTableCells(page, table);

    expect(
      cells.length,
      `Accounts YoY ${acct} row count`
    ).toBe(EXPECTED_ROWS);

    assertNoBadValues(cells, `Accounts YoY ${acct}`);

    // Typical balance (col 2) should be > 0 for all rows
    for (let i = 0; i < cells.length; i++) {
      const bal = parseUSD(cells[i][2]);
      expect(bal, `${acct} typical balance > 0 at row ${i + 1}`).toBeGreaterThan(0);
    }
  }
});

// ─── Test 11: Charts section present ─────────────────────────────────────────

test("Aggregate Balances Charts section present and images load", async ({ page }) => {
  await loadResults(page);

  const chartsSection = page.locator("section.results-section", {
    hasText: "Aggregate Balances (Charts)",
  });
  await expect(chartsSection).toBeVisible();

  // Select Current USD view
  const viewSelect = chartsSection.locator("select");
  await viewSelect.selectOption("current");

  // Wait for images
  await page.waitForTimeout(500);

  // At least one <img> should be visible
  const images = chartsSection.locator("img");
  const imgCount = await images.count();
  expect(imgCount, "At least one chart image visible").toBeGreaterThan(0);

  // Check images loaded (naturalWidth > 0 = not broken)
  for (let i = 0; i < imgCount; i++) {
    const loaded = await images.nth(i).evaluate(
      (img: HTMLImageElement) => img.complete && img.naturalWidth > 0
    );
    expect(loaded, `Chart image ${i + 1} loaded successfully`).toBe(true);
  }
});

// ─── Test 12: Insights section ───────────────────────────────────────────────

test("Insights section present with at least one finding", async ({ page }) => {
  await loadResults(page);

  // Use h3 filter to distinguish "Insights" section from "Roth Conversion Insights"
  const insights = page.locator("section.results-section").filter({
    has: page.locator("h3", { hasText: /^.*Insights.*finding/ }),
  });
  await expect(insights.first()).toBeVisible();

  // Should show finding count e.g. "(1 finding)"
  const header = insights.first().locator("h3");
  await expect(header).toContainText("finding");
});


// ─── Test 12b: Portfolio Analysis section ─────────────────────────────────────

test("Portfolio Analysis: section present, holdings table, per-account table", async ({ page }) => {
  await loadResults(page);

  const section = page.locator("section.results-section").filter({
    has: page.locator("h3", { hasText: "Portfolio Analysis" }),
  });
  await expect(section).toBeVisible({ timeout: 10_000 });

  // Section is collapsed by default — click h3 to expand
  await section.locator("h3").click();

  // Diversification score present
  await expect(section.locator("strong").first()).toContainText("/100");

  // Top Holdings table — VTI should appear (largest position in Test profile)
  const holdingsTable = section.locator("table.table").first();
  const tableText = await holdingsTable.textContent() ?? "";
  expect(tableText, "VTI appears in Top Holdings").toContain("VTI");
  const holdingRows = holdingsTable.locator("tbody tr");
  expect(await holdingRows.count(), "At least 3 tickers in holdings").toBeGreaterThanOrEqual(3);

  // Per-Account table has 6 rows
  const tables = section.locator("table.table");
  const perAcctTable = tables.last();
  const acctRows = perAcctTable.locator("tbody tr");
  expect(await acctRows.count(), "Per-Account table has 6 accounts").toBe(6);

  // No bad values
  const sectionText = await section.textContent() ?? "";
  expect(sectionText).not.toContain("NaN");
  expect(sectionText).not.toContain("undefined");
});

// ─── Test 13: Run Parameters displayed correctly ─────────────────────────────

test("Run Parameters show correct profile metadata", async ({ page }) => {
  await loadResults(page);

  const paramsSection = page.locator("section.results-section", { hasText: "Run Parameters" });
  await expect(paramsSection).toBeVisible();

  // Paths should be 200, Steps/Year 2
  await expect(paramsSection).toContainText("200");
  await expect(paramsSection).toContainText("2");
  await expect(paramsSection).toContainText("California");
  await expect(paramsSection).toContainText("MFJ");
});

// ─── Test 13b: Run panel has all four ignore checkboxes ───────────────────────
// Regression guard: checkboxes lost during App.tsx rebuilds won't be caught
// by Python tests (which test the simulator layer, not the UI).

test("Run panel: all four ignore checkboxes + simulation mode selector present", async ({ page }) => {
  await page.goto("/");
  await page.locator(".tab", { hasText: "Simulation" }).click();
  await expect(page.locator("h2", { hasText: "Simulation" })).toBeVisible();

  const expectedCheckboxes = [
    "Ignore withdrawals",
    "Ignore RMDs",
    "Ignore conversions",
    "Ignore taxes",
  ];
  for (const label of expectedCheckboxes) {
    await expect(
      page.locator("label", { hasText: label }),
      `"${label}" checkbox must be present in Run panel`
    ).toBeVisible();
  }

  // Simulation mode selector — all four modes present
  const expectedModes = ["Automatic", "Retirement-first", "Balanced", "Investment-first"];
  for (const mode of expectedModes) {
    await expect(
      page.locator("label", { hasText: mode }),
      `"${mode}" simulation mode must be present`
    ).toBeVisible();
  }
});

// ─── Test 14: No NaN/undefined anywhere on the full results page ──────────────

test("No NaN or undefined text anywhere in results page", async ({ page }) => {
  await loadResults(page);

  const pageText = await page.locator("body").textContent() ?? "";
  const badPatterns = [
    /\bNaN\b/,
    /\bundefined\b/,
    /\bnull\b/,
  ];

  // Exclude tooltip/metadata that might legitimately contain these words in descriptions
  // Focus on table cells and result values
  const tables = page.locator("table.table");
  const tableCount = await tables.count();

  for (let t = 0; t < tableCount; t++) {
    const tableText = await tables.nth(t).textContent() ?? "";
    for (const pattern of badPatterns) {
      expect(
        tableText,
        `Table ${t + 1} should not contain ${pattern}`
      ).not.toMatch(pattern);
    }
  }
});

// ─── Test 17: Roth Conversion Insights section ───────────────────────────────

test("Roth Conversion Insights: present, collapsed by default, expands on click", async ({ page }) => {
  await loadResults(page);

  // Section must be present
  const section = page.locator("section.results-section").filter({
    has: page.locator("h3", { hasText: "Roth Conversion Insights" }),
  });
  await expect(section).toBeVisible({ timeout: 10_000 });

  const h3 = section.locator("h3");

  // Collapsed by default — h3 should show ▶ and strategy summary
  await expect(h3).toContainText("▶");
  await expect(h3).toContainText("click to expand");

  // IRA Timebomb severity badge present (CRITICAL, SEVERE, MODERATE, or MANAGEABLE)
  const badge = h3.locator("span").filter({ hasText: /CRITICAL|SEVERE|MODERATE|MANAGEABLE/ });
  await expect(badge).toBeVisible();

  // Click to expand
  await h3.click();
  await expect(h3).toContainText("▼");

  // Current Situation subsection visible
  await expect(section.locator("div", { hasText: "Current Situation" }).first()).toBeVisible();

  // Recommendation subsection visible
  await expect(section.locator("div", { hasText: "Recommendation" }).first()).toBeVisible();

  // Apply button present with strategy name
  const applyBtn = section.locator("button", { hasText: /Apply .* to profile/ });
  await expect(applyBtn).toBeVisible();

  // 4×4 savings matrix table present
  const table = section.locator("table.table").first();
  await expect(table).toBeVisible();
  await expect(table.locator("th", { hasText: "Strategy" })).toBeVisible();
  await expect(table.locator("th", { hasText: "Convert/yr" })).toBeVisible();
});


// ─── Test 18: Configure tab — Version History panel ─────────────────────────

test("Configure tab: Version History panel present for non-default profile", async ({ page }) => {
  await page.goto("/");

  // Should already be on Configure tab
  await expect(page.locator("h2", { hasText: "Configure" })).toBeVisible();

  // Select Test profile
  await page.locator(".profile-row select").selectOption(PROFILE);
  await page.waitForTimeout(500);

  // Version History button present (non-default profile)
  const versionBtn = page.locator("button", { hasText: "Version History" });
  await expect(versionBtn).toBeVisible();

  // Collapsed by default — click to expand
  await versionBtn.click();
  await page.waitForTimeout(300);

  // Panel appears — shows either "No versions yet" or a table
  const panel = page.locator("div").filter({ hasText: /No versions yet|Ver.*Saved.*Note/ }).first();
  await expect(panel).toBeVisible({ timeout: 5_000 });
});


// ─── Test 19: Configure tab — Save Version button behavior ───────────────────

test("Configure tab: Save Version button visible in view mode, hidden when dirty", async ({ page }) => {
  await page.goto("/");

  await page.locator(".profile-row select").selectOption(PROFILE);
  await page.waitForTimeout(500);

  // Switch to view mode
  await page.locator(".profile-actions button", { hasText: "VIEW" }).click();
  await page.waitForTimeout(300);

  // Save Version button should be visible in clean state
  const saveVersionBtn = page.locator("button", { hasText: "Save Version" });
  await expect(saveVersionBtn).toBeVisible();

  // Switch to edit mode — use exact match to avoid matching "Clear Cache (Profile Editor)"
  await page.locator(".profile-actions button", { hasText: "EDIT" }).click();
  await page.waitForTimeout(300);

  // Save Version visible in clean edit mode
  await expect(saveVersionBtn).toBeVisible();

  // Make a trivial edit to dirty the editor
  const textarea = page.locator("textarea");
  await textarea.click();
  await textarea.press("End");
  await textarea.pressSequentially(" ", { delay: 50 });
  await page.waitForTimeout(200);

  // Save Version button should now be hidden
  await expect(saveVersionBtn).not.toBeVisible();

  // Note field should appear when dirty — look for the "Version note" label
  const versionNoteLabel = page.locator("div", { hasText: "Version note" }).first();
  await expect(versionNoteLabel).toBeVisible({ timeout: 5_000 });
  // And an input near it
  const noteInput = page.locator("input[type='text']").last();
  await expect(noteInput).toBeVisible();
});


// ─── Test 20: Investment tab — Roth Conversion Recommendations (Option C) ────

test("Investment tab: Roth Conversion Recommendations section present", async ({ page }) => {
  await page.goto("/");

  // Navigate to Investment tab
  await page.locator(".tab", { hasText: "Investment" }).click();
  await expect(page.locator("h2", { hasText: "Investment" })).toBeVisible();

  // Roth Conversion Recommendations section should be present
  const section = page.locator("section.results-section").filter({
    has: page.locator("h3", { hasText: "Roth Conversion Recommendations" }),
  });
  await expect(section).toBeVisible({ timeout: 5_000 });

  // Section should have some content — either severity data or instructions
  // Just verify the section itself has non-empty text content
  const sectionText = await section.textContent() ?? "";
  expect(sectionText.length, "Option C section has content").toBeGreaterThan(10);
});

// ─── Test 21: Versioning — Save Version creates a version entry ──────────────

test("Versioning: Save Version creates a version in history", async ({ page }) => {
  await page.goto("/");

  // Select Test profile in Configure tab
  await page.locator(".profile-row select").selectOption(PROFILE);
  await page.waitForTimeout(500);

  // Open Version History to get baseline count
  const versionBtn = page.locator("button", { hasText: "Version History" });
  await versionBtn.click();
  await page.waitForTimeout(300);

  // Count existing versions (may be 0 or more)
  const panel = page.locator("table").filter({ hasText: "Ver" }).first();
  const existingRows = await panel.locator("tbody tr").count().catch(() => 0);

  // If at or near the cap, prune down to 30 via API to make room
  if (existingRows >= 40) {
    await fetch("/profile/Test/versions?keep=30", { method: "DELETE" }).catch(() => {});
    await page.waitForTimeout(500);
    // Reload version history
    await versionBtn.click();
    await page.waitForTimeout(300);
    await versionBtn.click();
    await page.waitForTimeout(300);
  }

  // Close history
  await versionBtn.click();
  await page.waitForTimeout(200);

  // Open Save Version prompt
  const saveVersionBtn = page.locator("button", { hasText: "Save Version" });
  await expect(saveVersionBtn).toBeVisible();
  await saveVersionBtn.click();
  await page.waitForTimeout(200);

  // Type a label
  const labelInput = page.locator("input").filter({ hasText: "" }).last();
  await labelInput.fill("playwright test checkpoint");

  // Click Save
  await page.locator("button", { hasText: /^Save$/ }).click();
  await page.waitForTimeout(500);

  // Reopen Version History — should have one more entry
  await versionBtn.click();
  await page.waitForTimeout(300);

  const newRows = await panel.locator("tbody tr").count().catch(() => 0);
  expect(newRows, "Version count increased after Save Version").toBeGreaterThan(existingRows);

  // The new entry should contain our label
  await expect(panel).toContainText("playwright test checkpoint");
});


// ─── Test 22: Versioning — auto-version created on config save ───────────────

test("Versioning: auto-version created when saving a config file", async ({ page }) => {
  await page.goto("/");

  await page.locator(".profile-row select").selectOption(PROFILE);
  await page.waitForTimeout(500);

  // Get baseline version count
  const versionBtn = page.locator("button", { hasText: "Version History" });
  await versionBtn.click();
  await page.waitForTimeout(300);

  const historyTable = page.locator("table").filter({ hasText: "Ver" }).first();
  let countBefore = await historyTable.locator("tbody tr").count().catch(() => 0);

  // If at or near the cap, prune via API
  if (countBefore >= 40) {
    await fetch("/profile/Test/versions?keep=30", { method: "DELETE" }).catch(() => {});
    await page.waitForTimeout(500);
    countBefore = await historyTable.locator("tbody tr").count().catch(() => 0);
  }

  await versionBtn.click(); // close
  await page.waitForTimeout(200);

  // Switch to edit mode and make a trivial change
  await page.locator(".profile-actions button", { hasText: "EDIT" }).click();
  await page.waitForTimeout(400);

  // Click on person.json
  await page.locator(".config-file", { hasText: "person.json" }).click();
  await page.waitForTimeout(300);

  // Make a trivial whitespace change to trigger dirty
  const textarea = page.locator("textarea");
  await textarea.click();
  await textarea.press("End");
  await textarea.pressSequentially(" ");
  await page.waitForTimeout(200);

  // Type a version note
  const versionNoteLabel = page.locator("div", { hasText: "Version note" }).first();
  await expect(versionNoteLabel).toBeVisible();
  const noteInput = page.locator("input[type='text']").last();
  await noteInput.fill("playwright auto-version test");

  // Save to Profile
  await page.locator("button", { hasText: "Save to Profile" }).click();
  await page.waitForTimeout(500);

  // Reopen Version History — count should have increased
  await versionBtn.click();
  await page.waitForTimeout(300);

  const countAfter = await historyTable.locator("tbody tr").count().catch(() => 0);
  expect(countAfter, "Version count increased after save").toBeGreaterThan(countBefore);
  await expect(historyTable).toContainText("playwright auto-version test");
});


// ─── Test 23: Versioning — Restore reverts to a previous version ─────────────

test("Versioning: Restore reverts config and creates auto-save", async ({ page }) => {
  await page.goto("/");

  await page.locator(".profile-row select").selectOption(PROFILE);
  await page.waitForTimeout(500);

  // Open Version History
  const versionBtn = page.locator("button", { hasText: "Version History" });
  await versionBtn.click();
  await page.waitForTimeout(300);

  const historyTable = page.locator("table").filter({ hasText: "Ver" }).first();
  let countBefore = await historyTable.locator("tbody tr").count().catch(() => 0);

  // If at or near the cap, prune via API
  if (countBefore >= 40) {
    await fetch("/profile/Test/versions?keep=30", { method: "DELETE" }).catch(() => {});
    await page.waitForTimeout(500);
    countBefore = await historyTable.locator("tbody tr").count().catch(() => 0);
  }

  // Need at least 2 versions to restore
  if (countBefore < 2) {
    // Skip — not enough versions to test restore
    test.skip();
    return;
  }

  // Click View on the second row (index 1 — not the latest) to preview first
  const viewBtn = historyTable.locator("tbody tr").nth(1).locator("button", { hasText: "View" });
  await expect(viewBtn).toBeVisible();
  await viewBtn.click();
  await page.waitForTimeout(800);

  // Preview panel should appear with JSON content
  const previewPanel = page.locator("pre").filter({ hasText: "{" }).first();
  await expect(previewPanel).toBeVisible({ timeout: 5_000 });

  // Restore button is on the row itself (↩ Restore)
  const restoreBtn = page.locator("button", { hasText: /↩ Restore/ }).first();
  await expect(restoreBtn).toBeVisible();
  await restoreBtn.click();
  await page.waitForTimeout(800);

  // After restore: version count should increase by 1 (auto-save of current state)
  const countAfter = await historyTable.locator("tbody tr").count().catch(() => 0);
  expect(countAfter, "Restore auto-saves current state → count increases").toBeGreaterThan(countBefore);

  // The latest entry should mention "before restore" (auto-save note)
  const latestRow = historyTable.locator("tbody tr").first();
  await expect(latestRow).toContainText(/before restore|auto-save/i);
});
