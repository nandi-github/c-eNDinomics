"""
asset_calibration.py
=====================
Reads from the market_data cache and produces a candidate assets.json.

Does NOT write directly to src/config/assets.json.
Output goes to asset-model/candidate/assets.json for human review.
Run promote_model.py to validate and promote to production.

What this builds:
  Layer 1-4: mu_annual, sigma_annual, yield_annual, corr_matrix
             Multi-window geometric blend:
               5yr  × 0.15  (current regime)
               10yr × 0.35  (full market cycle)
               20yr × 0.30  (long-run)
               prior × 0.20 (hand-calibrated anchor — prevents wild swings)
  Layer 5:   top_holdings, sector, instrument_type, holdings_as_of
             (populated from ETF holdings cache)

Usage:
    python3 src/asset_calibration.py
    python3 src/asset_calibration.py --windows 5 10 20 --weights 0.20 0.40 0.40
    python3 src/asset_calibration.py --no-look-through   # skip Layer 5
    python3 src/asset_calibration.py --dry-run           # print candidate, don't write
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE         = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT    = os.path.abspath(os.path.join(_HERE, ".."))
_CACHE_DIR    = os.path.join(_REPO_ROOT, "market_data", "cache", "store")
_ASSETS_IN    = os.path.join(_HERE, "config", "assets.json")    # current production model
_CANDIDATE_DIR = os.path.join(_REPO_ROOT, "asset-model", "candidate")
_CANDIDATE_OUT = os.path.join(_CANDIDATE_DIR, "assets.json")

sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Multi-window blend weights
# ---------------------------------------------------------------------------

DEFAULT_WINDOWS = [5, 10, 20]          # years
DEFAULT_WEIGHTS = [0.15, 0.35, 0.30]   # must sum to < 1.0 (remainder = prior weight)
PRIOR_WEIGHT    = 0.20                  # weight on hand-calibrated anchor

# Per-class sigma floor — prevents calibration from producing implausibly low vol
SIGMA_FLOOR: Dict[str, float] = {
    "US_STOCKS":   0.10,
    "INTL_STOCKS": 0.10,
    "LONG_TREAS":  0.06,
    "INT_TREAS":   0.04,
    "TIPS":        0.04,
    "GOLD":        0.10,
    "COMMOD":      0.12,
    "REIT":        0.12,
    "CASH":        0.005,
}

# Per-class mu ceiling — prevents short windows from producing absurd estimates
MU_CEIL: Dict[str, float] = {
    "US_STOCKS":   0.22,   # individual stocks can hit 18-22% annualised
    "INTL_STOCKS": 0.18,
    "LONG_TREAS":  0.10,
    "INT_TREAS":   0.08,
    "TIPS":        0.07,
    "GOLD":        0.15,
    "COMMOD":      0.16,
    "REIT":        0.16,
    "CASH":        0.06,
}
MU_FLOOR: Dict[str, float] = {
    "US_STOCKS":   0.02,
    "INTL_STOCKS": 0.01,
    "LONG_TREAS":  -0.02,
    "INT_TREAS":   -0.01,
    "TIPS":        -0.01,
    "GOLD":        -0.02,
    "COMMOD":      -0.03,
    "REIT":        0.00,
    "CASH":        0.00,
}

# Qualified dividend ratio by class (used for dist section)
QUALIFIED_RATIO: Dict[str, float] = {
    "US_STOCKS":   0.90,
    "INTL_STOCKS": 0.80,
    "LONG_TREAS":  0.00,
    "INT_TREAS":   0.00,
    "TIPS":        0.00,
    "GOLD":        0.00,
    "COMMOD":      0.00,
    "REIT":        0.20,
    "CASH":        0.00,
}


# ---------------------------------------------------------------------------
# Return calibration helpers
# ---------------------------------------------------------------------------

def _geometric_mu_sigma(closes: List[float]) -> Tuple[float, float]:
    """
    Compute annualised geometric mean return and volatility from daily closes.
    Returns (mu_annual, sigma_annual). Returns (0, 0) if insufficient data.
    """
    if len(closes) < 50:
        return 0.0, 0.0
    arr  = np.array(closes, dtype=float)
    rets = np.diff(np.log(arr))          # log returns
    if len(rets) < 20:
        return 0.0, 0.0
    mu_daily    = float(np.mean(rets))
    sigma_daily = float(np.std(rets, ddof=1))
    mu_annual   = float((1 + mu_daily) ** 252 - 1)
    sigma_annual = sigma_daily * math.sqrt(252)
    return mu_annual, sigma_annual


def _dividend_yield(closes: List[float], dividends: List[float]) -> float:
    """Trailing 12-month dividend yield from daily series."""
    if not closes or not dividends:
        return 0.0
    # Sum dividends in the last 252 trading days
    n = len(dividends)
    trailing = sum(dividends[max(0, n - 252):])
    last_price = closes[-1]
    return float(trailing / last_price) if last_price > 0 else 0.0


def _window_slice(closes: List[float], dividends: List[float],
                  years: int) -> Tuple[List[float], List[float]]:
    """Return the last `years` worth of data (approx 252 bars/year)."""
    n = years * 252
    return closes[-n:], dividends[-n:]


def _blend_estimates(
    closes: List[float],
    dividends: List[float],
    asset_class: str,
    prior_mu: float,
    prior_sigma: float,
    windows: List[int],
    weights: List[float],
    prior_weight: float,
) -> Tuple[float, float, float]:
    """
    Multi-window geometric blend of mu and sigma, anchored to prior.
    Returns (mu_annual, sigma_annual, yield_annual).
    """
    mu_estimates     = []
    sigma_estimates  = []
    valid_weights    = []

    for win, wt in zip(windows, weights):
        c_slice, _ = _window_slice(closes, dividends, win)
        mu, sigma  = _geometric_mu_sigma(c_slice)
        if mu != 0.0 and sigma != 0.0:
            mu_estimates.append(mu)
            sigma_estimates.append(sigma)
            valid_weights.append(wt)

    if not mu_estimates:
        # No valid windows — fall back to prior entirely
        return prior_mu, prior_sigma, _dividend_yield(closes, dividends)

    # Normalise valid weights so they + prior_weight = 1.0
    total_window_weight = sum(valid_weights)
    scale = (1.0 - prior_weight) / total_window_weight if total_window_weight > 0 else 0
    normalised = [w * scale for w in valid_weights]

    mu_blend    = sum(m * w for m, w in zip(mu_estimates, normalised)) + prior_mu * prior_weight
    sigma_blend = sum(s * w for s, w in zip(sigma_estimates, normalised)) + prior_sigma * prior_weight

    # Apply per-class bounds
    mu_blend    = max(MU_FLOOR.get(asset_class, -0.05),
                  min(MU_CEIL.get(asset_class, 0.25), mu_blend))
    sigma_blend = max(SIGMA_FLOOR.get(asset_class, 0.02), sigma_blend)

    yield_est = _dividend_yield(closes, dividends)
    return round(mu_blend, 6), round(sigma_blend, 6), round(yield_est, 6)


# ---------------------------------------------------------------------------
# Correlation matrix
# ---------------------------------------------------------------------------

def _build_correlation_matrix(
    price_map: Dict[str, List[float]],
    tickers: List[str],
) -> List[List[float]]:
    """Build a correlation matrix from daily returns. Returns identity if < 2 tickers."""
    n = len(tickers)
    if n < 2:
        return [[1.0]] if n == 1 else []

    # Find overlapping length
    min_len = min((len(price_map[t]) for t in tickers if t in price_map), default=0)
    if min_len < 50:
        return np.eye(n).tolist()

    log_rets = []
    for t in tickers:
        closes = np.array(price_map.get(t, [])[-min_len:], dtype=float)
        if len(closes) < 50:
            log_rets.append(np.zeros(min_len - 1))
        else:
            log_rets.append(np.diff(np.log(closes + 1e-10)))

    mat = np.array(log_rets)   # shape: (n_tickers, n_days)
    try:
        corr = np.corrcoef(mat)
        # Replace NaN with identity row/col
        for i in range(n):
            for j in range(n):
                if not math.isfinite(corr[i, j]):
                    corr[i, j] = 1.0 if i == j else 0.0
        return corr.tolist()
    except Exception:
        return np.eye(n).tolist()


# ---------------------------------------------------------------------------
# Look-through: populate Layer 5 from holdings cache
# ---------------------------------------------------------------------------

def _populate_look_through(
    assets_cfg: Dict,
    cache_dir: str,
    top_n: int = 20,
) -> Dict:
    """
    Add top_holdings, sector, instrument_type, holdings_as_of to each ticker
    in assets_cfg, reading from the market_data cache.
    """
    try:
        from market_data.cache.cache import MarketDataCache
        cache = MarketDataCache(cache_dir)
    except ImportError:
        print("[calibration] WARNING: market_data package not found — skipping look-through")
        return assets_cfg

    enriched = 0
    skipped  = 0

    for ticker, cfg in assets_cfg.items():
        # Sector info
        sector_info = cache.get_sector(ticker, max_age_days=60)
        if sector_info:
            cfg["sector"]          = sector_info.sector
            cfg["instrument_type"] = sector_info.instrument_type
            cfg["sector_provider"] = sector_info.provider
            cfg["sector_as_of"]    = sector_info.as_of_date.isoformat()

        # ETF holdings (only for ETFs — skip individual stocks)
        instrument_type = cfg.get("instrument_type", "")
        if instrument_type in ("broad_etf", "sector_etf") or (
            instrument_type == "" and cfg.get("class") in
            ("US_STOCKS", "INTL_STOCKS", "LONG_TREAS", "INT_TREAS", "TIPS", "GOLD", "COMMOD")
            and len(ticker) <= 5   # rough ETF heuristic
        ):
            holdings = cache.get_holdings(ticker, max_age_days=14)
            if holdings and holdings.holdings:
                cfg["top_holdings"] = [
                    {
                        "ticker":     h.ticker,
                        "name":       h.name,
                        "sector":     h.sector,
                        "weight_pct": h.weight_pct,
                    }
                    for h in holdings.holdings[:top_n]
                ]
                cfg["holdings_as_of"]    = holdings.as_of_date.isoformat()
                cfg["holdings_provider"] = holdings.provider
                cfg["n_holdings_total"]  = holdings.n_holdings
                enriched += 1
            else:
                skipped += 1

    print(f"[calibration] Look-through: {enriched} ETFs enriched, {skipped} skipped (no cache)")
    return assets_cfg


# ---------------------------------------------------------------------------
# Main calibration function
# ---------------------------------------------------------------------------

def run_calibration(
    assets_in: str      = _ASSETS_IN,
    candidate_out: str  = _CANDIDATE_OUT,
    cache_dir: str      = _CACHE_DIR,
    windows: List[int]  = DEFAULT_WINDOWS,
    weights: List[float] = DEFAULT_WEIGHTS,
    prior_weight: float  = PRIOR_WEIGHT,
    look_through: bool   = True,
    dry_run: bool        = False,
) -> Dict:
    """
    Build a candidate assets.json from the market_data cache.

    Args:
        assets_in:     current production assets.json (used as prior)
        candidate_out: output path for candidate model
        cache_dir:     market_data cache directory
        windows:       lookback windows in years
        weights:       weights per window (must sum < 1.0)
        prior_weight:  weight on hand-calibrated anchor
        look_through:  populate Layer 5 ETF holdings
        dry_run:       print candidate but don't write

    Returns:
        candidate assets.json dict
    """
    assert abs(sum(weights) + prior_weight - 1.0) < 1e-9, \
        f"weights {weights} + prior_weight {prior_weight} must sum to 1.0"

    print(f"\n{'='*60}")
    print(f"  eNDinomics Asset Calibration")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Windows: {windows}yr  Weights: {weights}  Prior: {prior_weight}")
    print(f"{'='*60}\n")

    # Load current production model as prior
    if not os.path.isfile(assets_in):
        raise FileNotFoundError(f"assets.json not found at {assets_in}")
    with open(assets_in) as f:
        prior_model = json.load(f)
    prior_assets = prior_model.get("assets", {})

    # Load market data cache
    try:
        from market_data.cache.cache import MarketDataCache
        cache = MarketDataCache(cache_dir)
    except ImportError:
        raise RuntimeError("market_data package not found. Install or add to path.")

    tickers = sorted(prior_assets.keys())
    print(f"Calibrating {len(tickers)} tickers: {tickers}\n")

    new_assets: Dict = {}
    price_map: Dict[str, List[float]] = {}

    for ticker in tickers:
        prior_cfg   = prior_assets[ticker]
        asset_class = prior_cfg.get("class", "US_STOCKS")
        prior_mu    = float(prior_cfg.get("mu_annual", 0.065))
        prior_sigma = float(prior_cfg.get("sigma_annual", 0.16))

        # Load prices from cache
        prices = cache.get_prices(ticker, max_age_days=3)   # accept up to 3 days old
        if prices is None or len(prices.bars) < 100:
            print(f"  {ticker:6s}  NO PRICES in cache — using prior  "
                  f"(mu={prior_mu:.3f}, sigma={prior_sigma:.3f})")
            new_assets[ticker] = {
                **prior_cfg,
                "_calibration": {
                    "method": "prior_only",
                    "reason": "no_cache_data",
                    "as_of":  datetime.date.today().isoformat(),
                },
            }
            continue

        closes    = prices.closes
        dividends = prices.dividends
        price_map[ticker] = closes

        mu, sigma, yield_est = _blend_estimates(
            closes, dividends, asset_class,
            prior_mu, prior_sigma,
            windows, weights, prior_weight,
        )

        delta_mu    = mu    - prior_mu
        delta_sigma = sigma - prior_sigma
        print(f"  {ticker:6s}  mu={mu:.4f} ({delta_mu:+.4f})  "
              f"sigma={sigma:.4f} ({delta_sigma:+.4f})  "
              f"yield={yield_est:.4f}  bars={len(closes)}")

        new_assets[ticker] = {
            "class":         asset_class,
            "mu_annual":     mu,
            "sigma_annual":  sigma,
            "expense_ratio": prior_cfg.get("expense_ratio", 0.001),
            "tracking_error": prior_cfg.get("tracking_error", 0.01),
            "dist": {
                "yield_annual":    yield_est,
                "qualified_ratio": QUALIFIED_RATIO.get(asset_class, 0.0),
            },
            "_provenance": prior_cfg.get("_provenance", {}),
            "_calibration": {
                "method":       "multi_window_blend",
                "windows_yr":   windows,
                "weights":      weights,
                "prior_weight": prior_weight,
                "bars_used":    len(closes),
                "as_of":        datetime.date.today().isoformat(),
                "provider":     prices.provider,
            },
        }

    # ── Correlation matrix ────────────────────────────────────────────────
    print(f"\nBuilding correlation matrix for {len(tickers)} tickers...")
    corr_matrix = _build_correlation_matrix(price_map, tickers)
    print(f"Correlation matrix: {len(tickers)}x{len(tickers)}")

    # ── Layer 5: ETF look-through ─────────────────────────────────────────
    if look_through:
        print(f"\nPopulating Layer 5 (ETF look-through)...")
        new_assets = _populate_look_through(new_assets, cache_dir)

    # ── Class fallbacks ───────────────────────────────────────────────────
    class_buckets: Dict[str, list] = {}
    for ticker, cfg in new_assets.items():
        cls = cfg["class"]
        calib = cfg.get("_calibration", {})
        if calib.get("method") != "prior_only":
            class_buckets.setdefault(cls, []).append(cfg)

    class_fallbacks = {}
    for cls, cfgs in class_buckets.items():
        class_fallbacks[cls] = {
            "class":         cls,
            "_fallback":     True,
            "mu_annual":     round(float(np.mean([c["mu_annual"]    for c in cfgs])), 6),
            "sigma_annual":  round(float(np.mean([c["sigma_annual"] for c in cfgs])), 6),
            "expense_ratio": 0.001,
            "tracking_error": 0.01,
            "dist": {
                "yield_annual":    round(float(np.mean([c["dist"]["yield_annual"] for c in cfgs])), 6),
                "qualified_ratio": QUALIFIED_RATIO.get(cls, 0.0),
            },
        }

    # ── Assemble candidate model ──────────────────────────────────────────
    candidate = {
        "model_version":  _next_version(prior_model.get("model_version", "1.0.0")),
        "schema_version": prior_model.get("schema_version", "1"),
        "released_at":    datetime.date.today().isoformat(),
        "valid_from":     datetime.date.today().isoformat(),
        "valid_until":    (datetime.date.today() + datetime.timedelta(days=30)).isoformat(),
        "status":         "candidate",   # promote_model.py changes this to "production"
        "training": {
            "method":                 "multi_window_blend",
            "data_through":           datetime.date.today().isoformat(),
            "windows_used":           windows,
            "weights":                weights,
            "prior_weight":           prior_weight,
            "event_signals_included": False,
            "auto_refresh_enabled":   False,
            "notes": (
                f"Calibrated from market_data cache. "
                f"Multi-window blend: {list(zip(windows, weights))} + "
                f"prior×{prior_weight}. "
                f"Promoted from {prior_model.get('model_version', '?')}."
            ),
        },
        "assets":      new_assets,
        "class_fallbacks": class_fallbacks,
        "correlations": {
            "assets_order": tickers,
            "matrix":       corr_matrix,
            "_note": (
                f"Computed from {min(len(p) for p in price_map.values() or [[]])} "
                f"overlapping daily bars."
            ),
        },
        "overrides": prior_model.get("overrides", []),
        "readme": prior_model.get("readme", ""),
    }

    if dry_run:
        print(f"\n[DRY RUN] Candidate model (not written):")
        print(json.dumps({k: v for k, v in candidate.items()
                          if k not in ("assets", "correlations")}, indent=2))
        return candidate

    # ── Write candidate ───────────────────────────────────────────────────
    os.makedirs(os.path.dirname(candidate_out), exist_ok=True)
    with open(candidate_out, "w") as f:
        json.dump(candidate, f, indent=2)
    print(f"\nCandidate written to: {candidate_out}")
    print(f"Next step: python3 src/promote_model.py")

    return candidate


def _next_version(current: str) -> str:
    """Increment minor version: '1.0.0' → '1.1.0'."""
    try:
        parts = current.split(".")
        parts[1] = str(int(parts[1]) + 1)
        return ".".join(parts)
    except Exception:
        return current + ".1"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Calibrate asset model from market data cache")
    p.add_argument("--assets-in",   default=_ASSETS_IN)
    p.add_argument("--out",         default=_CANDIDATE_OUT)
    p.add_argument("--cache-dir",   default=_CACHE_DIR)
    p.add_argument("--windows",     nargs="+", type=int,   default=DEFAULT_WINDOWS)
    p.add_argument("--weights",     nargs="+", type=float, default=DEFAULT_WEIGHTS)
    p.add_argument("--prior-weight",           type=float, default=PRIOR_WEIGHT)
    p.add_argument("--no-look-through", action="store_true")
    p.add_argument("--dry-run",         action="store_true")
    args = p.parse_args()

    run_calibration(
        assets_in     = args.assets_in,
        candidate_out = args.out,
        cache_dir     = args.cache_dir,
        windows       = args.windows,
        weights       = args.weights,
        prior_weight  = args.prior_weight,
        look_through  = not args.no_look_through,
        dry_run       = args.dry_run,
    )


if __name__ == "__main__":
    main()
