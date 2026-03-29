# filename: loaders.py

import json
import logging
import os
from typing import Any, Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)
import numpy as np

# Global defaults
YEARS = 30
INFL_BASELINE_ANNUAL = 0.035

CANONICAL_CLASSES = [
    "US_STOCKS", "INTL_STOCKS",
    "LONG_TREAS", "INT_TREAS",
    "TIPS", "GOLD", "COMMOD", "OTHER"
]

# -----------------------------
# Generic helpers
# -----------------------------
def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _safe_num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _years_range(spec: str, max_years: int = YEARS) -> List[int]:
    spec = str(spec).strip()
    if spec in ("*", "all"):
        return list(range(1, max_years + 1))
    if "-" in spec:
        a, b = spec.split("-", 1)
        try:
            ai = max(1, int(a)); bi = min(int(b), max_years)
        except Exception:
            return []
        return list(range(ai, bi + 1))
    try:
        y = max(1, min(int(spec), max_years))
    except Exception:
        return []
    return [y]

def _ages_range(spec: str, current_age: float, max_years: int = YEARS) -> List[int]:
    """Convert age range spec to simulation year indices (closed intervals, later row wins)."""
    spec = str(spec).strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        try:
            age_start, age_end = int(a), int(b)
        except ValueError:
            return []
        yr_start = max(1, age_start - int(current_age))
        yr_end   = min(max_years, age_end - int(current_age))
        if yr_end < yr_start:
            return []
        return list(range(yr_start, yr_end + 1))
    try:
        age = int(spec)
        yr  = age - int(current_age)
        if 1 <= yr <= max_years:
            return [yr]
    except Exception:
        pass
    return []


def _normalize_weights_from_pct_map(pct_map: Dict[str, float], add_other_if_under_100: bool = True) -> Dict[str, float]:
    total_pct = sum(max(0.0, _safe_num(v, 0.0)) for v in pct_map.values())
    p = dict(pct_map)
    if add_other_if_under_100 and total_pct > 0.0 and total_pct < 100.0:
        p["OTHER"] = 100.0 - total_pct
        total_pct = 100.0
    if total_pct <= 1e-12:
        return {}
    out = {k: max(0.0, _safe_num(v, 0.0)) / total_pct for k, v in p.items()}
    s = sum(out.values())
    if s > 0.0:
        out = {k: v / s for k, v in out.items()}
    return out

# -----------------------------
# Taxes (unified)
# -----------------------------
def load_tax_unified(path: str, state: str, filing: str) -> Dict[str, Any]:
    data = _load_json(path)
    fed = data.get("federal", {}) or {}
    states = data.get("states", {}) or {}

    filing_key = str(filing).strip()
    state_key = str(state).strip()

    ord_br = (fed.get("ordinary_brackets", {}) or {}).get(filing_key, []) or []
    qual_br = (fed.get("qualified_brackets", {}) or {}).get(filing_key, []) or []
    std_ded = (fed.get("standard_deduction", {}) or {}).get(filing_key, 0.0)

    niit_blk = fed.get("niit", {}) or {}
    niit_rate = _safe_num(niit_blk.get("rate", 0.0), 0.0)
    niit_thresh = _safe_num((niit_blk.get("threshold", {}) or {}).get(filing_key, 0.0), 0.0)

    st_cfg = states.get(state_key, {}) or {}
    st_type = str(st_cfg.get("type", "none"))
    st_ord = (st_cfg.get("ordinary_brackets", {}) or {}).get(filing_key, []) or []
    st_qual = (st_cfg.get("qualified_brackets", {}) or {}).get(filing_key, [])
    st_std_ded = _safe_num((st_cfg.get("standard_deduction", {}) or {}).get(filing_key, 0.0), 0.0)
    excise_cfg = st_cfg.get("capital_gains_excise", {}) or st_cfg.get("cg_excise", {}) or {}
    excise_rate = _safe_num(excise_cfg.get("rate", 0.0), 0.0)

    return {
        "FILING": filing_key,
        "FED_ORD": ord_br,
        "FED_QUAL": qual_br,
        "FED_STD_DED": float(std_ded),
        "NIIT_RATE": float(niit_rate),
        "NIIT_THRESH": float(niit_thresh),
        "STATE_TYPE": st_type,
        "STATE_TREAT_QUAL_AS_ORD": bool(st_cfg.get("treat_qualified_as_ordinary", False)),
        "STATE_ORD": st_ord,
        "STATE_QUAL": st_qual,
        "STATE_STD_DED": float(st_std_ded),
        "STATE_CG_EXCISE": {"rate": float(excise_rate)},
    }

