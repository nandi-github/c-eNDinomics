# eNDinomics Test Suite Documentation

**File:** `src/test_flags.py`  
**Total checks:** 592 (Python) + 59 (Playwright) = **651 checks**  
**Groups:** 27 Python groups + 1 Playwright group  
**Last updated:** 2026-03-26

---

## Purpose and Philosophy

This test suite verifies that every customer-configurable option in the profile JSON files routes correctly through the simulator and produces the expected behavioural changes in output. It is **not** a retirement feasibility test — it does not assert portfolio survival, adequate wealth, or sensible financial planning outcomes. It only asserts that **configuration X produces output behaviour Y**.

Every test runs against ephemeral profiles created on-the-fly and deleted after each group. No persistent profile state is required except `profiles/Test/` (for group standard runs) and `profiles/default/` (canonical schema template).

---

## Architecture

### Test Harness Components

| Component | Purpose |
|-----------|---------|
| `write_profile(tag, **kwargs)` | Creates a temporary profile directory with JSON files from BASE_* fixtures or caller-supplied overrides |
| `drop_profile(tag)` | Deletes the ephemeral profile after the test group completes |
| `load_cfg(name)` | Loads all JSON configs for a profile into a single dict via `loaders.py` |
| `_income_arrays(income_cfg, paths, n_years)` | Converts loaded income config into numpy path arrays for the simulator; builds `ordinary_income_cur_paths`, `w2_income_cur_paths`, `income_sources_cur_paths` |
| `sim(cfg, paths, ...)` | Calls `run_accounts_new` directly — no HTTP, no server needed |
| `ephemeral_run(tag, paths, ...)` | `write_profile` + `load_cfg` + `sim` + `drop_profile` in one call |
| `check_updates(server_url)` | Fetches `/manifest` from running server, compares SHA-256 hashes of all tracked files |

### BASE Fixtures

All groups start from these baseline configs and override only the fields under test:

- `BASE_PERSON` — MFJ, CA, age 46, birth_year 1980, target_age 95, Roth conversion enabled
- `BASE_INCOME` — all income sources zero
- `BASE_ALLOCATION` — 6 accounts: BROKERAGE-1/2, TRAD_IRA-1/2, ROTH_IRA-1/2 with realistic starting balances
- `BASE_WITHDRAWAL` — three-tier schedule: $150K ages 47-64, $200K ages 65-74, $250K ages 75-95
- `BASE_INFLATION` — 3.5% constant
- `BASE_ECONOMIC` — standard withdrawal sequence (TRAD → BROK → ROTH), bad-market order reversed

### Run Modes

```bash
# Full suite — requires server running, auto-runs checkupdates first
python3 -B test_flags.py --comprehensive-test

# Python-only — no server needed, skips checkupdates gate
python3 -B test_flags.py --comprehensive-test --skip-playwright

# Fast mode — 50 paths instead of 200
python3 -B test_flags.py --comprehensive-test --fast

# Named profile standard run
python3 -B test_flags.py --profile MyProfile

# Hash verification only
python3 -B test_flags.py --checkupdates
```

### checkupdates Gate

When `--comprehensive-test` is invoked **without** `--skip-playwright`, the harness automatically runs `--checkupdates` first. If any tracked file hash differs between local disk and the running server, the test suite aborts with a clear error message. This prevents running tests against stale server code.

---

## Group Reference

### G1 — Ignore-Flag Matrix (34 checks)

**What it tests:** Every combination of the three ignore flags (`ignore_withdrawals`, `ignore_conversions`, `ignore_rmds`), verifying that each flag independently zeroes the correct output arrays and that no combination produces a crash or NaN values.

**Scenarios:** 8 combinations (2³) × assertions per combo.

**Key assertions:**
- `ignore_withdrawals=True` → `planned_current` all zeros
- `ignore_conversions=True` → `total_converted_nom_mean` = 0
- `ignore_rmds=True` → `rmd_current_mean` all zeros
- `ignore_taxes=True` → all tax arrays zero
- All combinations produce finite portfolio values

