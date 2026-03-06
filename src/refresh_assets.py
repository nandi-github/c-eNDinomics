"""
refresh_assets.py
-----------------
Automatically regenerates assets.json from live Yahoo Finance data
when the file is missing or stale (older than STALE_DAYS).

- Scans ALL profiles' allocation_yearly.json to collect every ticker
  and its asset class mapping.
- Generates calibrated mu_annual, sigma_annual, yield_annual, corr_matrix
  from historical price data.
- Called at server startup from api.py via refresh_assets_if_stale().

Usage (standalone):
    python refresh_assets.py --out src/assets.json --years 20 --days 30
"""

import argparse
import datetime as dt
import json
import os
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALE_DAYS = 30          # regenerate if assets.json is older than this
LOOKBACK_YEARS = 20      # historical lookback for mu/sigma/corr calibration

# Qualified dividend ratio defaults by asset class
DEFAULT_QUALIFIED_RATIO: Dict[str, float] = {
    "US_STOCKS":   0.90,
    "INTL_STOCKS": 0.80,
    "LONG_TREAS":  0.00,
    "INT_TREAS":   0.00,
    "TIPS":        0.00,
    "GOLD":        0.00,
    "COMMOD":      0.00,
    "REIT":        0.20,
    "CASH":        0.00,
}

# Default expense ratios by ticker (well-known ETFs)
KNOWN_EXPENSE_RATIOS: Dict[str, float] = {
    "VTI":  0.0003,
    "QQQ":  0.0020,
    "VXUS": 0.0007,
    "TLT":  0.0015,
    "IEF":  0.0015,
    "SCHP": 0.0003,
    "GLD":  0.0040,
    "DBC":  0.0085,
    "VNQ":  0.0012,
    "BND":  0.0003,
}
DEFAULT_EXPENSE_RATIO  = 0.0010
DEFAULT_TRACKING_ERROR = 0.0100


# ---------------------------------------------------------------------------
# Ticker → class extraction from allocation_yearly.json
# ---------------------------------------------------------------------------

