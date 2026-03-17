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
# ---------------------------------------------------------------------------
# Concentration thresholds — instrument-type aware
# ---------------------------------------------------------------------------
# Broad market ETFs are inherently diversified (3,700+ holdings for VTI).
# Flagging them at 20% is misleading. Sector/factor ETFs are concentrated
# by design and warrant a lower threshold. Individual stocks get the 4% rule.
#
# Phase 2 (asset model): add instrument_type to assets.json for a cleaner
# lookup. For now, classify by known tickers.

# Broad market ETFs — low concentration risk per unit of weight
BROAD_ETF_TICKERS = {
    "VTI", "ITOT", "SCHB", "IVV", "SPY", "VOO",   # US total/large market
    "VXUS", "IXUS", "SCHF",                          # international total
    "EFA",                                            # developed intl
    "BND", "AGG", "SCHZ",                            # total bond market
    "IEF", "TLT", "SHY",                             # treasury duration
    "SCHP", "TIP",                                    # TIPS
    "LQD",                                            # investment grade corp
    "GLD", "IAU",                                     # gold
    "DBC", "PDBC",                                    # broad commodities
}

# Sector/factor/thematic ETFs — concentrated by design
SECTOR_ETF_TICKERS = {
    "QQQ", "QQQM",                                   # Nasdaq-100 (tech-heavy)
    "VUG", "SCHG", "IWF",                            # US growth
    "VTV", "IWD",                                    # US value
    "XLK", "VGT", "FTEC",                            # technology sector
    "XLF", "VFH",                                    # financials sector
    "XLE", "VDE",                                    # energy sector
    "XLV", "VHT",                                    # health care
    "XLI", "VIS",                                    # industrials
    "VNQ", "IYR",                                    # real estate
    "EEM", "VWO",                                    # emerging markets
    "ARKK", "ARKW", "ARKG",                          # thematic/speculative
}

# Per-instrument-type thresholds
BROAD_ETF_THRESHOLD   = 0.40   # 40% — broad ETF, inherently diversified
SECTOR_ETF_THRESHOLD  = 0.25   # 25% — sector ETF, concentrated by design
STOCK_THRESHOLD       = 0.04   # 4%  — individual stock, industry consensus
DEFAULT_THRESHOLD     = 0.15   # 15% — anything not classified above

# Legacy aggregate thresholds
EQUITY_HEAVY_THRESHOLD   = 0.85
EQUITY_LIGHT_THRESHOLD   = 0.30
INTL_LOW_THRESHOLD       = 0.10
BOND_NEAR_ZERO_THRESHOLD = 0.05


def _concentration_threshold(ticker: str) -> float:
    """Return the appropriate concentration threshold for a given ticker."""
    if ticker in BROAD_ETF_TICKERS:
        return BROAD_ETF_THRESHOLD
    if ticker in SECTOR_ETF_TICKERS:
        return SECTOR_ETF_THRESHOLD
    # Heuristic: tickers with 1-4 uppercase letters and no numbers are likely
    # individual stocks; longer codes or codes with numbers are likely ETFs.
    import re
    if re.match(r'^[A-Z]{1,4}$', ticker):
        return STOCK_THRESHOLD
    return DEFAULT_THRESHOLD


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
    # ── Layer 5: look-through ─────────────────────────────────────────────
    true_stock_exposure: List[TickerWeight]  # actual stocks after ETF look-through
    sector_weights:      Dict[str, float]    # GICS sector breakdown via look-through
    holdings_as_of:      Optional[str]       # freshness date of holdings data
    look_through_coverage_pct: float         # % of portfolio covered by look-through


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