**Why it matters:** These flags are used extensively in the test harness itself to isolate specific subsystems. If a flag doesn't work cleanly, every test that uses it is compromised.

---

### G2 — RMD Behaviour (11 checks)

**What it tests:** Required Minimum Distribution computation, SECURE 2.0 age brackets, and surplus RMD routing policy.

**Scenarios:**
- `extra_handling: reinvest_in_brokerage` → surplus RMD above spending plan goes to brokerage
- `extra_handling: cash_out` → surplus RMD disappears from portfolio (spent)
- `birth_year 1950` → RMD age 72 (pre-SECURE)
- `birth_year 1953` → RMD age 73 (SECURE 1.0)
- `birth_year 1960` → RMD age 75 (SECURE 2.0)
- Multiple TRAD accounts → each gets independent RMD debit
- ROTH accounts → never receive RMD debits

**Key assertions:**
- RMD fires at correct age per birth year
- RMD = 0 before the age threshold, > 0 after
- Brokerage balance higher when `reinvest_in_brokerage` vs `cash_out`
- All TRAD accounts show RMD outflow; ROTH accounts do not

---

### G3 — Roth Conversion Policy (15 checks)

**What it tests:** All configurable options in `roth_conversion_policy`.

**Scenarios:**
- `enabled: false` → zero conversions
- `window_years: now-65` (narrow) vs `now-75` (wide) → conversions stop at correct age
- `keepit_below: "fill the bracket"` vs `"22%"` vs `"none"` → conversion capped correctly
- `rmd_assist: "convert"` → RMD counts toward conversion room
- `avoid_niit: true` → conversion halts before NIIT threshold
- `irmaa_guard: enabled` → conversion capped at IRMAA tier boundary

**Key assertions:**
- Narrow window produces fewer total conversions than wide window
- `22%` bracket cap keeps conversion tax in 22% bracket
- NIIT guard: NIIT = 0 when avoid_niit=true, > 0 when false with high income
- `rmd_assist` runs produce ≥ the same conversion as non-assist (RMD consumes some room)

---

### G4 — Income Types and Schedules (26 checks)

**What it tests:** All income types in `income.json` route through the tax engine correctly.

**Scenarios:**
- W2 income → raises ordinary income → fewer Roth conversion dollars available
- Rental income → ordinary income, no AMT
- Interest income → ordinary income
- `ordinary_other` → ordinary income (SS, pension)
- `qualified_div` → LTCG rates, no crash
- `cap_gains` → LTCG rates, no crash
- Staggered schedule (income starts year 6) → correct year routing
- All income types simultaneously → no crash, tax arrays populated

**Key assertions:**
- Federal tax > 0 whenever ordinary income > standard deduction
- W2 run produces higher taxes than rental run at same amount (AMT fires on W2)
- Staggered income: tax = 0 in years 1-5, > 0 in years 6+
- All income combinations produce finite, non-negative tax arrays

---

### G5 — Inflation Schedule (5 checks)

**What it tests:** Inflation array routing and deflator computation.

**Scenarios:**
- Zero inflation → `future_mean == current_mean` every year
- Variable inflation → deflator grows monotonically

**Key assertions:**
- Zero inflation: `future_mean[y] ≈ current_mean[y]` within tolerance
- Variable inflation: deflator is strictly increasing
- Portfolio values sensible in both cases

---

### G6 — Withdrawal Schedule (27 checks)

**What it tests:** Withdrawal schedule loading, floor enforcement, and all withdrawal-related fields.

**Scenarios:**
- Three-tier step-up schedule → avg(tier3) > avg(tier2) > avg(tier1)
- `floor_k` → realized withdrawal never below floor
- `apply_withdrawals=False` → planned_current all zeros
- Bad-market scaling → withdrawals reduced during drawdown
- Makeup payments → recovery in good years after bad-market scaling
- Upside scaling → withdrawals increase when portfolio outperforms

