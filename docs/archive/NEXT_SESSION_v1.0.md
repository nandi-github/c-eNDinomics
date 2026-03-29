# eNDinomics — Next Session Build Plan v1.0
## Immediate Scope + Full Backlog | March 17, 2026

---

## Context for New Chat
- Repo: https://github.com/nandi-github/c-eNDinomics
- Asset model v1.3.0 live, all tests green (378 Python + 16 Playwright)
- CAPE adjustment working, simulation_core bug fixed
- See SESSION_STATE.md for complete current state

---

## IMMEDIATE (Next Session — do in order)

### 1. Rename "Run" tab → "Simulation" + Add "Investment" placeholder tab
**Files:** `src/ui/src/App.tsx`, `src/ui/tests/smoke.spec.ts`

**Changes:**
- Tab nav: Configure | **Simulation** | Results  (rename "Run" → "Simulation")
- Add 4th tab: **Investment** (between Simulation and Results)
- Investment tab content: placeholder UI showing config file schemas
  - Shows: market_signals.json status (fresh/stale from health endpoint)
  - Shows: investment_strategy.json editor stub
  - Message: "Signal computation coming — Phase 2"
- Update smoke.spec.ts: check for "Simulation" tab (not "Run")
- Update smoke.spec.ts: check Investment tab is present

**Why:** Sets UX intent. Separates retirement simulation from investment decision engine. Establishes the tab structure that Phase 2 builds into.

---

### 2. Simulation Mode Transformer (wire the flag to actual behavior)
**File:** `src/simulator_new.py`

**Current state:** `simulation_mode` flag exists in person.json, UI, and payload — but simulator_new.py ignores it completely. All modes run identically.

**What to build:**
```python
def compute_mode_weights(current_age, retirement_age, simulation_mode):
    if simulation_mode == "investment":   return 1.0, 0.0
    if simulation_mode == "retirement":  return 0.0, 1.0
    if simulation_mode == "balanced":    return 0.5, 0.5
    # automatic: glide path
    years_to_retirement = max(0, retirement_age - current_age)
    if years_to_retirement >= 15: investment_w = 0.85
    elif years_to_retirement >= 10: investment_w = 0.65
    elif years_to_retirement >= 5:  investment_w = 0.40
    elif years_to_retirement >= 0:  investment_w = 0.20
    else: investment_w = 0.0
    return investment_w, 1.0 - investment_w
```

**What changes per mode:**
- investment_w high → emphasize CAGR/Sharpe in summary, relax withdrawal constraints
- retirement_w high → emphasize survival probability, enforce spending floor
- Dashboard: show mode-appropriate metrics (Sharpe for investment, survival % for retirement)
- Does NOT change the underlying simulation math — same GBM paths for all modes

---

### 3. Roth Conversion Optimizer
**New file:** `src/roth_optimizer.py`

**This is the highest-value single feature for the target user (high TRAD IRA balance).**

**What it does:**
Given current TRAD IRA balance, expected growth rate, tax brackets, and conversion window years → compute optimal annual conversion amount to minimize lifetime taxes.

```python
def optimize_roth_conversion(
    trad_ira_balance: float,     # current balance
    current_age: int,
    retirement_age: int,         # when income stops (lower bracket window)
    rmd_start_age: int,          # 73 for most
    target_death_age: int,
    annual_growth_rate: float,   # from asset model
    current_income: float,       # W2 + other
    filing_status: str,
    state: str,
    existing_roth_policy: dict,  # from person.json
) -> dict:
    # Returns: {
    #   optimal_annual_conversion: float,
    #   bracket_to_fill: str,      # e.g. "22%"
    #   estimated_rmd_reduction: float,
    #   estimated_lifetime_tax_savings: float,
    #   year_by_year_schedule: List[dict],
    #   warnings: List[str],       # IRMAA triggers, NIIT cliffs
    # }
```

**Output in UI:** New "Roth Optimizer" section in Results, showing:
- Optimal conversion amount per year (next 15 years)
- Estimated lifetime tax savings vs doing nothing
- Warning if conversion triggers IRMAA surcharge
- Side-by-side: "Do nothing" vs "Optimized" RMD projections

---

### 4. Update Grand Plan Section 10 (Build Status)
Replace the old build status table with current state reflecting:
- Simulation engine: complete + bug fixed
- Market data layer: Phase 1 complete
- Asset model: v1.3.0 with CAPE adjustment
- Portfolio look-through: complete
- Simulation mode: UI only, transformer pending
- Investment tab: placeholder only
- Roth optimizer: not started
- Signal computation: not started
- Cost basis: not started

---

## NEAR-TERM (2-3 sessions after immediate)

### 5. CAPE Valuation Layer — Scenario Bands
Show users 4 scenario bands on the main projection chart:
```
Optimistic (historical holds): assumes VTI 10%
Base case (CAPE-blended):      current v1.3.0 = 7.4%
Conservative (CAPE-heavy):     CAPE-implied ~6%
Pessimistic (GMO view):        ~4% real
```
Users see the range of credible outcomes, not just one number.

### 6. Investment Tab Phase 2 — Signal Computation
**New file:** `market_data/signal_computation.py`

