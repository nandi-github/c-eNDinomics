"""
market_data/providers/etf_dot_com_provider.py
=============================================
ETF holdings provider with fund-family-specific fetchers.

Confirmed working (2026-03-16):
  iShares:  direct CSV — https://www.ishares.com/us/products/{id}/{slug}/...?tab=holdings&fileType=csv
  Vanguard: JSON API  — https://investor.vanguard.com/investment-products/etfs/profile/api/{TICKER}/portfolio-holding/stock
  SPDR:     xlsx      — https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{ticker}.xlsx
  Invesco:  blocked   — no working free URL; use iShares fallback for IVZ-managed ETFs
  Schwab:   403       — no working free URL

For tickers not served by any working URL, the fetcher falls back to
yfinance funds_data, then stale cache.
"""

from __future__ import annotations

import datetime
import io
import json
import time
import urllib.request
import urllib.error
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from .base import (
    ETFHoldings, FatalProviderError, Holding,
    HoldingsProvider, ProviderError,
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_TIMEOUT = 25
_SLEEP   = 1.5


# ---------------------------------------------------------------------------
# iShares registry: {ticker: (product_id, url_slug)}
# ---------------------------------------------------------------------------
_ISHARES: Dict[str, Tuple[str, str]] = {
    "IEF":  ("239456", "ishares-7-10-year-treasury-bond-etf"),
    "TLT":  ("239454", "ishares-20-plus-year-treasury-bond-etf"),
    "LQD":  ("239566", "ishares-iboxx-investment-grade-corporate-bond-etf"),
    "IAU":  ("239597", "ishares-gold-trust"),
    "EEM":  ("239637", "ishares-msci-emerging-markets-etf"),
    "EFA":  ("239623", "ishares-msci-eafe-etf"),
    "TIP":  ("239467", "ishares-tips-bond-etf"),
    "AGG":  ("239458", "ishares-core-us-aggregate-bond-etf"),
    "IVV":  ("239726", "ishares-core-sp-500-etf"),
    "IWM":  ("239714", "ishares-russell-2000-etf"),
    "IXUS": ("244048", "ishares-core-msci-total-international-stock-etf"),
    "IWF":  ("239706", "ishares-russell-1000-growth-etf"),
    "IWD":  ("239705", "ishares-russell-1000-value-etf"),
    "SHY":  ("239452", "ishares-1-3-year-treasury-bond-etf"),
}

# Physical commodity / gold ETFs — hold bullion not stocks.
# These legitimately have 0 equity holdings — cache as empty holding list.
_PHYSICAL_COMMODITY_ETFS = {"IAU", "GLD", "SLV", "GLDM", "DBC", "PDBC",
                            "USO", "UNG"}

# Invesco QQQ — tracks Nasdaq-100, Nasdaq publishes components
_QQQ_FAMILY = {"QQQ", "QQQM"}

# Vanguard tickers (JSON API, paginated)
_VANGUARD_EQUITY = {"VTI", "VXUS", "VTV", "VUG", "VNQ", "VWO",
                    "VEA", "VB", "VO", "VV", "VDE", "VFH", "VHT"}
_VANGUARD_BOND   = {"BND", "BNDX", "VTIP", "VGLT", "VGIT", "VCIT",
                    "VCSH", "BSV", "BLV", "VMBS"}
_VANGUARD        = _VANGUARD_EQUITY | _VANGUARD_BOND

# SPDR tickers — correct slugs from confirmed working URL pattern
_SPDR_SLUGS: Dict[str, str] = {
    "SPY":  "spy",
    "XLE":  "xle",
    "XLF":  "xlf",
    "XLK":  "xlk",
    "XLV":  "xlv",
    "XLI":  "xli",
    "XLP":  "xlp",
    "XLY":  "xly",
    "XLB":  "xlb",
    "XLU":  "xlu",
    "XLRE": "xlre",
    "GLD":  "spdrgoldshares",    # GLD is "SPDR Gold Shares" not just "gld"
    "SLV":  "slv",
}


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, extra_headers: Optional[Dict] = None,
         follow_redirects: bool = True) -> bytes:
    """Fetch URL bytes. Raises ProviderError on failure."""
    headers = {"User-Agent": _USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)

    opener = urllib.request.build_opener()
    if not follow_redirects:
        opener = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler()
        )

    req = urllib.request.Request(url, headers=headers)
    try:
        time.sleep(_SLEEP)
        with opener.open(req, timeout=_TIMEOUT) as resp:
            if resp.status not in (200, 206):
                raise ProviderError(f"HTTP {resp.status} from {url}")
            return resp.read()
    except ProviderError:
        raise
    except urllib.error.HTTPError as e:
        raise ProviderError(f"HTTP {e.code} from {url}")
    except Exception as e:
        raise ProviderError(f"Request failed for {url}: {e}")