def _compute_look_through(
    ticker_weights: Dict[str, float],   # {ticker: weight_pct_of_portfolio}
    assets_cfg: Dict[str, Any],         # full assets dict from assets.json
    top_n: int = 20,
) -> tuple:
    """
    Compute true stock-level exposure and sector breakdown by looking through ETFs.

    For each ETF ticker in ticker_weights:
      true_stock_exposure[stock] += etf_portfolio_weight * stock_weight_in_etf

    Returns:
      (true_stock_exposure, sector_weights, holdings_as_of, coverage_pct)
    """
    true_exposure: Dict[str, float] = {}    # {stock_ticker: true_pct_of_portfolio}
    sector_exposure: Dict[str, float] = {}  # {sector: pct_of_portfolio}
    holdings_dates: List[str] = []
    covered_weight = 0.0
    total_weight = sum(ticker_weights.values())

    for etf_ticker, etf_portfolio_pct in ticker_weights.items():
        asset_data = assets_cfg.get(etf_ticker.upper(), {})
        top_holdings = asset_data.get("top_holdings", [])

        if not top_holdings:
            # No look-through data — skip (individual stock or no cache)
            continue

        covered_weight += etf_portfolio_pct
        as_of = asset_data.get("holdings_as_of", "")
        if as_of:
            holdings_dates.append(as_of)

        # Determine if this is an equity ETF — only do equity look-through
        # Bond/commodity ETFs produce treasury/futures holdings which pollute stock analysis
        instrument_type = asset_data.get("instrument_type", "")
        asset_class     = asset_data.get("class", "")
        is_equity_etf   = (
            instrument_type in ("broad_etf", "sector_etf") and
            asset_class in ("US_STOCKS", "INTL_STOCKS")
        )
        if not is_equity_etf:
            continue   # skip bond/commodity look-through for equity analysis

        # Skip patterns that indicate non-equity holdings (bond ISINs, cash, futures)
        _NON_EQUITY = {"CASH", "USD", "CASH_USD", "-", ""}
        _ISIN_PREFIX = ("US912", "US9128", "US91282")  # treasury ISINs

        # holdings weights are % of ETF — scale by ETF's portfolio weight
        for holding in top_holdings:
            stock     = holding.get("ticker", "").upper()
            h_weight  = float(holding.get("weight_pct", 0)) / 100.0  # ETF-relative
            sector    = holding.get("sector", "Unknown") or "Unknown"

            if not stock or h_weight <= 0:
                continue

            # Filter out non-equity holdings from look-through
            if stock in _NON_EQUITY:
                continue
            # Filter treasury ISINs (US912...) — these are bond positions not stocks
            if any(stock.startswith(pfx) for pfx in _ISIN_PREFIX):
                continue
            # Filter anything longer than 6 chars that's not a recognisable ticker
            # (ISINs are 12 chars, CUSIPs are 9 chars — real stock tickers are ≤5)
            if len(stock) > 6 and not stock.isalpha():
                continue

            # True portfolio exposure = ETF weight × stock weight within ETF
            true_pct = (etf_portfolio_pct / 100.0) * h_weight * 100.0

            true_exposure[stock] = true_exposure.get(stock, 0.0) + true_pct
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + true_pct

    # Sort by exposure descending
    sorted_stocks = sorted(true_exposure.items(), key=lambda x: -x[1])
    true_stock_weights = [
        TickerWeight(ticker=t, asset_class="look_through", weight_pct=round(w, 4))
        for t, w in sorted_stocks[:top_n]
    ]

    # Normalise sector weights to sum to 100 (only covered portion)
    sector_weights_pct = {
        k: round(v, 2) for k, v in
        sorted(sector_exposure.items(), key=lambda x: -x[1])
    }

    coverage_pct = round((covered_weight / total_weight * 100) if total_weight > 0 else 0, 1)
    holdings_as_of = max(holdings_dates) if holdings_dates else None

    # Look-through overlap flags
    # Find stocks appearing via multiple ETFs (phantom diversification)
    return true_stock_weights, sector_weights_pct, holdings_as_of, coverage_pct