def extract_tickers_from_alloc(alloc_path: str) -> Dict[str, str]:
    """
    Walk allocation_yearly.json and return {ticker: asset_class} mapping.
    Looks inside begin.<account>.portfolios.<portfolio>.holdings_pct.<class>.[{ticker}].
    Also walks overrides for any additional tickers.
    """
    if not os.path.isfile(alloc_path):
        return {}

    with open(alloc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ticker_class: Dict[str, str] = {}

    def _walk_holdings(holdings_pct: dict):
        for cls, holdings in holdings_pct.items():
            if isinstance(holdings, list):
                for h in holdings:
                    ticker = h.get("ticker", "").strip().upper()
                    if ticker:
                        ticker_class[ticker] = cls

    # begin section
    for acct_data in data.get("begin", {}).values():
        for port_data in acct_data.get("portfolios", {}).values():
            _walk_holdings(port_data.get("holdings_pct", {}))

    # overrides section (may add tickers not in begin)
    for override in data.get("overrides", []):
        for key, val in override.items():
            if isinstance(val, dict) and "portfolios" in val:
                for port_data in val["portfolios"].values():
                    _walk_holdings(port_data.get("holdings_pct", {}))

    return ticker_class


def collect_tickers_from_all_profiles(profiles_root: str) -> Dict[str, str]:
    """
    Scan all profiles under profiles_root for allocation_yearly.json
    and merge their ticker→class mappings.
    """
    merged: Dict[str, str] = {}
    if not os.path.isdir(profiles_root):
        return merged

    for profile in os.listdir(profiles_root):
        alloc_path = os.path.join(profiles_root, profile, "allocation_yearly.json")
        tickers = extract_tickers_from_alloc(alloc_path)
        merged.update(tickers)

    return merged


# ---------------------------------------------------------------------------
# Staleness check
# ---------------------------------------------------------------------------

def is_stale(assets_path: str, stale_days: int = STALE_DAYS) -> bool:
    """Return True if assets.json is missing or older than stale_days."""
    if not os.path.isfile(assets_path):
        return True
    age_seconds = time.time() - os.path.getmtime(assets_path)
    return age_seconds > stale_days * 86400


# ---------------------------------------------------------------------------
# Market data helpers (mirrors generate_assets_from_market_data.py)
# ---------------------------------------------------------------------------

def _estimate_return_and_vol(prices) -> Tuple[float, float]:
    import pandas as pd
    prices = prices.dropna()
    if len(prices) < 64:
        return 0.0, 0.0
    rets = prices.pct_change().dropna()
    if rets.empty:
        return 0.0, 0.0
    mu_annual = float((1.0 + rets.mean()) ** 252 - 1.0)
    sigma_annual = float(np.sqrt(rets.var() * 252))
    return mu_annual, sigma_annual


def _estimate_dividend_yield(dividends, prices) -> float:
    import pandas as pd
    dividends = dividends.dropna()
    prices = prices.dropna()
    if prices.empty or dividends.empty:
        return 0.0
    last_date = dividends.index.max()
    trailing = dividends[dividends.index > last_date - pd.DateOffset(years=1)]
    if trailing.empty:
        return 0.0
    last_price = float(prices.iloc[-1])
    return float(trailing.sum() / last_price) if last_price > 0 else 0.0


def _download(ticker: str, start: dt.date, end: dt.date):
    """Download price + dividends via yfinance. Returns (prices, dividends)."""
    try:
        import yfinance as yf
        data = yf.download(ticker, start=start, end=end,
                           auto_adjust=False, progress=False)
        if data.empty:
            return None, None
        price_col = "Adj Close" if "Adj Close" in data.columns else "Close"
        prices = data[price_col]
        dividends = data.get("Dividends", None)
        import pandas as pd
        if dividends is None:
            dividends = pd.Series(dtype=float)
        return prices, dividends
    except Exception as e:
        print(f"  [refresh_assets] WARNING: download failed for {ticker}: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def build_assets_config(
    ticker_class: Dict[str, str],
    years: int = LOOKBACK_YEARS,
) -> Dict:
    """
    Build assets.json dict from live market data for all tickers in ticker_class.
    """
    import pandas as pd

    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=365 * years)

    tickers = sorted(ticker_class.keys())
    assets_cfg: Dict[str, Dict] = {}
    price_series_list = []
    valid_tickers = []

    for ticker in tickers:
        cls = ticker_class[ticker]
        print(f"  [refresh_assets] Fetching {ticker} ({cls}) ...")
        prices, dividends = _download(ticker, start_date, end_date)

        if prices is None or len(prices) < 64:
            print(f"  [refresh_assets] WARNING: insufficient data for {ticker}, using defaults.")
            mu_annual, sigma_annual, yield_annual = 0.0, 0.0, 0.0
        else:
            mu_annual, sigma_annual = _estimate_return_and_vol(prices)
            yield_annual = _estimate_dividend_yield(dividends, prices) if dividends is not None else 0.0
            price_series_list.append(prices.rename(ticker))
            valid_tickers.append(ticker)

        assets_cfg[ticker] = {
            "class": cls,
            "mu_annual": round(mu_annual, 6),
            "sigma_annual": round(sigma_annual, 6),
            "expense_ratio": KNOWN_EXPENSE_RATIOS.get(ticker, DEFAULT_EXPENSE_RATIO),
            "tracking_error": DEFAULT_TRACKING_ERROR,
            "dist": {
                "yield_annual": round(yield_annual, 6),
                "qualified_ratio": DEFAULT_QUALIFIED_RATIO.get(cls, 0.0),
            },
        }

    # Build correlation matrix on overlapping daily returns
    corr_matrix = np.eye(len(tickers)).tolist()
    if len(price_series_list) >= 2:
        price_df = pd.concat(price_series_list, axis=1, join="inner")
        rets = price_df.pct_change().dropna()
        if rets.shape[0] > 10:
            corr_full = np.eye(len(tickers))
            valid_idx = [tickers.index(t) for t in valid_tickers]
            sub_corr = rets.corr().values
            for i, vi in enumerate(valid_idx):
                for j, vj in enumerate(valid_idx):
                    corr_full[vi][vj] = sub_corr[i][j]
            corr_matrix = corr_full.tolist()

    # Build class-level fallback entries by averaging tickers in each class
    # These are used when allocation_yearly.json references a class with no specific ticker
    class_buckets: Dict[str, list] = {}
    for ticker, cfg in assets_cfg.items():
        cls = cfg["class"]
        if cfg["mu_annual"] != 0.0 or cfg["sigma_annual"] != 0.0:
            class_buckets.setdefault(cls, []).append(cfg)

    class_fallbacks: Dict[str, Dict] = {}
    for cls, cfgs in class_buckets.items():
        avg_mu    = float(np.mean([c["mu_annual"]    for c in cfgs]))
        avg_sigma = float(np.mean([c["sigma_annual"] for c in cfgs]))
        avg_yield = float(np.mean([c["dist"]["yield_annual"] for c in cfgs]))
        class_fallbacks[cls] = {
            "class": cls,
            "_fallback": True,
            "mu_annual": round(avg_mu, 6),
            "sigma_annual": round(avg_sigma, 6),
            "expense_ratio": DEFAULT_EXPENSE_RATIO,
            "tracking_error": DEFAULT_TRACKING_ERROR,
            "dist": {
                "yield_annual": round(avg_yield, 6),
                "qualified_ratio": DEFAULT_QUALIFIED_RATIO.get(cls, 0.0),
            },
        }

    return {
        "_generated": dt.datetime.now().isoformat(),
        "_lookback_years": years,
        "assets": assets_cfg,
        "class_fallbacks": class_fallbacks,
        "correlations": {
            "assets_order": tickers,
            "matrix": corr_matrix,
        },
    }