# ---------------------------------------------------------------------------
# iShares CSV parser
# ---------------------------------------------------------------------------

def _parse_ishares_csv(content: str) -> List[Holding]:
    """
    iShares CSV: preamble rows, then CSV starting with 'Name,Sector,...,Weight (%),...'
    Equity ETFs: Name=company, no Ticker column -> use ISIN
    Bond ETFs:   Name=bond description, use ISIN
    """
    import csv as _csv
    holdings: List[Holding] = []
    lines = content.splitlines()

    # Find CSV header — line with comma AND "weight"
    start = 0
    for i, line in enumerate(lines):
        if "," in line and "weight" in line.lower():
            start = i
            break

    def _col(row: dict, *keys: str) -> str:
        for k in keys:
            for rk, rv in row.items():
                if rk is not None and rk.strip().lower() == k.lower():
                    return str(rv or "").strip()
        return ""

    try:
        reader = _csv.DictReader(io.StringIO("\n".join(lines[start:])))
    except Exception:
        return []

    for row in reader:
        try:
            wt_str = _col(row, "Weight (%)", "weight (%)", "wt. %")
            wt_str = wt_str.replace("%", "").replace(",", "").strip()
            if not wt_str:
                continue
            wt = float(wt_str)
            if wt <= 0:
                continue

            ticker = _col(row, "Ticker", "ticker", "Symbol")
            name   = _col(row, "Name", "name", "Security Name")
            isin   = _col(row, "ISIN", "isin")
            sector = _col(row, "Sector", "sector", "Asset Class")

            ident = ticker or isin or name
            if not ident or ident in ("-", ""):
                continue
            if ident.upper() in ("CASH", "USD", "CASH_USD"):
                continue

            holdings.append(Holding(
                ticker=ident[:20].upper(), name=name or ident,
                sector=sector, weight_pct=round(wt, 4),
            ))
        except (ValueError, KeyError):
            continue
    return holdings


# ---------------------------------------------------------------------------
# Vanguard JSON parser (paginated)
# ---------------------------------------------------------------------------

def _fetch_vanguard(ticker: str, endpoint: str = "stock") -> List[Holding]:
    """
    Vanguard JSON API — paginated, 500 holdings/page.
    endpoint: "stock" for equity ETFs, "bond" for bond ETFs.
    Response: {"size": N, "fund": {"entity": [{ticker, longName, percentWeight, ...}]}}
    """
    all_holdings: List[Holding] = []
    start = 1
    page_size = 500
    base = (f"https://investor.vanguard.com/investment-products/etfs/profile"
            f"/api/{ticker}/portfolio-holding/{endpoint}")

    while True:
        url = f"{base}?start={start}&count={page_size}"
        try:
            raw = _get(url, extra_headers={"Referer": "https://investor.vanguard.com"})
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            if all_holdings:
                break   # partial success — use what we have
            raise ProviderError(f"Vanguard JSON fetch failed for {ticker}: {e}")

        entities = (data.get("fund") or {}).get("entity") or []
        if not entities:
            break

        for e in entities:
            try:
                sym = str(e.get("ticker") or "").strip().upper()
                wt  = float(e.get("percentWeight") or 0)
                if not sym or wt <= 0:
                    continue
                all_holdings.append(Holding(
                    ticker=sym,
                    name=str(e.get("longName") or sym),
                    sector=str(e.get("sector") or ""),
                    weight_pct=round(wt, 4),
                ))
            except (ValueError, TypeError):
                continue

        total = int(data.get("size") or 0)
        if start + page_size - 1 >= total:
            break
        start += page_size

    return all_holdings


