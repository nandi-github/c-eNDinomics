"""
market_data/cache/cache.py
==========================
File-based cache for market data.

Structure:
  market_data/cache/
    manifest.json          ← {key: {provider, timestamp, ttl_days, file}}
    data/
      holdings_VTI.json
      holdings_QQQ.json
      prices_VTI.json
      sector_VTI.json
      ...

Design:
- All reads go through cache before hitting any provider
- All provider results are written to cache immediately
- Stale entries are returned with a warning rather than failing silently
- Cache is always a valid fallback — stale data beats no data
"""

from __future__ import annotations

import datetime
import json
import os
import time
from typing import Any, Dict, List, Optional

from ..providers.base import ETFHoldings, Holding, PriceHistory, DailyBar, SectorInfo


# ---------------------------------------------------------------------------
# Cache manifest entry
# ---------------------------------------------------------------------------

class CacheEntry:
    def __init__(self, key: str, provider: str, timestamp: float,
                 ttl_days: int, filepath: str):
        self.key       = key
        self.provider  = provider
        self.timestamp = timestamp
        self.ttl_days  = ttl_days
        self.filepath  = filepath

    def is_fresh(self, ttl_days: Optional[int] = None) -> bool:
        ttl = ttl_days if ttl_days is not None else self.ttl_days
        age_days = (time.time() - self.timestamp) / 86400
        return age_days <= ttl

    def age_days(self) -> float:
        return (time.time() - self.timestamp) / 86400

    def to_dict(self) -> dict:
        return {
            "provider":  self.provider,
            "timestamp": self.timestamp,
            "ttl_days":  self.ttl_days,
            "filepath":  self.filepath,
        }


# ---------------------------------------------------------------------------
# Main cache class
# ---------------------------------------------------------------------------

