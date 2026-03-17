# Market Data Layer — Architecture Spec
## eNDinomics Grand Plan | Component: Asset Model | Version 1.0 | March 2026

---

## 1. The Problem

ETF look-through analysis requires live holdings data. Static lookups are wrong
by design — the ETF manager's job is to rebalance. A VTI holdings table from
6 months ago misrepresents current exposure.

The same applies to return calibration: mu/sigma estimates from a fixed CSV
go stale. Regime changes (rate environment, sector rotation) shift the
distribution of returns meaningfully over 6-12 month windows.

Both problems have the same solution: a **market data layer** that runs
independently of the simulation, caches results locally, and feeds the asset
model.

---

## 2. Core Design Principles

1. **Separation of concerns — strictly enforced**
   - Data fetching: `market_data/` package — knows about APIs, not about eNDinomics
   - Asset model update: `asset_calibration.py` — reads from cache, writes to assets.json
   - Simulation: `simulation_core.py` — reads assets.json only, zero network calls
   - No network calls at simulation time. Ever.

2. **Provider agnosticism**
   - Each data type (ETF holdings, price history, sector classification) has an
     abstract interface
   - Free providers implemented first; paid providers drop in without changing
     downstream code
   - Provider priority: primary → fallback → cache (never fail silently)

3. **Cache-first, API-second**
   - Every fetch writes to `market_data/cache/YYYY-MM-DD/`
   - Cache TTL is configurable per data type (holdings: 7 days, prices: 1 day)
   - Simulation never touches the API — it reads assets.json only
   - Stale cache is preferred over a failed API call

4. **Transparency**
   - Every snapshot records `assets_model_version` and per-data-type
     `last_updated` timestamps
   - UI shows "Holdings data as of YYYY-MM-DD" in Portfolio Analysis
   - Promotion log records which provider served which data

5. **Human-gated promotion**
   - `asset_calibration.py` writes a candidate model to `asset-model/vX.Y.Z/`
   - `promote_model.py` validates bounds, SPD, required tickers, then requires
     explicit human confirmation before writing to `src/config/assets.json`
   - No auto-overwrite. Ever.

---

## 3. File Structure

```
root/
  market_data/                    ← standalone package, no eNDinomics imports
    __init__.py
    providers/
      __init__.py
      base.py                     ← abstract interfaces
      yfinance_provider.py        ← free: prices, basic holdings
      etf_dot_com_provider.py     ← free: detailed ETF holdings CSV
      openbb_provider.py          ← free: broad financial data
      iex_provider.py             ← paid tier 1: IEX Cloud
      refinitiv_provider.py       ← paid tier 2: Refinitiv/LSEG
    cache/
      YYYY-MM-DD/
        holdings_VTI.json
        holdings_QQQ.json
        prices_2yr.parquet
        sectors.json
      cache_manifest.json         ← {data_type: {ticker: {provider, timestamp, ttl}}}
    fetchers/
      holdings_fetcher.py         ← orchestrates provider priority for ETF holdings
      price_fetcher.py            ← orchestrates provider priority for price history
      sector_fetcher.py           ← GICS sector classification per ticker
    scheduler/
      weekly_job.py               ← cron-friendly entry point
      last_run.json               ← {data_type: last_success_timestamp}
    tests/
      test_providers.py
      test_cache.py
      test_fetchers.py

  src/
    asset_calibration.py          ← reads from market_data/cache, writes candidate model
    promote_model.py              ← validates + gates write to assets.json
    asset-model/
      v1.0.0/
        assets.json               ← Layers 1-4 (current)
        features.msgpack          ← Layers 5-11 (look-through, sector, etc.)
        manifest.json
```

---

## 4. Abstract Provider Interface