# ---------------------------------------------------------------------------
# SPDR xlsx parser (stdlib zipfile, no openpyxl needed)
# ---------------------------------------------------------------------------

def _parse_spdr_xlsx(raw_bytes: bytes) -> List[Holding]:
    """
    Parse SPDR xlsx using stdlib zipfile + ElementTree.
    Columns: Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency
    Weight column is a raw float (e.g. 7.707647 = 7.71%)
    """
    try:
        z  = zipfile.ZipFile(io.BytesIO(raw_bytes))
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        # Build shared strings lookup
        ss_xml  = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = [
            (si.find(".//x:t", ns).text or "")
            for si in ss_xml.findall("x:si", ns)
            if si.find(".//x:t", ns) is not None
        ]

        # Find sheet1
        sheet_xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows = sheet_xml.findall(".//x:row", ns)

        def _cell_val(c) -> str:
            t = c.get("t", "")
            v = c.find("x:v", ns)
            if v is None:
                return ""
            if t == "s":
                idx = int(v.text)
                return strings[idx] if idx < len(strings) else ""
            return v.text or ""

        # Find header row (contains "Name" and "Weight")
        header_idx = -1
        header_map: Dict[str, int] = {}
        for i, row in enumerate(rows):
            vals = [_cell_val(c) for c in row.findall("x:c", ns)]
            joined = " ".join(vals).lower()
            if "name" in joined and "weight" in joined and "ticker" in joined:
                header_idx = i
                header_map = {v.lower().strip(): j for j, v in enumerate(vals)}
                break

        if header_idx == -1:
            return []

        col_name   = header_map.get("name", 0)
        col_ticker = header_map.get("ticker", 1)
        col_weight = header_map.get("weight", 4)
        col_sector = header_map.get("sector", 5)

        holdings: List[Holding] = []
        for row in rows[header_idx + 1:]:
            cells = row.findall("x:c", ns)
            if len(cells) <= col_weight:
                continue
            vals = [_cell_val(c) for c in cells]

            def _v(idx: int) -> str:
                return vals[idx].strip() if idx < len(vals) else ""

            name   = _v(col_name)
            ticker = _v(col_ticker)
            wt_str = _v(col_weight)
            sector = _v(col_sector)

            if not ticker or not wt_str:
                continue
            try:
                wt = float(wt_str)
            except ValueError:
                continue
            if wt <= 0:
                continue

            holdings.append(Holding(
                ticker=ticker.upper(), name=name,
                sector=sector, weight_pct=round(wt, 4),
            ))
        return holdings
    except Exception as e:
        raise ProviderError(f"SPDR xlsx parse failed: {e}")


# ---------------------------------------------------------------------------
# Generic CSV parser (kept for tests)
# ---------------------------------------------------------------------------

