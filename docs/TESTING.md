# eNDinomics Testing Guide

## Overview

The test suite has two layers that work together:

| Layer | File | What it tests | Runtime |
|-------|------|--------------|---------|
| Python functional | `src/test_flags.py` | Simulator math, taxes, RMDs, conversions, data integrity | ~12s |
| Playwright UI | `src/ui/tests/smoke.spec.ts` | Browser rendering, table columns, no NaN, rate guards | ~45s |

Both layers run together with one command when the API server is up.

---

## Quick Reference

```bash
# Full suite (Python + UI) — server must be running
cd root/src && python3 -B test_flags.py --comprehensive-test

# Python only (no server needed)
cd root/src && python3 -B test_flags.py --comprehensive-test --skip-playwright

# UI only (Playwright directly)
cd root/src/ui && npx playwright test

# UI only with visible browser (debug)
cd root/src/ui && npx playwright test --headed

# View last Playwright HTML report
cd root/src/ui && npx playwright show-report
```

---

## First-Time Setup (Playwright)

Run once after cloning or on a new machine:

```bash
cd root/src/ui
npm install                      # picks up @playwright/test from package.json
npx playwright install chromium  # downloads Chromium browser (~170MB)
```

Or use the wrapper script which handles everything:

```bash
cd root/src
chmod +x run-ui-tests.sh
./run-ui-tests.sh --install      # one-time browser install
./run-ui-tests.sh                # run tests (starts/stops server automatically)
```

---

## Python Test Groups (G1–G19)

| Group | Name | What it covers |
|-------|------|---------------|
| G1 | Flag matrix | All ignore_* flags: withdrawals, RMDs, conversions |
| G2 | RMDs | SECURE 2.0 start ages, per-birth-year factors, schedule |
| G3 | Conversion policy | Bracket fill, window years, NIIT avoidance |
| G4 | Income | W2, rental, interest, cap gains stacking |
| G5 | Inflation | Rate schedules, real vs nominal conversion |
| G6 | Withdrawal | Schedule, floor, shortfall detection |
| G7 | Allocation | Per-account, per-year, override periods |
| G8 | Shocks | All preset levels, co-impact, augment vs override |
| G9 | Ages | Current age, birth year, `current_age="compute"` |
| G10 | Rebalancing | Drift detection, brokerage cap gains, IRA free rebal |
| G11 | Tax wiring | Federal/state/NIIT correct flow, standard deductions |
| G12 | Conversion tax | Bracket fill math, tax cost debit from brokerage |
| G13 | YoY sanity | Geometric CAGR, real vs nominal gap, shock visible |
| G14 | Cashflow verification | Balances move correctly when withdrawals/RMDs applied |
| G15 | Insights engine | All insight trigger thresholds (drawdown, RMD cliff, NIIT) |
| G16 | Dynamic sim years | n_years from target_age, 10–60 year clamp |
| G17 | UI data integrity | All median-path fields present, eff rate ≤ 100%, spending invariant |
| G18 | Snapshot regression | ~25 key numbers vs saved baseline (5% tolerance) |
| G19 | Playwright UI | Browser: column counts, no NaN, rate guard, chart load |

---

## What G17 and G19 Guard Against (UI Regressions)

These two groups exist because UI bugs are easy to miss in code review:

**G17 (Python-side UI integrity):**
- All median-path fields present in snapshot JSON
- `total_ordinary_income_median_path` includes cap gains (prevents eff rate > 100%)
- `total_withdraw_future_median_path` > 0 in RMD years (prevents zero "For spending future $")
- Tax components sum correctly, no negative values

**G19 (Playwright browser tests):**
- Every table renders with the exact expected column count
- Every table has exactly 49 rows (for Test profile, target_age=95)
- No cell contains literal text "NaN", "undefined", or "null"
- Effective tax rate column never shows > 100% in any year
- "For spending future $" > 0 in all RMD years (year 30+)
- All 6 accounts load correctly in the Accounts YoY table
- Chart PNG images load without 404

---

## When Tests Run

**Always run before committing:**
```bash
cd root/src && python3 -B test_flags.py --comprehensive-test
```
If the server is running, G19 runs automatically. If not, it skips with a note.

**After any change to:**
- `simulator_new.py`, `taxes_core.py`, `roth_conversion_core.py`, `rmd_core.py` → G1–G16 catch regressions
- `snapshot.py`, `api.py` → G18 catches regressions
- `App.tsx`, `styles.css` → G19 catches rendering regressions
- `reporting.py` → currently manual only (chart output not yet tested by automation)

---

## Updating the Regression Baseline (G18)

G18 compares ~25 key numbers against a saved baseline. After an intentional change that shifts numbers:

```bash
cd root/src && python3 -B test_flags.py --comprehensive-test --update-baseline
```

This clears the old baseline. The next run regenerates it from the current output.

---

## Skipping Playwright in CI

For environments without a browser (pure Python CI, Docker without X11):

```bash
python3 -B test_flags.py --comprehensive-test --skip-playwright
```

G19 is also auto-skipped if the server is not reachable on `:8000` — it won't fail the run.

---

## File Locations

```
root/src/
  test_flags.py              ← Python test suite (G1–G19)
  run-ui-tests.sh            ← wrapper: starts server, runs Playwright, stops server
  ui/
    playwright.config.ts     ← Playwright config (baseURL, timeouts, reporters)
    package.json             ← includes @playwright/test devDependency
    tests/
      smoke.spec.ts          ← 14 Playwright UI tests
    playwright-report/       ← HTML report (git-ignored)
    test-results/            ← screenshots/videos on failure (git-ignored)
```

---

## Interpreting Failures

**G17 failure:** A field is missing from the snapshot JSON or a calculation invariant broke in Python. Check `simulator_new.py` or `snapshot.py`.

**G19 failure:** The UI rendered something wrong. Check `App.tsx`. Playwright saves a screenshot and video for every failed test — open the HTML report:
```bash
cd root/src/ui && npx playwright show-report
```

**G18 failure:** A number shifted more than 5% from baseline. Either a genuine regression or an intentional change — use `--update-baseline` if intentional.
