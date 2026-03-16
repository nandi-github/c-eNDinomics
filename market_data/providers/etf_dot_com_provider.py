"""
market_data/providers/etf_dot_com_provider.py
=============================================
Provider backed by ETF.com holdings CSV download.

ETF.com publishes daily holdings CSVs for most US-listed ETFs at:
  https://www.etf.com/[TICKER]#holdings  (HTML)
  https://www.etf.com/etfanalytics/etf-finder-data/[TICKER]/holdings.csv

No API key required. Rate limit: be polite, use cache.

Coverage: top 250+ holdings with ticker, name, weight, sector.
This is the primary holdings provider — better depth than yfinance.

Note: URL patterns change occasionally. If this fails, the fallback
chain tries yfinance, then the stale cache.
"""

from __future__ import annotations

import csv
import datetime
import io
import time
import urllib.request
from typing import List, Optional

from .base import (
    ETFHoldings, FatalProviderError, Holding,
    HoldingsProvider, ProviderError,
)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; eNDinomics-market-data/1.0; "
    "+https://github.com/nandi-github/c-eNDinomics)"
)
_TIMEOUT_SECS = 15
_SLEEP_SECS   = 1.0   # between requests


class ETFDotComProvider(HoldingsProvider):
    """
    ETF holdings from ETF.com CSV download.

    Tries multiple URL patterns in sequence — ETF.com occasionally
    changes its URL structure. If all fail, raises ProviderError
    and the fetcher falls back to the next provider.
    """

    @property
    def name(self) -> str:
        return "etf_dot_com"

    def _url_candidates(self, ticker: str) -> List[str]:
        t = ticker.upper()
        return [
            # Pattern 1: direct CSV endpoint (most common)
            f"https://www.etf.com/etfanalytics/etf-finder-data/{t}/holdings.csv",
            # Pattern 2: alternate path format
            f"https://www.etf.com/{t}/holdings.csv",
            # Pattern 3: iShares (used by many Blackrock ETFs via ETF.com mirror)
            f"https://www.ishares.com/us/products/etf-product-data/{t}/1467271812596.ajax"
            f"?tab=holdings&fileType=csv",
        ]

    def _fetch_url(self, url: str) -> str:
        """Fetch URL and return content as string. Raises ProviderError on failure."""
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            time.sleep(_SLEEP_SECS)
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECS) as resp:
                if resp.status != 200:
                    raise ProviderError(f"HTTP {resp.status} from {url}")
                raw = resp.read()
                return raw.decode("utf-8", errors="replace")
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Request failed for {url}: {e}")

    def _parse_csv(self, content: str, ticker: str) -> List[Holding]:
        """
        Parse ETF.com holdings CSV into Holding list.
        Handles multiple column name variants.
        """
        holdings: List[Holding] = []

        # ETF.com sometimes prepends report header rows before the actual CSV header.
        # Skip lines until we find the first line containing column keywords.
        lines = content.splitlines()
        start_idx = 0
        for i, line in enumerate(lines):
            lower = line.lower()
            if any(kw in lower for kw in ("ticker", "symbol", "weight")):
                start_idx = i
                break

        csv_content = "\n".join(lines[start_idx:])
        reader = csv.DictReader(io.StringIO(csv_content))

        # Normalise column names — ETF.com uses different names for different funds
        def _get(row: dict, *keys: str, default="") -> str:
            for k in keys:
                # Case-insensitive lookup, guard against None keys
                for rk, rv in row.items():
                    if rk is not None and rk.strip().lower() == k.lower():
                        return str(rv or "").strip()
            return default

        for row in reader:
            try:
                sym    = _get(row, "Ticker", "Symbol", "ticker", "symbol")
                name   = _get(row, "Name", "Holding Name", "Description")
                sector = _get(row, "Sector", "GICS Sector", "Asset Class")
                wt_str = _get(row, "Weight (%)", "Weight(%)", "Weight", "% Weight",
                               "Weighting", "Portfolio Weight")

                # Clean weight string: "4.12%" → 4.12
                wt_str = wt_str.replace("%", "").replace(",", "").strip()
                if not sym or not wt_str:
                    continue
                wt = float(wt_str)
                if wt <= 0:
                    continue

                holdings.append(Holding(
                    ticker     = sym.upper(),
                    name       = name,
                    sector     = sector,
                    weight_pct = round(wt, 4),
                ))
            except (ValueError, KeyError):
                continue

        return holdings

    def fetch_holdings(self, ticker: str) -> ETFHoldings:
        last_error: Optional[Exception] = None

        for url in self._url_candidates(ticker):
            try:
                content  = self._fetch_url(url)
                holdings = self._parse_csv(content, ticker)

                if len(holdings) >= 5:
                    return ETFHoldings(
                        etf_ticker   = ticker.upper(),
                        as_of_date   = datetime.date.today(),
                        provider     = self.name,
                        total_assets = None,
                        holdings     = holdings,
                        n_holdings   = len(holdings),
                    )
                else:
                    last_error = ProviderError(
                        f"Parsed only {len(holdings)} holdings from {url}"
                    )

            except ProviderError as e:
                last_error = e
                continue

        raise ProviderError(
            f"ETFDotCom: all URL patterns failed for {ticker}. "
            f"Last error: {last_error}"
        )
