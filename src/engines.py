# filename: engines.py

"""
Engines and helpers for the simulator:
- Per-path shock matrices (dispersion across paths)
- Guardrails parameters (drawdown-aware gates; used by simulator)
- Tax helpers (progressive brackets, dividends, capital gains)
- FIFO TaxLots (account-level and optional per-asset)
- Class-bucket rebalancing helpers (value moves between target buckets)

Phase 4 additions:
- ClassBucket struct: track nominal balances by canonical asset class inside an account
- Rebalancing helpers: compute drift vs target and apply costless moves (IRAs) or sell/buy ops (brokerage)
- Per-asset TaxLots support: lightweight structure keyed by ticker for FIFO realized gains
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any


# -----------------------------
# Global config defaults
# -----------------------------
INFL_BASELINE_ANNUAL = 0.035
INFL_VOL_ANNUAL = 0.010  # reserved
INFL_SHOCK_DOWN_PROB = 0.05
INFL_SHOCK_DOWN = -0.010
INFL_MAX = 0.08
INFL_MIN = -0.02

# Guardrails (informational; simulator may use)
GUARDRAILS = {
    "dd_cut_thresholds": [(0.10, 0.95), (0.20, 0.85), (0.30, 0.70), (0.40, 0.60)],
    "restore_step": 0.05,
    "min_multiplier": 0.50,
    "recession_extra_cut": 0.90,
}

CANONICAL_CLASSES = [
    "US_STOCKS", "INTL_STOCKS",
    "LONG_TREAS", "INT_TREAS",
    "TIPS", "GOLD", "COMMOD", "OTHER"
]


# -----------------------------
# Per-path shock matrix builder
# -----------------------------
def build_shock_matrix_from_json(events: List[Dict[str, Any]],
                                 years: int,
                                 spy: int,
                                 paths: int,
                                 mode: str = "augment") -> Dict[str, np.ndarray]:
    """
    Build per-class multiplicative shock matrices with dispersion across paths.
    Returns: dict { class_name: np.ndarray (paths, steps) }.
    """
    steps = years * spy
    out: Dict[str, np.ndarray] = {cls: np.ones((paths, steps), dtype=float) for cls in CANONICAL_CLASSES}

    rng = np.random.default_rng(123456789)

    def _span_indices(start_year: int, start_quarter: int, quarters: int) -> Tuple[int, int]:
        start_y = max(1, min(years, int(start_year)))
        start_q = max(1, min(spy, int(start_quarter)))
        start_idx = (start_y - 1) * spy + (start_q - 1)
        end_idx = min(steps, start_idx + max(0, int(quarters)))
        return start_idx, end_idx

    def _profile_linear(depth: float, span: int, rising: bool = False) -> np.ndarray:
        if span <= 0:
            return np.ones(0, dtype=float)
        frac = np.linspace(0.0, 1.0, span)
        change = (-depth) if not rising else (+depth)
        return 1.0 + change * frac

    def _profile_poly(depth: float, span: int, alpha: float, rising: bool = False) -> np.ndarray:
        if span <= 0:
            return np.ones(0, dtype=float)
        x = np.linspace(0.0, 1.0, span) ** max(0.1, float(alpha))
        change = (-depth) if not rising else (+depth)
        return 1.0 + change * x

    def _apply_event(ev: Dict[str, Any]):
        cls = str(ev.get("class", "")).strip()
        if cls not in out:
            return
        depth = float(ev.get("depth", 0.0))
        dip_q = int(ev.get("dip_quarters", 0))
        rec_q = int(ev.get("recovery_quarters", 0))
        start_year = int(ev.get("start_year", 1))
        start_quarter = int(ev.get("start_quarter", 1))
        dip_profile = ev.get("dip_profile", {}) or {}
        rise_profile = ev.get("rise_profile", {}) or {}

        s0, e0 = _span_indices(start_year, start_quarter, dip_q)
        s1, e1 = _span_indices(start_year, start_quarter + dip_q, rec_q)

        if (dip_profile.get("type", "linear") == "poly"):
            alpha = float(dip_profile.get("alpha", 1.2))
            dip_mult = _profile_poly(depth, max(0, e0 - s0), alpha, rising=False)
        else:
            dip_mult = _profile_linear(depth, max(0, e0 - s0), rising=False)

        if (rise_profile.get("type", "linear") == "poly"):
            alpha = float(rise_profile.get("alpha", 1.2))
            rec_mult = _profile_poly(depth, max(0, e1 - s1), alpha, rising=True)
        else:
            rec_mult = _profile_linear(depth, max(0, e1 - s1), rising=True)

        base = out[cls]
        if s0 < e0:
            if mode == "override":
                base[:, s0:e0] = dip_mult
            else:
                base[:, s0:e0] *= dip_mult
        if s1 < e1:
            if mode == "override":
                base[:, s1:e1] = rec_mult
            else:
                base[:, s1:e1] *= rec_mult

        # Optional co-impact across classes
        for key in ("coimpact_down", "corecovery_up"):
            sub = ev.get(key, {}) or {}
            sub_mode = str(sub.get("mode", "none")).lower()
            classes = list(sub.get("classes", []) or [])
            scale = float(sub.get("scale", 0.0))
            if not classes or sub_mode == "none" or scale <= 0.0:
                continue
            sl = slice(s0, e0) if key == "coimpact_down" else slice(s1, e1)
            if sl.start >= sl.stop:
                continue
            base_prof = dip_mult if key == "coimpact_down" else rec_mult
            for c2 in classes:
                if c2 not in out:
                    continue
                if mode == "override":
                    out[c2][:, sl] = 1.0 + (base_prof - 1.0) * scale
                else:
                    out[c2][:, sl] *= (1.0 + (base_prof - 1.0) * scale)

    for ev in (events or []):
        _apply_event(ev)

    sigma_map = {
        "US_STOCKS": 0.010,
        "INTL_STOCKS": 0.012,
        "COMMOD": 0.015,
        "GOLD": 0.012,
        "LONG_TREAS": 0.004,
        "INT_TREAS": 0.003,
        "TIPS": 0.003,
    }
    for cls, mat in out.items():
        sigma = sigma_map.get(cls, 0.008)
        noise = rng.normal(0.0, sigma, size=mat.shape)
        out[cls] = np.clip(mat * (1.0 + noise), 0.50, 1.50)
    return out


# -----------------------------
# FIFO TaxLots (account-level and per-asset)
# -----------------------------
class TaxLots:
    """
    FIFO lots with (units, basis_per_unit). Basis is nominal per unit.
    """
    def __init__(self):
        self.lots: List[Tuple[float, float]] = []

    def add(self, units: float, basis_per_unit: float):
        if units <= 1e-12:
            return
        self.lots.append((float(units), float(basis_per_unit)))

    def sell(self, units: float) -> Tuple[float, float]:
        """
        Sell units FIFO; returns (units_sold, total_basis_units).
        total_basis_units = sum(units_sold_i * basis_per_unit_i).
        """
        remaining = float(units)
        total_basis_units = 0.0
        sold = 0.0
        while remaining > 1e-12 and self.lots:
            q0, b0 = self.lots[0]
            take = min(q0, remaining)
            q0 -= take
            remaining -= take
            sold += take
            total_basis_units += take * b0
            if q0 <= 1e-12:
                self.lots.pop(0)
            else:
                self.lots[0] = (q0, b0)
        return sold, total_basis_units

    def total_units(self) -> float:
        return sum(q for q, _ in self.lots)


def make_asset_taxlots() -> Dict[str, TaxLots]:
    """
    Create per-asset TaxLots container.
    Returns a dict mapping ticker -> TaxLots.
    """
    return {}


def asset_lots_add(lots_by_ticker: Dict[str, TaxLots], ticker: str, units: float, basis_per_unit: float):
    if ticker not in lots_by_ticker:
        lots_by_ticker[ticker] = TaxLots()
    lots_by_ticker[ticker].add(units, basis_per_unit)


def asset_lots_sell(lots_by_ticker: Dict[str, TaxLots], ticker: str, units: float) -> Tuple[float, float]:
    """
    Sell units from ticker FIFO; returns (units_sold, total_basis_units).
    If ticker has no lots, returns (0.0, 0.0).
    """
    tl = lots_by_ticker.get(ticker)
    if not tl:
        return 0.0, 0.0
    return tl.sell(units)


# -----------------------------
# Class-bucket rebalancing helpers
# -----------------------------
def init_class_buckets() -> Dict[str, float]:
    """
    Initialize class buckets for canonical classes with zero nominal balances.
    """
    return {cls: 0.0 for cls in CANONICAL_CLASSES}


def class_buckets_total(buckets: Dict[str, float]) -> float:
    return float(sum(max(0.0, v) for v in buckets.values()))


def normalize_target_classes(target: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize target class weights to sum to 1.0.
    """
    s = sum(max(0.0, v) for v in target.values())
    if s <= 1e-12:
        return {cls: (1.0 if cls == "OTHER" else 0.0) for cls in CANONICAL_CLASSES}
    out = {cls: max(0.0, target.get(cls, 0.0)) / s for cls in CANONICAL_CLASSES}
    return out


