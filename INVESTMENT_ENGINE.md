# Investment Engine — Design Specification
## eNDinomics | Component: Investment Tab | Version 1.0 | March 2026

---

## 1. What This Is (and What It Is Not)

The Investment tab is a **decision assistant**, not a simulator.

| | Simulation Tab | Investment Tab |
|--|---------------|----------------|
| Time horizon | 30-50 years | Today / week / month / quarter |
| Engine | Monte Carlo (GBM) | Regime detection + signal analysis |
| Output | Projection tables | Ordered action list |
| Question answered | "What will I have at 95?" | "What should I do Monday?" |
| Config files | person.json, allocation_yearly.json | investment_strategy.json, market_signals.json |
| Cost basis needed | No (estimated) | Yes (Phase 2, brokerage only) |
| Run time | ~5-15 seconds | <1 second (reads cached signals) |

The shared brain underneath both tabs is identical: the asset model, look-through analysis, and market data pipeline. The Investment tab reads the **regime-adjusted** layer of the asset model rather than the long-run static parameters.

---

## 2. Architecture

```
market_data/cache/              (weekly refresh via refresh_model.sh)
    prices, holdings, sectors
         ↓
signal_computation.py           (Phase 2 — runs after market_data refresh)
    CMF, Wyckoff phase, OBV divergence
    CAPE ratio (from FRED)
    VIX, yield curve slope
    Bayesian regime posterior
         ↓
market_signals.json             (auto-populated, never hand-edited)
         ↓
investment_engine.py            (Phase 3)
    reads: market_signals.json
           investment_strategy.json
           investment_constraints.json
           allocation_yearly.json (current portfolio)
           cost_basis.json (Phase 2, brokerage only)
         ↓
action_list                     (ordered recommendations with rationale)
```

---

## 3. Configuration Files

### 3.1 investment_strategy.json (user-maintained)

Expresses your directional investment philosophy and preferences.

```json
{
  "risk_appetite": "moderate",
  "time_horizon": "quarterly",
  "rebalancing_trigger": "signal",
  "sector_tilts": {
    "Information Technology": "neutral",
    "Energy": "underweight",
    "Financials": "neutral",
    "Healthcare": "overweight",
    "Utilities": "underweight"
  },
  "excluded_sectors": [],
  "tax_sensitivity": "high",
  "cash_reserve_pct": 5.0,
  "signal_weights": {
    "momentum": 0.30,
    "valuation": 0.40,
    "regime": 0.30
  },
  "position_sizing": "kelly",
  "readme": {
    "risk_appetite": "aggressive | moderate | conservative",
    "time_horizon": "immediate | weekly | monthly | quarterly",
    "rebalancing_trigger": "drift_band | signal | manual",
    "tax_sensitivity": "high (prefer LTCG, avoid wash sales) | medium | low",
    "position_sizing": "kelly | equal_weight | risk_parity | manual"
  }
}
```

### 3.2 market_signals.json (auto-populated by signal_computation.py)

Never edited by hand. Refreshed weekly by `refresh_model.sh` (Phase 2 adds signal computation step).

```json
{
  "_generated": "2026-03-16T22:00:00",
  "_source": "signal_computation.py v1.0",
  "macro": {
    "cape_ratio": 35.2,
    "cape_implied_10yr_real_return": 0.028,
    "vix": 18.4,
    "vix_regime": "complacent",
    "yield_curve_slope_2_10": 0.82,
    "yield_curve_regime": "normal",
    "credit_spread_hy": 3.1,
    "fed_funds_rate": 4.25
  },
  "regime": {
    "posterior": {
      "expansion": 0.62,
      "slowdown": 0.28,
      "contraction": 0.07,
      "recovery": 0.03
    },
    "dominant": "expansion",
    "confidence": 0.62
  },
  "tickers": {
    "VTI": {
      "cmf_21d": 0.18,
      "wyckoff_phase": "markup",
      "obv_divergence": "none",
      "momentum_12m_1m": 0.24,
      "as_of": "2026-03-14"
    },
    "QQQ": {
      "cmf_21d": 0.09,
      "wyckoff_phase": "late_markup",
      "obv_divergence": "bearish",
      "momentum_12m_1m": 0.31,
      "as_of": "2026-03-14"
    },
    "GLD": {
      "cmf_21d": 0.31,
      "wyckoff_phase": "accumulation_c",
      "obv_divergence": "none",
      "momentum_12m_1m": 0.18,
      "as_of": "2026-03-14"
    }
  }
}
```

### 3.3 investment_constraints.json (user-maintained)

Hard rules that override signal recommendations regardless of strength.

```json
{
  "max_single_position_pct": 40.0,
  "min_international_pct": 10.0,
  "max_sector_concentration_pct": 25.0,
  "min_bond_allocation_pct": 20.0,
  "no_margin": true,
  "wash_sale_lookback_days": 30,
  "min_lot_size_usd": 1000,
  "max_trades_per_action": 5,
  "require_ltcg_only": false
}
```

### 3.4 cost_basis.json (Phase 2 — brokerage accounts only)

Required for tax-lot optimization and wash sale detection.
**Not required for TRAD IRA or ROTH IRA** — all IRA distributions are taxed
as ordinary income regardless of underlying cost basis.

