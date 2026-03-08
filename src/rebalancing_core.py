# filename: rebalancing_core.py
"""
Rebalancing engine — Phase 1.

Consumes per-class balances from simulation_core.simulate_balances() and
applies drift-band rebalancing logic per account per year per path.

Design decisions (Phase 1):
  - Band: ±drift_threshold of target weight per class (default 10%)
    e.g. target 20%, threshold 10% → band is 18%-22% of account total
  - Rebalance only if ANY class drifts outside its band
  - All gains are LTCG (no lot tracking, no short-term gains in Phase 1)
  - Rebalancing is costless inside TRAD_IRA and Roth (no tax event)
  - Brokerage rebalancing realizes LTCG gains → fed into taxes_core
  - Cost basis tracked at account level (not lot level) in Phase 1
  - Target weights come from per_year_portfolios (same source as simulation)
  - Suppression: rebalancing disabled during bad markets if policy says so
  - Cap: maximum realized gains per year in brokerage (from econ policy)

Phase 2 (future):
  - Short-term lot tracking
  - Tax-loss harvesting
  - Per-lot cost basis
  - Per-path bad market detection from realized drawdown
"""

import logging
from typing import Dict, Any, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

ALL_CLASSES = [
    "US_STOCKS", "INTL_STOCKS", "LONG_TREAS",
    "INT_TREAS", "TIPS", "GOLD", "COMMOD", "OTHER",
]


# ── Account type helpers ──────────────────────────────────────────────────────

def _is_taxable(acct_name: str, acct_types: Dict[str, str]) -> bool:
    return acct_types.get(acct_name, "taxable").lower() == "taxable"


# ── Target weight extraction ──────────────────────────────────────────────────

def _target_class_weights(
    per_year_pf: Dict[str, Any],
    acct: str,
    y: int,
) -> Dict[str, float]:
    """
    Extract normalized target class weights for account at year y.
    Mirrors simulation_core._pf_defs_for_year logic.
    Returns {class: weight} summing to 1.0, or {} if no data.
    """
    rows = per_year_pf.get(acct, [])
    if not isinstance(rows, list) or not rows:
        return {}
    row = rows[min(y, len(rows) - 1)]
    pf = row.get("portfolios", {}) or {}

    class_w: Dict[str, float] = {c: 0.0 for c in ALL_CLASSES}
    for pf_def in pf.values():
        w_pf = float(pf_def.get("weight", 0.0))
        for cls, w in (pf_def.get("classes", {}) or {}).items():
            if cls in class_w:
                class_w[cls] += w_pf * float(w)

    total = sum(class_w.values())
    if total <= 1e-12:
        return {}
    return {c: v / total for c, v in class_w.items()}


# ── Drift detection ───────────────────────────────────────────────────────────

def _drift_mask(
    actual_weights: Dict[str, np.ndarray],
    target_weights: Dict[str, float],
    drift_threshold: float,
) -> np.ndarray:
    """
    Returns boolean array (paths,) — True where ANY class has drifted
    outside its band.

    Band: [target - drift_threshold*target, target + drift_threshold*target]
    e.g. target=0.20, threshold=0.10 → band [0.18, 0.22]
    """
    paths = next(iter(actual_weights.values())).shape[0]
    needs_rebal = np.zeros(paths, dtype=bool)

    for cls, target_w in target_weights.items():
        if target_w <= 1e-12:
            continue
        actual_w = actual_weights.get(cls, np.zeros(paths))
        band = drift_threshold * target_w
        drifted = (actual_w < target_w - band) | (actual_w > target_w + band)
        needs_rebal |= drifted

    return needs_rebal


# ── Rebalancing gain computation ──────────────────────────────────────────────

