# eNDinomics Session State — v3.0
_Updated: session 23 complete (2026-03-20)_

## Repository
- **Repo:** https://github.com/nandi-github/c-eNDinomics
- **Local:** `/Volumes/My Shared Files/workspace/research/c-eNDinomics/`
- **Branch:** main, clean working tree
- **Latest commits:**
  - `832b897` — feat: session 22 — Roth optimizer BETR, age-based withdrawals, Help panel
  - `bb53c17` — fix: rmd.json no longer recreated per-profile; default person.json updated
  - `(pending)` — feat: session 23 — Roth Insights UX, CAPE live, Option C, test fixes

## Test State (End of Session 23)
- **Python:** 495/495 (22 groups, G1–G22) ✅
- **Playwright:** 16/16 ✅

## Architecture Decisions (Locked)
1. GBM math identical across simulation modes — only success measurement changes
2. `api.py` is the injection point for UI-selected simulation_mode into person_cfg
3. `floor_success_rate` always computed regardless of mode
4. Per-year drawdown arrays computed from `dd_each`
5. Tax optimization: survivor cliff + 10yr heir rule + BETR 2-pass
6. Four named strategies (conservative/balanced/aggressive/maximum)
7. IRMAA guard at age 63 (2yr Medicare lookback)
8. Age-based withdrawal schedule: exclusive non-overlapping ranges
9. `rmd.json` is shared common file at `src/config/rmd.json` — not per-profile
10. `/roth-optimize` endpoint: standalone, uses snapshot projected balances if run_id provided
11. Withdrawal schedule: age-based format is official (`"ages": "47-64"`). Year-based tolerated.
12. CAPE scenario bands: rates computed live from `cape_config.json` at startup
13. Roth Conversion Insights section: collapsed by default, expands on click

## Key Files Changed (Session 23)
```
src/api.py              ← /roth-optimize endpoint; CAPE template whitelist
src/ui/src/App.tsx      ← Roth Conversion Insights (renamed, collapsible, default collapsed)
                           Current Situation + Recommendation subsections
                           Apply [strategy] to profile button (contextual label)
                           Option C — Investment tab persistent Roth panel
                           CAPE live wiring from cape_config.json
                           Help panel: tax_payment_source docs + cape_config.json download
src/ui/tests/smoke.spec.ts ← Tab "Run"→"Simulation" fix; survival rate label variants;
                              Insights selector fix (strict mode violation)
SESSION_STATE_v3_0.md
NEXT_SESSION_v3_0.md
```

## Key Numbers (Test Profile)
```
Starting portfolio:     $9.92M (BROKERAGE $750K, TRAD_IRA $4.8M, ROTH $370K)
current_age:            46 (birth_year 1980, computed)
retirement_age:         65
target_age:             95 (49 simulation years)
Investment YoY nominal: ~7.0% median (CAPE 35 adjusted)
Roth optimizer:         SEVERE/CRITICAL (projected RMD $439-526K/yr at age 75)
Recommended strategy:   Aggressive (32%), BETR ~37-40%, current rate 22%
Heir savings (high):    ~$649K
CAPE live:              35.0 → Conservative 6.4%, Optimistic 9.4%, Pessimistic 3.9%
```

## Roth Conversion Insights UX (Session 23)
```
Results tab — collapsed by default:
  ▶ Roth Conversion Insights  [CRITICAL]  ★ Aggressive · $383K/yr · click to expand

Expanded:
  ┌─ Current Situation ─────────────────────────────────┐
  │  TRAD IRA at 75: $12.9M → Forced RMD: $526K/yr     │
  │  ⚠ timebomb CRITICAL, ⚠ heir risk, ✓ 29yr window   │
  └─────────────────────────────────────────────────────┘
  ┌─ ★ Recommendation — Aggressive (32%) ───────────────┐
  │  $383K/yr · $99K tax · +$534K self · +$649K heir   │
  │  Why: ... Why not others: ↳ Conservative leaves...  │
  │  [ Apply Aggressive (32%) to profile ]               │
  └─────────────────────────────────────────────────────┘
  Lifetime Tax Savings 4×4 table
  ▶ Year-by-Year Schedule
  Source note
```

## Test Group Summary (495 checks)
| Group | Checks | Coverage |
|---|---|---|
| G1 | 34 | Ignore-flag matrix — BROK check uses realized withdrawals |
| G2–G5 | 39 | RMD, conversion, income, inflation |
| G6 | 27 | Withdrawal schedule (step-up, floor, age-based + validation) |
| G7–G16 | 113 | Allocation, shocks, ages, rebalancing, tax, YoY, cashflow, insights, dynamic years |
| G17 | 38 | UI data integrity |
| G18 | 22 | Snapshot regression |
| G19 | 1 | Playwright (16 smoke tests) |
| G20–G21 | 31 | Portfolio analysis, asset weight sanity |
| G22 | 50 | Roth optimizer (BETR, severity, bracket math, income ranges) |

## Pending for Session 23b
- Profile versioning (Option B in session 23 plan)
- Playwright tests for Roth Insights UI (Test 17, 18)
- income.json realistic W2/SS modeling
