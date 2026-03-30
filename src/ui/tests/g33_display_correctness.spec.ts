// filename: ui/tests/g33_display_correctness.spec.ts
// G33 — UI display correctness for v6.6 changes (standalone spec)
// Runs its own simulation in beforeAll so it can be run independently.

import { test, expect, Page } from "@playwright/test";

const BASE        = "http://localhost:8000";
const UI_PROFILE  = "PlaywrightTest";
const SIM_PATHS   = 100;
const SIM_STEPS   = 2;

let uiRunId = "";
let uiN     = 0;

// ── beforeAll: run a simulation so Results tab has data ──────────────────────

test.beforeAll(async ({ browser }) => {
  const ctx  = await browser.newContext();
  const page = await ctx.newPage();

  // Read person.json to get n_years, state, filing
  const pjRes = await page.request.get(`${BASE}/profile-config/${UI_PROFILE}/person.json`);
  const pjWrap = await pjRes.json();
  const pj = JSON.parse(pjWrap.content);
  const startAge = pj.birth_year ? new Date().getFullYear() - pj.birth_year : 46;
  const targetAge = pj.target_age ?? (pj.assumed_death_age ?? 95);
  uiN = targetAge - startAge;
  const state   = pj.state          ?? "California";
  const filing  = pj.filing_status  ?? "MFJ";
  const mode    = pj.simulation_mode ?? "retirement";

  // Trigger simulation run
  const runRes = await page.request.post(`${BASE}/run`, {
    data: {
      profile:        UI_PROFILE,
      paths:          SIM_PATHS,
      steps_per_year: SIM_STEPS,
      base_year:      new Date().getFullYear(),
      dollars:        "current",
      state, filing,
      simulation_mode: mode,
      shocks_mode:    "augment",
    },
  });
  const runData = await runRes.json();
  uiRunId = runData.run ?? "";

  await ctx.close();
});

// ── Helper: navigate to Results with profile + run selected ──────────────────

async function loadResults(page: Page) {
  await page.goto(BASE);
  await page.click('button:has-text("Results")');

  // Select profile
  const profSel = page.locator(".results-header select").first();
  await expect(profSel).toBeVisible({ timeout: 10_000 });
  await profSel.selectOption(UI_PROFILE);

  // Select run if we have one
  if (uiRunId) {
    const runSel = page.locator(".results-header select").nth(1);
    await runSel.selectOption({ label: new RegExp(uiRunId.slice(0, 20)) }).catch(() => {});
  }

  // Wait for snapshot table
  await page.waitForSelector("table.table tbody tr", { timeout: 30_000 });
}

// ── G33a — Investment return rows ────────────────────────────────────────────

test("G33a: Investment return — Nominal row shows Mean·Median·Stress", async ({ page }) => {
  await loadResults(page);
  const row = page.locator("table.table tbody tr").filter({
    has: page.locator("td", { hasText: "Investment return — Nominal (gross)" }),
  });
  await expect(row).toHaveCount(1);
  const val = await row.locator("td").nth(1).textContent() ?? "";
  expect(val).toContain("Mean:");
  expect(val).toContain("Median:");
  expect(val).toContain("Stress:");
});

test("G33a2: Investment return — Real row present", async ({ page }) => {
  await loadResults(page);
  await expect(
    page.locator("table.table tbody tr").filter({
      has: page.locator("td", { hasText: "Investment return — Real (gross)" }),
    })
  ).toHaveCount(1);
});

// ── G33b — Portfolio net CAGR sub-rows ───────────────────────────────────────

test("G33b: Portfolio net CAGR — Nominal sub-row present and indented", async ({ page }) => {
  await loadResults(page);
  const row = page.locator("table.table tbody tr").filter({
    has: page.locator("td", { hasText: "Portfolio net CAGR — Nominal" }),
  });
  await expect(row).toHaveCount(1);
  const pl = await row.locator("td").first().evaluate(el =>
    parseInt(getComputedStyle(el).paddingLeft)
  );
  expect(pl).toBeGreaterThan(12);
});

test("G33b2: Portfolio net CAGR — Real sub-row present", async ({ page }) => {
  await loadResults(page);
  await expect(
    page.locator("table.table tbody tr").filter({
      has: page.locator("td", { hasText: "Portfolio net CAGR — Real" }),
    })
  ).toHaveCount(1);
});

// ── G33c — Results page JS stability ─────────────────────────────────────────

test("G33c: Results page loads without JS scope errors", async ({ page }) => {
  const jsErrors: string[] = [];
  page.on("pageerror", err => jsErrors.push(err.message));
  await loadResults(page);
  const scopeErrors = jsErrors.filter(e =>
    e.includes("successRate") || e.includes("ReferenceError") || e.includes("is not defined")
  );
  expect(scopeErrors).toHaveLength(0, `JS errors: ${scopeErrors.join("; ")}`);
  await expect(page.locator("table.table thead th").first()).toBeVisible();
});