def compute_class_drift(buckets: Dict[str, float], target_weights: Dict[str, float]) -> Dict[str, float]:
    """
    Compute drift by class: actual_weight - target_weight.
    Returns drift dict keyed by class.
    """
    total = class_buckets_total(buckets)
    if total <= 1e-12:
        return {cls: -target_weights.get(cls, 0.0) for cls in CANONICAL_CLASSES}
    actual_w = {cls: max(0.0, buckets.get(cls, 0.0)) / total for cls in CANONICAL_CLASSES}
    return {cls: actual_w.get(cls, 0.0) - target_weights.get(cls, 0.0) for cls in CANONICAL_CLASSES}


def rebalance_class_buckets_costless(buckets: Dict[str, float],
                                     target_weights: Dict[str, float],
                                     threshold: float = 0.10) -> Dict[str, float]:
    """
    Costless rebalance (IRAs): move nominal value across class buckets to match target within threshold.
    Returns new buckets dict (modified copy).
    """
    total = class_buckets_total(buckets)
    if total <= 1e-12:
        return dict(buckets)
    target_nom = {cls: target_weights.get(cls, 0.0) * total for cls in CANONICAL_CLASSES}
    drift = compute_class_drift(buckets, target_weights)
    max_d = max(abs(v) for v in drift.values())
    if max_d < threshold:
        return dict(buckets)
    # Move value: set buckets to target_nom (costless within IRA)
    return dict(target_nom)


