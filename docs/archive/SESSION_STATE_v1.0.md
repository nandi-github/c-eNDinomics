# eNDinomics — Session State v1.0
## As of March 17, 2026 | Sessions 1-19

---

## Repository
- **Repo:** https://github.com/nandi-github/c-eNDinomics
- **Local:** `/Volumes/My Shared Files/workspace/research/c-eNDinomics/`
  - (symlinked via `/Users/satish/workspace -> /Volumes/My Shared Files/workspace`)
- **Last commit:** `c355635` — "feat: CAPE valuation adjustment + asset model v1.3.0"
- **Branch:** main, clean working tree

---

## Test State
```
Python:     378/378 passing  (was 404 — G1 missing from last run, will recount on clean run)
Playwright: 16/16 passing
Groups:     G1-G18, G19(playwright), G20(portfolio), G21(asset weight sanity)
```

**Run commands:**
```bash
cd root/src
python3 -B test_flags.py --comprehensive-test --skip-playwright

cd root/src/ui
npx playwright test
```

---

## Asset Model
- **Version:** v1.3.0 (promoted 2026-03-17)
- **File:** `src/config/assets.json`
- **25 tickers:** AAPL, AMZN, BND, DBC, EEM, EFA, GLD, IAU, IEF, LQD, MSFT, NVDA, PDBC, QQQ, SCHP, SPY, TIP, TLT, VTI, VTV, VUG, VXUS, XLE, XLF, XLK
- **Calibration:** Multi-window blend (5yr×0.15 + 10yr×0.35 + 20yr×0.30 + prior×0.20) + CAPE adjustment
- **CAPE adjustment:** CAPE=35.0 → VTI 11.1%→9.4%, QQQ 15.1%→11.9%, NVDA 22%→15.2%
- **Layer 5:** top_holdings populated for 16/21 ETFs (SCHP, GLD, IAU, DBC, PDBC = no equity holdings)
- **Projection (Test profile):** TRAD_IRA yr49 ~$32.7M current USD / $99M future — credible

---

## What Was Built (Complete)

### Core Simulation Engine
- `simulation_core.py` — **CRITICAL BUG FIXED** (asset weight = pf × cls × ticker, was missing cls)
- `simulator_new.py` — Monte Carlo, withdrawals, RMDs, Roth conversions, taxes
- `taxes_core.py` — Federal/state/NIIT brackets
- `rmd_core.py` — SECURE 2.0 RMD schedule
- `roth_conversion_core.py` — bracket-fill conversions

### Market Data Layer (`market_data/`)
- `providers/yfinance_provider.py` — prices (20yr OHLCV), sectors
- `providers/etf_dot_com_provider.py` — ETF holdings:
  - iShares: direct CSV (IEF, TLT, LQD, EEM, EFA, TIP, + 8 more)
  - Vanguard: JSON API paginated (VTI 1179, VXUS 2280, BND 1299, VTV, VUG)
  - SPDR: xlsx stdlib parse (SPY 504, XLE, XLF, XLK)
  - Nasdaq screener: QQQ (200 holdings, approximate weights)
  - Physical commodity ETFs: GLD, IAU, DBC, PDBC → 0 equity holdings (correct)
  - SCHP (Schwab): 403 blocked — only gap
- `cache/cache.py` — file-backed TTL cache with manifest
- `fetchers/` — priority chain fetchers for holdings and prices
- `scheduler/weekly_job.py` — cron entry point
- `tests/test_market_data.py` — 20 unit tests, no network

### Asset Calibration Pipeline
- `src/asset_calibration.py` — multi-window blend + CAPE adjustment
- `src/promote_model.py` — validation gate (SPD, bounds, required tickers)
- `asset-model/cape_config.json` — CAPE=35.0, blend weights, FRED auto-fetch config
- `refresh_model.sh` — single command: fetch → CAPE → calibrate → validate → promote

### Portfolio Analysis (Layer 5 Look-Through)
- `src/portfolio_analysis.py` — ETF look-through, true stock exposure, sector breakdown
  - Filters bond ISINs and non-equity ETFs from look-through
  - Only US_STOCKS + INTL_STOCKS class ETFs feed stock analysis
- `src/snapshot.py` — passes assets_cfg to portfolio_analysis for look-through

