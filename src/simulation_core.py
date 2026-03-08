# filename: simulation_core.py

import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from assets_loader import load_assets_model
from engines_assets import draw_asset_log_returns, shock_yearly_log_adjustments
from engines import build_shock_matrix_from_json

logger = logging.getLogger(__name__)

YEARS = 30

ALL_CLASSES = [
    "US_STOCKS", "INTL_STOCKS", "LONG_TREAS",
    "INT_TREAS", "TIPS", "GOLD", "COMMOD", "OTHER",
]


def _build_deflator(infl_yearly: Optional[np.ndarray], years: int) -> np.ndarray:
    """
    Build cumulative deflator from yearly inflation rates.
    """
    if infl_yearly is not None and np.asarray(infl_yearly).size > 0:
        arr = np.asarray(infl_yearly, dtype=float).reshape(-1)
        if arr.size < years:
            arr = np.concatenate(
                [arr, np.full(years - arr.size, arr[-1] if arr.size > 0 else 0.0)]
            )
        elif arr.size > years:
            arr = arr[:years]
        return np.cumprod(1.0 + arr)
    else:
        return np.ones(years, dtype=float)


def _pf_defs_for_year(
    per_year_pf: Dict[str, Any], acct: str, y: int, years: int
) -> Dict[str, Any]:
    """
    Extract the portfolio definition for a given account and year
    from per_year_portfolios.
    """
    rows = per_year_pf.get(acct, [])
    if not isinstance(rows, list) or len(rows) == 0:
        return {}
    if len(rows) == 1:
        row = rows[0]
    elif len(rows) >= years:
        row = rows[y]
    else:
        row = rows[min(y, len(rows) - 1)]
    return row.get("portfolios", {}) or {}