def plan_brokerage_rebalance(buckets: Dict[str, float],
                             target_weights: Dict[str, float],
                             cap_nom: float,
                             threshold: float = 0.10) -> Dict[str, float]:
    """
    Brokerage rebalance plan subject to cap on sells (nominal).
    This returns a plan dict with desired nominal sells by class (positive values for sells).
    Later, simulator can translate sells into FIFO realized gains, taxes, and reallocate buys.
    """
    total = class_buckets_total(buckets)
    if total <= 1e-12 or cap_nom <= 1e-12:
        return {cls: 0.0 for cls in CANONICAL_CLASSES}
    drift = compute_class_drift(buckets, target_weights)
    max_d = max(abs(v) for v in drift.values())
    if max_d < threshold:
        return {cls: 0.0 for cls in CANONICAL_CLASSES}
    target_nom = {cls: target_weights.get(cls, 0.0) * total for cls in CANONICAL_CLASSES}
    # Overweights: classes where buckets[cls] > target_nom[cls]; plan sells from those.
    sells = {}
    remaining_cap = float(cap_nom)
    for cls in CANONICAL_CLASSES:
        excess = max(0.0, buckets.get(cls, 0.0) - target_nom.get(cls, 0.0))
        take = min(excess, remaining_cap)
        sells[cls] = take
        remaining_cap -= take
        if remaining_cap <= 1e-12:
            break
    # If cap exhausted or no excess, sells will be partial; simulator can allocate buys to underweights with proceeds.
    return {cls: float(sells.get(cls, 0.0)) for cls in CANONICAL_CLASSES}


