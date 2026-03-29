# eNDinomics — Grand Plan
**Version 2.0 | Updated 2026-03-29**  
**Status: Active development — v6.5 shipped**

---

## Vision

Most retirement calculators give you a number. eNDinomics gives you the math behind the number — all of it, running simultaneously, with Monte Carlo uncertainty on top. The goal is a full life planning platform that covers every phase from first paycheck to estate planning, modeled with the same rigor a quantitative analyst would apply.

The tool is built for people who want to understand their retirement math, not just get a result.

---

## The Three Models

eNDinomics is structured around three distinct but connected engines. They share the same asset model and market data layer but answer fundamentally different questions.

### Model 1 — Financial Engine
**Question:** What is my wealth trajectory?  
**Time horizon:** 30–50 years  
**Engine:** Monte Carlo (GBM, 200 paths)  
**Output:** Portfolio projections with probability bands, tax drag, inflation-adjusted balances

The foundation. Everything else is built on top of this. It models:
- All account types: brokerage, TRAD IRA, Roth IRA, 401K, after-tax
- Asset allocation with portfolio buckets and asset class weights
- Annual deposits, withdrawals, RMDs, Roth conversions
- Federal + state taxes, NIIT, IRMAA, Additional Medicare Tax
- Market shocks (scripted drawdown events layered on stochastic returns)
- Inflation-adjusted real vs nominal tracking

### Model 2 — Retirement Planner
**Question:** How do I draw down safely?  
**Time horizon:** Now → assumed death age  
**Engine:** Simulation tab with four modes  
**Output:** Withdrawal schedule, survival probability, sequence risk analysis, Roth optimization

Sits on top of Model 1. Adds:
- **Four simulation modes:** Automatic (phase-aware glide path) / Retirement-first (survival priority) / Investment-first (growth priority) / Balanced (50/50)
- **Lifecycle phases:** Accumulation → Transition → Distribution → RMD — inferred from actual income and spending, not from a hardcoded retirement age
- **W2 Surplus Waterfall:** Routes surplus income through IRS-limited buckets (401K → Roth → backdoor → brokerage) rather than dumping everything to brokerage
- **Roth Conversion Optimizer:** BETR analysis, multi-scenario (self/survivor/heir), IRMAA-aware
- **Sequence-of-returns risk:** Drawdown charts, bad-market withdrawal sequencing, floor survival rate
- **RMD forecasting:** Per IRS uniform lifetime tables, reinvestment policy, timebomb severity

### Model 3 — Investment Assistant
**Question:** What should I do Monday?  
**Time horizon:** This week / this quarter  
**Engine:** Regime detection + signal analysis (see `INVESTMENT_ENGINE.md`)  
**Output:** Ordered action list with rationale

Not a simulator — a decision assistant. Reads:
- Market regime signals (CAPE ratio, CMF, Wyckoff phase, OBV divergence, VIX, yield curve)
- User's current portfolio allocation and sector tilts
- User's investment strategy preferences (`investment_strategy.json`)

Answers: rebalance now? Which sector to tilt? Is this a risk-on or risk-off quarter? Time-weighted vs tactical allocation?

The shared brain under all three models: the asset model (`config/assets.json`), market data pipeline, and look-through analysis.

---

## Architecture Roadmap

### Completed ✅

**v6.0–v6.3 — Foundation**
- Full guided editor for all 7 config files
- Monte Carlo engine with 200 paths, GBM, asset classes
- Tax engine: federal brackets, state, NIIT, excise, IRMAA (display), Additional Medicare Tax
- Roth conversion optimizer (BETR, multi-scenario)
- RMD engine (SECURE 2.0: age 73/75 by birth year)
- Bad-market withdrawal sequencing
- Scenario shocks (scripted drawdowns with co-impact)
- Version history (50 versions per profile)
- Playwright test suite (95 tests)
- Python functional test suite (32 groups, 650+ checks)

**v6.4–v6.5 — Cashflow Engine**
- Lifecycle phase inference (accumulation/transition/distribution/RMD) from actual income
- W2 surplus waterfall deposits (IRS-limited priority routing)
- Per-shock enable/disable toggle (keep but skip)
- Shock mode: none/augment/replace with sync to Simulation panel
- Insights auto-expand on critical/warn findings
- Total Portfolio phase badges
- Headroom tier: portfolio can sustain more than planned
- Field reference panel (flattened, readable)
- `sanity.sh` — standard test command

### In Progress / Next

