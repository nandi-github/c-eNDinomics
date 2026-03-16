"""
market_data/providers/base.py
==============================
Abstract interfaces for all market data providers.

Design principles:
- No eNDinomics imports — this package is standalone
- Each interface is minimal: one responsibility per class
- Concrete providers implement these; callers depend only on these
- ProviderError signals a recoverable failure (try next provider)
  FatalProviderError signals a configuration/auth failure (don't retry)
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data classes — plain data, no business logic
# ---------------------------------------------------------------------------

@dataclass
class Holding:
    """One stock/ETF position inside an ETF."""
    ticker:     str          # e.g. "AAPL"
    name:       str          # e.g. "Apple Inc."
    sector:     str          # GICS sector e.g. "Information Technology"
    weight_pct: float        # 0-100, percentage of ETF NAV


@dataclass
class ETFHoldings:
    """Complete holdings snapshot for one ETF."""
    etf_ticker:   str
    as_of_date:   datetime.date
    provider:     str                    # which provider served this
    total_assets: Optional[float]        # AUM in USD, None if unavailable
    holdings:     List[Holding]          # sorted by weight_pct descending
    n_holdings:   int = 0               # total holdings count (may exceed len(holdings))

    def __post_init__(self):
        if self.n_holdings == 0:
            self.n_holdings = len(self.holdings)
        # Keep sorted descending by weight
        self.holdings = sorted(self.holdings, key=lambda h: h.weight_pct, reverse=True)


@dataclass
class DailyBar:
    """One day of OHLCV data for a ticker."""
    date:     datetime.date
    open:     float
    high:     float
    low:      float
    close:    float          # adjusted close
    volume:   float
    dividend: float = 0.0


@dataclass
class PriceHistory:
    """Price + dividend history for one ticker."""
    ticker:     str
    provider:   str
    as_of_date: datetime.date
    bars:       List[DailyBar]   # sorted ascending by date

    @property
    def closes(self) -> List[float]:
        return [b.close for b in self.bars]

    @property
    def dates(self) -> List[datetime.date]:
        return [b.date for b in self.bars]

    @property
    def dividends(self) -> List[float]:
        return [b.dividend for b in self.bars]


@dataclass
class SectorInfo:
    """GICS sector and sub-sector classification for a ticker."""
    ticker:      str
    name:        str                  # company/fund name
    sector:      str                  # GICS sector
    industry:    str                  # GICS industry
    provider:    str
    as_of_date:  datetime.date
    instrument_type: str = "unknown"  # "broad_etf" | "sector_etf" | "stock" | "bond_etf" | "commodity_etf"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """
    Raised when a provider fails to return data for a specific request.
    The fetcher will try the next provider in the priority chain.
    """
    pass


class FatalProviderError(Exception):
    """
    Raised for configuration/auth failures that indicate the provider
    is not usable at all (missing API key, account suspended, etc.).
    The fetcher will skip this provider entirely for the session.
    """
    pass


class CacheError(Exception):
    """Raised when cache read/write fails."""
    pass


# ---------------------------------------------------------------------------
# Abstract provider interfaces
# ---------------------------------------------------------------------------

class HoldingsProvider(ABC):
    """Provides ETF holdings (top stocks within an ETF)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier e.g. 'etf_dot_com'."""
        ...

    @property
    def requires_api_key(self) -> bool:
        return False

    @property
    def api_key_env_var(self) -> Optional[str]:
        """Environment variable name for API key, if required."""
        return None

    @abstractmethod
    def fetch_holdings(self, ticker: str) -> ETFHoldings:
        """
        Fetch current ETF holdings.

        Args:
            ticker: ETF ticker symbol e.g. "VTI"

        Returns:
            ETFHoldings with at least top-10 positions

        Raises:
            ProviderError: if fetch fails (network, parsing, rate limit)
            FatalProviderError: if provider is misconfigured
        """
        ...

    def supported_tickers(self) -> List[str]:
        """
        Tickers this provider can reliably serve.
        Empty list means provider claims to support all tickers.
        """
        return []


class PriceProvider(ABC):
    """Provides historical price and dividend data."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def requires_api_key(self) -> bool:
        return False

    @abstractmethod
    def fetch_history(self, ticker: str, years: int = 20) -> PriceHistory:
        """
        Fetch historical daily OHLCV + dividends.

        Args:
            ticker: ticker symbol
            years:  lookback window in years

        Returns:
            PriceHistory with adjusted closes and dividends

        Raises:
            ProviderError: if fetch fails
            FatalProviderError: if provider is misconfigured
        """
        ...


class SectorProvider(ABC):
    """Provides GICS sector classification and instrument type."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def fetch_sector(self, ticker: str) -> SectorInfo:
        """
        Fetch sector and instrument type classification.

        Raises:
            ProviderError: if classification unavailable
        """
        ...
