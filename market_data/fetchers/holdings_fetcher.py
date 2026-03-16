"""
market_data/fetchers/holdings_fetcher.py
========================================
Orchestrates the provider priority chain for ETF holdings.

Priority order (default):
  1. ETFDotComProvider  — best depth, no API key
  2. YFinanceHoldingsProvider — basic holdings, fallback

When all providers fail:
  - Returns stale cache if available (with warning)
  - Raises ProviderError only if cache is also empty

This means the caller always gets data or a clear error — never silent zeros.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from ..cache.cache import MarketDataCache
from ..providers.base import (
    ETFHoldings, FatalProviderError, HoldingsProvider, ProviderError,
)


class HoldingsFetcher:
    """
    Fetches ETF holdings using a configurable provider priority chain.

    Usage:
        cache   = MarketDataCache(cache_dir)
        fetcher = HoldingsFetcher(
            providers=[ETFDotComProvider(), YFinanceHoldingsProvider()],
            cache=cache,
        )
        holdings = fetcher.get("VTI")           # fresh (< 7 days)
        holdings = fetcher.get("VTI", max_age_days=30)  # allow stale
    """

    def __init__(
        self,
        providers: List[HoldingsProvider],
        cache: MarketDataCache,
        default_max_age_days: int = 7,
    ):
        self.providers            = providers
        self.cache                = cache
        self.default_max_age_days = default_max_age_days
        self._fatal_providers: set = set()   # providers that failed fatally

    def get(
        self,
        ticker: str,
        max_age_days: Optional[int] = None,
        force_refresh: bool = False,
    ) -> ETFHoldings:
        """
        Return ETF holdings, using cache when fresh.

        Args:
            ticker:        ETF ticker e.g. "VTI"
            max_age_days:  max cache age to accept (default: 7)
            force_refresh: bypass cache and fetch from provider

        Returns:
            ETFHoldings

        Raises:
            ProviderError: if all providers fail AND cache is empty
        """
        ttl = max_age_days if max_age_days is not None else self.default_max_age_days
        ticker = ticker.upper()

        # 1. Check fresh cache (unless force_refresh)
        if not force_refresh:
            cached = self.cache.get_holdings(ticker, max_age_days=ttl)
            if cached is not None:
                return cached

        # 2. Try providers in priority order
        errors: List[str] = []
        for provider in self.providers:
            if provider.name in self._fatal_providers:
                continue   # skip providers that failed fatally this session

            try:
                result = provider.fetch_holdings(ticker)
                self.cache.put_holdings(result)
                return result

            except FatalProviderError as e:
                self._fatal_providers.add(provider.name)
                errors.append(f"{provider.name} [FATAL]: {e}")
                continue

            except ProviderError as e:
                errors.append(f"{provider.name}: {e}")
                continue

            except Exception as e:
                errors.append(f"{provider.name} [unexpected]: {e}")
                continue

        # 3. All providers failed — use stale cache rather than failing completely
        stale = self.cache.get_holdings(ticker, max_age_days=365)
        if stale is not None:
            age = round((datetime.date.today() - stale.as_of_date).days, 1)
            print(
                f"[HoldingsFetcher] WARNING: Using stale cache for {ticker} "
                f"({age} days old). Provider errors: {'; '.join(errors)}"
            )
            return stale

        raise ProviderError(
            f"HoldingsFetcher: all providers failed for {ticker} and no cache available. "
            f"Errors: {'; '.join(errors)}"
        )

    def prefetch(
        self,
        tickers: List[str],
        max_age_days: Optional[int] = None,
        force_refresh: bool = False,
    ) -> dict:
        """
        Fetch holdings for multiple tickers. Returns {ticker: ETFHoldings | Exception}.
        Errors are collected rather than raised so a single bad ticker doesn't
        block the whole batch.
        """
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = self.get(
                    ticker,
                    max_age_days=max_age_days,
                    force_refresh=force_refresh,
                )
            except ProviderError as e:
                results[ticker] = e
                print(f"[HoldingsFetcher] {ticker}: {e}")
        return results