# -----------------------------
# Tax helpers (progressive brackets)
# -----------------------------
def calc_progressive_tax(amount_nom: float, ytd_nom: float, brackets: List[Dict[str, float]]) -> float:
    """
    Progressive tax on nominal amounts across brackets with prior-ytd offsets.
    brackets: [{ "up_to": float or None (top band), "rate": float }, ... ] sorted by increasing up_to.
    """
    if amount_nom <= 1e-12:
        return 0.0
    tax = 0.0
    remaining = float(amount_nom)
    prev_cap = float(ytd_nom)
    for br in (brackets or []):
        cap = br.get("up_to"); rate = float(br.get("rate", 0.0))
        if cap is None:
            tax += remaining * rate
            remaining = 0.0
            break
        band = max(0.0, min(remaining, float(cap) - prev_cap))
        tax += band * rate
        remaining -= band
        prev_cap = float(cap)
        if remaining <= 1e-12:
            break
    return tax


def compute_dividend_taxes_components(ordinary_div_nom: float,
                                      qualified_div_nom: float,
                                      fed_ord_brackets: List[Dict[str, float]],
                                      fed_qual_brackets: List[Dict[str, float]],
                                      state_type: str,
                                      state_ord_brackets: List[Dict[str, float]],
                                      niit_rate: float,
                                      niit_threshold_nom: float,
                                      ytd_income_nom: float) -> Dict[str, float]:
    """
    Return detailed components for dividends/interest (nominal):
      { "fed_ord", "fed_qual", "state", "niit", "excise" }
    Note: state treats total dividends as ordinary; extend for state qualified brackets if needed.
    """
    fed_ord = calc_progressive_tax(ordinary_div_nom, ytd_income_nom, fed_ord_brackets)
    fed_qual = calc_progressive_tax(qualified_div_nom, ytd_income_nom + ordinary_div_nom, fed_qual_brackets)
    state = calc_progressive_tax(ordinary_div_nom + qualified_div_nom, ytd_income_nom, state_ord_brackets) if state_type != "none" else 0.0
    niit = 0.0
    if (ordinary_div_nom + qualified_div_nom + ytd_income_nom) > niit_threshold_nom:
        niit = (ordinary_div_nom + qualified_div_nom) * float(niit_rate)
    return {"fed_ord": fed_ord, "fed_qual": fed_qual, "state": state, "niit": niit, "excise": 0.0}


def compute_gains_taxes_components(realized_gains_nom: float,
                                   fed_qual_brackets: List[Dict[str, float]],
                                   state_ord_brackets: List[Dict[str, float]],
                                   niit_rate: float,
                                   niit_threshold_nom: float,
                                   ytd_income_nom: float,
                                   excise_rate_nom: float = 0.0) -> Dict[str, float]:
    """
    Return detailed components for capital gains (nominal):
      { "fed_qual", "state", "niit", "excise" }
    """
    if realized_gains_nom <= 1e-12:
        return {"fed_qual": 0.0, "state": 0.0, "niit": 0.0, "excise": 0.0}
    fed_cg = calc_progressive_tax(realized_gains_nom, ytd_income_nom, fed_qual_brackets)
    state = calc_progressive_tax(realized_gains_nom, ytd_income_nom, state_ord_brackets)
    niit = 0.0
    if (realized_gains_nom + ytd_income_nom) > niit_threshold_nom:
        niit = realized_gains_nom * float(niit_rate)
    excise = realized_gains_nom * float(excise_rate_nom)
    return {"fed_qual": fed_cg, "state": state, "niit": niit, "excise": excise}

# --- End of file ---