**Key assertions:**
- Tier ordering: higher tiers produce higher average realized withdrawals
- Floor: `realized_current_mean[y] >= floor_k * 1000` every year
- Bad market: scaled withdrawal < unscaled withdrawal during shock years
- Makeup: cumulative realized in recovery > cumulative without makeup

---

### G7 — Allocation and Deposits (8 checks)

**What it tests:** Per-account allocation overrides and deposit injection.

**Scenarios:**
- Allocation override years 5-10 in `augment` mode → no crash
- Brokerage deposits years 1-5 → BROK end balance > no-deposit baseline
- TRAD-heavy setup with minimal brokerage → no crash (withdrawal sequence handles exhaustion)

**Key assertions:**
- Deposits increase target account balance relative to baseline
- Override mode `augment` does not corrupt existing portfolio weights
- TRAD-heavy setup with small brokerage: simulation completes without NaN

---

### G8 — Shock Events (59 checks)

**What it tests:** All configurable fields in `shocks_yearly.json`. This is the largest group by check count.

**Scenarios covered:**

| Field | Values tested |
|-------|--------------|
| `type` | `dip_profile`, `rise_profile` |
| `dip_profile.type` | `poly` (alpha>1), `poly` (alpha<1), `linear`, `exp` |
| `rise_profile.type` | `poly`, `linear`, `exp` |
| `override_mode` | `strict`, `augment` |
| `recovery_to` | `baseline`, `none` |
| `coimpact_down.mode` | `limited`, `broad` |
| `corecovery_up` | with `organic=true`, `organic_profile=exp` |
| `correlated_to` + `scale` | cross-asset correlation |
| `start_quarter` | Q1, Q2, Q3, Q4 |
| Edge cases | year 1 shock, year 28 shock, multiple staggered events, all 7 asset classes |

**Key assertions:**
- Shock year returns are lower than no-shock baseline for shocked asset class
- Rise profile year returns are higher than no-shock baseline
- `recovery_to: none` → no recovery above shock floor
- `recovery_to: baseline` → returns back to pre-shock level within recovery window
- Edge case shocks: simulation completes, portfolio finite, no NaN

---

### G9 — Age Variations (9 checks)

**What it tests:** Age-dependent behaviour: RMD eligibility, pre-retirement long horizon, at-retirement immediate RMD.

**Scenarios:**
- Age 40 (pre-retirement, 55yr horizon) → no RMD in simulation window
- Age 73 (birth_year 1953, SECURE 1.0) → RMD fires immediately in year 1
- Age 72 (birth_year 1951, RMD age 73) → RMD fires in year 2

**Key assertions:**
- Age 40: `rmd_current_mean` all zeros for 30 years
- Age 73: `rmd_current_mean[0] > 0`
- Age 72 (RMD at 73): `rmd_current_mean[0] = 0`, `rmd_current_mean[1] > 0`

---

### G10 — Rebalancing Flag (5 checks)

**What it tests:** Master rebalancing switch and behaviour with/without it.

**Scenarios:**
- `rebalancing_enabled=True` → no crash, cap gains array populated from rebalancing gains
- `rebalancing_enabled=False` → no crash, simulation completes cleanly

**Key assertions:**
- Both modes produce finite portfolio values
- No NaN in any output array

---

### G11 — Tax Wiring (46 checks)

**What it tests:** End-to-end tax pipeline correctness. Verifies the four tax wiring gaps identified in development, plus bracket math and Additional Medicare Tax.

**Sub-groups:**

**G11a-d (Tax wiring gaps):**
- Gap 1: Tax debit hits brokerage balance (tax costs money, not just a number)
- Gap 2: `withdrawals.taxes_*_current_mean` arrays populated and non-zero when income present
- Gap 3: `fed_year0` reflects year-0 tax rate only, not 30-year average
- Gap 4: Summary totals consistent with yearly array sums

**G11e-p (Bracket math and filing status):**
- MFJ vs Single: same income produces different tax (wider MFJ brackets)
- CA state tax fires when income > CA standard deduction
- TX (no income tax): state tax = 0 every year
- NIIT: fires when investment income > threshold, suppressed by `avoid_niit=true`
- Effective rate: in plausible range [1%, 60%] for realistic income levels