def _look_through_flags(
    true_stock_weights: List[TickerWeight],
    ticker_weights: Dict[str, float],
    coverage_pct: float,
) -> List[str]:
    """Generate flags from look-through analysis."""
    flags = []

    if coverage_pct < 50:
        flags.append(
            f"Look-through coverage {coverage_pct:.0f}% — "
            f"holdings data missing for some ETFs"
        )
        return flags

    # Flag stocks with > 5% true exposure (real concentration)
    for tw in true_stock_weights[:10]:
        if tw.weight_pct > 5.0:
            flags.append(
                f"True exposure: {tw.ticker} is {tw.weight_pct:.1f}% of portfolio "
                f"via ETF look-through (threshold 5%)"
            )

    # Flag top-2 combined exposure > 10%
    if len(true_stock_weights) >= 2:
        top2 = true_stock_weights[0].weight_pct + true_stock_weights[1].weight_pct
        if top2 > 10.0:
            flags.append(
                f"Top 2 stocks ({true_stock_weights[0].ticker} + "
                f"{true_stock_weights[1].ticker}) = {top2:.1f}% of portfolio "
                f"via look-through — concentrated in market leaders"
            )

    return flags


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
    concentrated = [
        t for t in ticker_weights
        if t.weight_pct > _concentration_threshold(t.ticker) * 100
    ]
    for t in concentrated:
        thresh = _concentration_threshold(t.ticker)
        kind = ("broad ETF" if t.ticker in BROAD_ETF_TICKERS
                else "sector ETF" if t.ticker in SECTOR_ETF_TICKERS
                else "stock")
        flags.append(
            f"Concentrated: {t.ticker} is {t.weight_pct:.0f}% of portfolio "
            f"(threshold {thresh*100:.0f}% for {kind})"
        )
    return flags


def compute_portfolio_analysis(
    alloc_cfg: Dict[str, Any],
    starting_balances: Dict[str, float],
    ending_balances_cur: Optional[Dict[str, float]] = None,
    assets_cfg: Optional[Dict[str, Any]] = None,   # assets.json["assets"] for look-through
) -> PortfolioAnalysis:
    """
    Compute full portfolio analysis including ETF look-through (Layer 5).

    Args:
        alloc_cfg:            dict from allocation_yearly.json
        starting_balances:    {account_name: balance_in_current_usd}
        ending_balances_cur:  optional {account_name: balance} for current-$ ending weights
        assets_cfg:           optional assets.json["assets"] dict for ETF look-through.
                              If None, look-through fields will be empty.
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

        # Concentration: flag any ticker that exceeds its instrument-type threshold
        concentrated_tickers = [
            t for t in tickers_sorted
            if t.weight_pct > _concentration_threshold(t.ticker) * 100
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
            is_concentrated=len(concentrated_tickers) > 0,
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

    # ── Layer 5: ETF look-through ─────────────────────────────────────────
    # Build {ticker: portfolio_weight_pct} for look-through input
    ticker_portfolio_weights = {
        t: (w / total_balance * 100.0)
        for t, (w_pct, _cls) in agg_ticker_weights.items()
        for w in [w_pct / 100.0 * total_balance]
    }
    # Simpler: just use the weight_pct directly from agg_tickers_sorted
    ticker_pct_map = {tw.ticker: tw.weight_pct for tw in agg_tickers_sorted}

    if assets_cfg:
        true_stocks, sector_wts, holdings_as_of, coverage_pct = _compute_look_through(
            ticker_pct_map, assets_cfg
        )
        look_through_flags = _look_through_flags(true_stocks, ticker_pct_map, coverage_pct)
        flags = flags + look_through_flags
    else:
        true_stocks    = []
        sector_wts     = {}
        holdings_as_of = None
        coverage_pct   = 0.0

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
        true_stock_exposure=true_stocks,
        sector_weights=sector_wts,
        holdings_as_of=holdings_as_of,
        look_through_coverage_pct=coverage_pct,
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
