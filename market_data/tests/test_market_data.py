"""
market_data/tests/test_market_data.py
======================================
Test suite for the market_data package.

Tests are structured in three levels:
  1. Unit tests — test data classes and cache logic (no network, always pass)
  2. Provider tests — test provider logic with mocked HTTP (no network)
  3. Integration tests — test against real APIs (skipped by default, need network)

Run unit tests only (CI-safe):
    python3 -B -m pytest market_data/tests/ -v -k "not integration"

Run all tests including network:
    python3 -B -m pytest market_data/tests/ -v --integration
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add repo root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _ROOT)

from market_data.cache.cache import MarketDataCache
from market_data.fetchers.holdings_fetcher import HoldingsFetcher
from market_data.fetchers.price_fetcher import PriceFetcher
from market_data.providers.base import (
    DailyBar, ETFHoldings, Holding, PriceHistory,
    ProviderError, SectorInfo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_holdings(ticker="VTI", n=10) -> ETFHoldings:
    holdings = [
        Holding(
            ticker=f"STOCK{i}", name=f"Company {i}",
            sector="Technology", weight_pct=round(10.0 / n * (n - i + 1), 2),
        )
        for i in range(1, n + 1)
    ]
    return ETFHoldings(
        etf_ticker   = ticker,
        as_of_date   = datetime.date.today(),
        provider     = "test",
        total_assets = 1_000_000_000.0,
        holdings     = holdings,
    )


def _make_prices(ticker="VTI", n=100) -> PriceHistory:
    start = datetime.date(2020, 1, 2)
    bars  = [
        DailyBar(
            date=start + datetime.timedelta(days=i),
            open=100.0 + i * 0.1, high=101.0 + i * 0.1,
            low=99.0 + i * 0.1,   close=100.5 + i * 0.1,
            volume=1_000_000.0,
        )
        for i in range(n)
    ]
    return PriceHistory(
        ticker=ticker, provider="test",
        as_of_date=datetime.date.today(), bars=bars,
    )


# ---------------------------------------------------------------------------
# Unit: Data classes
# ---------------------------------------------------------------------------

class TestDataClasses(unittest.TestCase):

    def test_holdings_sorted_descending(self):
        h = _make_holdings("VTI", 5)
        weights = [x.weight_pct for x in h.holdings]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_price_history_properties(self):
        p = _make_prices("VTI", 50)
        self.assertEqual(len(p.closes), 50)
        self.assertEqual(len(p.dates), 50)
        self.assertEqual(len(p.dividends), 50)
        self.assertGreater(p.closes[-1], p.closes[0])   # prices went up

    def test_holdings_n_holdings(self):
        h = _make_holdings("QQQ", 20)
        self.assertEqual(h.n_holdings, 20)
        self.assertEqual(len(h.holdings), 20)


# ---------------------------------------------------------------------------
# Unit: Cache
# ---------------------------------------------------------------------------

class TestCache(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache  = MarketDataCache(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_holdings_roundtrip(self):
        original = _make_holdings("VTI", 15)
        self.cache.put_holdings(original)
        retrieved = self.cache.get_holdings("VTI")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.etf_ticker, "VTI")
        self.assertEqual(len(retrieved.holdings), 15)
        self.assertEqual(retrieved.holdings[0].ticker, original.holdings[0].ticker)

    def test_prices_roundtrip(self):
        original = _make_prices("IEF", 200)
        self.cache.put_prices(original)
        retrieved = self.cache.get_prices("IEF")
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved.bars), 200)
        self.assertAlmostEqual(retrieved.bars[0].close, original.bars[0].close)

    def test_sector_roundtrip(self):
        info = SectorInfo(
            ticker="VTI", name="Vanguard Total Stock Market ETF",
            sector="Diversified", industry="ETF",
            provider="test", as_of_date=datetime.date.today(),
            instrument_type="broad_etf",
        )
        self.cache.put_sector(info)
        retrieved = self.cache.get_sector("VTI")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.instrument_type, "broad_etf")

    def test_cache_miss_returns_none(self):
        result = self.cache.get_holdings("NONEXISTENT")
        self.assertIsNone(result)

    def test_stale_returns_none_with_strict_ttl(self):
        import time
        h = _make_holdings("SPY")
        self.cache.put_holdings(h)
        # Manually backdate the manifest entry
        self.cache._manifest["holdings_SPY"]["timestamp"] = time.time() - (10 * 86400)
        self.cache._save_manifest()
        # Fresh cache (< 7 days) → miss
        result = self.cache.get_holdings("SPY", max_age_days=7)
        self.assertIsNone(result)
        # Lenient cache (< 30 days) → hit
        result = self.cache.get_holdings("SPY", max_age_days=30)
        self.assertIsNotNone(result)

    def test_status_returns_entries(self):
        self.cache.put_holdings(_make_holdings("VTI"))
        self.cache.put_prices(_make_prices("VTI"))
        status = self.cache.status()
        self.assertEqual(len(status), 2)
        keys = [s["key"] for s in status]
        self.assertIn("holdings_VTI", keys)
        self.assertIn("prices_VTI", keys)

    def test_clear_by_prefix(self):
        self.cache.put_holdings(_make_holdings("VTI"))
        self.cache.put_holdings(_make_holdings("QQQ"))
        self.cache.put_prices(_make_prices("VTI"))
        removed = self.cache.clear("holdings_")
        self.assertEqual(removed, 2)
        self.assertEqual(len(self.cache.status()), 1)   # only prices_VTI remains

    def test_manifest_persists(self):
        self.cache.put_holdings(_make_holdings("TLT"))
        # Create new cache instance pointing to same dir
        cache2 = MarketDataCache(self.tmpdir)
        result = cache2.get_holdings("TLT")
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# Unit: Fetcher with mocked providers
# ---------------------------------------------------------------------------

class TestHoldingsFetcher(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache  = MarketDataCache(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_uses_cache_when_fresh(self):
        # Pre-populate cache
        self.cache.put_holdings(_make_holdings("VTI"))

        mock_provider = MagicMock()
        mock_provider.name = "mock"
        fetcher = HoldingsFetcher([mock_provider], self.cache)

        result = fetcher.get("VTI")
        # Provider should NOT be called — cache is fresh
        mock_provider.fetch_holdings.assert_not_called()
        self.assertEqual(result.etf_ticker, "VTI")

    def test_calls_provider_on_cache_miss(self):
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.fetch_holdings.return_value = _make_holdings("QQQ")

        fetcher = HoldingsFetcher([mock_provider], self.cache)
        result  = fetcher.get("QQQ")

        mock_provider.fetch_holdings.assert_called_once_with("QQQ")
        self.assertEqual(result.etf_ticker, "QQQ")
        # Should now be in cache
        self.assertIsNotNone(self.cache.get_holdings("QQQ"))

    def test_falls_back_to_second_provider(self):
        failing = MagicMock()
        failing.name = "failing"
        failing.fetch_holdings.side_effect = ProviderError("timeout")

        working = MagicMock()
        working.name = "working"
        working.fetch_holdings.return_value = _make_holdings("IEF")

        fetcher = HoldingsFetcher([failing, working], self.cache)
        result  = fetcher.get("IEF")

        self.assertEqual(result.etf_ticker, "IEF")
        failing.fetch_holdings.assert_called_once()
        working.fetch_holdings.assert_called_once()

    def test_returns_stale_cache_when_all_fail(self):
        import time
        # Put stale entry in cache
        self.cache.put_holdings(_make_holdings("TLT"))
        self.cache._manifest["holdings_TLT"]["timestamp"] = time.time() - (20 * 86400)
        self.cache._save_manifest()

        failing = MagicMock()
        failing.name = "failing"
        failing.fetch_holdings.side_effect = ProviderError("all down")

        fetcher = HoldingsFetcher([failing], self.cache, default_max_age_days=7)
        # Fresh cache miss (stale) + provider fail → returns stale cache
        result = fetcher.get("TLT")
        self.assertEqual(result.etf_ticker, "TLT")

    def test_raises_when_all_fail_and_no_cache(self):
        failing = MagicMock()
        failing.name = "failing"
        failing.fetch_holdings.side_effect = ProviderError("down")

        fetcher = HoldingsFetcher([failing], self.cache)
        with self.assertRaises(ProviderError):
            fetcher.get("NONEXISTENT")

    def test_prefetch_collects_errors(self):
        good = MagicMock(); good.name = "good"
        good.fetch_holdings.side_effect = lambda t: _make_holdings(t)

        bad = MagicMock(); bad.name = "bad"

        fetcher = HoldingsFetcher([good], self.cache)
        # Patch second call to fail
        call_count = [0]
        def side_effect(ticker):
            call_count[0] += 1
            if ticker == "FAIL":
                raise ProviderError("nope")
            return _make_holdings(ticker)
        good.fetch_holdings.side_effect = side_effect

        results = fetcher.prefetch(["VTI", "FAIL"])
        self.assertIsInstance(results["VTI"], ETFHoldings)
        self.assertIsInstance(results["FAIL"], ProviderError)


# ---------------------------------------------------------------------------
# Unit: ETFDotCom CSV parser
# ---------------------------------------------------------------------------

class TestETFDotComParser(unittest.TestCase):

    def test_parse_standard_csv(self):
        from market_data.providers.etf_dot_com_provider import _parse_csv_holdings

        csv_content = """Ticker,Name,Weight (%),Sector