**G11r (AMT unit test — taxes_core.py direct):**
- `compute_annual_taxes()` directly: W2 $350K MFJ → AMT = 0.9% × $100K = $900
- Exact IRS formula: AMT applies to wages above $250K MFJ / $200K Single
- Single filer threshold: $200K → AMT on $150K = $1,350

**G11s (AMT vectorized — compute_annual_taxes_paths):**
- `compute_annual_taxes_paths()` directly with paths=200 W2 arrays
- W2 $350K: delta vs no-W2 ≈ $900 (MFJ), ≈ $1,350 (Single)
- All 200 paths identical delta (deterministic income → no path variance)

---

### G12 — Roth Conversion Tax Verification (26 checks)

**What it tests:** Conversion tax correctness — that conversions cost the right amount and don't double-count with ordinary taxes.

**Scenarios:**
- Conversion active → `conv_tax > 0`
- Conversion disabled → `conv_tax = 0`
- Tax rate (conv_tax / converted) → in marginal bracket range [10%, 50%]
- Conversion fires only within `window_years` range
- TRAD balance decreases, ROTH balance increases vs no-conversion baseline
- No double-debiting: conversion tax not double-counted in ordinary tax block
- `meta.run_params` populated; `meta.runtime_overrides` correctly reflects overrides

**Key assertions:**
- `conv_tax_total > 0` when conversions enabled
- `conv_tax_total = 0` when disabled or outside window
- `conv_tax / conv_amount` in [0.10, 0.50]
- TRAD end balance: with-conversion < without-conversion
- ROTH end balance: with-conversion > without-conversion

---

### G13 — YoY Returns Sanity (42 checks)

**What it tests:** Year-over-year return arrays are consistent, well-formed, and economically sensible.

**Checks:**
- All YoY arrays present and length n_years
- All values finite (no NaN, no Inf)
- Nominal YoY > Real YoY every year (inflation preserved)
- Values in sane range: [-50%, +100%] per year
- 30-year geometric mean: [3%, 25%] nominal
- Investment YoY ≥ Portfolio YoY in most years (withdrawal drag)
- YoY has variance (not flat — no degenerate Monte Carlo bug)
- Per-account YoY arrays for all 6 accounts
- Shock year region: lower YoY than no-shock baseline for shocked class
- `summary.cagr_nominal_mean` consistent with YoY-derived geometric mean

---

### G14 — Cashflow Verification (15 checks)

**What it tests:** That money flows balance correctly — withdrawals reduce balances, conversions move money correctly, taxes reduce brokerage.

**Key assertions:**
- Portfolio balance at end of year y = balance at end of year y-1 + growth - withdrawals - taxes
- Conversion: TRAD reduced by conversion amount, ROTH increased by same amount
- Tax debit: brokerage reduced by tax amount each year
- No money creation: total outflows ≤ total inflows + starting balance

---

### G15 — Insights Engine (23 checks)

**What it tests:** The insights / summary analysis fields that the UI displays to the user.

**Checks:**
- `insights.ira_timebomb_severity` present and one of: `NONE`, `LOW`, `MODERATE`, `HIGH`, `SEVERE`, `CRITICAL`
- `insights.betr` (Break-Even Tax Rate) in plausible range [5%, 50%]
- `insights.future_rmd_rate` in plausible range
- `insights.conversion_window_years` matches person.json window
- Survival rate in [0, 100]
- All insight fields present when simulation runs with realistic config

---

### G16 — Dynamic Simulation Years (28 checks)

**What it tests:** The dynamic `n_years = target_age - current_age` computation and that all output arrays are correctly sized.

**Scenarios:**
- `target_age=75` (short horizon, n_years≈29)
- `target_age=95` (standard horizon, n_years≈49)
- `target_age=110` (long horizon, n_years≈64, capped at 60)

**Key assertions:**
- All output arrays have length exactly `n_years`
- YoY arrays, tax arrays, withdrawal arrays all correctly sized
- `portfolio.future_median` length = n_years
- Capping at 60 years works correctly

