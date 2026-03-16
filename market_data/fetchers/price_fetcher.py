"""
market_data/fetchers/price_fetcher.py
=====================================
Orchestrates provider priority chain for price history.
Same pattern as HoldingsFetcher.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from ..cache.cache import MarketDataCache
from ..providers.base import (
    FatalProviderError, PriceHistory, PriceProvider, ProviderError,
)


class PriceFetcher:
    """
    Fetches historical price data using a configurable provider priority chain.

    Usage:
        fetcher = PriceFetcher(
            providers=[YFinancePriceProvider()],
            cache=cache,
        )
        prices = fetcher.get("VTI", years=20)
    """

    def __init__(
        self,
        providers: List[PriceProvider],
        cache: MarketDataCache,
        default_max_age_days: int = 1,
    ):
        self.providers            = providers
        self.cache                = cache
        self.default_max_age_days = default_max_age_days
        self._fatal_providers: set = set()

    def get(
        self,
        ticker: str,
        years: int = 20,
        max_age_days: Optional[int] = None,
        force_refresh: bool = False,
    ) -> PriceHistory:
        """
        Return price history, using cache when fresh.

        Args:
            ticker:       ticker symbol
            years:        lookback years when fetching from provider
            max_age_days: max cache age to accept (default: 1 day)
            force_refresh: bypass cache

        Raises:
            ProviderError: if all providers fail AND no cache available
        """
        ttl    = max_age_days if max_age_days is not None else self.default_max_age_days
        ticker = ticker.upper()

        if not force_refresh:
            cached = self.cache.get_prices(ticker, max_age_days=ttl)
            if cached is not None:
                return cached

        errors: List[str] = []
        for provider in self.providers:
            if provider.name in self._fatal_providers:
                continue

            try:
                result = provider.fetch_history(ticker, years=years)
                self.cache.put_prices(result)
                return result

            except FatalProviderError as e:
                self._fatal_providers.add(provider.name)
                errors.append(f"{provider.name} [FATAL]: {e}")

            except ProviderError as e:
                errors.append(f"{provider.name}: {e}")

            except Exception as e:
                errors.append(f"{provider.name} [unexpected]: {e}")

        # Use stale cache before failing
        stale = self.cache.get_prices(ticker, max_age_days=365)
        if stale is not None:
            age = (datetime.date.today() - stale.as_of_date).days
            print(
                f"[PriceFetcher] WARNING: Using stale cache for {ticker} "
                f"({age} days old). Errors: {'; '.join(errors)}"
            )
            return stale

        raise ProviderError(
            f"PriceFetcher: all providers failed for {ticker}. "
            f"Errors: {'; '.join(errors)}"
        )

    def prefetch(
        self,
        tickers: List[str],
        years: int = 20,
        max_age_days: Optional[int] = None,
        force_refresh: bool = False,
    ) -> dict:
        """Fetch prices for multiple tickers. Errors collected, not raised."""
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = self.get(
                    ticker, years=years,
                    max_age_days=max_age_days,
                    force_refresh=force_refresh,
                )
            except ProviderError as e:
                results[ticker] = e
                print(f"[PriceFetcher] {ticker}: {e}")
        return results
