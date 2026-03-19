# eNDinomics — Session State v2.0
## As of March 19, 2026 | Sessions 1-21

---

## Repository
- **Repo:** https://github.com/nandi-github/c-eNDinomics
- **Local:** `/Volumes/My Shared Files/workspace/research/c-eNDinomics/`
  - (symlinked via `/Users/satish/workspace -> /Volumes/My Shared Files/workspace`)
- **Last commit:** `c1bf8eb` — "fix: restore G1 flag matrix to GROUPS list (424/424 passing)"
- **Branch:** main, clean working tree (origin/main = local HEAD)

---

## Test State
```
Python:     424/424 passing  (21 groups, G1–G21)
Playwright: 16/16 passing
```

**Run commands:**
```bash
cd root/src
python3 -B test_flags.py --comprehensive-test --skip-playwright

cd root/src/ui
npx playwright test
```

### Test Groups
| Group | Name | Checks |
|---|---|---|
| G1 | Ignore-flag matrix (8 combos + ignore_taxes) | 33 |
| G2 | RMD schedule | 11 |
| G3 | Roth conversion policy | 15 |
| G4 | Income | 18 |
| G5 | Inflation | 5 |
| G6 | Withdrawal | 8 |
| G7 | Allocation | 8 |
| G8 | Shocks | 59 |
| G9 | Ages | 9 |
| G10 | Rebalancing | 5 |
| G11 | Tax wiring + bracket math | 37 |
| G12 | Roth conversion tax | 26 |
| G13 | YoY sanity | 33 |
| G14 | Cashflow verification | 15 |
| G15 | Insights engine | 23 |
| G16 | Dynamic simulation years | 28 |
| G17 | UI data integrity (includes G17j — mode fields) | 38 |
| G18 | Snapshot regression | 22 |
| G19 | Playwright (16 smoke tests) | 1 |
| G20 | Portfolio analysis + look-through | 24 |
| G21 | Asset weight sanity + CAGR plausibility | 7 |

---

## Asset Model
- **Version:** v1.3.0 (promoted 2026-03-17)
- **File:** `src/config/assets.json`
- **25 tickers:** AAPL, AMZN, BND, DBC, EEM, EFA, GLD, IAU, IEF, LQD, MSFT, NVDA, PDBC, QQQ, SCHP, SPY, TIP, TLT, VTI, VTV, VUG, VXUS, XLE, XLF, XLK
- **CAPE adjustment:** CAPE=35.0 → VTI 11.1%→9.4%, QQQ 15.1%→11.9%, NVDA 22%→15.2%

---

## What Was Built — Sessions 1–19 (Carried Forward)

### Core Simulation Engine
- `simulation_core.py` — CRITICAL BUG FIXED (asset weight = pf × cls × ticker)
- `simulator_new.py` — Monte Carlo, withdrawals, RMDs, Roth conversions, taxes
- `taxes_core.py` — Federal/state/NIIT brackets
- `rmd_core.py` — SECURE 2.0 RMD schedule
- `roth_conversion_core.py` — bracket-fill conversions

### Market Data Layer
- Full provider stack: yfinance, iShares CSV, Vanguard JSON, SPDR xlsx, QQQ screener
- 16/21 ETFs with holdings look-through (SCHP 403 blocked — only gap)
- `refresh_model.sh` — single command full pipeline

### Portfolio Analysis
- `portfolio_analysis.py` — ETF look-through, true stock exposure, sector breakdown
- Filters bond ISINs and non-equity ETFs

---

## What Was Built — Session 20

### Tab Rename + Investment Tab
- Run tab renamed → **Simulation**
- **Investment** tab added (Phase 1 placeholder)
- Tab order: Configure | Simulation | Investment | Results

### Simulation Mode Transformer
- `compute_mode_weights(current_age, retirement_age, simulation_mode)` in `simulator_new.py`
- Glide path for "automatic"; hard values for investment/retirement/balanced
- `res["summary"]` gets: `simulation_mode`, `investment_weight`, `retirement_weight`, `primary_metric`, `composite_score`
- GBM math unchanged

### Roth Optimizer Phase 1
- `src/roth_optimizer.py` — bracket-fill with IRMAA/NIIT guards
- **Not yet called from api.py** — output not in snapshot
- Phase 1 only; BETR 2-pass rewrite planned for S22

### api.py Fixes
- `simulation_mode` extracted from UI payload, injected into `person_cfg`
- Stored in `run_info.flags.simulation_mode`

### Grand Plan v1.5
- Section 10 build status updated

---

## What Was Built — Session 21

### Simulation Mode Behavioral Wiring (`simulator_new.py`)
- **Retirement-first**: success measured vs full planned withdrawal (strict)
- **Investment-first**: success measured vs spending floor `_sched_base` only (lenient)
- `floor_success_rate` always computed for UI comparison
- `success_rate_label` tells UI which bar was used
- Bug fix: `'_sched_base' in dir()` → `'_sched_base' in locals()`
- `drawdown_by_year_p50/p90` per-year arrays exported to summary

### Summary Table Mode-Aware (`App.tsx`)
- Objective badge row: mode icon + composite score
- Success rate row: dynamic label + tooltip by mode
- Floor-only rate as secondary indented row in retirement mode
- CAGR rows bold in investment mode; drawdown rows bold+red in retirement