---

### G17 — UI Data Integrity (45 checks)

**What it tests:** That the API response contains all fields the UI expects, in the correct format, with no NaN or undefined values.

**Checks:**
- All top-level response keys present: `portfolio`, `withdrawals`, `taxes`, `summary`, `returns`, `returns_acct`, `returns_acct_levels`, `meta`, `conversions`, `accounts`
- `portfolio.future_median` length = n_years, all > 0
- `portfolio.future_mean`, `p10`, `p90` all present
- `withdrawals.planned_current` length = n_years
- `taxes.fed_cur_mean_by_year` length = n_years, all finite
- `meta.run_params` has `state`, `filing_status`, `rmd_table`
- No NaN values anywhere in the response
- All numeric arrays contain only finite values

---

### G18 — Snapshot Regression (22 checks)

**What it tests:** That simulation outputs remain stable across code changes. Catches unintentional behavioural regressions.

**How it works:**
1. First run: computes output values and saves as `test_results/regression_baseline.json`
2. Subsequent runs: compares current output against saved baseline
3. `--update-baseline` flag: clears baseline and regenerates

**What is baselined:**
- `portfolio.future_median[-1]` (end portfolio value)
- `summary.survival_rate_pct`
- `withdrawals.rmd_current_mean` (first year with RMDs)
- `taxes.fed_cur_mean_by_year[0]` (year-1 federal tax)

**Tolerance:** 5% on all values (accommodates stochastic variance across path counts).

---

### G19 — Playwright UI Smoke Tests (3 checks + 59 browser tests)

**What it tests:** Full UI pipeline from browser interaction through API to rendered results.

**Requires:** Running server at `http://localhost:8000`, Chrome/Chromium installed.

**Setup:** Creates `PlaywrightTest` profile from `__testui__` template, runs Playwright, deletes profile.

**Browser tests cover:**
- Page loads with correct title and tab structure
- `__system__*` and `__testui__` profiles hidden from UI dropdown
- Results load and render for PlaywrightTest profile
- Summary table: correct column count, survival rate in [0, 100]
- Aggregate Balances: 4 columns, 3 rows, all balances > 0
- Account Balances: 5 columns, all 6 accounts present by name
- Total Portfolio table: n_years rows, year sequence 1..n_years
- Withdrawals table: 14 columns, RMD rows > 0 in RMD era
- Taxes table: 9 columns, effective rate ≤ 100% every year
- Withdrawal diff: not deeply negative in pre-RMD years
- Accounts YoY: n_years rows per account, all balances > 0
- Charts section present with rendered chart
- Insights section present with content
- Portfolio Analysis section present
- Run Parameters section present
- Run panel: ignore checkboxes + mode selector present
- No NaN or `undefined` anywhere in rendered results
- Roth Conversion Insights: present and expandable
- Version History: panel present in Configure tab
- Save Version: hidden when config is dirty
- Investment tab: Roth Conversion Recommendations present
- Versioning: Save Version creates history entry
- Versioning: auto-version fires on config save
- Versioning: Restore reverts config and creates auto-save entry

---

### G20 — Portfolio Allocation Analysis (24 checks)

**What it tests:** Asset allocation reporting — that portfolio composition, weights, and class-level data are computed correctly.

**Checks:**
- Asset class weights sum to 1.0 for each account each year
- All 8 canonical asset classes represented: US_STOCKS, INTL_STOCKS, LONG_TREAS, INT_TREAS, TIPS, GOLD, COMMOD, OTHER
- Class-level balance arrays present and non-negative
- Weighted average return consistent with asset class returns and weights

---

### G21 — Asset Weight Sanity (7 checks)

**What it tests:** That portfolio weights are normalized correctly across accounts and years, with no weight > 1 or < 0.

**Key assertions:**
- All individual class weights in [0, 1]
- Sum of all class weights per portfolio = 1.0 ± 0.001
- No NaN in weight arrays

---

### G22 — Roth Optimizer (55 checks)