class MarketDataCache:
    """
    File-backed cache for holdings, prices, and sector data.

    Usage:
        cache = MarketDataCache("/path/to/market_data/cache")
        holdings = cache.get_holdings("VTI", max_age_days=7)
        if holdings is None:
            holdings = provider.fetch_holdings("VTI")
            cache.put_holdings(holdings)
    """

    HOLDINGS_TTL = 7     # ETF holdings refresh weekly
    PRICES_TTL   = 1     # Prices refresh daily
    SECTOR_TTL   = 30    # Sector classification refreshes monthly

    def __init__(self, cache_dir: str):
        self.cache_dir    = cache_dir
        self.data_dir     = os.path.join(cache_dir, "data")
        self.manifest_path = os.path.join(cache_dir, "manifest.json")
        self._manifest: Dict[str, dict] = {}
        os.makedirs(self.data_dir, exist_ok=True)
        self._load_manifest()

    # ── Manifest ─────────────────────────────────────────────────────────────

    def _load_manifest(self):
        if os.path.isfile(self.manifest_path):
            try:
                with open(self.manifest_path) as f:
                    self._manifest = json.load(f)
            except Exception:
                self._manifest = {}

    def _save_manifest(self):
        with open(self.manifest_path, "w") as f:
            json.dump(self._manifest, f, indent=2)

    def _entry(self, key: str) -> Optional[CacheEntry]:
        m = self._manifest.get(key)
        if not m:
            return None
        return CacheEntry(
            key       = key,
            provider  = m.get("provider", "unknown"),
            timestamp = float(m.get("timestamp", 0)),
            ttl_days  = int(m.get("ttl_days", 7)),
            filepath  = m.get("filepath", ""),
        )

    def _register(self, key: str, provider: str, ttl_days: int, filepath: str):
        self._manifest[key] = {
            "provider":  provider,
            "timestamp": time.time(),
            "ttl_days":  ttl_days,
            "filepath":  filepath,
            "as_of":     datetime.date.today().isoformat(),
        }
        self._save_manifest()

    def _read_json(self, filepath: str) -> Optional[dict]:
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath) as f:
                return json.load(f)
        except Exception:
            return None

    def _write_json(self, filepath: str, data: dict):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    # ── Holdings ─────────────────────────────────────────────────────────────

    def get_holdings(self, ticker: str,
                     max_age_days: Optional[int] = None) -> Optional[ETFHoldings]:
        """Return cached holdings if fresh enough, else None."""
        key   = f"holdings_{ticker.upper()}"
        entry = self._entry(key)
        if entry is None:
            return None
        ttl = max_age_days if max_age_days is not None else self.HOLDINGS_TTL
        if not entry.is_fresh(ttl) and max_age_days is not None:
            return None   # caller wants fresh data only
        data = self._read_json(entry.filepath)
        if data is None:
            return None
        return self._deserialize_holdings(data)

    def put_holdings(self, holdings: ETFHoldings):
        key      = f"holdings_{holdings.etf_ticker}"
        filepath = os.path.join(self.data_dir, f"{key}.json")
        self._write_json(filepath, self._serialize_holdings(holdings))
        self._register(key, holdings.provider, self.HOLDINGS_TTL, filepath)

    def _serialize_holdings(self, h: ETFHoldings) -> dict:
        return {
            "etf_ticker":   h.etf_ticker,
            "as_of_date":   h.as_of_date.isoformat(),
            "provider":     h.provider,
            "total_assets": h.total_assets,
            "n_holdings":   h.n_holdings,
            "holdings":     [
                {"ticker": hi.ticker, "name": hi.name,
                 "sector": hi.sector, "weight_pct": hi.weight_pct}
                for hi in h.holdings
            ],
        }

    def _deserialize_holdings(self, d: dict) -> ETFHoldings:
        holdings = [
            Holding(ticker=h["ticker"], name=h.get("name", ""),
                    sector=h.get("sector", ""), weight_pct=h["weight_pct"])
            for h in d.get("holdings", [])
        ]
        return ETFHoldings(
            etf_ticker   = d["etf_ticker"],
            as_of_date   = datetime.date.fromisoformat(d["as_of_date"]),
            provider     = d["provider"],
            total_assets = d.get("total_assets"),
            holdings     = holdings,
            n_holdings   = d.get("n_holdings", len(holdings)),
        )

    # ── Prices ───────────────────────────────────────────────────────────────

    def get_prices(self, ticker: str,
                   max_age_days: Optional[int] = None) -> Optional[PriceHistory]:
        key   = f"prices_{ticker.upper()}"
        entry = self._entry(key)
        if entry is None:
            return None
        ttl = max_age_days if max_age_days is not None else self.PRICES_TTL
        if not entry.is_fresh(ttl) and max_age_days is not None:
            return None
        data = self._read_json(entry.filepath)
        if data is None:
            return None
        return self._deserialize_prices(data)

    def put_prices(self, prices: PriceHistory):
        key      = f"prices_{prices.ticker}"
        filepath = os.path.join(self.data_dir, f"{key}.json")
        self._write_json(filepath, self._serialize_prices(prices))
        self._register(key, prices.provider, self.PRICES_TTL, filepath)

    def _serialize_prices(self, p: PriceHistory) -> dict:
        return {
            "ticker":     p.ticker,
            "provider":   p.provider,
            "as_of_date": p.as_of_date.isoformat(),
            "bars": [
                {"date": b.date.isoformat(), "open": b.open, "high": b.high,
                 "low": b.low, "close": b.close, "volume": b.volume,
                 "dividend": b.dividend}
                for b in p.bars
            ],
        }

    def _deserialize_prices(self, d: dict) -> PriceHistory:
        bars = [
            DailyBar(
                date     = datetime.date.fromisoformat(b["date"]),
                open     = b["open"], high=b["high"], low=b["low"],
                close    = b["close"], volume=b["volume"],
                dividend = b.get("dividend", 0.0),
            )
            for b in d.get("bars", [])
        ]
        return PriceHistory(
            ticker     = d["ticker"],
            provider   = d["provider"],
            as_of_date = datetime.date.fromisoformat(d["as_of_date"]),
            bars       = bars,
        )

    # ── Sector ───────────────────────────────────────────────────────────────

    def get_sector(self, ticker: str,
                   max_age_days: Optional[int] = None) -> Optional[SectorInfo]:
        key   = f"sector_{ticker.upper()}"
        entry = self._entry(key)
        if entry is None:
            return None
        ttl = max_age_days if max_age_days is not None else self.SECTOR_TTL
        if not entry.is_fresh(ttl) and max_age_days is not None:
            return None
        data = self._read_json(entry.filepath)
        if data is None:
            return None
        return SectorInfo(
            ticker          = data["ticker"],
            name            = data.get("name", ""),
            sector          = data.get("sector", ""),
            industry        = data.get("industry", ""),
            provider        = data["provider"],
            as_of_date      = datetime.date.fromisoformat(data["as_of_date"]),
            instrument_type = data.get("instrument_type", "unknown"),
        )

    def put_sector(self, info: SectorInfo):
        key      = f"sector_{info.ticker}"
        filepath = os.path.join(self.data_dir, f"{key}.json")
        self._write_json(filepath, {
            "ticker": info.ticker, "name": info.name,
            "sector": info.sector, "industry": info.industry,
            "provider": info.provider,
            "as_of_date": info.as_of_date.isoformat(),
            "instrument_type": info.instrument_type,
        })
        self._register(key, info.provider, self.SECTOR_TTL, filepath)

    # ── Utility ──────────────────────────────────────────────────────────────

    def status(self) -> List[dict]:
        """Return cache status for all entries — for reporting and debugging."""
        rows = []
        for key, m in self._manifest.items():
            entry = CacheEntry(
                key       = key,
                provider  = m.get("provider", "?"),
                timestamp = float(m.get("timestamp", 0)),
                ttl_days  = int(m.get("ttl_days", 7)),
                filepath  = m.get("filepath", ""),
            )
            rows.append({
                "key":       key,
                "provider":  entry.provider,
                "age_days":  round(entry.age_days(), 1),
                "ttl_days":  entry.ttl_days,
                "fresh":     entry.is_fresh(),
                "as_of":     m.get("as_of", ""),
            })
        return sorted(rows, key=lambda r: r["key"])

    def clear(self, key_prefix: Optional[str] = None):
        """Remove cache entries. Pass prefix to remove a subset e.g. 'holdings_'."""
        keys_to_remove = [
            k for k in self._manifest
            if key_prefix is None or k.startswith(key_prefix)
        ]
        for key in keys_to_remove:
            filepath = self._manifest[key].get("filepath", "")
            if filepath and os.path.isfile(filepath):
                os.remove(filepath)
            del self._manifest[key]
        self._save_manifest()
        return len(keys_to_remove)