# -----------------------------
# Withdrawals schedule
# -----------------------------

def _validate_withdrawal_schedule(rows: list, current_age: float, global_floor_k: float) -> None:
    """
    Validate withdrawal schedule rows. Raises ValueError on any of:
    - Overlapping age ranges
    - age_end <= age_start (reversed or zero-length range)
    - base_k > amount_k (floor exceeds target)
    - base_k < global floor_k (row floor below global floor)
    Logs a warning for ages entirely before current_age (silently skipped).
    """
    import logging as _log
    _logger = _log.getLogger(__name__)

    # Collect age-based ranges for overlap detection
    age_ranges: list = []  # [(age_start, age_end, row_index)]

    for i, row in enumerate(rows):
        if "ages" not in row:
            continue  # year-based rows not validated for age overlaps

        spec = str(row["ages"]).strip()
        if "-" not in spec:
            raise ValueError(
                f"withdrawal_schedule row {i+1}: 'ages' must be a range like '47-65', got '{spec}'"
            )
        a, b = spec.split("-", 1)
        try:
            age_start, age_end = int(a), int(b)
        except ValueError:
            raise ValueError(
                f"withdrawal_schedule row {i+1}: non-integer ages in '{spec}'"
            )

        # Rule: age_end must be > age_start
        if age_end <= age_start:
            raise ValueError(
                f"withdrawal_schedule row {i+1}: age_end ({age_end}) must be > age_start ({age_start})"
            )

        # Warn if entirely in the past
        if age_end <= current_age:
            _logger.debug(
                "withdrawal_schedule row %d: ages '%s' is entirely before current_age=%.1f — skipped",
                i+1, spec, current_age
            )

        # Rule: base_k <= amount_k
        amt_k = _safe_num(row.get("amount_k", 0.0), 0.0)
        bk    = _safe_num(row.get("base_k", global_floor_k), global_floor_k)
        if bk > amt_k:
            raise ValueError(
                f"withdrawal_schedule row {i+1} ages '{spec}': "
                f"base_k ({bk:.0f}K) > amount_k ({amt_k:.0f}K) — floor cannot exceed target"
            )

        # Rule: base_k >= global floor_k
        if bk < global_floor_k and row.get("base_k") is not None:
            _logger.warning(
                "withdrawal_schedule row %d ages '%s': base_k (%.0fK) < global floor_k (%.0fK)",
                i+1, spec, bk, global_floor_k
            )

        age_ranges.append((age_start, age_end, i+1))

    # Overlap detection: check every pair
    for i in range(len(age_ranges)):
        for j in range(i+1, len(age_ranges)):
            s1, e1, r1 = age_ranges[i]
            s2, e2, r2 = age_ranges[j]
            # Closed intervals overlap if s1 <= e2 AND s2 <= e1
            if s1 <= e2 and s2 <= e1:
                raise ValueError(
                    f"withdrawal_schedule rows {r1} and {r2} have overlapping age ranges: "
                    f"'{s1}-{e1}' and '{s2}-{e2}'. Use exclusive non-overlapping ranges, "
                    f"e.g. '47-64' and '65-74'."
                )


