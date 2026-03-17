"""
market_data/scheduler/weekly_job.py
=====================================
Weekly market data refresh job.

Fetches holdings, prices, and sector data for all tickers in assets.json.
Writes results to the cache. Does NOT update assets.json directly —
that requires running asset_calibration.py + promote_model.py.

Usage:
    python -m market_data.scheduler.weekly_job               # from repo root
    python -m market_data.scheduler.weekly_job --dry-run     # fetch + show status, no write
    python -m market_data.scheduler.weekly_job --tickers VTI QQQ IEF
    python -m market_data.scheduler.weekly_job --force       # bypass TTL, refresh all

Cron example (weekly Sunday 6 AM):
    0 6 * * 0 cd /path/to/c-eNDinomics && python -m market_data.scheduler.weekly_job

launchd plist: see docs/launchd_market_data.plist
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from typing import List

# Resolve paths relative to this file
_HERE      = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))   # market_data/scheduler/ → market_data/ → repo root
_SRC_DIR   = os.path.join(_REPO_ROOT, "src")
sys.path.insert(0, _REPO_ROOT)   # so `market_data` package is importable

from market_data.cache.cache import MarketDataCache
from market_data.fetchers.holdings_fetcher import HoldingsFetcher
from market_data.fetchers.price_fetcher import PriceFetcher
from market_data.providers.base import ProviderError
from market_data.providers.etf_dot_com_provider import (
    ETFDotComProvider, YFinanceFundsDataProvider,
)
from market_data.providers.yfinance_provider import (
    YFinanceHoldingsProvider, YFinancePriceProvider, YFinanceSectorProvider,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR  = os.path.join(_REPO_ROOT, "market_data", "cache", "store")
_DEFAULT_ASSETS_JSON = os.path.join(_SRC_DIR, "config", "assets.json")

# TTLs — how old data can be before we consider it stale
HOLDINGS_MAX_AGE = 7    # days
PRICES_MAX_AGE   = 1    # days
SECTOR_MAX_AGE   = 30   # days


# ---------------------------------------------------------------------------
# Ticker source
# ---------------------------------------------------------------------------

def _tickers_from_assets_json(assets_path: str) -> List[str]:
    """Extract all ticker symbols from assets.json."""
    if not os.path.isfile(assets_path):
        print(f"[weekly_job] WARNING: assets.json not found at {assets_path}")
        return []
    with open(assets_path) as f:
        data = json.load(f)
    return sorted(data.get("assets", {}).keys())


def _is_etf(ticker: str, assets: dict) -> bool:
    """Return True if ticker looks like an ETF (not an individual stock)."""
    cls = assets.get(ticker, {}).get("class", "")
    # Individual stocks have class US_STOCKS but are single-company
    # Heuristic: tickers in the BROAD/SECTOR ETF lists are ETFs
    etf_classes = {"US_STOCKS", "INTL_STOCKS", "LONG_TREAS", "INT_TREAS",
                   "TIPS", "GOLD", "COMMOD"}
    individual_stocks = {"AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META",
                         "TSLA", "BRK.B", "JPM", "V"}
    return ticker not in individual_stocks


# ---------------------------------------------------------------------------
# Main job
# ---------------------------------------------------------------------------

def run_weekly_job(
    tickers: List[str],
    cache_dir: str,
    dry_run: bool = False,
    force: bool = False,
    fetch_holdings: bool = True,
    fetch_prices: bool = True,
    fetch_sectors: bool = True,
    assets_path: str = _DEFAULT_ASSETS_JSON,
) -> dict:
    """
    Run the weekly data refresh for the given tickers.

    Returns a summary dict with counts of successes/failures.
    """
    print(f"\n{'='*60}")
    print(f"  eNDinomics Market Data Weekly Job")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Tickers: {tickers}")
    print(f"  Dry-run: {dry_run}  Force: {force}")
    print(f"{'='*60}\n")

    if dry_run:
        print("[DRY RUN] Would fetch but not write. Showing cache status only.\n")

    os.makedirs(cache_dir, exist_ok=True)
    cache = MarketDataCache(cache_dir)

    # ── Print current cache status ─────────────────────────────────────────
    status = cache.status()
    if status:
        print("Current cache status:")
        for row in status:
            freshness = "✓" if row["fresh"] else "⚠ STALE"
            print(f"  {row['key']:30s}  {row['age_days']:5.1f}d  {freshness}  ({row['provider']})")
        print()

    if dry_run:
        return {"dry_run": True, "cache_entries": len(status)}

    # ── Build fetchers ──────────────────────────────────────────────────────
    holdings_fetcher = HoldingsFetcher(
        providers=[
            ETFDotComProvider(),
            YFinanceFundsDataProvider(),
            YFinanceHoldingsProvider(),
        ],
        cache=cache,
        default_max_age_days=HOLDINGS_MAX_AGE,
    )
    price_fetcher = PriceFetcher(
        providers=[YFinancePriceProvider()],
        cache=cache,
        default_max_age_days=PRICES_MAX_AGE,
    )
    sector_provider = YFinanceSectorProvider()

    summary = {
        "holdings": {"ok": 0, "fail": 0, "skip": 0},
        "prices":   {"ok": 0, "fail": 0, "skip": 0},
        "sectors":  {"ok": 0, "fail": 0, "skip": 0},
    }
    t0 = time.time()

    # ── Holdings ───────────────────────────────────────────────────────────
    if fetch_holdings:
        # Load assets to determine which tickers are ETFs
        assets_data = {}
        if os.path.isfile(assets_path):
            with open(assets_path) as f:
                assets_data = json.load(f).get("assets", {})

        etf_tickers = [t for t in tickers if _is_etf(t, assets_data)]
        print(f"── Holdings ({len(etf_tickers)} ETFs) ──────────────────────────")

        for ticker in etf_tickers:
            # Check if fresh enough already
            cached = cache.get_holdings(ticker, max_age_days=HOLDINGS_MAX_AGE)
            if cached and not force:
                age = (datetime.date.today() - cached.as_of_date).days
                print(f"  {ticker:6s}  SKIP (cached {age}d ago, {len(cached.holdings)} holdings)")
                summary["holdings"]["skip"] += 1
                continue

            try:
                result = holdings_fetcher.get(ticker, force_refresh=True)
                print(f"  {ticker:6s}  OK   ({len(result.holdings)} holdings, {result.provider})")
                summary["holdings"]["ok"] += 1
            except ProviderError as e:
                print(f"  {ticker:6s}  FAIL ({e})")
                summary["holdings"]["fail"] += 1

        print()

    # ── Prices ────────────────────────────────────────────────────────────
    if fetch_prices:
        print(f"── Prices ({len(tickers)} tickers) ─────────────────────────────")
        for ticker in tickers:
            cached = cache.get_prices(ticker, max_age_days=PRICES_MAX_AGE)
            if cached and not force:
                age = (datetime.date.today() - cached.as_of_date).days
                print(f"  {ticker:6s}  SKIP (cached {age}d ago, {len(cached.bars)} bars)")
                summary["prices"]["skip"] += 1
                continue

            try:
                result = price_fetcher.get(ticker, years=20, force_refresh=True)
                print(f"  {ticker:6s}  OK   ({len(result.bars)} bars, {result.provider})")
                summary["prices"]["ok"] += 1
            except ProviderError as e:
                print(f"  {ticker:6s}  FAIL ({e})")
                summary["prices"]["fail"] += 1

        print()

    # ── Sectors ──────────────────────────────────────────────────────────
    if fetch_sectors:
        print(f"── Sectors ({len(tickers)} tickers) ────────────────────────────")
        for ticker in tickers:
            cached = cache.get_sector(ticker, max_age_days=SECTOR_MAX_AGE)
            if cached and not force:
                age = (datetime.date.today() - cached.as_of_date).days
                print(f"  {ticker:6s}  SKIP (cached {age}d ago, {cached.sector})")
                summary["sectors"]["skip"] += 1
                continue

            try:
                import time as _t
                result = sector_provider.fetch_sector(ticker)
                cache.put_sector(result)
                print(f"  {ticker:6s}  OK   ({result.sector} / {result.instrument_type})")
                summary["sectors"]["ok"] += 1
            except ProviderError as e:
                print(f"  {ticker:6s}  FAIL ({e})")
                summary["sectors"]["fail"] += 1

        print()

    elapsed = time.time() - t0
    print(f"{'='*60}")
    print(f"  Done in {elapsed:.1f}s")
    for data_type, counts in summary.items():
        print(f"  {data_type:10s}: {counts['ok']} ok, {counts['skip']} skip, {counts['fail']} fail")
    print(f"{'='*60}\n")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Weekly market data refresh for eNDinomics"
    )
    p.add_argument("--tickers", nargs="*",
                   help="Tickers to fetch (default: all in assets.json)")
    p.add_argument("--cache-dir", default=_DEFAULT_CACHE_DIR,
                   help="Cache directory")
    p.add_argument("--assets", default=_DEFAULT_ASSETS_JSON,
                   help="Path to assets.json (for ticker discovery)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show cache status only, do not fetch")
    p.add_argument("--force", action="store_true",
                   help="Bypass TTL and refresh all data")
    p.add_argument("--no-holdings", action="store_true")
    p.add_argument("--no-prices",   action="store_true")
    p.add_argument("--no-sectors",  action="store_true")
    args = p.parse_args()

    tickers = args.tickers or _tickers_from_assets_json(args.assets)
    if not tickers:
        print("No tickers found. Pass --tickers or check --assets path.")
        sys.exit(1)

    summary = run_weekly_job(
        tickers        = tickers,
        cache_dir      = args.cache_dir,
        dry_run        = args.dry_run,
        force          = args.force,
        fetch_holdings = not args.no_holdings,
        fetch_prices   = not args.no_prices,
        fetch_sectors  = not args.no_sectors,
        assets_path    = args.assets,
    )

    # Exit non-zero if any failures
    total_fail = sum(v["fail"] for v in summary.values() if isinstance(v, dict))
    sys.exit(1 if total_fail > 0 else 0)


if __name__ == "__main__":
    main()