**What it tests:** The Roth conversion optimizer (`roth_optimizer.py`) — BETR computation, strategy recommendations, scenario analysis, and insights generation.

**Sub-groups:**

**G22a — BETR computation:**
- BETR (Break-Even Tax Rate) formula: `1 - (1-current_rate)/(1-future_rate)`
- MFJ vs Single produces different BETR (wider brackets → lower MFJ current rate)
- High income → high BETR → strong convert signal
- Low income → low BETR → defer signal

**G22b — Strategy matrix:**
- Conservative (22%), Balanced (24%), Aggressive (32%), Maximum (37%)
- Each strategy produces correct annual conversion amount
- Savings ordering: higher strategies produce higher heir savings (more conversion)

**G22c — Scenario analysis:**
- Self (MFJ) scenario: conversion helps up to BETR
- Survivor scenario: single-filer brackets → higher future rate → more valuable to convert
- Heir moderate/high: 37% forced liquidation rate makes conversion always valuable
- `heir_driven_recommendation` flag set correctly when heir savings dominate

**G22d — IRMAA interaction:**
- IRMAA not active below age 63
- IRMAA advisory note present when age ≥ 63 and conversion crosses tier boundary
- `irmaa_sensitivity: high` tightens recommendation vs `low`

**G22e — Warnings deduplication:**
- IRA timebomb warning not duplicated between `warnings[]` and UI-generated fields
- Heir warnings only appear once
- `warnings[]` array contains no empty entries

**G22h-j — heir_driven_recommendation:**
- `heir_driven_recommendation: true` when heir savings > self savings
- `heir_driven_recommendation: false` when self savings dominate
- UI explanation text references correct savings figure

---

### G23 — Bad Market Response (10 checks)

**What it tests:** That `economicglobal.json` bad market settings actually fire and affect withdrawals.

**Scenarios:**
- Shock that crosses `drawdown_threshold` → bad market flag set
- Bad market → withdrawal scaling fires, realized < planned
- Bad market → withdrawal sequence switches to bad-market order (bonds first)
- Recovery year after bad market → makeup payment fires
- `bad_market_frac_by_year` field present in withdrawals output

**Key assertions:**
- During shock: `realized_current_mean[shock_yr] < planned_current[shock_yr]`
- After shock: `realized_current_mean` recovers toward planned
- Makeup: cumulative realized over shock+recovery > cumulative without makeup

---

### G24 — Upside Scaling and Safe Withdrawal Rate (5 checks)

**What it tests:** Upside scaling (withdrawals increase when portfolio outperforms) and safe withdrawal rate calculation.

**Scenarios:**
- `upside_scaling_enabled: true` with strong portfolio → withdrawals above planned in good years
- `upside_scaling_enabled: false` → withdrawals never exceed planned
- Safe withdrawal rate: computed as max withdrawal sustaining 90%+ survival rate

**Key assertions:**
- Upside: `realized > planned` in at least some years when enabled with good returns
- No upside: `realized <= planned` always when disabled
- SWR: value in plausible range [2%, 8%] for realistic portfolio

---

### G25 — Social Security Provisional Income (17 checks)

**What it tests:** The IRS three-tier SS provisional income formula for taxable SS inclusion.

**Design:** SS provisional income = non-SS income + 0.5 × gross SS benefit.

**Tiers (MFJ):**
- Tier 0: provisional < $32,000 → 0% of SS taxable
- Tier 1: $32,000 ≤ provisional < $44,000 → up to 50% taxable
- Tier 2: provisional ≥ $44,000 → up to 85% taxable (cap: 85% of gross)

**Single filer thresholds:** $25,000 / $34,000

**G25a — Unit tests (formula only):**
- Tier 0: provisional $18K → taxable = $0
- Tier 0 boundary: provisional $31,999 → taxable = $0
- Tier 1: provisional $38K → taxable = $3,000 (exact formula check)
- Tier 2 high: provisional $118K → taxable = 85% × gross
- Tier 2 boundary: just above $44K → taxable > tier 1 result
- Monotonic: taxable non-decreasing as non-SS income increases
- Cap: taxable never exceeds 85% × gross SS