test("G33c2: Survival rate renders a valid percentage", async ({ page }) => {
  await loadResults(page);
  const survRow = page.locator("table.table tbody tr").filter({
    has: page.locator("td", { hasText: /Full-plan survival rate/ }),
  });
  await expect(survRow).toHaveCount(1);
  const val = await survRow.locator("td").nth(1).textContent() ?? "";
  expect(val).toMatch(/\d+\.\d+%/);
});

// ── G33d — Insights basis label ──────────────────────────────────────────────

test("G33d: Insights header contains 'median path' basis label", async ({ page }) => {
  await loadResults(page);
  const h3 = page.locator("h3").filter({ hasText: "Insights" }).first();
  await expect(h3).toBeVisible({ timeout: 10_000 });
  const txt = await h3.textContent() ?? "";
  expect(txt.toLowerCase()).toContain("median path");
});

// ── G33e — Section header casing ─────────────────────────────────────────────

test("G33e: Person.json section headers are title case not ALL CAPS", async ({ page }) => {
  await page.goto(BASE);
  await page.click('button:has-text("Configure")');
  await page.waitForSelector("[data-section]", { timeout: 10_000 });
  const headers = await page.locator("[data-section]").allTextContents();
  for (const h of headers) {
    const stripped = h.replace(/[▶▼\s]/g, "");
    if (!stripped) continue;
    const letters = stripped.replace(/[^a-zA-Z]/g, "");
    if (!letters) continue;
    const isAllCaps = letters === letters.toUpperCase() && letters !== letters.toLowerCase();
    expect(isAllCaps).toBe(false, `"${stripped}" should not be ALL CAPS`);
  }
});

test("G33e2: Specific section headers use expected title case", async ({ page }) => {
  await page.goto(BASE);
  await page.click('button:has-text("Configure")');
  await page.waitForSelector("[data-section]", { timeout: 10_000 });
  for (const expected of ["Identity", "Simulation Horizon", "Social Security", "Spouse"]) {
    await expect(
      page.locator("[data-section]").filter({ hasText: expected }).first()
    ).toBeVisible({ message: `"${expected}" should be visible` });
  }
});

// ── G33f — Currency toggle ────────────────────────────────────────────────────

test("G33f: Portfolio Projection has Today's USD / Future USD toggle", async ({ page }) => {
  await loadResults(page);
  await expect(page.locator("button", { hasText: "Today's USD" })).toBeVisible({ timeout: 10_000 });
  await expect(page.locator("button", { hasText: "Future USD" })).toBeVisible();
});

test("G33f2: Clicking Future USD toggle updates chart description", async ({ page }) => {
  await loadResults(page);
  await page.locator("button", { hasText: "Future USD" }).click();
  await page.waitForTimeout(500);
  const section = page.locator(".results-section").filter({
    has: page.locator("h3", { hasText: "Portfolio Projection" }),
  });
  const txt = await section.textContent() ?? "";
  expect(txt.toLowerCase()).toContain("nom");
});

// ── G33g — Chart SVG ─────────────────────────────────────────────────────────

test("G33g: Portfolio Projection SVG present with path elements", async ({ page }) => {
  await loadResults(page);
  const section = page.locator(".results-section").filter({
    has: page.locator("h3", { hasText: "Portfolio Projection" }),
  });
  await expect(section).toBeVisible({ timeout: 10_000 });
  const paths = await section.locator("svg path").count();
  expect(paths).toBeGreaterThanOrEqual(3);
});

test("G33g2: Chart SVG contains Typical legend entry", async ({ page }) => {
  await loadResults(page);
  const section = page.locator(".results-section").filter({
    has: page.locator("h3", { hasText: "Portfolio Projection" }),
  });
  const svgText = await section.locator("svg").textContent() ?? "";
  expect(svgText).toContain("Typical");
});

// ── G33h — Arithmetic check suppressed ───────────────────────────────────────

test("G33h: Arithmetic check banner absent when survival ≥ 95%", async ({ page }) => {
  await loadResults(page);
  const survRow = page.locator("table.table tbody tr").filter({
    has: page.locator("td", { hasText: /Full-plan survival rate/ }),
  });
  const survText = await survRow.locator("td").nth(1).textContent() ?? "0%";
  if (parseFloat(survText) >= 95) {
    await expect(page.locator("text=arithmetic check")).toHaveCount(0);
  }
});

// ── G33i — No "Not meaningful" text ──────────────────────────────────────────

test("G33i: 'Not meaningful' text never appears in CAGR rows", async ({ page }) => {
  await loadResults(page);
  await expect(page.locator("text=Not meaningful")).toHaveCount(0);
});

// ── G33j — CAGR format ───────────────────────────────────────────────────────

test("G33j: Portfolio net CAGR rows show Median: format not old 'net (vs' format", async ({ page }) => {
  await loadResults(page);
  const row = page.locator("table.table tbody tr").filter({
    has: page.locator("td", { hasText: "Portfolio net CAGR — Nominal" }),
  });
  await expect(row).toHaveCount(1);
  const val = await row.locator("td").nth(1).textContent() ?? "";
  expect(val).toMatch(/Median:/);
  expect(val).not.toContain("net (vs");
});
