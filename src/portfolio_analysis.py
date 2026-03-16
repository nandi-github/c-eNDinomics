"""
portfolio_analysis.py — eNDinomics Portfolio Allocation Extractor
==================================================================
Pure function: compute_portfolio_analysis(alloc_cfg, starting_balances, ending_balances)
  -> PortfolioAnalysis

Computes:
  - Per-account target allocation breakdown (by asset class, geography, type)
  - Aggregate portfolio breakdown weighted by account balance
  - Concentration flags (any single ticker > threshold)
  - Diversification score
  - Target vs actual drift (when ending_balances provided)

Architecture
------------
- No simulator imports, no I/O, no side effects
- Takes alloc_cfg dict (from allocation_yearly.json) and balance dicts
- Returns PortfolioAnalysis dataclass, serialisable to dict for snapshot
- Designed to be called from snapshot.py and consumed by App.tsx

Geography mapping
-----------------
US_STOCKS   → geo: "US"         type: "Equity"
INTL_STOCKS → geo: "Intl"       type: "Equity"
LONG_TREAS  → geo: "US"         type: "Fixed Income"
INT_TREAS   → geo: "US"         type: "Fixed Income"
TIPS        → geo: "US"         type: "Fixed Income"
GOLD        → geo: "Global"     type: "Alternatives"
COMMOD      → geo: "Global"     type: "Alternatives"
CASH        → geo: "US"         type: "Cash"
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Class → geography and type mappings
# ---------------------------------------------------------------------------

CLASS_GEO: Dict[str, str] = {
    "US_STOCKS":    "US",
    "INTL_STOCKS":  "International",
    "LONG_TREAS":   "US",
    "INT_TREAS":    "US",
    "TIPS":         "US",
    "GOLD":         "Global",
    "COMMOD":       "Global",
    "CASH":         "US",
}

CLASS_TYPE: Dict[str, str] = {
    "US_STOCKS":    "Equity",
    "INTL_STOCKS":  "Equity",
    "LONG_TREAS":   "Fixed Income",
    "INT_TREAS":    "Fixed Income",
    "TIPS":         "Fixed Income",
    "GOLD":         "Alternatives",
    "COMMOD":       "Alternatives",
    "CASH":         "Cash",
}

# Thresholds for insights
CONCENTRATION_THRESHOLD  = 0.20   # single ticker > 20% of account → flag
EQUITY_HEAVY_THRESHOLD   = 0.85   # equity > 85% → flag as aggressive
EQUITY_LIGHT_THRESHOLD   = 0.30   # equity < 30% → flag as conservative
INTL_LOW_THRESHOLD       = 0.10   # international < 10% of equity → flag
BOND_NEAR_ZERO_THRESHOLD = 0.05   # bonds < 5% for near-retirement → flag


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ClassWeight:
    asset_class: str      # e.g. "US_STOCKS"
    geo:         str      # e.g. "US"
    asset_type:  str      # e.g. "Equity"
    weight_pct:  float    # 0-100


@dataclass
class TickerWeight:
    ticker:      str
    asset_class: str
    weight_pct:  float    # 0-100, fraction of this account's total


@dataclass
class AccountAnalysis:
    account:        str
    balance_cur:    float                  # current USD median
    balance_pct:    float                  # % of total portfolio
    class_weights:  List[ClassWeight]      # per asset class
    ticker_weights: List[TickerWeight]     # per ticker (sorted descending)
    geo_weights:    Dict[str, float]       # {"US": 65.0, "International": 20.0, ...}
    type_weights:   Dict[str, float]       # {"Equity": 70.0, "Fixed Income": 30.0, ...}
    top_ticker:     Optional[str]          # highest weight ticker
    top_ticker_pct: float                  # its weight
    is_concentrated: bool                  # any ticker > threshold


@dataclass
class AggregateAnalysis:
    total_balance_cur:  float
    class_weights:      List[ClassWeight]
    geo_weights:        Dict[str, float]
    type_weights:       Dict[str, float]
    ticker_weights:     List[TickerWeight]   # portfolio-level, sorted descending
    equity_pct:         float
    fixed_income_pct:   float
    alternatives_pct:   float
    cash_pct:           float
    us_equity_pct:      float                # US equity as % of total portfolio
    intl_equity_pct:    float                # Intl equity as % of total portfolio
    diversification_score: float             # 0-100 (higher = more diversified)
    flags:              List[str]            # human-readable insight flags


@dataclass
class PortfolioAnalysis:
    aggregate:      AggregateAnalysis
    accounts:       List[AccountAnalysis]
    n_accounts:     int
    n_tickers:      int          # unique tickers across portfolio

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------

def _extract_account_class_weights(account_cfg: Dict[str, Any]) -> Dict[str, float]:
    """
    Given a single account config from global_allocation, return
    {asset_class: weight_pct} normalised to sum to 100.
    """
    weights: Dict[str, float] = {}
    portfolios = account_cfg.get("portfolios", {})
    for pf_name, pf in portfolios.items():
        pf_weight = float(pf.get("weight_pct", 0)) / 100.0
        for cls, cls_pct in pf.get("classes_pct", {}).items():
            w = pf_weight * float(cls_pct) / 100.0 * 100.0   # → back to pct
            weights[cls] = weights.get(cls, 0.0) + w
    return weights


def _extract_ticker_weights(account_cfg: Dict[str, Any]) -> Dict[str, tuple]:
    """
    Return {ticker: (weight_pct, asset_class)} for one account.
    """
    result: Dict[str, tuple] = {}
    portfolios = account_cfg.get("portfolios", {})
    for pf_name, pf in portfolios.items():
        pf_weight = float(pf.get("weight_pct", 0)) / 100.0
        for cls, cls_pct in pf.get("classes_pct", {}).items():
            cls_weight = pf_weight * float(cls_pct) / 100.0
            holdings = pf.get("holdings_pct", {}).get(cls, [])
            for h in holdings:
                ticker = h.get("ticker", "")
                ticker_pct = float(h.get("pct", 0)) / 100.0
                w = cls_weight * ticker_pct * 100.0   # → pct
                if ticker:
                    prev_w, _ = result.get(ticker, (0.0, cls))
                    result[ticker] = (prev_w + w, cls)
    return result


def _geo_type_rollup(class_weights: Dict[str, float]) -> tuple:
    """Roll up class weights into geo and type dicts."""
    geo: Dict[str, float] = {}
    typ: Dict[str, float] = {}
    for cls, pct in class_weights.items():
        g = CLASS_GEO.get(cls, "Other")
        t = CLASS_TYPE.get(cls, "Other")
        geo[g] = geo.get(g, 0.0) + pct
        typ[t] = typ.get(t, 0.0) + pct
    return geo, typ


def _diversification_score(ticker_weights: Dict[str, tuple],
                            geo: Dict[str, float],
                            typ: Dict[str, float]) -> float:
    """
    Simple 0-100 score:
      - Ticker count component (0-40): more tickers = higher score, caps at 10
      - Geo spread component (0-30): US < 80% adds points
      - Type spread component (0-30): having equity + bonds + alternatives
    """
    n_tickers = len(ticker_weights)
    ticker_score = min(40.0, n_tickers * 4.0)

    us_pct = geo.get("US", 0.0)
    geo_score = 30.0 if us_pct < 60 else (20.0 if us_pct < 75 else 10.0)

    has_equity = typ.get("Equity", 0.0) > 5.0
    has_bonds  = typ.get("Fixed Income", 0.0) > 5.0
    has_alts   = typ.get("Alternatives", 0.0) > 2.0
    type_score = sum([10.0 * has_equity, 10.0 * has_bonds, 10.0 * has_alts])

    return round(ticker_score + geo_score + type_score, 1)


def _aggregate_flags(equity_pct: float,
                     intl_equity_pct: float,
                     fixed_income_pct: float,
                     ticker_weights: List[TickerWeight]) -> List[str]:
    """Generate human-readable flags for aggregate portfolio."""
    flags = []
    if equity_pct > EQUITY_HEAVY_THRESHOLD * 100:
        flags.append(f"Aggressive: {equity_pct:.0f}% equity (>85% threshold)")
    if equity_pct < EQUITY_LIGHT_THRESHOLD * 100:
        flags.append(f"Conservative: {equity_pct:.0f}% equity (<30% threshold)")
    if equity_pct > 0 and intl_equity_pct / equity_pct < INTL_LOW_THRESHOLD:
        flags.append(f"Low international diversification: {intl_equity_pct:.0f}% intl of total")
    if fixed_income_pct < BOND_NEAR_ZERO_THRESHOLD * 100:
        flags.append(f"Near-zero fixed income: {fixed_income_pct:.0f}%")
    concentrated = [t for t in ticker_weights if t.weight_pct > CONCENTRATION_THRESHOLD * 100]
    for t in concentrated:
        flags.append(f"Concentrated: {t.ticker} is {t.weight_pct:.0f}% of portfolio")
    return flags


def compute_portfolio_analysis(
    alloc_cfg: Dict[str, Any],
    starting_balances: Dict[str, float],
    ending_balances_cur: Optional[Dict[str, float]] = None,
) -> PortfolioAnalysis:
    """
    Compute full portfolio analysis.

    Args:
        alloc_cfg:            dict from allocation_yearly.json (global_allocation section)
        starting_balances:    {account_name: balance_in_current_usd}
        ending_balances_cur:  optional {account_name: balance} for current-$ ending weights
    """
    global_alloc = alloc_cfg.get("global_allocation", alloc_cfg)

    # Use ending balances if available, else starting
    balances = ending_balances_cur if ending_balances_cur else starting_balances
    total_balance = max(sum(balances.values()), 1.0)   # avoid /0

    account_analyses: List[AccountAnalysis] = []
    agg_class_weights: Dict[str, float] = {}
    agg_ticker_weights: Dict[str, tuple] = {}

    for acct_name, acct_cfg in global_alloc.items():
        bal = float(balances.get(acct_name, 0.0))
        bal_pct = bal / total_balance * 100.0

        class_w = _extract_account_class_weights(acct_cfg)
        ticker_w = _extract_ticker_weights(acct_cfg)
        geo, typ = _geo_type_rollup(class_w)

        # Build sorted ticker list
        tickers_sorted = sorted(
            [TickerWeight(ticker=t, asset_class=cls, weight_pct=round(w, 2))
             for t, (w, cls) in ticker_w.items()],
            key=lambda x: x.weight_pct, reverse=True
        )

        top = tickers_sorted[0] if tickers_sorted else None
        class_list = [
            ClassWeight(
                asset_class=cls,
                geo=CLASS_GEO.get(cls, "Other"),
                asset_type=CLASS_TYPE.get(cls, "Other"),
                weight_pct=round(w, 2)
            )
            for cls, w in sorted(class_w.items(), key=lambda x: -x[1])
        ]

        account_analyses.append(AccountAnalysis(
            account=acct_name,
            balance_cur=bal,
            balance_pct=round(bal_pct, 2),
            class_weights=class_list,
            ticker_weights=tickers_sorted,
            geo_weights={k: round(v, 2) for k, v in geo.items()},
            type_weights={k: round(v, 2) for k, v in typ.items()},
            top_ticker=top.ticker if top else None,
            top_ticker_pct=round(top.weight_pct, 2) if top else 0.0,
            is_concentrated=any(t.weight_pct > CONCENTRATION_THRESHOLD * 100
                                 for t in tickers_sorted),
        ))

        # Accumulate into aggregate — weighted by balance
        weight_factor = bal / total_balance
        for cls, pct in class_w.items():
            agg_class_weights[cls] = agg_class_weights.get(cls, 0.0) + pct * weight_factor
        for ticker, (pct, cls) in ticker_w.items():
            prev_pct, _ = agg_ticker_weights.get(ticker, (0.0, cls))
            agg_ticker_weights[ticker] = (prev_pct + pct * weight_factor, cls)

    # Build aggregate
    agg_geo, agg_typ = _geo_type_rollup(agg_class_weights)
    agg_tickers_sorted = sorted(
        [TickerWeight(ticker=t, asset_class=cls, weight_pct=round(w, 2))
         for t, (w, cls) in agg_ticker_weights.items()],
        key=lambda x: x.weight_pct, reverse=True
    )
    agg_class_list = [
        ClassWeight(
            asset_class=cls,
            geo=CLASS_GEO.get(cls, "Other"),
            asset_type=CLASS_TYPE.get(cls, "Other"),
            weight_pct=round(w, 2)
        )
        for cls, w in sorted(agg_class_weights.items(), key=lambda x: -x[1])
    ]

    equity_pct        = round(agg_typ.get("Equity", 0.0), 2)
    fixed_income_pct  = round(agg_typ.get("Fixed Income", 0.0), 2)
    alternatives_pct  = round(agg_typ.get("Alternatives", 0.0), 2)
    cash_pct          = round(agg_typ.get("Cash", 0.0), 2)
    us_equity_pct     = round(agg_class_weights.get("US_STOCKS", 0.0), 2)
    intl_equity_pct   = round(agg_class_weights.get("INTL_STOCKS", 0.0), 2)

    div_score = _diversification_score(agg_ticker_weights, agg_geo, agg_typ)
    flags     = _aggregate_flags(equity_pct, intl_equity_pct, fixed_income_pct,
                                  agg_tickers_sorted)

    aggregate = AggregateAnalysis(
        total_balance_cur=round(total_balance, 2),
        class_weights=agg_class_list,
        geo_weights={k: round(v, 2) for k, v in agg_geo.items()},
        type_weights={k: round(v, 2) for k, v in agg_typ.items()},
        ticker_weights=agg_tickers_sorted,
        equity_pct=equity_pct,
        fixed_income_pct=fixed_income_pct,
        alternatives_pct=alternatives_pct,
        cash_pct=cash_pct,
        us_equity_pct=us_equity_pct,
        intl_equity_pct=intl_equity_pct,
        diversification_score=div_score,
        flags=flags,
    )

    unique_tickers = len(agg_ticker_weights)

    return PortfolioAnalysis(
        aggregate=aggregate,
        accounts=account_analyses,
        n_accounts=len(account_analyses),
        n_tickers=unique_tickers,
    )


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys, os

    # Find Test profile
    script_dir = os.path.dirname(os.path.abspath(__file__))
    alloc_path = os.path.join(script_dir, "profiles", "Test", "allocation_yearly.json")
    if not os.path.isfile(alloc_path):
        print(f"Not found: {alloc_path}")
        sys.exit(1)

    with open(alloc_path) as f:
        alloc_cfg = json.load(f)

    starting = alloc_cfg.get("starting", {})
    analysis = compute_portfolio_analysis(alloc_cfg, starting)

    print(f"=== Portfolio Analysis ===")
    print(f"Total: ${analysis.aggregate.total_balance_cur:,.0f}")
    print(f"Diversification score: {analysis.aggregate.diversification_score}/100")
    print(f"\nAsset type breakdown:")
    for k, v in sorted(analysis.aggregate.type_weights.items(), key=lambda x: -x[1]):
        print(f"  {k:20s}  {v:.1f}%")
    print(f"\nGeography breakdown:")
    for k, v in sorted(analysis.aggregate.geo_weights.items(), key=lambda x: -x[1]):
        print(f"  {k:20s}  {v:.1f}%")
    print(f"\nTop tickers (portfolio-weighted):")
    for t in analysis.aggregate.ticker_weights[:5]:
        print(f"  {t.ticker:6s}  {t.weight_pct:.1f}%  ({t.asset_class})")
    print(f"\nFlags:")
    for f in analysis.aggregate.flags:
        print(f"  ⚠  {f}")
    print(f"\nPer-account:")
    for acct in analysis.accounts:
        print(f"  {acct.account:20s}  ${acct.balance_cur:>12,.0f}  "
              f"({acct.balance_pct:.1f}%)  "
              f"equity={acct.type_weights.get('Equity',0):.0f}%  "
              f"{'⚠ concentrated' if acct.is_concentrated else ''}")