def _parse_csv_holdings(content: str) -> List[Holding]:
    import csv as _csv
    holdings: List[Holding] = []
    lines = content.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "," in line and any(kw in line.lower()
                               for kw in ("ticker", "symbol", "weight")):
            start = i
            break
    try:
        reader = _csv.DictReader(io.StringIO("\n".join(lines[start:])))
    except Exception:
        return []
    for row in reader:
        try:
            def _g(*keys):
                for k in keys:
                    for rk, rv in row.items():
                        if rk is not None and rk.strip().lower() == k.lower():
                            return str(rv or "").strip()
                return ""
            sym    = _g("Ticker", "Symbol", "ticker", "symbol")
            name   = _g("Name", "Holding Name", "Description")
            sector = _g("Sector", "GICS Sector", "Asset Class")
            wt_str = _g("Weight (%)", "Weight(%)", "Weight", "% Weight").replace("%","").replace(",","").strip()
            if not sym or not wt_str: continue
            wt = float(wt_str)
            if wt <= 0: continue
            holdings.append(Holding(ticker=sym.upper(), name=name,
                                    sector=sector, weight_pct=round(wt, 4)))
        except (ValueError, KeyError):
            continue
    return holdings


# ---------------------------------------------------------------------------
# Nasdaq-100 component fetcher (for QQQ/QQQM)
# Nasdaq publishes the index components at a stable JSON endpoint.
# ---------------------------------------------------------------------------

def _fetch_nasdaq100() -> List[Holding]:
    """
    Fetch Nasdaq-100 components from Nasdaq's public screener API.
    Returns holdings weighted by market cap rank (approximate equal weight
    within rank buckets — exact weights require paid data).
    """
    url = ("https://api.nasdaq.com/api/quote/QQQ/info"
           "?assetclass=etf")
    # Try Nasdaq screener for NDX components
    screener_url = ("https://api.nasdaq.com/api/screener/stocks"
                    "?tableonly=true&limit=200&exchange=nasdaq&index=NDX")
    try:
        raw  = _get(screener_url, extra_headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nasdaq.com/",
        })
        data = json.loads(raw.decode("utf-8", errors="replace"))
        rows = (data.get("data") or {}).get("table", {}).get("rows") or []

        holdings: List[Holding] = []
        n = len(rows)
        for i, row in enumerate(rows):
            sym  = str(row.get("symbol") or "").strip().upper()
            name = str(row.get("name")   or "").strip()
            if not sym:
                continue
            # Approximate weight: top-heavy distribution (Nasdaq-100 is cap-weighted)
            # True weights need paid data; this gives the right top-10 names
            rank_weight = round(max(0.1, (n - i) / n * 3.0), 4)
            holdings.append(Holding(
                ticker=sym, name=name,
                sector=str(row.get("sector") or ""),
                weight_pct=rank_weight,
            ))
        return holdings
    except Exception as e:
        raise ProviderError(f"Nasdaq-100 screener failed: {e}")


# ---------------------------------------------------------------------------
# Main provider
# ---------------------------------------------------------------------------