def _compute_rebal_gains(
    cls_bal_y: Dict[str, np.ndarray],
    target_weights: Dict[str, float],
    acct_total: np.ndarray,
    basis_fraction: np.ndarray,
    needs_rebal: np.ndarray,
    capgain_limit: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute LTCG gains from rebalancing a single brokerage account.

    Only overweight classes generate gains — selling excess above target.
    Underweight classes are buys — no taxable event.

    Parameters
    ----------
    cls_bal_y       : {class: (paths,)} current class balances this year
    target_weights  : {class: float} target allocation
    acct_total      : (paths,) total account balance
    basis_fraction  : (paths,) cost basis as fraction of market value
                      1.0 = fully at basis (no gain)
                      0.0 = fully appreciated (max gain)
    needs_rebal     : (paths,) boolean — which paths need rebalancing
    capgain_limit   : max LTCG per path per year ($). 0 = no cap.

    Returns
    -------
    rebal_gains          : (paths,) realized LTCG gains this year
    updated_basis_fraction : (paths,) updated basis after rebalancing
    """
    paths = acct_total.shape[0]
    rebal_gains = np.zeros(paths, dtype=float)

    for cls, target_w in target_weights.items():
        if target_w <= 1e-12:
            continue
        current_bal = cls_bal_y.get(cls, np.zeros(paths))
        target_bal  = target_w * acct_total

        # Sell the overweight portion — only on paths that need rebalancing
        sell_amount = np.where(
            needs_rebal & (current_bal > target_bal),
            current_bal - target_bal,
            0.0
        )
        # Gain = sell_amount * unrealized gain fraction
        gain = sell_amount * (1.0 - basis_fraction)
        rebal_gains += np.maximum(gain, 0.0)

    # Apply annual cap
    if capgain_limit > 0.0:
        rebal_gains = np.minimum(rebal_gains, capgain_limit)

    # Update basis fraction: selling appreciated shares and buying at market
    # partially resets basis toward 1.0 (new shares bought at current price)
    safe_total = np.maximum(acct_total, 1.0)
    rebal_fraction = np.where(needs_rebal, rebal_gains / safe_total, 0.0)
    updated_basis = np.clip(
        basis_fraction + rebal_fraction * (1.0 - basis_fraction),
        0.0, 1.0
    )

    return rebal_gains, updated_basis


# ── Main entry point ──────────────────────────────────────────────────────────

def apply_rebalancing(
    acct_eoy_nom: Dict[str, np.ndarray],
    acct_class_eoy_nom: Dict[str, Dict[str, np.ndarray]],
    alloc_accounts: Dict[str, Any],
    econ_policy_yearly: List[Dict[str, Any]],
    paths: int,
    years: int,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    """
    Apply annual drift-band rebalancing across all accounts.

    Parameters
    ----------
    acct_eoy_nom        : per-account total balances (paths x years) — READ ONLY
    acct_class_eoy_nom  : per-account per-class balances — READ ONLY
    alloc_accounts      : from loaders.load_allocation_yearly_accounts()
    econ_policy_yearly  : list of per-year policy dicts (length = years)
                          built by build_econ_policy_yearly()
    paths, years        : simulation dimensions

    Returns
    -------
    rebal_gains_brokerage : (paths x years) LTCG gains from brokerage rebalancing
    rebal_gains_total     : (paths x years) same as above (all taxable gains)
    basis_fractions       : {acct: (paths,)} final cost basis fractions
    """
    per_year_pf = alloc_accounts.get("per_year_portfolios", {}) or {}
    acct_names  = list(per_year_pf.keys())

    # Build acct_types lookup
    acct_types: Dict[str, str] = {}
    for row in (alloc_accounts.get("accounts") or []):
        name  = str(row.get("name",  "")).strip()
        atype = str(row.get("type", "taxable")).strip()
        if name:
            acct_types[name] = atype

    # Initial basis fraction: 0.5 (conservative Phase 1 assumption)
    # Interpretation: 50% of current market value is unrealized gain
    basis_fractions: Dict[str, np.ndarray] = {
        acct: np.full(paths, 0.5, dtype=float)
        for acct in acct_names
        if _is_taxable(acct, acct_types)
    }

    rebal_gains_brokerage = np.zeros((paths, years), dtype=float)
    rebal_gains_total     = np.zeros((paths, years), dtype=float)

    for y in range(years):
        policy       = econ_policy_yearly[y] if y < len(econ_policy_yearly) else {}
        rebal_policy = policy.get("rebalancing", {}) or {}

        brokerage_enabled = bool(rebal_policy.get("brokerage_enabled",   True))
        suppress_bad_mkt  = bool(rebal_policy.get("suppress_in_bad_market", True))
        drift_threshold   = float(rebal_policy.get("global_drift_threshold", 0.10))
        capgain_limit     = float(rebal_policy.get("brokerage_capgain_limit_k", 10.0)) * 1_000.0

        # Phase 1: bad market flag is a global off-switch
        # Phase 2: per-path drawdown detection wired in from simulator_new.py
        in_bad_market = False

        for acct in acct_names:
            acct_total = acct_eoy_nom[acct][:, y]
            acct_class = acct_class_eoy_nom.get(acct, {})

            # Current class balances this year
            cls_bal_y: Dict[str, np.ndarray] = {
                cls: acct_class[cls][:, y]
                for cls in ALL_CLASSES
                if cls in acct_class
            }

            # Target weights for this account and year
            target_w = _target_class_weights(per_year_pf, acct, y)
            if not target_w:
                continue

            # Actual weights this year
            safe_total = np.maximum(acct_total, 1.0)
            actual_w: Dict[str, np.ndarray] = {
                cls: cls_bal_y.get(cls, np.zeros(paths)) / safe_total
                for cls in ALL_CLASSES
            }

            # Which paths need rebalancing?
            needs_rebal = _drift_mask(actual_w, target_w, drift_threshold)
            if not np.any(needs_rebal):
                continue

            is_taxable_acct = _is_taxable(acct, acct_types)

            if is_taxable_acct:
                if not brokerage_enabled:
                    continue
                if suppress_bad_mkt and in_bad_market:
                    continue

                gains, updated_basis = _compute_rebal_gains(
                    cls_bal_y      = cls_bal_y,
                    target_weights = target_w,
                    acct_total     = acct_total,
                    basis_fraction = basis_fractions[acct],
                    needs_rebal    = needs_rebal,
                    capgain_limit  = capgain_limit,
                )
                basis_fractions[acct] = updated_basis
                rebal_gains_brokerage[:, y] += gains
                rebal_gains_total[:, y]     += gains

                logger.debug(
                    "[rebal] y=%d %s taxable | paths_rebal=%d "
                    "mean_gain=$%.0f max_gain=$%.0f",
                    y + 1, acct,
                    int(np.sum(needs_rebal)),
                    float(gains[needs_rebal].mean()) if np.any(needs_rebal) else 0.0,
                    float(gains.max()),
                )
            else:
                # TRAD_IRA / Roth — free rebalancing, no tax event
                logger.debug(
                    "[rebal] y=%d %s tax-free | paths_rebal=%d",
                    y + 1, acct, int(np.sum(needs_rebal)),
                )

    return rebal_gains_brokerage, rebal_gains_total, basis_fractions


# ── Policy expansion helper ───────────────────────────────────────────────────

def build_econ_policy_yearly(
    econ_policy: Dict[str, Any],
    years: int,
) -> List[Dict[str, Any]]:
    """
    Expand econ_policy {defaults, overrides} into a flat list of per-year dicts.
    """
    defaults  = econ_policy.get("defaults",  {}) or {}
    overrides = econ_policy.get("overrides", []) or []

    yearly = [dict(defaults) for _ in range(years)]

    for ov in overrides:
        yr_range = _parse_years_range(str(ov.get("years", "*")), years)
        for y in yr_range:
            if 1 <= y <= years:
                merged = dict(yearly[y - 1])
                for k, v in ov.items():
                    if k in ("years", "_comment"):
                        continue
                    if isinstance(v, dict) and isinstance(merged.get(k), dict):
                        merged[k] = {**merged[k], **v}
                    else:
                        merged[k] = v
                yearly[y - 1] = merged

    return yearly


def _parse_years_range(years_str: str, max_years: int) -> List[int]:
    s = years_str.strip()
    if s == "*":
        return list(range(1, max_years + 1))
    if "-" in s:
        parts = s.split("-")
        try:
            return list(range(int(parts[0].strip()), int(parts[1].strip()) + 1))
        except (ValueError, IndexError):
            return []
    try:
        return [int(s)]
    except ValueError:
        return []