**G25b — Single filer thresholds:**
- Same SS gross with $30K non-SS: single filer pays more tax than MFJ

**G25c — End-to-end simulation:**
- SS-only (no W2): taxes non-negative, no crash
- SS + $150K W2: total taxes significantly higher than SS-only
- Both runs: federal tax arrays non-negative throughout

**G25d — exclude_from_plan:**
- `exclude_from_plan: true` → SS income = 0, ordinary_other ≈ 0 in SS-active years
- Taxes ≤ same profile with SS included (no SS income = lower bracket)

**G25e — Manual ordinary_other preservation:**
- When user manually sets `ordinary_other` AND has SS block: manual entry preserved
- SS injection only overrides years where ordinary_other = 0

---

### G26 — Excess Income Policy (12 checks)

**What it tests:** The excess income policy system — income from `income.json` sources offsetting portfolio withdrawals, and surplus routing to brokerage.

**Architecture:** Surplus is injected into `deposits_yearly` **before** `simulate_balances` so it compounds correctly through the year-by-year growth model. Post-simulation injection was tried first but deposits don't compound — only pre-simulation injection via `deposits_yearly` is architecturally correct.

**G26a — misc income loading:**
- `misc` type with years spec → correct values at correct year indices
- `misc_taxable=0.0` for rows with `"taxable": false`
- `misc_taxable=1.0` for rows without explicit taxable (default)
- Year 5 taxable bonus: misc[4] = $50K, misc_taxable[4] = 1.0
- Years 10-12 non-taxable gift: misc[9] = $17K, misc_taxable[9] = 0.0
- Year 15 taxable inheritance: misc[14] = $100K, misc_taxable[14] = 1.0

**G26b — Income offset reduces portfolio withdrawal:**
- $200K W2 income, $150K target → net W2 at 30% tax ≈ $140K → portfolio draws only shortfall
- `realized_current_mean` with W2 < `realized_current_mean` without W2

**G26c — Surplus deposits compound in portfolio:**
- $500K W2, $150K target → $200K/yr surplus → injected into brokerage deposits
- Portfolio (current_median) higher with surplus vs no-income baseline
- Withdrawal floor (`base_k=100K`) still enforced — floor is not waived by income offset

**G26d — Non-taxable misc excluded from tax engine:**
- Taxable misc ($50K) → higher federal tax than non-taxable misc ($50K)
- Non-taxable misc: goes through surplus routing but not `ordinary_income_cur_paths`

---

### G27 — IRA/Roth Contribution Rules (13 checks)

**What it tests:** `_apply_ira_contribution_rules()` in `api.py` — IRS contribution eligibility enforcement. All tests call the function directly (unit tests, no simulation needed).

**IRS Rules Enforced:**
1. **Earned income requirement:** W2 > 0 required for any IRA/Roth contribution
2. **Annual limit:** min(W2, $7,000 under-50 | $8,000 age 50+) per account
3. **Roth MAGI phase-out:** MFJ $236K–$246K linear reduction; Single $150K–$165K
4. **TRAD IRA:** no income phase-out (contribution always permitted at any income)