AAPL,Apple Inc.,7.25,Information Technology
MSFT,Microsoft Corp.,6.89,Information Technology
AMZN,Amazon.com Inc.,3.45,Consumer Discretionary
NVDA,NVIDIA Corp.,5.12,Information Technology
GOOGL,Alphabet Inc.,4.33,Communication Services
"""
        holdings = _parse_csv_holdings(csv_content)
        self.assertEqual(len(holdings), 5)
        # Sorted by weight descending
        self.assertEqual(holdings[0].ticker, "AAPL")
        self.assertAlmostEqual(holdings[0].weight_pct, 7.25)
        self.assertEqual(holdings[0].sector, "Information Technology")

    def test_parse_with_header_offset(self):
        from market_data.providers.etf_dot_com_provider import _parse_csv_holdings

        csv_content = """ETF Holdings Report
Generated: 2026-03-16

Ticker,Name,Weight (%)
VTI_HOLD,Vanguard Total Stock Market,100.00
"""
        holdings = _parse_csv_holdings(csv_content)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].ticker, "VTI_HOLD")

    def test_skips_zero_weight_rows(self):
        from market_data.providers.etf_dot_com_provider import _parse_csv_holdings

        csv_content = """Ticker,Name,Weight (%)
AAPL,Apple,5.0
CASH,Cash,0.0
MSFT,Microsoft,3.5
"""
        holdings = _parse_csv_holdings(csv_content)
        self.assertEqual(len(holdings), 2)
        tickers = [h.ticker for h in holdings]
        self.assertNotIn("CASH", tickers)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
