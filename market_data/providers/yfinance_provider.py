"""
market_data/providers/yfinance_provider.py
==========================================
Provider backed by yfinance (Yahoo Finance).

Capabilities:
- PriceProvider:   full OHLCV + dividend history (20yr, daily)
- HoldingsProvider: top holdings via .get_info() — limited depth (~10 items)
- SectorProvider:  GICS sector from .info dict

Rate limits: Yahoo Finance is unofficial and rate-limits aggressively.
We use a small sleep between calls and rely on the cache to avoid repeat hits.

Install: pip install yfinance
"""

from __future__ import annotations

import datetime
import time
from typing import List, Optional

from .base import (
    DailyBar, ETFHoldings, FatalProviderError, Holding,
    HoldingsProvider, PriceHistory, PriceProvider,
    ProviderError, SectorInfo, SectorProvider,
)

_SLEEP_BETWEEN_CALLS = 0.5   # seconds — be polite to Yahoo


class YFinancePriceProvider(PriceProvider):
    """Historical price + dividend history via yfinance."""

    @property
    def name(self) -> str:
        return "yfinance"

    def fetch_history(self, ticker: str, years: int = 20) -> PriceHistory:
        try:
            import yfinance as yf
            import pandas as pd
        except ImportError:
            raise FatalProviderError("yfinance not installed: pip install yfinance")

        end   = datetime.date.today()
        start = end - datetime.timedelta(days=365 * years + 5)  # +5 days buffer

        try:
            time.sleep(_SLEEP_BETWEEN_CALLS)
            raw = yf.download(
                ticker, start=start, end=end,
                auto_adjust=True,   # adjusted prices
                progress=False,
                actions=True,       # include dividends
            )
        except Exception as e:
            raise ProviderError(f"yfinance download failed for {ticker}: {e}")

        if raw is None or raw.empty:
            raise ProviderError(f"yfinance returned empty data for {ticker}")

        # Flatten MultiIndex columns from newer yfinance
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        # Build bars
        bars: List[DailyBar] = []
        close_col = "Close"
        for date, row in raw.iterrows():
            try:
                bar = DailyBar(
                    date     = date.date() if hasattr(date, "date") else date,
                    open     = float(row.get("Open",  0) or 0),
                    high     = float(row.get("High",  0) or 0),
                    low      = float(row.get("Low",   0) or 0),
                    close    = float(row.get(close_col, 0) or 0),
                    volume   = float(row.get("Volume", 0) or 0),
                    dividend = float(row.get("Dividends", 0) or 0),
                )
                if bar.close > 0:
                    bars.append(bar)
            except Exception:
                continue

        if len(bars) < 20:
            raise ProviderError(
                f"yfinance returned only {len(bars)} bars for {ticker} "
                f"(need ≥ 20)"
            )

        bars.sort(key=lambda b: b.date)

        return PriceHistory(
            ticker     = ticker.upper(),
            provider   = self.name,
            as_of_date = datetime.date.today(),
            bars       = bars,
        )


class YFinanceSectorProvider(SectorProvider):
    """GICS sector + instrument type classification via yfinance .info."""

    # Known broad ETFs — override yfinance's sector with "ETF"
    _BROAD_ETF = {
        "VTI","ITOT","SCHB","IVV","SPY","VOO",
        "VXUS","IXUS","SCHF","EFA",
        "BND","AGG","SCHZ","IEF","TLT","SHY",
        "SCHP","TIP","LQD","GLD","IAU","DBC","PDBC",
    }
    _SECTOR_ETF = {
        "QQQ","QQQM","VUG","SCHG","IWF","VTV","IWD",
        "XLK","VGT","FTEC","XLF","VFH","XLE","VDE",
        "XLV","VHT","XLI","VIS","VNQ","IYR","EEM","VWO",
        "ARKK","ARKW","ARKG",
    }

    @property
    def name(self) -> str:
        return "yfinance"

    def fetch_sector(self, ticker: str) -> SectorInfo:
        try:
            import yfinance as yf
        except ImportError:
            raise FatalProviderError("yfinance not installed")

        t = ticker.upper()

        # Determine instrument type from known lists first
        if t in self._BROAD_ETF:
            instrument_type = "broad_etf"
        elif t in self._SECTOR_ETF:
            instrument_type = "sector_etf"
        else:
            instrument_type = None   # resolve from .info below

        try:
            time.sleep(_SLEEP_BETWEEN_CALLS)
            info = yf.Ticker(ticker).info or {}
        except Exception as e:
            raise ProviderError(f"yfinance .info failed for {ticker}: {e}")

        if not info:
            raise ProviderError(f"yfinance returned empty info for {ticker}")

        sector   = info.get("sector", "")   or info.get("fundFamily", "") or "Unknown"
        industry = info.get("industry", "") or info.get("category", "")   or "Unknown"
        name     = info.get("longName", "") or info.get("shortName", "")  or ticker
        q_type   = info.get("quoteType", "").upper()

        # Resolve instrument type from quoteType if not known
        if instrument_type is None:
            if q_type in ("ETF", "MUTUALFUND"):
                category = (info.get("category", "") or "").lower()
                if "sector" in category or "industry" in category:
                    instrument_type = "sector_etf"
                else:
                    instrument_type = "broad_etf"
            elif q_type == "EQUITY":
                instrument_type = "stock"
            elif q_type in ("BOND", "FIXED_INCOME"):
                instrument_type = "bond_etf"
            else:
                instrument_type = "unknown"

        return SectorInfo(
            ticker          = t,
            name            = name,
            sector          = sector,
            industry        = industry,
            provider        = self.name,
            as_of_date      = datetime.date.today(),
            instrument_type = instrument_type,
        )


class YFinanceHoldingsProvider(HoldingsProvider):
    """
    Basic ETF holdings via yfinance.

    Coverage: ~10-15 top holdings from .info["holdings"] field.
    This is a fallback — ETFDotComProvider provides better depth.
    """

    @property
    def name(self) -> str:
        return "yfinance"

    def fetch_holdings(self, ticker: str) -> ETFHoldings:
        try:
            import yfinance as yf
        except ImportError:
            raise FatalProviderError("yfinance not installed")

        try:
            time.sleep(_SLEEP_BETWEEN_CALLS)
            t    = yf.Ticker(ticker)
            info = t.info or {}
        except Exception as e:
            raise ProviderError(f"yfinance .info failed for {ticker}: {e}")

        raw_holdings = info.get("holdings", [])
        if not raw_holdings:
            raise ProviderError(
                f"yfinance returned no holdings for {ticker} "
                f"(this is common — use ETFDotComProvider instead)"
            )

        holdings: List[Holding] = []
        for h in raw_holdings:
            symbol = (h.get("symbol") or h.get("holdingPercent", "")).strip().upper()
            name   = h.get("holdingName", "") or symbol
            pct    = float(h.get("holdingPercent", 0) or 0) * 100.0
            if symbol and pct > 0:
                holdings.append(Holding(
                    ticker     = symbol,
                    name       = name,
                    sector     = "",    # yfinance doesn't provide this here
                    weight_pct = round(pct, 4),
                ))

        if not holdings:
            raise ProviderError(f"yfinance: could not parse holdings for {ticker}")

        total_assets = float(info.get("totalAssets", 0) or 0) or None

        return ETFHoldings(
            etf_ticker   = ticker.upper(),
            as_of_date   = datetime.date.today(),
            provider     = self.name,
            total_assets = total_assets,
            holdings     = holdings,
            n_holdings   = len(holdings),
        )