```python
# market_data/providers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import datetime

@dataclass
class Holding:
    ticker: str           # e.g. "AAPL"
    name:   str           # e.g. "Apple Inc."
    sector: str           # GICS sector e.g. "Information Technology"
    weight_pct: float     # 0-100, % of ETF

@dataclass
class ETFHoldings:
    etf_ticker:   str
    as_of_date:   datetime.date
    provider:     str
    total_assets: Optional[float]   # AUM in USD
    holdings:     List[Holding]     # sorted by weight desc

@dataclass
class PriceHistory:
    ticker:     str
    provider:   str
    as_of_date: datetime.date
    dates:      List[datetime.date]
    closes:     List[float]
    dividends:  List[float]

class HoldingsProvider(ABC):
    name: str                    # "yfinance" | "etf_dot_com" | "iex" | ...

    @abstractmethod
    def fetch_holdings(self, ticker: str) -> ETFHoldings:
        """Fetch current ETF holdings. Raises ProviderError on failure."""
        ...

    @abstractmethod
    def supported_tickers(self) -> List[str]:
        """Tickers this provider can serve. Empty = claims to support all."""
        ...

    @property
    def requires_api_key(self) -> bool:
        return False

class PriceProvider(ABC):
    name: str

    @abstractmethod
    def fetch_history(self, ticker: str, years: int = 20) -> PriceHistory:
        ...

class ProviderError(Exception):
    """Raised when a provider fails to return data."""
    pass
```

---

## 5. Provider Priority System

```python
# market_data/fetchers/holdings_fetcher.py

class HoldingsFetcher:
    """
    Fetches ETF holdings using provider priority chain.
    Falls back through providers; uses cache if all fail.
    """
    def __init__(self, providers: List[HoldingsProvider], cache: Cache):
        self.providers = providers   # ordered by priority
        self.cache = cache

    def get(self, ticker: str, max_age_days: int = 7) -> ETFHoldings:
        # 1. Check cache first
        cached = self.cache.get_holdings(ticker, max_age_days)
        if cached:
            return cached

        # 2. Try providers in priority order
        errors = []
        for provider in self.providers:
            try:
                result = provider.fetch_holdings(ticker)
                self.cache.put_holdings(result)
                return result
            except ProviderError as e:
                errors.append(f"{provider.name}: {e}")
                continue

        # 3. Use stale cache rather than fail completely
        stale = self.cache.get_holdings(ticker, max_age_days=365)
        if stale:
            print(f"[WARN] Using stale holdings for {ticker}: {errors}")
            return stale

        raise ProviderError(f"All providers failed for {ticker}: {errors}")
```

**Default provider stack (free tier):**
```python
providers = [
    ETFDotComProvider(),     # best holdings detail, no API key
    YFinanceProvider(),      # broad coverage, rate-limited
    OpenBBProvider(),        # fallback, community-maintained
]
```

**Paid tier drop-in (no other code changes):**
```python
providers = [
    IEXCloudProvider(api_key=os.environ["IEX_KEY"]),   # prepend, takes priority
    ETFDotComProvider(),
    YFinanceProvider(),
]
```

---

## 6. Data Types and Update Frequency

| Data type | TTL | Primary (free) | Paid alternative |
|-----------|-----|----------------|-----------------|
| ETF holdings | 7 days | ETF.com CSV | iShares API, IEX |
| Price history | 1 day | yfinance | Refinitiv, Bloomberg |
| GICS sector | 30 days | yfinance `.info` | MSCI direct |
| Dividend history | 7 days | yfinance | IEX Cloud |
| Options flow | 1 day | (not free) | CBOE, IEX |
| Wyckoff/CMF signals | 1 day | computed from prices | — |

---

## 7. What This Enables (consumption side)

**`asset_calibration.py` reads from cache:**
```python
from market_data.fetchers import HoldingsFetcher, PriceFetcher

# ETF look-through → Layer 5 of assets.json
for ticker in asset_tickers:
    holdings = holdings_fetcher.get(ticker)
    assets_json[ticker]["top_holdings"] = [
        {"ticker": h.ticker, "sector": h.sector, "weight_pct": h.weight_pct}
        for h in holdings.holdings[:20]   # top 20 holdings
    ]
    assets_json[ticker]["holdings_as_of"] = str(holdings.as_of_date)
    assets_json[ticker]["holdings_provider"] = holdings.provider
```

