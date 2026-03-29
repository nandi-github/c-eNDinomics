# eNDinomics — Next Session Build Plan v2.0
## Session 22 Scope + Full Backlog | March 19, 2026

---

## Context for New Chat
- Repo: https://github.com/nandi-github/c-eNDinomics
- Last commit: `c1bf8eb` — all tests green (424/424 Python + 16/16 Playwright)
- Sessions 1–21 complete — see SESSION_STATE_v2_0.md for full current state
- Grand Plan v1.6 captures the multi-generational tax optimization architecture

---

## IMMEDIATE (Session 22 — do in order)

### 1. roth_optimizer.py — Full BETR Rewrite
**File:** `src/roth_optimizer.py`
**Replaces:** Phase 1 bracket-fill (complete but simplistic)

**What to build:**

#### 1a. IRA Timebomb Severity Classifier
```python
def classify_ira_timebomb(trad_ira_balance, current_age, projected_balance_at_rmd):
    # Use simulation's projected median IRA balance at RMD age (not compound assumption)
    rmd_factor = get_rmd_factor(rmd_age)  # from rmd_core.py uniform lifetime table
    rmd_year1 = projected_balance_at_rmd / rmd_factor
    if rmd_year1 > 500_000:  return "CRITICAL"   # 37% lock-in certain
    if rmd_year1 > 200_000:  return "SEVERE"     # likely 32-35%
    if rmd_year1 > 100_000:  return "MODERATE"   # 22-24% risk
    return "MANAGEABLE"
```

#### 1b. BETR 2-Pass Calculation
```python
# Pass 1: current_marginal_rate at conversion amount X
# Pass 2: future_rate = max(rmd_rate_self, rmd_rate_survivor, heir_liquidation_rate)
# BETR = future_rate × (1 + after_tax_return)^n
# Convert if current_marginal_rate < BETR
```

**Future rates to model (use highest):**
- Self (MFJ): projected RMD marginal rate at age 73+
- Self (Survivor/Single): same RMDs, halved brackets — the cliff
- Heir (moderate earner $100K–$200K): 10-year forced liquidation rate
- Heir (high earner $300K+): 10-year forced liquidation rate (often 37%+)

#### 1c. IRMAA Guard — Age 63, Not 65
- IRMAA is based on MAGI from 2 years prior
- Guard triggers at age 63 (conversion in yr 63 → Medicare premium in yr 65)
- For large IRA, IRMAA (~$4K–$14K/yr) is a secondary concern — flag but don't block

#### 1d. Four Named Strategies
```python
strategies = {
    "conservative": fill_to_top_of(bracket="22%"),   # IRMAA-safe
    "balanced":     fill_to_top_of(bracket="24%"),   # standard
    "aggressive":   fill_to_top_of(bracket="32%"),   # IRMAA acceptable
    "maximum":      fill_to_top_of(bracket="37%"),   # any rate < future lock-in
}
```

#### 1e. Output Structure
```python
{
    "timebomb_severity": "CRITICAL",
    "projected_rmd_year1": 850000,
    "strategies": {
        "conservative": {
            "annual_conversion": 45000,
            "bracket_filled": "22%",
            "tax_cost_year1": 9900,
            "betr": 0.31,
            "scenarios": {
                "self_mfj":      {"lifetime_savings": 180000, "vs_nothing": "+$180K"},
                "self_survivor": {"lifetime_savings": 360000, "vs_nothing": "+$360K"},
                "heir_moderate": {"lifetime_savings": 800000, "vs_nothing": "+$800K"},
                "heir_high":     {"lifetime_savings": 1200000, "vs_nothing": "+$1.2M"},
            }
        },
        # ... balanced, aggressive, maximum
    },
    "recommended_strategy": "aggressive",
    "recommended_reason": "IRA timebomb severity CRITICAL. IRMAA at current portfolio level is rounding error vs bracket savings.",
    "irmaa_notes": ["Age 63: conversion above $103K MAGI triggers IRMAA tier 1 (+$2.5K/yr Medicare)"],
    "warnings": [],
    "year_by_year_schedule": [
        {"year": 1, "age": 46, "convert": 120000, "tax_cost": 28800, "cumulative_savings": 0},
        ...
    ],
}
```

---

### 2. person.json Schema Additions
**File:** `src/profiles/Test/person.json` (and default/)