# ---------------------------------------------------------------------------
# Public API — called from api.py at startup
# ---------------------------------------------------------------------------

def refresh_assets_if_stale(
    assets_path: str,
    profiles_root: str,
    stale_days: int = STALE_DAYS,
    years: int = LOOKBACK_YEARS,
) -> bool:
    """
    Check if assets.json is stale or missing. If so, regenerate from live data.
    Returns True if regenerated, False if still fresh.
    Called once at server startup.
    """
    if not is_stale(assets_path, stale_days):
        print(f"[refresh_assets] assets.json is fresh (< {stale_days} days old). Skipping.")
        return False

    print(f"[refresh_assets] assets.json is stale or missing. Regenerating ...")
    ticker_class = collect_tickers_from_all_profiles(profiles_root)

    if not ticker_class:
        print("[refresh_assets] WARNING: no tickers found in any profile. Skipping.")
        return False

    print(f"[refresh_assets] Found {len(ticker_class)} tickers: {sorted(ticker_class.keys())}")

    try:
        config = build_assets_config(ticker_class, years=years)
        with open(assets_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"[refresh_assets] assets.json regenerated with {len(ticker_class)} tickers.")
        return True
    except Exception as e:
        print(f"[refresh_assets] ERROR during regeneration: {e}")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Regenerate assets.json from live market data")
    p.add_argument("--profiles", default="profiles", help="Path to profiles root directory")
    p.add_argument("--out", default="assets.json", help="Output assets.json path")
    p.add_argument("--years", type=int, default=LOOKBACK_YEARS, help="Lookback years")
    p.add_argument("--days", type=int, default=0,
                   help="Stale threshold in days (0 = force regenerate)")
    args = p.parse_args()

    ticker_class = collect_tickers_from_all_profiles(args.profiles)
    if not ticker_class:
        print("No tickers found. Check profiles directory.")
        return

    if args.days > 0 and not is_stale(args.out, args.days):
        print(f"assets.json is fresh (< {args.days} days). Use --days 0 to force.")
        return

    print(f"Regenerating assets.json for {len(ticker_class)} tickers ...")
    config = build_assets_config(ticker_class, years=args.years)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Done. Written to {args.out}")


if __name__ == "__main__":
    main()