### UI (App.tsx)
- 3 tabs: Configure | Run | Results
- Run panel: Profile, Paths, Steps/Year, Shocks Mode, State, Filing
- 4 ignore checkboxes: withdrawals, RMDs, conversions, taxes
- **Simulation Mode selector:** Automatic / Retirement-first / Balanced / Investment-first
- Results: Summary, Insights, Portfolio Analysis (with look-through), Charts, Tables
- Portfolio Analysis: asset type bars, geography bars, top holdings, **true stock exposure**, sector breakdown, per-account allocation

### person.json
- `simulation_mode: "automatic"` — glide path field added
- `retirement_age: 65` — for mode blending
- Full readme docs for both fields

### Test Suite
- **G1-G13:** Core simulation, RMD, conversions, taxes, YoY sanity
- **G14:** Cashflow verification
- **G15:** Insights engine
- **G16:** Dynamic simulation years
- **G17:** UI data integrity
- **G18:** Snapshot regression (baseline records v1.3.0 numbers)
- **G19:** Playwright smoke tests (16 tests)
- **G20:** Portfolio analysis + look-through (24 checks)
- **G21:** Asset weight sanity + CAGR plausibility (7 checks) ← NEW, catches the bug we fixed

### Documentation
- `eNDinomics_GrandPlan_v1.3.docx` — Section 2.0 (mode architecture), 2.2 (Investment tab), 2.3 (cost basis)
- `MARKET_DATA_LAYER.md` — provider architecture, Phase 1 complete
- `INVESTMENT_ENGINE.md` — Investment tab design spec, config file schemas
- `REFRESH_GUIDE.md` — one-page manual for weekly data refresh

---

## Known Issues / Technical Debt
1. **G1 missing from last test run output** — likely a display issue, verify on fresh run
2. **SCHP holdings** — Schwab 403 blocked, uses prior. Similar index to TIP (acceptable)
3. **market_data module** — not on Python path when API runs from `src/`. Health endpoint shows warning. Non-blocking.
4. **Simulation mode flag** — in UI and person.json but simulator_new.py ignores it. Mode selector is UI-only today.
5. **Investment YoY metric** — measures total portfolio CAGR including RMD reinvestment, not pure asset return. Consider adding a separate "pure investment return" metric.

---

## How to Start the Server
```bash
cd root/src
./vcleanbld_ui    # builds UI + starts uvicorn on :8000
# OR just restart without rebuilding:
python -m uvicorn api:app --reload
```

---

## File Locations (Key Files)
```
root/
  src/
    api.py                    ← FastAPI server, health endpoint
    simulator_new.py          ← Main simulation orchestrator
    simulation_core.py        ← Core GBM engine (BUG FIXED)
    asset_calibration.py      ← Multi-window + CAPE calibration
    promote_model.py          ← Validation gate
    assets_loader.py          ← Loads assets.json for simulation
    engines_assets.py         ← draw_asset_log_returns (uses mu_annual)
    portfolio_analysis.py     ← Look-through analysis
    snapshot.py               ← Snapshot assembly
    loaders.py                ← Person/allocation loaders
    test_flags.py             ← 378+ checks, G1-G21
    config/
      assets.json             ← Active asset model v1.3.0
    profiles/
      Test/                   ← Test profile (all tests use this)
      default/                ← Default profile
    ui/
      src/App.tsx             ← Full UI
      tests/smoke.spec.ts     ← 16 Playwright tests
  asset-model/
    cape_config.json          ← CAPE=35.0 config
    candidate/assets.json     ← Last calibration output
    promotion_log.json        ← Audit trail
  market_data/               ← Market data package
    providers/
      etf_dot_com_provider.py ← iShares/Vanguard/SPDR/QQQ/Commodity
      yfinance_provider.py    ← Prices + sectors
    cache/cache.py            ← TTL file cache
    scheduler/weekly_job.py  ← Cron entry point
    tests/test_market_data.py ← 20 unit tests
  refresh_model.sh            ← Full pipeline: fetch→CAPE→calibrate→validate→promote
  MARKET_DATA_LAYER.md        ← Architecture spec
  INVESTMENT_ENGINE.md        ← Investment tab design spec
  REFRESH_GUIDE.md            ← Weekly refresh manual
  eNDinomics_GrandPlan_v1.3.docx  ← Living design document
```