Reads from market_data cache, computes:
- CMF (21-day Chaikin Money Flow) per ticker
- Wyckoff phase detection (price + volume pattern)
- OBV divergence
- CAPE from FRED API
- Bayesian regime posterior (4 states: expansion/slowdown/contraction/recovery)

Outputs: `market_signals.json` — auto-populated by `refresh_model.sh`

### 7. True Investment YoY Metric
The current "Investment YoY" metric includes RMD reinvestment which inflates it.
Add a separate metric: "Pure Asset Return" = return on the portfolio excluding cash flows.
This is the actual investment performance number, separate from portfolio growth.

### 8. Tax-Efficient Transfer Detection
Detect when user has appreciated low-basis positions in brokerage + dependents
in 0% LTCG bracket → surface gifting opportunity with dollar estimate.
Requires: cost_basis.json (Phase 1 of this feature — just the detection logic).

---

## MEDIUM-TERM (Future Sessions)

### Investment Tab Phase 3 — Action Generator
- `src/investment_engine.py`
- Reads: market_signals.json + investment_strategy.json + investment_constraints.json
- Produces: ordered action list with rationale, position sizing, review date
- Kelly criterion position sizing
- Requires cost_basis.json for tax-lot optimization

### Options Overlay Strategy Modeling
- Long PUT protection on concentrated positions
- Covered CALL income generation
- Collar net cost calculation
- Legacy low-basis position management (60-cent NVDA scenario)
- Assignment → redeployment automation

### Speculation/Manipulation Detection
- Price-volume divergence flags
- Unusual volume relative to average
- Smart money index (early vs late session price action)
- Momentum unsupported by fundamentals (requires EDGAR data)

### SEC EDGAR Fundamental Data
- `market_data/providers/edgar_provider.py`
- FCF yield, debt/equity, revenue growth, margins per ticker
- Feeds fundamental quality score for look-through holdings
- Feeds speculation detection layer

### Cost Basis Tracking
- `cost_basis.json` — per-account lot tracking (brokerage only)
- IRA accounts annotated as ordinary-income (no lot tracking)
- Required for: tax-lot optimization, wash sale detection, estate planning
- Introduce when building Investment tab Phase 3

### Beneficiary / Tax-Transfer Planning
- Gifting appreciated shares to 0% LTCG bracket dependents
- Kiddie Tax check (under 19, or full-time student under 24)
- 10-year rule for inherited IRA planning
- Step-up in basis awareness

---

## Architecture Decisions (Locked)
1. **One tool, not two apps** — simulation modes on shared engine
2. **Investment tab is separate** from simulation mode — different time horizon, different engine
3. **Base model → transformer → vertical** — same asset model feeds all use cases
4. **Cost basis** — introduce only when building Investment tab Phase 3 (brokerage trades)
5. **CAPE adjustment** — blend: historical 40%, CAPE-implied 35%, prior 25% (5-15yr horizon)
6. **Asset weights** — always: portfolio_w × class_w × ticker_pct (bug fixed in simulation_core.py)
7. **Simulation mode transformer** — thin function, doesn't change GBM math, changes objective + display

---

## Key Numbers (Test Profile, v1.3.0, March 2026)
```
Starting portfolio:     $9.92M
  Brokerage:            $750K
  TRAD IRA:             $4.8M  ← RMD bomb, 15yr to RMD start
  ROTH:                 $370K

Investment YoY nominal: 7.36% median  (7.39% mean)
Investment YoY real:    5.02% median

49yr projections (current USD median):
  Brokerage:            $7.9M
  TRAD IRA:             $44.9M
  ROTH:                 $13.1M
  Total:                $65.9M

Tax rate:
  Pre-RMD (yr1-28):     14-18%
  At RMD start (yr30):  36.8%  ← Roth optimizer is the fix
  
CAPE:                   35.0 (expensive — 10yr implied 6.4% nominal)
VTI mu (CAPE-adjusted): 9.38%  (raw 11.7%, prior 6.5%)
```

---

## How to Run (Quick Reference)
```bash
# Start server
cd root/src && ./vcleanbld_ui

# Full test suite
cd root/src && python3 -B test_flags.py --comprehensive-test --skip-playwright

# Playwright
cd root/src/ui && npx playwright test

# Refresh market data + recalibrate + promote
cd root && ./refresh_model.sh

# Manual recalibrate only
cd root/src && python3 asset_calibration.py && python3 promote_model.py --yes
```

---

## Files to Provide in New Chat
Provide these files (from repo or Downloads) at start of new session:
1. `SESSION_STATE.md` (this companion doc)
2. `eNDinomics_GrandPlan_v1.4.docx`
3. `src/ui/src/App.tsx` — current UI
4. `src/simulator_new.py` — simulation orchestrator
5. `src/simulation_core.py` — core engine (bug fixed)
6. `src/test_flags.py` — full test suite
7. `src/ui/tests/smoke.spec.ts` — Playwright tests
8. `INVESTMENT_ENGINE.md` — Investment tab spec
9. `src/portfolio_analysis.py` — look-through

*Version 1.0 | March 17, 2026 | Sessions 1-19 complete*
*Next version: update after each session with completed items and new discoveries*