| Check | Scenario | Expected |
|-------|---------|---------|
| 27a | Roth, W2=0 | Deposit → $0 (no earned income) |
| 27b | TRAD, W2=0 | Deposit → $0 (same rule) |
| 27c | Roth, W2=$50K, age 45, deposit=$5K | $5K allowed (under cap) |
| 27d | Roth, W2=$50K, age 45, deposit=$20K | Clamped to $7K (under-50 cap) |
| 27e | Roth, W2=$50K, age 50, deposit=$20K | Clamped to $8K (50+ catch-up) |
| 27f | Roth, W2=$3K, age 45, deposit=$7K | Clamped to $3K (W2 < limit) |
| 27g | Roth, MAGI=$300K MFJ | → $0 (above $246K ceiling) |
| 27h | Roth, MAGI=$241K MFJ (midpoint) | Partial reduction ≈50%, 2500<x<5000 |
| 27i | TRAD, W2=$500K | $7K allowed (no income phase-out) |
| 27j | Brokerage, W2=0 | $50K untouched (IRS rules don't apply) |
| 27k | Roth Single, MAGI=$170K | → $0 (above $165K single ceiling) |
| 27k | Roth Single, MAGI=$100K | $7K allowed (below $150K single floor) |

**All enforcement is silent** — deposits clamped/zeroed with `logging.INFO` only, no exceptions raised.

---

## Manifest and File Tracking

The manifest system (`manifest.lock`) tracks SHA-256 hashes of all files Claude provides. It enforces that the server is always running the same code that the tests expect.

### Tracked Files

**Python backend:** `api.py`, `loaders.py`, `simulator_new.py`, `snapshot.py`, `roth_optimizer.py`, `taxes_core.py`, `test_flags.py`

**UI:** `ui/src/App.tsx`, `ui/tests/smoke.spec.ts`, `ui/tests/global-setup.ts`, `ui/tests/global-teardown.ts`, `ui/playwright.config.ts`

**Profile configs (default/ only):** `profiles/default/person.json`, `withdrawal_schedule.json`, `income.json`, `allocation_yearly.json`, `inflation_yearly.json`, `shocks_yearly.json`, `economic.json`

### Rules
- **Only `profiles/default/`** is tracked — user profiles are user data, not deployable artifacts
- `__system__*` and `__testui__` are generated by `--reset-system-profiles` — never tracked
- Runtime assert in `api.py` prevents non-default profile paths from ever entering `MANIFEST_FILES`
- Startup verification skips non-default profile entries from stale manifest.lock files

---

## Known Coverage Gaps

These are intentionally out of scope for this harness (require `api.py` pre-processing path or integration test setup):

| Gap | Reason |
|-----|--------|
| `economicglobal.json` `cash_reserve.months` | Requires full HTTP API path |
| `rebalancing.brokerage_capgain_limit_k` | Cap gain limit is advisory in current implementation |
| `rebalancing.suppress_in_bad_market` | Covered indirectly by G23 but not isolated |
| `shock_scaling_enabled` global toggle | Covered by G23 behaviour tests |
| W2 income end-to-end through `build_income_streams` | Income core pipeline; AMT wired at `compute_annual_taxes_paths` level (G11s) |
| SS `self_start_age` gating in simulator | SS income currently appears from year 1 regardless of start age — fix pending |
| IRMAA as real cash outflow | Currently advisory only |
| Cost basis tracking | Phase 3 grand plan item |

---

## Test Execution Times (paths=200)

| Group | Time | Checks |
|-------|------|--------|
| G1 | ~0.9s | 34 |
| G2 | ~0.5s | 11 |
| G3 | ~1.1s | 15 |
| G4 | ~0.9s | 26 |
| G5 | ~0.4s | 5 |
| G6 | ~0.5s | 27 |
| G7 | ~0.4s | 8 |
| G8 | ~2.6s | 59 |
| G9 | ~0.8s | 9 |
| G10 | ~0.3s | 5 |
| G11 | ~1.3s | 46 |
| G12 | ~0.3s | 26 |
| G13 | ~0.4s | 42 |
| G14 | ~0.1s | 15 |
| G15 | ~0.0s | 23 |
| G16 | ~0.2s | 28 |
| G17 | ~0.1s | 45 |
| G18 | ~0.1s | 22 |
| G19 | ~52s | 3 + 59 browser |
| G20 | ~0.0s | 24 |
| G21 | ~0.0s | 7 |
| G22 | ~0.0s | 55 |
| G23 | ~0.2s | 10 |
| G24 | ~0.1s | 5 |
| G25 | ~0.4s | 17 |
| G26 | ~0.6s | 12 |
| G27 | ~0.0s | 13 |
| **Total** | **~65s** | **592 + 59** |

`--skip-playwright` reduces total to ~13s. `--fast` (50 paths) reduces to ~25s including Playwright.