def load_sched(
    path: str,
    current_age: float = 0.0,
    max_years: int = YEARS,
) -> Tuple[np.ndarray, np.ndarray]:
    """Load withdrawal schedule — age-based or year-based format.

    Age-based format (recommended — self-documenting):
        Use exclusive, non-overlapping age ranges:
        { "ages": "47-64", "amount_k": 150, "base_k": 100 }
        { "ages": "65-74", "amount_k": 200, "base_k": 140 }
        { "ages": "75-95", "amount_k": 250, "base_k": 180 }

        Rules enforced:
        - Ranges must not overlap (ValueError raised)
        - age_end must be > age_start (ValueError raised)
        - base_k must be <= amount_k (ValueError raised)
        - Ages before current_age are silently skipped (warning logged)

        Conversion: year = age - current_age (year 1 = current_age + 1)

    Year-based format (legacy — still supported):
        { "years": "1-18", "amount_k": 150, "base_k": 100 }
        Year numbers are simulation-relative (year 1 = first simulation year).

    Parameters
    ----------
    path : str
        Path to the withdrawal_schedule.json file.
    current_age : float
        Owner's current age. Required for age-based format conversion.
        Pass person_cfg["current_age"] from api.py.
    max_years : int
        Simulation horizon in years (target_age - current_age).
        Arrays are sized to this length. Defaults to YEARS (30) for
        backward compatibility.

    Returns
    -------
    desired : np.ndarray (max_years,)
        Target withdrawal amount per year in dollars.
    base : np.ndarray (max_years,)
        Minimum acceptable (floor) withdrawal per year in dollars.
    """
    data = _load_json(path)
    desired = np.zeros(max_years, dtype=float)
    base    = np.zeros(max_years, dtype=float)

    global_floor_k = _safe_num(data.get("floor_k", 0.0), 0.0)
    rows = data.get("schedule", []) or []

    # Validate age-based rows before processing
    if current_age > 0:
        _validate_withdrawal_schedule(rows, current_age, global_floor_k)

    for row in rows:
        amt_k      = _safe_num(row.get("amount_k", 0.0), 0.0)
        row_base_k = _safe_num(row.get("base_k", global_floor_k), global_floor_k)

        if "ages" in row:
            # Age-based format
            spec = str(row["ages"]).strip()
            if "-" in spec:
                a, b = spec.split("-", 1)
                try:
                    age_start, age_end = int(a), int(b)
                except ValueError:
                    continue
                yr_start = max(1, age_start - int(current_age))
                yr_end   = min(max_years, age_end - int(current_age))
                yrs = list(range(yr_start, yr_end + 1)) if yr_end >= yr_start else []
            else:
                yrs = []
        else:
            # Year-based format (legacy)
            yrs = _years_range(str(row.get("years", "*")), max_years)

        for y in yrs:
            if 1 <= y <= max_years:
                desired[y - 1] = amt_k      * 1000.0
                base[y - 1]    = row_base_k * 1000.0

    return desired, base

# -----------------------------
# Inflation
# -----------------------------
def load_inflation_yearly(path: Optional[str], years_count: int = YEARS) -> Optional[List[float]]:
    if not path:
        return None
    data = _load_json(path)
    annual = data.get("annual")
    if isinstance(annual, list) and len(annual) > 0:
        arr = [float(x) for x in annual]
        if len(arr) < years_count:
            arr += [arr[-1]] * (years_count - len(arr))
        elif len(arr) > years_count:
            arr = arr[:years_count]
        return arr
    infl_rows = data.get("inflation", []) or []
    # default_rate_pct: top-level field in inflation_yearly.json.
    # Sets the fallback rate for any year not covered by an explicit row.
    # If absent, falls back to INFL_BASELINE_ANNUAL (3.5%).
    _default_pct = data.get("default_rate_pct")
    _default_dec = max(-1.0, float(_default_pct) / 100.0) if _default_pct is not None else INFL_BASELINE_ANNUAL
    out = [_default_dec] * years_count
    for r in infl_rows:
        yrs = _years_range(str(r.get("years", "*")), years_count)
        rate_pct = _safe_num(r.get("rate_pct", 0.0), 0.0)
        rate_dec = max(-1.0, rate_pct / 100.0)
        for y in yrs:
            if 1 <= y <= years_count:
                out[y - 1] = rate_dec
    return out

# -----------------------------
# Shocks
# -----------------------------
def load_shocks(path: Optional[str]) -> Tuple[List[Dict[str, Any]], str, List[str]]:
    """Load shock events from JSON. Mode is ignored from file — UI run parameter always wins.
    Returns (events, "", class_list) — mode field intentionally empty so api.py uses UI choice.
    Events with enabled=false are excluded from the returned list."""
    if not path:
        return [], "", []
    data = _load_json(path)
    # Intentionally do NOT read "mode" from JSON — mode comes from the UI run parameter only
    all_events = data.get("events", []) or []
    # Filter out explicitly disabled events (enabled=false); default is enabled
    events = [e for e in all_events if e.get("enabled", True) is not False]
    class_list = sorted({str(e.get("class", "")).strip() for e in events if str(e.get("class", "")).strip()})
    return events, "", class_list