**v6.6 — Stream 3: BETR Accumulation**
- BETR computation extended to pre-retirement accumulation phase
- Bracket gap conversion during W2 years
- Phase-aware conversion schedule in Roth Insights
- G33 test group

**v6.6 — SS Provisional Income (A6)**
- Auto-compute taxable SS fraction from person.json SS config
- IRS §86 thresholds per filing status
- G34 test group

**v6.6 — IRMAA as Real Outflow (A3)**
- Engine deducts IRMAA from brokerage each year age 65+
- Config-driven brackets in taxes_states_mfj_single.json
- G35 test group

### Planned

**Stream 4 — Multi-User Auth**
- User login/registration (bcrypt + JWT)
- Per-user profile isolation: `users/{userid}/profiles/`
- System profiles shared read-only: `system/profiles/default/`
- Session lock: one active session per user, override capability
- No profile seeding on registration — new users see system profiles immediately

**Stream 5 — Landing Page + Demo**
- Pre-login landing page in App.tsx (conditional render on JWT absence)
- Hero: three-model overview, feature cards
- Guided auto-play demo with fictional user (not Satish)
- GrandPlan narrative page at `/grandplan`
- Login/signup in corner of landing page

**Stream 6 — Investment Tab (Phase 1)**
- Market signal computation pipeline
- Regime detection (CAPE, VIX, yield curve)
- Action list output
- `investment_strategy.json` editor

**Later**
- Cost basis tracking (brokerage only, Phase 2)
- SE tax / SECA
- State residency advisory
- SS start age optimization in Roth optimizer
- Mobile-responsive layout
- PDF export of results

---

## Design Principles

**1. No magic numbers** — every assumption is configurable and visible. The user controls inflation, return assumptions, shock events, spending plan, conversion policy.

**2. Tax-aware everywhere** — conversions, withdrawals, RMDs, IRMAA, provisional income all modeled together, not in isolation.

**3. Phase-aware** — the simulator knows what life stage you're in and adjusts priorities accordingly. Accumulation ≠ distribution ≠ RMD era.

**4. Honest uncertainty** — Monte Carlo P10/P50/P90 bands are shown throughout. No single-number false precision.

**5. Modular JSON config** — every user decision lives in a JSON file with a schema, readme, and guided editor. Power users can edit raw JSON; casual users use the guided UI.

**6. Test everything** — 32 functional test groups covering every customer-configurable option. Playwright UI tests for every table and section. `--sanity` as the standard gate before any commit.

---

## File Structure

```
src/
  # Core engine
  simulator_new.py          ← Monte Carlo + phase inference + waterfall
  simulation_core.py        ← simulate_balances, shock matrix
  engines.py / engines_assets.py  ← GBM, shock application
  taxes_core.py             ← All tax computation
  roth_optimizer.py         ← BETR, multi-scenario analysis
  roth_conversion_core.py   ← Bracket fill logic
  withdrawals_core.py       ← Per-account withdrawal sequencing
  rmd_core.py               ← IRS uniform lifetime tables
  portfolio_analysis.py     ← Diversification, look-through
  income_core.py            ← Income stream assembly
  loaders.py                ← All JSON file loading
  snapshot.py               ← Result serialization
  api.py                    ← FastAPI endpoints

  # UI
  ui/src/App.tsx             ← Entire React frontend (~8000 lines)
  ui/src/styles.css          ← CSS
  ui/src/main.tsx            ← Entry point

  # Tests
  test_flags.py              ← 32 functional test groups
  ui/tests/smoke.spec.ts     ← 95 Playwright tests
  sanity.sh                  ← Standard sanity command

  # Config (system-wide)
  config/
    assets.json              ← Asset model (GBM params, correlations)
    taxes_states_mfj_single.json  ← Tax brackets by state/filing
    system_shocks.json       ← System shock presets
    rmd.json                 ← IRS uniform lifetime table
    economicglobal.json      ← Bad-market drawdown threshold, defaults
    cape_config.json         ← CAPE ratio config

  # Profiles (→ users/{userid}/profiles/ after Stream 4)
  profiles/
    default/                 ← System reference profile (read-only)
    {user-profile}/          ← User-created profiles

  # Future (Stream 4)
  system/
    profiles/
      default/               ← Shared system profiles
  users/
    {userid}/
      profiles/
        {profile}/
```

---

## Personal Context
Owner: age 58, IRA $6M, Roth $500K, brokerage $2M. W2 income currently counterproductive (RMD timebomb). Primary use case: optimize the accumulation-to-distribution transition. The tool is built for this exact situation — high-balance, multi-account, tax-complexity-heavy retirement planning where generic tools fall short.