class ETFDotComProvider(HoldingsProvider):
    """
    ETF holdings using fund-family-specific endpoints.
    iShares → direct CSV
    Vanguard → JSON API (paginated)
    SPDR     → xlsx (stdlib parse, no openpyxl)
    """

    @property
    def name(self) -> str:
        return "etf_dot_com"

    def fetch_holdings(self, ticker: str) -> ETFHoldings:
        t = ticker.upper()

        # ── Physical commodity ETFs — hold bullion, not stocks ────────────
        # Return empty holdings (correct — no equity look-through possible)
        if t in _PHYSICAL_COMMODITY_ETFS:
            return ETFHoldings(
                etf_ticker=t, as_of_date=datetime.date.today(),
                provider=self.name, total_assets=None,
                holdings=[], n_holdings=0,
            )

        # ── iShares ───────────────────────────────────────────────────────
        if t in _ISHARES:
            pid, slug = _ISHARES[t]
            url = (f"https://www.ishares.com/us/products/{pid}/{slug}"
                   f"/1467271812596.ajax?tab=holdings&fileType=csv")
            try:
                content  = _get(url).decode("utf-8", errors="replace")
                holdings = _parse_ishares_csv(content)
                if len(holdings) >= 3:
                    return ETFHoldings(
                        etf_ticker=t, as_of_date=datetime.date.today(),
                        provider=self.name, total_assets=None,
                        holdings=holdings, n_holdings=len(holdings),
                    )
            except ProviderError as e:
                raise ProviderError(f"iShares CSV failed for {t}: {e}")

        # ── Vanguard ─────────────────────────────────────────────────────
        if t in _VANGUARD:
            endpoint = "bond" if t in _VANGUARD_BOND else "stock"
            holdings = _fetch_vanguard(t, endpoint=endpoint)
            if len(holdings) >= 3:
                return ETFHoldings(
                    etf_ticker=t, as_of_date=datetime.date.today(),
                    provider=self.name, total_assets=None,
                    holdings=holdings, n_holdings=len(holdings),
                )
            raise ProviderError(f"Vanguard returned only {len(holdings)} holdings for {t}")

        # ── SPDR ─────────────────────────────────────────────────────────
        if t in _SPDR_SLUGS:
            slug = _SPDR_SLUGS[t]
            url  = (f"https://www.ssga.com/us/en/intermediary/etfs/library-content"
                    f"/products/fund-data/etfs/us/holdings-daily-us-en-{slug}.xlsx")
            try:
                raw      = _get(url)
                holdings = _parse_spdr_xlsx(raw)
                if len(holdings) >= 5:
                    return ETFHoldings(
                        etf_ticker=t, as_of_date=datetime.date.today(),
                        provider=self.name, total_assets=None,
                        holdings=holdings, n_holdings=len(holdings),
                    )
            except ProviderError as e:
                raise ProviderError(f"SPDR xlsx failed for {t}: {e}")

        # ── QQQ / QQQM — Nasdaq-100 components ───────────────────────────
        if t in _QQQ_FAMILY:
            holdings = _fetch_nasdaq100()
            if len(holdings) >= 10:
                return ETFHoldings(
                    etf_ticker=t, as_of_date=datetime.date.today(),
                    provider=self.name, total_assets=None,
                    holdings=holdings, n_holdings=len(holdings),
                )
            raise ProviderError(f"Nasdaq-100 component fetch returned {len(holdings)} holdings")

        raise ProviderError(
            f"ETFDotCom: no working URL for {t}. "
            f"Not in iShares/Vanguard/SPDR/QQQ registry."
        )


# ---------------------------------------------------------------------------
# yfinance funds_data fallback
# ---------------------------------------------------------------------------

class YFinanceFundsDataProvider(HoldingsProvider):
    """yfinance funds_data (yfinance >= 0.2.37)."""

    @property
    def name(self) -> str:
        return "yfinance_funds"

    def fetch_holdings(self, ticker: str) -> ETFHoldings:
        try:
            import yfinance as yf
        except ImportError:
            raise FatalProviderError("yfinance not installed")

        try:
            time.sleep(1.0)
            fd = yf.Ticker(ticker).funds_data
        except Exception as e:
            raise ProviderError(f"yfinance.funds_data failed for {ticker}: {e}")

        if fd is None:
            raise ProviderError(f"funds_data is None for {ticker}")

        try:
            top = getattr(fd, "top_holdings", None)
            if top is None or (hasattr(top, "empty") and top.empty):
                raise ProviderError(f"no top_holdings for {ticker}")
            holdings: List[Holding] = []
            for idx, row in top.iterrows():
                sym = str(idx).strip().upper() if idx else ""
                pct = float(row.get("holdingPercent", 0) or 0) * 100.0
                if sym and pct > 0:
                    holdings.append(Holding(
                        ticker=sym,
                        name=str(row.get("holdingName", "") or ""),
                        sector="", weight_pct=round(pct, 4),
                    ))
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"funds_data parse failed for {ticker}: {e}")

        if not holdings:
            raise ProviderError(f"no holdings from funds_data for {ticker}")

        return ETFHoldings(
            etf_ticker=ticker.upper(), as_of_date=datetime.date.today(),
            provider=self.name, total_assets=None, holdings=holdings,
        )