def load_system_shocks(path: Optional[str], preset: str) -> Tuple[List[Dict[str, Any]], str, List[str]]:
    """Load a named system shock preset from system_shocks.json.
    These are read-only presets; mode is always augment.
    Returns (events, "augment", class_list)."""
    if not path or not os.path.isfile(path):
        return [], "augment", []
    data = _load_json(path)
    presets = data.get("presets", {})
    preset_data = presets.get(preset)
    if not preset_data:
        return [], "augment", []
    events = preset_data.get("events", []) or []
    class_list = sorted({str(e.get("class", "")).strip() for e in events if str(e.get("class", "")).strip()})
    return events, "augment", class_list

# -----------------------------
# Allocation (begin + overrides → expanded per_year_portfolios)
# -----------------------------
def load_allocation_yearly_accounts(path: str) -> Dict[str, Any]:
    cfg = _load_json(path)
    warnings: List[str] = []

    # Accounts (authoring list) or infer from per_year_portfolios
    accounts_list = cfg.get("accounts", []) or []
    accounts: Dict[str, str] = {}
    for row in accounts_list:
        name = str(row.get("name", "")).strip()
        acct_type = str(row.get("type", "taxable")).strip()
        if not name:
            warnings.append("Account with empty name skipped.")
            continue
        accounts[name] = acct_type
    acct_names = list(accounts.keys()) if accounts_list else list((cfg.get("per_year_portfolios", {}) or {}).keys())

    # Starting
    starting_cfg = cfg.get("starting", {}) or {}
    starting: Dict[str, float] = {acct: float(_safe_num(starting_cfg.get(acct, 0.0), 0.0)) for acct in acct_names}

    # Deposits (accept either 'deposits' or 'deposits_yearly' with rows)
    deposits_cfg_rows = cfg.get("deposits", []) or cfg.get("deposits_yearly", []) or []
    deposits_yearly: Dict[str, np.ndarray] = {acct: np.zeros(YEARS, dtype=float) for acct in acct_names}
    for row in deposits_cfg_rows:
        yrs = _years_range(str(row.get("years", "*")))
        for acct in acct_names:
            amt = _safe_num(row.get(acct, 0.0), 0.0)
            for y in yrs:
                if 1 <= y <= YEARS:
                    deposits_yearly[acct][y - 1] = float(amt)

    # Normalization helpers
    def _normalize_portfolio_weights(portfolios: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        for name, p in portfolios.items():
            p.pop("weight", None)
        total_pct = sum(max(0.0, _safe_num(p.get("weight_pct", 0.0), 0.0)) for p in portfolios.values())
        if total_pct <= 0.0:
            for name in portfolios.keys():
                portfolios[name]["weight"] = 0.0
            return portfolios
        for name, p in portfolios.items():
            pct = max(0.0, _safe_num(p.get("weight_pct", 0.0), 0.0))
            p["weight"] = pct / total_pct
        s = sum(p.get("weight", 0.0) for p in portfolios.values())
        if s > 0.0:
            for name, p in portfolios.items():
                p["weight"] = p["weight"] / s
        return portfolios

    def _normalize_classes_in_portfolio(portfolio: Dict[str, Any]) -> Dict[str, float]:
        classes_pct = portfolio.get("classes_pct")
        classes_weights = portfolio.get("classes")
        if isinstance(classes_pct, dict):
            return _normalize_weights_from_pct_map({k: _safe_num(v, 0.0) for k, v in classes_pct.items()}, add_other_if_under_100=True)
        if isinstance(classes_weights, dict):
            s = sum(float(v) for v in classes_weights.values())
            if s <= 0.0:
                return {"OTHER": 1.0}
            return {k: float(v) / s for k, v in classes_weights.items()}
        return {"OTHER": 1.0}

    def _resolve_year_item(src: Dict[str, Any]) -> Dict[str, Any]:
        pf_map = (src.get("portfolios", {}) or {})
        for pf_name, pf in pf_map.items():
            pf["classes"] = _normalize_classes_in_portfolio(pf)
            pf.pop("weight", None)
        pf_map = _normalize_portfolio_weights(pf_map)
        return {"portfolios": pf_map}

    # If already expanded, normalize and return
    if "per_year_portfolios" in cfg and isinstance(cfg["per_year_portfolios"], dict) and cfg["per_year_portfolios"]:
        per_year_portfolios = cfg["per_year_portfolios"]
        # Normalize each year's pf maps and pad/trim to YEARS
        for acct, seq in per_year_portfolios.items():
            fixed_seq = []
            for item in seq:
                fixed_seq.append(_resolve_year_item(item))
            if len(fixed_seq) < YEARS and fixed_seq:
                fixed_seq = fixed_seq + [fixed_seq[-1]] * (YEARS - len(fixed_seq))
            elif len(fixed_seq) > YEARS:
                fixed_seq = fixed_seq[:YEARS]
            per_year_portfolios[acct] = fixed_seq
        return {
            "starting": starting,
            "deposits_yearly": deposits_yearly,
            "per_year_portfolios": per_year_portfolios,
            "warnings": warnings,
        }

    # Else expand begin + overrides
    begin = cfg.get("global_allocation") or cfg.get("begin") or {}
    per_year_portfolios: Dict[str, List[Dict[str, Any]]] = {acct: [] for acct in acct_names}
    for acct in acct_names:
        src0 = begin.get(acct, {}) or {}
        item0 = _resolve_year_item(src0)
        per_year_portfolios[acct].append(item0)

    # Replicate base to YEARS
    for acct in acct_names:
        base_item = per_year_portfolios[acct][0] if per_year_portfolios[acct] else {"portfolios": {}}
        for y in range(1, YEARS):
            pf_copy: Dict[str, Dict[str, Any]] = {}
            for pf_name, pf in (base_item.get("portfolios", {}) or {}).items():
                pf_copy[pf_name] = {
                    "weight": float(pf.get("weight", 0.0)),
                    "classes": dict(pf.get("classes", {})),
                    "holdings_pct": dict(pf.get("holdings_pct", {})),
                }
            per_year_portfolios[acct].append({"portfolios": pf_copy})

    # Apply overrides
    overrides = cfg.get("overrides", []) or []
    for ov in overrides:
        yrs = _years_range(ov.get("years", "*"), YEARS)
        mode = str(ov.get("mode", "augment")).strip().lower()
        for acct in acct_names:
            acct_block = ov.get(acct, {}) or {}
            pf_changes = (acct_block.get("portfolios", {}) or {})
            if not pf_changes:
                continue
            for y in yrs:
                idx = y - 1
                current = per_year_portfolios[acct][idx]
                cur_pf = dict(current.get("portfolios", {}) or {})

                if mode == "override":
                    new_pf = {}
                    for pf_name, pf in pf_changes.items():
                        pf["classes"] = _normalize_classes_in_portfolio(pf)
                        pf.pop("weight", None)
                        new_pf[pf_name] = {
                            "weight_pct": _safe_num(pf.get("weight_pct", 0.0), 0.0),
                            "classes": pf["classes"],
                            "holdings_pct": dict(pf.get("holdings_pct", {})),
                        }
                    cur_pf = new_pf
                elif mode == "augment":
                    for pf_name, pf in pf_changes.items():
                        base = cur_pf.get(pf_name, {"classes": {}, "holdings_pct": {}, "weight_pct": 0.0})
                
                        # Start from base classes and holdings
                        merged_classes = dict(base.get("classes", {}) or {})
                        merged_holdings = dict(base.get("holdings_pct", {}) or {})
                
                        # If override specifies classes_pct or classes, recompute classes; otherwise keep base
                        if "classes_pct" in pf or "classes" in pf:
                            pf_classes = _normalize_classes_in_portfolio(pf)
                            if pf_classes:
                                merged_classes = pf_classes
                
                        # If override specifies holdings_pct, merge/replace holdings
                        for k, v in (pf.get("holdings_pct", {}) or {}).items():
                            merged_holdings[k] = v
                
                        # Weight_pct: override if provided, else keep base
                        w_pct = _safe_num(pf.get("weight_pct", base.get("weight_pct", 0.0)), 0.0)
                
                        cur_pf[pf_name] = {
                            "weight_pct": w_pct,
                            "classes": merged_classes,
                            "holdings_pct": merged_holdings,
                        }


                elif mode == "delta":
                    for pf_name, pf in pf_changes.items():
                        delta = _safe_num(pf.get("delta_pct", 0.0), 0.0)
                        base = cur_pf.get(pf_name, {"weight_pct": 0.0, "classes": {}, "holdings_pct": {}})
                        cur_pf[pf_name] = {
                            "weight_pct": max(0.0, _safe_num(base.get("weight_pct", 0.0), 0.0) + delta),
                            "classes": base.get("classes", {}),
                            "holdings_pct": base.get("holdings_pct", {}),
                        }

                elif mode == "scale":
                    for pf_name, pf in pf_changes.items():
                        factor = _safe_num(pf.get("scale", 1.0), 1.0)
                        base = cur_pf.get(pf_name, {"weight_pct": 0.0, "classes": {}, "holdings_pct": {}})
                        cur_pf[pf_name] = {
                            "weight_pct": max(0.0, _safe_num(base.get("weight_pct", 0.0), 0.0) * factor),
                            "classes": base.get("classes", {}),
                            "holdings_pct": base.get("holdings_pct", {}),
                        }

                elif mode == "retarget":
                    for pf_name, pf in pf_changes.items():
                        base = cur_pf.get(pf_name, {"weight_pct": 0.0, "classes": {}, "holdings_pct": {}})
                        cur_pf[pf_name] = {
                            "weight_pct": _safe_num(pf.get("weight_pct", _safe_num(base.get("weight_pct", 0.0), 0.0)), 0.0),
                            "classes": base.get("classes", {}),
                            "holdings_pct": base.get("holdings_pct", {}),
                        }

                # Build normalized pf map
                normalized_pf = {}
                for name, pf in cur_pf.items():
                    pf_norm_classes = pf.get("classes", {}) or {}
                    if "classes_pct" in pf:
                        pf_norm_classes = _normalize_classes_in_portfolio(pf)
                    normalized_pf[name] = {
                        "weight_pct": _safe_num(pf.get("weight_pct", 0.0), 0.0),
                        "classes": pf_norm_classes,
                        "holdings_pct": dict(pf.get("holdings_pct", {})),
                    }

                # Normalize weights
                normalized_pf = _normalize_portfolio_weights(normalized_pf)

                per_year_portfolios[acct][idx] = {"portfolios": normalized_pf}

    # at the very end of load_allocation_yearly_accounts, just before return
    result = {
        "starting": starting,
        "deposits_yearly": deposits_yearly,
        "per_year_portfolios": per_year_portfolios,
        "account_types": accounts,   # dict: account_name → type string (taxable/traditional_ira/roth_ira)
        "warnings": warnings,
    }
    logger.debug("[DEBUG loaders] alloc_accounts keys: %s", list(result.keys()))
    logger.debug("[DEBUG loaders] per_year_portfolios accounts: %s", list(per_year_portfolios.keys()))
    return result


# -----------------------------
# Validation
# -----------------------------
def validate_alloc_accounts(alloc_accounts: Dict[str, Any]) -> None:
    starting = alloc_accounts.get("starting", {}) or {}
    deposits_yearly = alloc_accounts.get("deposits_yearly", {}) or {}
    per_year = alloc_accounts.get("per_year_portfolios", {}) or {}

    # Validate the processed structure returned by load_allocation_yearly_accounts
    if not isinstance(per_year, dict) or not per_year:
        raise ValueError("per_year_portfolios missing or empty in alloc_accounts")





    for acct, seq in per_year.items():
        if not isinstance(seq, list) or len(seq) != YEARS:
            raise ValueError(f"Account '{acct}' must have {YEARS} yearly portfolio entries.")
        if acct not in starting:
            starting[acct] = 0.0
        if acct not in deposits_yearly:
            deposits_yearly[acct] = np.zeros(YEARS, dtype=float)
        for y, item in enumerate(seq, start=1):
            portfolios = (item or {}).get("portfolios", {}) or {}
            if not portfolios:
                raise ValueError(f"Year {y} has no portfolios for {acct}")
            wsum = sum(float(p.get("weight", 0.0)) for p in portfolios.values())
            if not (0.999 <= wsum <= 1.001):
                raise ValueError(f"Year {y} {acct} portfolio weights must sum to 1.0; got {wsum:.4f}")
            for name, pf in portfolios.items():
                classes = pf.get("classes", {}) or {}
                csum = sum(float(v) for v in classes.values())
                if not (0.999 <= csum <= 1.001):
                    raise ValueError(f"Year {y} {acct}:{name} class weights must sum to 1.0; got {csum:.4f}")

# -----------------------------
# Person
# -----------------------------
def load_person(path: str) -> Dict[str, Any]:
    data = _load_json(path)

    # current_age: "compute" → derive from birth_year and today's date
    _raw_age = data.get("current_age", 0.0)
    if str(_raw_age).strip().lower() == "compute":
        _birth_year = int(data.get("birth_year", 0) or 0)
        if _birth_year > 0:
            import datetime as _dt
            _today = _dt.date.today()
            # Age = years since birth_year, adjusted for whether birthday has passed
            _birth_month = int(data.get("birth_month", 1) or 1)
            _birth_day   = int(data.get("birth_day",   1) or 1)
            try:
                _bday = _dt.date(_birth_year, _birth_month, _birth_day)
            except ValueError:
                _bday = _dt.date(_birth_year, 1, 1)
            current_age = float(
                _today.year - _bday.year
                - ((_today.month, _today.day) < (_bday.month, _bday.day))
            )
        else:
            raise ValueError(
                "person.json: current_age='compute' requires a valid birth_year"
            )
    else:
        current_age = _safe_num(_raw_age, 0.0)

    retirement_age = _safe_num(
        data.get("retirement_age", data.get("current_age", 0.0)),
        0.0,
    )

    person_cfg: Dict[str, Any] = {
        "current_age": current_age,
        "retirement_age": retirement_age,
        "birth_year": int(data.get("birth_year", 0) or 0),
        "spouse": data.get("spouse", {}) or {},
        # Backwards-compatible: keep a generic conversion_policy
        "conversion_policy": data.get("conversion_policy", data.get("roth_conversion_policy", {})) or {},
    }

    # Pass through additional fields that are useful elsewhere
    if "assumed_death_age" in data:
        person_cfg["assumed_death_age"] = _safe_num(data.get("assumed_death_age", 0.0), 0.0)

    if "filing_status" in data:
        person_cfg["filing_status"] = data.get("filing_status")

    if "beneficiaries" in data:
        person_cfg["beneficiaries"] = data.get("beneficiaries", {}) or {}

    # New: keep rmd_policy as-is for RMD extra-handling behavior
    if "rmd_policy" in data:
        person_cfg["rmd_policy"] = data.get("rmd_policy", {}) or {}

    # Also keep the original roth_conversion_policy if present
    if "roth_conversion_policy" in data:
        person_cfg["roth_conversion_policy"] = data.get("roth_conversion_policy", {}) or {}

    # Pass through target_age (used by api.py for n_years computation)
    if "target_age" in data:
        person_cfg["target_age"] = int(_safe_num(data.get("target_age", 95), 95))

    # simulation_mode: automatic | investment | retirement | balanced
    person_cfg["simulation_mode"] = data.get("simulation_mode", "automatic")

    return person_cfg


# -----------------------------
# Income
# -----------------------------
def load_income(
    path: str,
    current_age: float = 0.0,
    max_years: int = YEARS,
) -> Dict[str, Any]:
    """Load income schedule — supports both age-based and year-based formats.

    Age-based format (recommended — self-documenting):
        { "ages": "47-64", "amount": 350000 }
        Converted to years using current_age: year = age - current_age

    Year-based format (legacy — still supported):
        { "years": "1-18", "amount": 350000 }

    dollar_type field (optional per row):
        "current" (default) — amount is in today's purchasing power; real value held constant.
        "future"            — amount is the actual nominal dollar received at that future date.
        Legacy field "amount_nom" is still accepted as a fallback for backward compatibility.

    Parameters
    ----------
    path : str
        Path to income.json
    current_age : float
        Owner's current age. Required for age-based format.
    max_years : int
        Simulation horizon. Arrays sized to this length.
    """
    data = _load_json(path)

    def _expand_series(rows_key: str) -> np.ndarray:
        out = np.zeros(max_years, dtype=float)
        for r in (data.get(rows_key, []) or []):
            # 'amount' is the canonical field name; 'amount_nom' is legacy (still supported)
            amt = _safe_num(r.get("amount", r.get("amount_nom", 0.0)), 0.0)
            if "ages" in r:
                yrs = _ages_range(str(r["ages"]), current_age, max_years)
            else:
                yrs = _years_range(str(r.get("years", "*")), max_years)
            for y in yrs:
                if 1 <= y <= max_years:
                    out[y - 1] = amt
        return out

    def _expand_is_future(rows_key: str) -> np.ndarray:
        """Per-year dollar_type flag: 1.0 = future/nominal dollars, 0.0 = current/real (default).
        'future' means the amount is already in nominal dollars as-of the start year of the range.
        'current' (default) means the amount is in today's purchasing power — the simulator
        inflates it each year so the real value stays constant.
        For 'future' entries: api.py divides by deflator[y] to convert to current USD."""
        out = np.zeros(max_years, dtype=float)  # default: current dollars
        for r in (data.get(rows_key, []) or []):
            if str(r.get("dollar_type", "current")).strip().lower() != "future":
                continue  # current is the default — leave as 0.0
            if "ages" in r:
                yrs = _ages_range(str(r["ages"]), current_age, max_years)
            else:
                yrs = _years_range(str(r.get("years", "*")), max_years)
            for y in yrs:
                if 1 <= y <= max_years:
                    out[y - 1] = 1.0
        return out

    def _expand_misc_taxable(rows: list) -> np.ndarray:
        """Per-year taxability flag for misc income (1.0 = taxable, 0.0 = non-taxable).
        Defaults to 1.0 (taxable) unless row has "taxable": false.
        Non-taxable misc (gifts, inheritances) still flows for surplus routing
        but is excluded from ordinary_income_cur_paths in the tax engine."""
        out = np.ones(max_years, dtype=float)  # default: all taxable
        for r in (rows or []):
            if bool(r.get("taxable", True)):
                continue  # taxable = default, leave as 1.0
            # Non-taxable entry: mark those years as 0.0
            if "ages" in r:
                yrs = _ages_range(str(r["ages"]), current_age, max_years)
            else:
                yrs = _years_range(str(r.get("years", "*")), max_years)
            for y in yrs:
                if 1 <= y <= max_years:
                    out[y - 1] = 0.0
        return out

    _income_types = ["w2", "rental", "interest", "ordinary_other",
                     "qualified_div", "cap_gains", "misc"]
    result = {t: _expand_series(t) for t in _income_types}
    result["misc_taxable"] = _expand_misc_taxable(data.get("misc", []))
    # Per-year future-dollar flags — 1.0 where dollar_type="future", 0.0 otherwise
    for t in _income_types:
        result[f"{t}_is_future"] = _expand_is_future(t)
    return result

# -----------------------------
# Economic policy
# -----------------------------
def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Merge override on top of base, recursively for dict values. Override wins on conflict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_economic_policy(path: str, global_path: Optional[str] = None) -> Dict[str, Any]:
    """Load economic policy, optionally merging a global base file.
    global_path (economicglobal.json) is loaded first; per-profile economic.json
    is merged on top — profile keys always win on conflict.
    """
    import os as _os
    global_data  = _load_json(global_path)  if global_path and _os.path.isfile(global_path)  else {}
    profile_data = _load_json(path)          if path        and _os.path.isfile(path)          else {}

    merged_defaults  = _deep_merge(
        global_data.get("defaults", {}) or {},
        profile_data.get("defaults", {}) or {},
    )
    # Global overrides are the base; profile overrides appended on top
    merged_overrides = (global_data.get("overrides", []) or []) + (profile_data.get("overrides", []) or [])

    defaults = merged_defaults
    ws = defaults.get("withdrawal_sequence", {}) or {}
    order_good            = ws.get("order_good_market",              []) or []
    order_bad             = ws.get("order_bad_market",               []) or []
    order_bad_conversion  = ws.get("order_bad_market_with_conversion", []) or order_bad
    tira_age_gate         = float(ws.get("tira_age_gate",    59.5))
    roth_last_resort      = bool(ws.get("roth_last_resort",  True))
    logger.debug("[DEBUG loaders] order_good_market: %s", order_good)
    logger.debug("[DEBUG loaders] order_bad_market: %s", order_bad)
    logger.debug("[DEBUG loaders] order_bad_market_with_conversion: %s", order_bad_conversion)
    logger.debug("[DEBUG loaders] tira_age_gate: %s", tira_age_gate)
    return {
        "defaults":                       defaults,
        "overrides":                      merged_overrides,
        "order_good_market":              order_good,
        "order_bad_market":               order_bad,
        "order_bad_market_with_conversion": order_bad_conversion,
        "tira_age_gate":                  tira_age_gate,
        "roth_last_resort":               roth_last_resort,
    }
# --- End of file ---