**New fields:**
```json
"spouse": {
    "age": 52,
    "expected_longevity": 88
},
"inheritors": [
    {
        "relationship": "child",
        "estimated_income": 300000,
        "filing_status": "MFJ",
        "age": 25
    }
],
"roth_optimizer_config": {
    "include_survivor_scenario": true,
    "include_heir_scenario": true,
    "irmaa_sensitivity": "low"
}
```

**Notes:**
- `irmaa_sensitivity: low` = flag IRMAA but don't let it block recommendation (appropriate for large IRA)
- `irmaa_sensitivity: high` = respect IRMAA cliff as hard constraint (appropriate for moderate IRA near threshold)
- `spouse.expected_longevity` = age at which optimizer switches to single-filer brackets for survivor scenario
- All fields optional with sensible defaults (no spouse → skip survivor scenario, no inheritors → skip heir scenario)

---

### 3. api.py — Inline Optimizer Call
**File:** `src/api.py`

After `run_accounts_new()` completes, call optimizer with simulation output:
```python
# Inject simulation results into optimizer
from roth_optimizer import optimize_roth_conversion_full

roth_opt = optimize_roth_conversion_full(
    person_cfg=person_cfg,
    simulation_summary=res["summary"],
    simulation_portfolio=res["portfolio"],
    withdrawals=res["withdrawals"],
)
res["roth_optimizer"] = roth_opt
```

Key: the optimizer uses the simulation's projected IRA balance at RMD age (from Monte Carlo median path) — not a simple compound growth assumption. This is what makes the BETR calculation accurate.

---

### 4. App.tsx — Results Tab Option A
**File:** `src/ui/src/App.tsx`

New collapsible section in Results tab, after Portfolio Analysis:

```
┌─ Roth Conversion Optimizer ────────────────────────────────────┐
│  ⚠ IRA Timebomb: CRITICAL                                      │
│  Projected RMD yr1 (age 73): ~$850K → 37% bracket lock-in     │
│                                                                  │
│  [3 headline cards]                                             │
│  [$120K/yr aggressive]  [37% BETR]  [$3.2M heir savings]       │
│                                                                  │
│  Strategy comparison table (4 strategies × 4 scenarios):        │
│  Strategy | Self MFJ | Self Survivor | Heir Moderate | Heir Hi  │
│  Conserv  |  $180K   |    $360K      |    $800K      |  $1.2M   │
│  Balanced |  $290K   |    $580K      |   $1.3M       |  $1.9M   │
│  Aggrssv  |  $480K   |    $960K      |   $2.1M       |  $3.2M   │ ← recommended
│  Maximum  |  $720K   |   $1.4M       |   $3.2M       |  $4.8M   │
│                                                                  │
│  Year-by-year schedule (collapsible):                           │
│  Yr | Age | Convert | Tax Cost | BETR | Cumul. Savings          │
│                                                                  │
│  ⚠ Warnings: IRMAA tier 1 triggered above $103K MAGI           │
└──────────────────────────────────────────────────────────────────┘
```

**Show only when:** `roth_conversion_enabled = true` in profile.
**If disabled:** Show nudge: "Enable Roth conversions in person.json to see optimizer recommendations."

---

### 5. G22 Test Group — Optimizer Output Validation
**File:** `src/test_flags.py`

New group `group22_roth_optimizer` checking:
- `res["roth_optimizer"]` present in snapshot when conversions enabled
- `timebomb_severity` is one of MANAGEABLE/MODERATE/SEVERE/CRITICAL
- `projected_rmd_year1` > 0
- All 4 strategies present
- Each strategy has all 4 scenarios
- `annual_conversion` > 0 for all strategies (test profile has $4.8M TRAD IRA)
- `betr` in [0, 1] for all strategies
- `lifetime_savings` > 0 for all scenarios
- `recommended_strategy` is one of the 4 named strategies
- `year_by_year_schedule` length = simulation years
- IRMAA warning present for test profile (age 46, conversions will eventually trigger)

---

## NEAR-TERM (Session 23)

### Simulation Tab — Roth Optimizer On-Demand (Option B)
- New "Run Roth Optimizer" button in Simulation tab
- Separate `/roth-optimize` API endpoint
- Accepts `profile` + optional `run_id` to pull projected balances from existing snapshot
- Returns optimizer output without re-running full Monte Carlo
- Shows same 4×4 matrix but allows tweaking person.json fields interactively