def simulate_balances(
    paths: int,
    years: int,
    spy: int,
    alloc_accounts: Dict[str, Any],
    assets_path: Optional[str],
    shocks_events: Optional[List[dict]],
    shocks_mode: str,
    infl_yearly: Optional[np.ndarray],
) -> Tuple[Dict[str, np.ndarray], np.ndarray, np.ndarray, Dict[str, Dict[str, np.ndarray]]]:
    """
    Core investment simulation: evolve account balances with Monte Carlo + shocks,
    no withdrawals, no taxes, no RMDs, no conversions.

    Returns
    -------
    acct_eoy_nom : Dict[str, np.ndarray]
        Per-account nominal end-of-year balances, shape (paths x years).
    total_nom_paths : np.ndarray
        Total nominal portfolio per path per year, shape (paths x years).
    total_real_paths : np.ndarray
        Total real portfolio per path per year (deflated by inflation).
    acct_class_eoy_nom : Dict[acct, Dict[class, np.ndarray]]
        Per-account per-class nominal balances, shape (paths x years).
        Used by rebalancing_core to compute drift vs target weights.
    """
    np.random.seed(42)
    paths = int(paths)
    years = int(years)
    spy = int(spy)
    steps = years * spy

    # ---- Deflator ----
    deflator = _build_deflator(infl_yearly, years)

    per_year_pf = alloc_accounts.get("per_year_portfolios", {}) or {}
    acct_names = list(per_year_pf.keys())
    starting_cfg = alloc_accounts.get("starting", {}) or {}

    # ---- Load asset model ----
    assets_model = load_assets_model(assets_path)
    assets_cfg = assets_model.get("assets", {})
    asset_order = assets_model.get("order", [])
    corr = assets_model.get("corr")

    # ---- Shocks (per class) ----
    shock_mats = build_shock_matrix_from_json(
        shocks_events or [], years, spy, paths, mode=shocks_mode or "augment"
    )
    shock_logs = shock_yearly_log_adjustments(
        shock_mats, years=years, spy=spy, paths=paths
    )

    # ---- Per-asset yearly log returns ----
    asset_log_R, asset_order = draw_asset_log_returns(
        paths, years, asset_order, assets_cfg, corr, seed=42
    )

    # ---- Balances ----
    acct_eoy_nom: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, years), dtype=float) for acct in acct_names
    }
    # Per-class balances — used by rebalancing_core
    acct_class_eoy_nom: Dict[str, Dict[str, np.ndarray]] = {
        acct: {cls: np.zeros((paths, years), dtype=float) for cls in ALL_CLASSES}
        for acct in acct_names
    }
    total_nom_paths = np.zeros((paths, years), dtype=float)

    # Optional debug of class weights for first year / account
    debug_class_w_printed = False

    # ---- Main simulation loop ----
    for y in range(years):
        for acct in acct_names:
            pf = _pf_defs_for_year(per_year_pf, acct, y, years)

            # Class-level and ticker-level weights (legacy logic)
            class_w: Dict[str, float] = {
                "US_STOCKS": 0.0,
                "INTL_STOCKS": 0.0,
                "LONG_TREAS": 0.0,
                "INT_TREAS": 0.0,
                "TIPS": 0.0,
                "GOLD": 0.0,
                "COMMOD": 0.0,
                "OTHER": 0.0,
            }
            asset_w: Dict[str, float] = {}

            for pf_name, pf_def in (pf or {}).items():
                # Legacy uses "weight" in 0–1 space; if using weight_pct elsewhere,
                # ensure load_allocation_yearly_accounts normalized this already.
                w_pf = float(pf_def.get("weight", 0.0))

                # Class-level weights
                for cls, w in (pf_def.get("classes", {}) or {}).items():
                    class_w[cls] = class_w.get(cls, 0.0) + w_pf * float(w)

                # Holdings within classes (tickers)
                hp = pf_def.get("holdings_pct", {}) or {}
                for cls, items in hp.items():
                    if not isinstance(items, list):
                        continue
                    for it in items:
                        ticker = str(it.get("ticker", "")).strip()
                        pct = float(it.get("pct", 0.0))
                        if ticker and pct > 0.0 and ticker in assets_cfg:
                            asset_w[ticker] = asset_w.get(ticker, 0.0) + w_pf * (
                                pct / 100.0
                            )

            # Normalize class weights
            w_sum = max(sum(class_w.values()), 1e-12)
            for k in list(class_w.keys()):
                class_w[k] = class_w[k] / w_sum

            # Debug once for BROKERAGE-1 at y=0
            if not debug_class_w_printed and y == 0 and acct.upper().startswith("BROKERAGE-1"):
                logger.debug("core class_w %s: %s", acct, class_w)
                debug_class_w_printed = True

            # Compute per-year multiplier paths (legacy logic)
            if asset_order and asset_log_R.shape[2] > 0:
                mult_paths = np.ones(paths, dtype=float)
                # Per-class numerator/denominator for weighted avg multiplier
                cls_mult_num: Dict[str, np.ndarray] = {c: np.zeros(paths) for c in ALL_CLASSES}
                cls_mult_den: Dict[str, float] = {c: 0.0 for c in ALL_CLASSES}
                for i, ticker in enumerate(asset_order):
                    w = float(asset_w.get(ticker, 0.0))
                    if w <= 1e-12:
                        continue
                    cls = assets_cfg[ticker]["class"]
                    er = float(assets_cfg[ticker].get("expense_ratio", 0.0))
                    s_log = shock_logs.get(
                        cls, np.zeros((paths, years), dtype=float)
                    )[:, y]
                    r_log = asset_log_R[:, y, i]
                    gross = np.exp(r_log + s_log) * max(0.0, 1.0 - er)
                    mult_paths *= gross ** w
                    # Accumulate weighted gross return per class
                    if cls in cls_mult_num:
                        cls_mult_num[cls] += w * gross
                        cls_mult_den[cls] += w
                year_mult = mult_paths
                # Normalize to per-class multiplier
                cls_mult: Dict[str, np.ndarray] = {}
                for c in ALL_CLASSES:
                    if cls_mult_den[c] > 1e-12:
                        cls_mult[c] = cls_mult_num[c] / cls_mult_den[c]
                    else:
                        cls_mult[c] = np.ones(paths, dtype=float)
            else:
                # Fallback: class shock-only multipliers
                def _year_mult(cls: str) -> np.ndarray:
                    arr = shock_mats.get(cls)
                    if arr is None or arr.shape != (paths, steps):
                        return np.ones(paths, dtype=float)
                    t0 = y * spy
                    t1 = t0 + spy
                    return arr[:, t0:t1].prod(axis=1)

                eq_mult = 0.5 * _year_mult("US_STOCKS") + 0.5 * _year_mult(
                    "INTL_STOCKS"
                )
                bd_mult = (
                    _year_mult("LONG_TREAS")
                    + _year_mult("INT_TREAS")
                    + _year_mult("TIPS")
                ) / 3.0
                gd_mult = _year_mult("GOLD")
                cm_mult = _year_mult("COMMOD")

                w_equity = class_w.get("US_STOCKS", 0.0) + class_w.get(
                    "INTL_STOCKS", 0.0
                )
                w_bonds = (
                    class_w.get("LONG_TREAS", 0.0)
                    + class_w.get("INT_TREAS", 0.0)
                    + class_w.get("TIPS", 0.0)
                )
                w_gold = class_w.get("GOLD", 0.0)
                w_commod = class_w.get("COMMOD", 0.0)
                w_sum2 = max(w_equity + w_bonds + w_gold + w_commod, 1e-12)
                w_equity /= w_sum2
                w_bonds /= w_sum2
                w_gold /= w_sum2
                w_commod /= w_sum2

                year_mult = (
                    w_equity * eq_mult
                    + w_bonds * bd_mult
                    + w_gold * gd_mult
                    + w_commod * cm_mult
                )
                # Fallback cls_mult from shock multipliers per class
                cls_mult = {
                    "US_STOCKS":   _year_mult("US_STOCKS"),
                    "INTL_STOCKS": _year_mult("INTL_STOCKS"),
                    "LONG_TREAS":  _year_mult("LONG_TREAS"),
                    "INT_TREAS":   _year_mult("INT_TREAS"),
                    "TIPS":        _year_mult("TIPS"),
                    "GOLD":        _year_mult("GOLD"),
                    "COMMOD":      _year_mult("COMMOD"),
                    "OTHER":       np.ones(paths, dtype=float),
                }

            # Compound balances (no deposits, no withdrawals in core)
            if y == 0:
                start_bal = float(starting_cfg.get(acct, 0.0))
                acct_eoy_nom[acct][:, y] = np.full(paths, start_bal, dtype=float) * year_mult
                for cls in ALL_CLASSES:
                    w_cls = class_w.get(cls, 0.0)
                    acct_class_eoy_nom[acct][cls][:, y] = (
                        start_bal * w_cls * cls_mult[cls]
                    )
            else:
                prev = acct_eoy_nom[acct][:, y - 1]
                acct_eoy_nom[acct][:, y] = prev * year_mult
                for cls in ALL_CLASSES:
                    prev_cls = acct_class_eoy_nom[acct][cls][:, y - 1]
                    acct_class_eoy_nom[acct][cls][:, y] = prev_cls * cls_mult[cls]

        # Total nominal portfolio per path for year y
        total_nom_paths_y = np.zeros(paths, dtype=float)
        for acct in acct_names:
            v = np.where(
                np.isfinite(acct_eoy_nom[acct][:, y]), acct_eoy_nom[acct][:, y], 0.0
            )
            total_nom_paths_y += v
        total_nom_paths[:, y] = total_nom_paths_y

    # Real paths from deflator
    total_real_paths = total_nom_paths / deflator

    return acct_eoy_nom, total_nom_paths, total_real_paths, acct_class_eoy_nom