**`portfolio_analysis.py` reads from assets.json (zero network):**
```python
# Look-through: VTI (34% of portfolio) × AAPL (4.1% of VTI) = 1.4% true exposure
for ticker_weight in portfolio_ticker_weights:
    etf_holdings = assets_cfg[ticker_weight.ticker].get("top_holdings", [])
    for holding in etf_holdings:
        true_exposure[holding["ticker"]] += (
            ticker_weight.weight_pct / 100.0 *
            holding["weight_pct"] / 100.0 * 100.0
        )
```

**UI shows in Portfolio Analysis:**
- "True stock exposure: AAPL 3.2%, MSFT 4.1%, NVDA 2.8%..." (look-through)
- "Sector breakdown: Technology 41%, Financials 12%, Healthcare 9%..."
- "Holdings data as of March 10, 2026 (ETF.com)"
- "Overlap: VTI + QQQ share 78% of top-20 holdings"

---

## 8. Scheduler Entry Point

```bash
# Run weekly (cron or launchd):
# 0 6 * * 0 cd /path/to/c-eNDinomics && python3 market_data/scheduler/weekly_job.py

python3 market_data/scheduler/weekly_job.py
  --tickers VTI VXUS QQQ IEF TLT SCHP GLD DBC   # from assets.json
  --data-types holdings prices sectors
  --max-age-days 7
  --dry-run                                        # fetch + cache, don't promote
```

After weekly fetch, human runs:
```bash
python3 src/asset_calibration.py    # reads cache → writes candidate model
python3 src/promote_model.py        # validates → human confirms → writes assets.json
```

---

## 9. Science Workstream (future)

The market_data package is designed to be a standalone research tool:

- **Signal accuracy tracking**: record which provider's holdings data best
  predicted subsequent performance
- **Provider comparison**: run the same calibration against different provider
  data sources and compare resulting mu/sigma estimates
- **Regime detection**: use the price history + options flow data to build
  Bayesian regime classifiers (Layer 8 of asset model per grand plan)
- **Wyckoff automation**: automate phase detection from price + volume data
  (Layer 13 per grand plan)

The `market_data/` package imports nothing from `src/`. It can be extracted
as a standalone library, published to PyPI, or replaced entirely without
touching the simulation engine.

---

## 10. Build Order

**Phase 1 (next dedicated session):**
1. `market_data/providers/base.py` — abstract interfaces
2. `market_data/providers/yfinance_provider.py` — prices + basic holdings
3. `market_data/providers/etf_dot_com_provider.py` — detailed holdings
4. `market_data/cache/` — JSON/parquet cache with manifest
5. `market_data/fetchers/holdings_fetcher.py` — priority chain
6. `market_data/scheduler/weekly_job.py` — entry point
7. Tests: provider unit tests with mocked HTTP

**Phase 2 (asset model session):**
8. `asset_calibration.py` — multi-window blend + look-through population
9. `promote_model.py` — validation gate
10. `portfolio_analysis.py` update — look-through aggregation
11. `App.tsx` update — true stock exposure + sector charts

**Phase 3 (science workstream, separate):**
12. Signal accuracy tracking
13. Provider comparison framework
14. Regime detection models

---

## 11. Relationship to Investment Tab

The market_data package is the data foundation for the Investment tab's
action engine (see INVESTMENT_ENGINE.md for full design).

Phase 2 of the Investment tab adds `signal_computation.py` which reads
from the market_data cache and produces `market_signals.json`:

```
market_data/cache/store/      (weekly refresh — prices, holdings, sectors)
         ↓
signal_computation.py         (new in Investment Phase 2)
    CMF (21-day Chaikin Money Flow) from OHLCV
    Wyckoff phase detection from price + volume
    OBV divergence from price vs on-balance-volume
    CAPE from FRED API (free, no key required)
    Bayesian regime posterior (4 states)
         ↓
market_signals.json           (Investment tab reads this)
```

The market_data package itself does not compute signals — it provides
the price history that signal_computation.py reads. This separation keeps
the data layer pure (fetch + cache only) and the signal computation
independently testable.