### Investment Tab — Persistent Tax Recommendations (Option C)
- Always-visible panel in Investment tab (not tied to a specific run)
- Shows: recommended strategy, next conversion deadline, IRMAA cliff distance
- "Last run" reference with link to that run's full optimizer output
- Color-coded urgency: GREEN (years to act), AMBER (act this year), RED (already suboptimal)

### CAPE Scenario Bands — Wire Live CAPE Value
- Currently hardcoded (10%/6%/4%)
- Read actual CAPE value from `cape_config.json` and adjust scenario lines dynamically
- Label shows: "Conservative (CAPE 35 → 6.2% implied)"

### Pure Investment Return Metric
- Strip RMD reinvestment from CAGR
- Add separate "Pure Asset Return" metric to Summary
- Current "Investment YoY" includes reinvestment cashflows which inflates it

---

## MEDIUM-TERM (Sessions 24+)

### Investment Tab Phase 2 — Signal Computation
- `market_data/signal_computation.py`
- CMF (21-day Chaikin Money Flow) per ticker
- Wyckoff phase detection
- OBV divergence, Bayesian regime posterior
- Outputs: `market_signals.json`

### Investment Tab Phase 3 — Action Generator
- `src/investment_engine.py`
- Signals + constraints → ordered action list
- Kelly criterion position sizing
- Tax-lot optimization (requires cost_basis.json)

### Tax-Efficient Transfer Detection
- Detect appreciated low-basis positions + dependents in 0% LTCG bracket
- Surface gifting opportunity with dollar estimate

---

## Architecture Decisions (Locked)
1. One tool, not two apps — simulation modes on shared engine
2. Investment tab is separate from simulation mode
3. GBM math identical across modes — only success measurement and display change
4. `api.py` is the injection point for simulation_mode AND roth_optimizer call
5. Optimizer uses simulation's projected IRA balance (Monte Carlo median path) — not compound assumption
6. IRMAA guard at age 63 (2-year Medicare lookback) — not 65
7. Tax optimization is multi-generational: survivor cliff + 10-year heir rule + BETR 2-pass
8. Four named strategies (conservative/balanced/aggressive/maximum) — menu, not mandate
9. `irmaa_sensitivity` in person.json controls whether IRMAA tips recommendation vs. just flagging

---

## Key Numbers (Test Profile, v1.3.0)
```
Starting portfolio:     $9.92M
  BROKERAGE:            $750K
  TRAD_IRA:             $4.8M  ← IRA timebomb: CRITICAL
  ROTH:                 $370K

Simulation mode:        Automatic (investment_w=0.85 at age 46, retirement 65)
Investment YoY nominal: 7.36% median
Investment YoY real:    5.02% median
Success rate:           100% (floor bar)
CAPE:                   35.0

49yr projections (current USD, median):
  TRAD_IRA:             ~$44.9M
  Total:                ~$65.9M

Projected RMD yr1 (age 73): ~$850K → 37% bracket lock-in
Timebomb severity:      CRITICAL
Recommended strategy:   Aggressive ($120K/yr, fill to 32%)
Estimated heir savings: ~$3.2M (high-earning heir, 10yr forced liquidation)
```

---

## Files to Provide in New Chat (Session 22)
1. `SESSION_STATE_v2_0.md` — this companion doc
2. `NEXT_SESSION_v2_0.md` — this file
3. `eNDinomics_GrandPlan_v1_6.docx` — living design doc
4. `src/ui/src/App.tsx` — current UI (4 tabs)
5. `src/simulator_new.py` — simulation orchestrator
6. `src/roth_optimizer.py` — Phase 1 to be replaced
7. `src/api.py` — server (add inline optimizer call)
8. `src/test_flags.py` — full test suite (add G22)
9. `src/ui/tests/smoke.spec.ts` — Playwright tests
10. `src/profiles/Test/person.json` — add spouse/inheritors/roth_optimizer_config

---

## How to Run (Quick Reference)
```bash
# Build UI + start server
cd root/src && ./vcleanbld_ui

# Full test suite (skip Playwright)
cd root/src && python3 -B test_flags.py --comprehensive-test --skip-playwright

# Playwright only
cd root/src/ui && npx playwright test

# Full suite including Playwright
cd root/src && python3 -B test_flags.py --comprehensive-test

# Refresh market data + recalibrate + promote
cd root && ./refresh_model.sh
```

*Version 2.0 | March 19, 2026 | Sessions 1–21 complete*
*Next version: update after session 22*