```json
{
  "BROKERAGE-1": {
    "lots": [
      {
        "ticker": "VTI",
        "shares": 150.0,
        "purchase_date": "2019-03-15",
        "cost_basis_per_share": 142.50,
        "lot_type": "long"
      },
      {
        "ticker": "QQQ",
        "shares": 45.0,
        "purchase_date": "2023-11-20",
        "cost_basis_per_share": 385.00,
        "lot_type": "short"
      }
    ],
    "_note": "Taxable brokerage — LTCG applies on lots held > 1 year"
  },
  "BROKERAGE-2": {
    "lots": []
  },
  "TRAD_IRA-1": {
    "_note": "All distributions = ordinary income. No lot tracking needed."
  },
  "ROTH_IRA-1": {
    "_note": "All qualified distributions = tax-free. No lot tracking needed."
  }
}
```

---

## 4. Runtime Options

Unlike the Simulation tab (fixed 30-50 year horizon), the Investment tab
allows the user to select the action horizon:

| Horizon | What changes |
|---------|-------------|
| Immediate | Only signals with high confidence (>0.8) fire. Tight constraints. |
| Weekly | Standard signal weights. Review date = +7 days. |
| Monthly | Smoothed signals (21-day CMF vs 5-day). Review = +30 days. |
| Quarterly | Valuation-weighted more heavily. Momentum smoothed. Review = +90 days. |

---

## 5. Output Format

The Investment tab produces an ordered action list, not projection tables.

```
Action Horizon: Quarterly  |  As of: 2026-03-17
Market Regime:  Expansion (62% confidence)
CAPE:           35.2  (↑ expensive vs historical 17)

Recommended Actions:

  1. SELL  QQQ   $45,000
     Lot: 2022-03-15 | Gain: $12,000 LTCG | Rate: 15%
     Rationale: Wyckoff late_markup + bearish OBV divergence.
                CAPE 35 signals rotation away from growth concentration.
                Current tech concentration 11.9% → target 9%.
     Impact: Concentration ↓, tax cost $1,800

  2. BUY   VTI   $30,000
     Rationale: CMF +0.18 accumulation. Broad market reduces
                sector concentration from QQQ rotation.

  3. BUY   GLD   $15,000
     Rationale: CMF +0.31 strong accumulation. Geopolitical
                hedge. Wyckoff Phase C (spring complete).

  4. HOLD  IEF   —
     Rationale: Yield curve normal. Duration neutral. No signal.

  5. HOLD  VTI (existing lots) —
     Rationale: Do not sell — wash sale risk on new VTI purchase.

Review by: 2026-06-15
```

---

## 6. What's Different From the Simulation Mode Flag

The simulation mode flag (Automatic/Retirement-first/Balanced/Investment-first)
on the Simulation tab controls **the objective function** of a long-run Monte
Carlo. It still runs 30-50 years of paths.

The Investment tab is a **separate tab** with a completely different engine,
different config files, and a different time horizon. The two are complementary:

- Simulation tab answers: "Am I on track? Will the money last?"
- Investment tab answers: "What specific actions should I take right now?"

The Investment-first mode on the Simulation tab is useful for users who want
the simulation to show growth metrics rather than survival metrics. It does
not replace the Investment tab's action engine.

---

## 7. Build Order

### Phase 1 — Tab + Placeholder (next session)
- Rename "Run" tab to "Simulation" in App.tsx
- Add "Investment" tab with config file editor UI (investment_strategy.json)
- Show market_signals.json status (fresh/stale)
- Placeholder: "Signal computation coming in Phase 2"

### Phase 2 — Signal Computation
- `signal_computation.py`: CMF, Wyckoff, OBV from price history in cache
- CAPE from FRED API (free, no key required)
- Bayesian regime classifier (4 states from VIX + yield curve + credit spreads)
- Adds signal computation step to `refresh_model.sh`
- Populates market_signals.json automatically

### Phase 3 — Action Generator
- `investment_engine.py`: signals + strategy + constraints → action list
- Kelly criterion position sizing
- Tax-lot optimization (requires cost_basis.json)
- Wash sale detection
- UI: ordered action table with rationale + review date

### Phase 4 — Outcome Tracking
- Record every recommendation with market state at time of decision
- Measure actual outcomes after review date
- Recalibrate signal weights based on what worked
- The system learns from its own decisions

---

## 8. Cost Basis — When to Introduce

| Feature | Needs cost_basis.json? |
|---------|----------------------|
| Retirement simulation | ❌ No |
| Simulation mode selector | ❌ No |
| Investment tab Phase 1 (placeholder) | ❌ No |
| Investment tab Phase 2 (signals) | ❌ No |
| Investment tab Phase 3 (action generator, brokerage trades) | ✅ Yes |
| Tax-loss harvesting | ✅ Yes |
| Wash sale detection | ✅ Yes |
| Estate planning (step-up in basis) | ✅ Yes |

The retirement simulation estimates brokerage capital gains using a blended
gain rate from asset class yield and implied appreciation. This is accurate
enough for long-run planning where income-based taxes (RMDs, conversions)
dominate. Introduce cost_basis.json when building Phase 3 of the Investment tab.

---

*Last updated: March 2026 | See MARKET_DATA_LAYER.md for data architecture*
*See eNDinomics_GrandPlan.docx Section 2.2-2.3 for full platform context*