### Portfolio Projection — CAPE Scenario Bands (`App.tsx`)
- Placed immediately after Summary (always visible, no collapse)
- Blue shaded fan = middle 80% of paths (floor–ceiling)
- 4 scenario lines: Optimistic 10%, Base (sim median), Conservative 6%, Pessimistic 4%
- Right-side legend with ending values per scenario

### Drawdown Over Time Chart — Mode-Aware (`App.tsx`)
- Retirement: pink sequence risk zone (yrs 1–10), severity badge (LOW/MODERATE/HIGH), callout box
- Investment: clean chart, no zone shading
- Chart flipped: 0% at top, dips downward (correct financial convention)
- Footer text explains mode-specific interpretation

### P10/P90/P50 Renamed Throughout UI
| Old | New |
|---|---|
| Floor balance (P10) | Floor balance |
| Ceiling balance (P90) | Ceiling balance |
| P10 (stress) | Stress floor |
| P90 (upside) | Upside ceiling |
| Stress (P90) | Stress |
| Median (P50) | Typical (median) |
| P10–P90 fan | middle 80% of simulation paths |

### Test Suite
- **G1 restored**: `group1_flag_matrix` added to GROUPS list (was defined but never registered, +33 checks)
- **G17j**: 13 new checks for simulation_mode, investment_weight, retirement_weight, composite_score, floor_success_rate, success_rate_label, drawdown_by_year arrays
- **smoke.spec.ts**: test 3 dynamic label matching, test 11 timeout extended to 60s, Investment tab assertion, Objective row assertion

### Grand Plan v1.6
- New Section 4a: Multi-Generational Tax Planning
- Section 10: fully updated build status (424/424, S20–S21 items)
- Section 11: Principle 9 (multi-generational tax)
- Section 12: file map updated

---

## Key Numbers (Test Profile, v1.3.0)
```
Starting portfolio:     $9.92M
  BROKERAGE:            $750K
  TRAD_IRA:             $4.8M  ← RMD timebomb, severity: CRITICAL
  ROTH:                 $370K

Simulation mode:        Automatic (investment_w=0.85 at age 46, retirement 65)
Investment YoY nominal: 7.36% median  (7.39% mean)
Investment YoY real:    5.02% median
Success rate:           100% (floor bar, investment_w=0.85)
CAPE:                   35.0 → VTI mu adjusted 11.1%→9.4%

49yr projections (current USD, median):
  BROKERAGE:            ~$7.9M
  TRAD_IRA:             ~$44.9M  ← BETR urgent: 37% lock-in at RMD start
  ROTH:                 ~$13.1M
  Total:                ~$65.9M

Tax rate at RMD start (yr30): 36.8%
Projected RMD year 1 (age 73): ~$850K+ ← severity CRITICAL confirmed
```

---

## Known Issues / Technical Debt
1. **SCHP holdings** — Schwab 403 blocked, uses prior. Similar index to TIP (acceptable)
2. **market_data module** — not on Python path when API runs from `src/`. Non-blocking.
3. **Simulation mode GBM** — modes produce different success rates (floor vs full-plan bar) but GBM math is identical across modes. Behavioral differentiation beyond success measurement is a future enhancement.
4. **Investment YoY metric** — includes RMD reinvestment, not pure asset return. Backlog item.
5. **CAPE scenario band rates** — hardcoded (10%/6%/4%). Should read from `cape_config.json` dynamically.
6. **roth_optimizer.py** — Phase 1 only (bracket-fill). Not yet called from api.py. Full BETR rewrite in S22.

---

## Architecture Decisions (Locked)
1. One tool, not two apps — simulation modes on shared engine
2. Investment tab is separate from simulation mode — different time horizon, different engine
3. GBM math identical across modes — only success measurement and display change
4. `api.py` is the injection point for UI-selected simulation_mode into person_cfg
5. `floor_success_rate` always computed regardless of mode for UI comparison
6. Per-year drawdown arrays computed from `dd_each` — no extra math
7. Tax optimization is multi-generational — survivor cliff, 10-year heir rule, BETR 2-pass

---

## How to Start the Server
```bash
cd root/src
./vcleanbld_ui    # builds UI + starts uvicorn on :8000
# OR restart without rebuilding:
python -m uvicorn api:app --reload
```

---

## File Locations (Key Files)
```
root/
  src/
    api.py                    ← FastAPI server + simulation_mode injection
    simulator_new.py          ← Monte Carlo orchestrator + compute_mode_weights()
    simulation_core.py        ← Core GBM engine (bug fixed)
    roth_optimizer.py         ← Phase 1 bracket-fill (BETR rewrite S22)
    asset_calibration.py      ← Multi-window + CAPE calibration
    promote_model.py          ← Validation gate
    portfolio_analysis.py     ← Look-through analysis
    test_flags.py             ← 424 checks, G1–G21
    config/
      assets.json             ← Active asset model v1.3.0
    profiles/
      Test/                   ← Test profile (all tests use this)
      default/                ← Default profile
    ui/
      src/App.tsx             ← Full UI (4 tabs)
      tests/smoke.spec.ts     ← 16 Playwright tests
  asset-model/
    cape_config.json          ← CAPE=35.0 config
    promotion_log.json        ← Audit trail
  market_data/               ← Market data package
  refresh_model.sh            ← Full pipeline
  eNDinomics_GrandPlan_v1_6.docx  ← Living design document (current)
  NEXT_SESSION_v2_0.md        ← This session's build plan
  SESSION_STATE_v2_0.md       ← This file
```

*Version 2.0 | March 19, 2026 | Sessions 1–21 complete*
*Next version: update after session 22*
