# filename: roth_optimizer.py
"""
Roth Conversion Optimizer — Full BETR 2-Pass Implementation

Architecture:
  1. IRA Timebomb Severity Classifier   — uses simulation projected IRA balance at RMD age
  2. Break-Even Tax Rate (BETR) 2-Pass  — current marginal rate vs projected future rate
  3. Four Named Strategies              — conservative / balanced / aggressive / maximum
  4. Four Scenarios per Strategy        — self MFJ / self survivor / heir moderate / heir high
  5. IRMAA Guard at Age 63              — 2-year Medicare lookback; flags but doesn't block for large IRA
  6. Year-by-year schedule              — per strategy, per conversion year

Key design decisions:
  - Uses simulation's Monte Carlo median projected IRA balance at RMD age (not compound assumption)
  - IRMAA guard at 63 (not 65) — conversion in yr N affects Medicare premiums at yr N+2
  - Four strategies are a menu, not a mandate — user picks based on IRMAA sensitivity and liquidity
  - irmaa_sensitivity in roth_optimizer_config controls whether IRMAA tips recommendation
  - Survivor scenario uses single-filer brackets from spouse expected longevity
  - Heir scenario uses 10-year forced liquidation rule (SECURE Act 2.0) for non-spouse beneficiaries
  - person.json beneficiaries.contingent drives heir profiles
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 2025/2026 Federal Tax Brackets ───────────────────────────────────────────
# Mirrors taxes_states_mfj_single.json. Embedded to avoid path dependencies.

FED_BRACKETS_MFJ = [
    (23_850,   0.10),
    (96_950,   0.12),
    (206_700,  0.22),
    (394_600,  0.24),
    (501_050,  0.32),
    (751_600,  0.35),
    (None,     0.37),
]

FED_BRACKETS_SINGLE = [
    (11_925,   0.10),
    (48_475,   0.12),
    (103_350,  0.22),
    (197_300,  0.24),
    (250_525,  0.32),
    (626_350,  0.35),
    (None,     0.37),
]

STD_DED_MFJ    = 31_500.0
STD_DED_SINGLE = 15_750.0

NIIT_RATE          = 0.038
NIIT_THRESH_MFJ    = 250_000.0
NIIT_THRESH_SINGLE = 200_000.0

# IRMAA 2025/2026 MFJ MAGI thresholds — monthly per-person surcharge
IRMAA_TIERS_MFJ = [
    (212_000,  0.0),
    (266_000,  70.90),
    (334_000,  177.90),
    (402_000,  284.60),
    (750_000,  391.30),
    (None,     419.30),
]

IRMAA_TIERS_SINGLE = [
    (106_000,  0.0),
    (133_000,  70.90),
    (167_000,  177.90),
    (201_000,  284.60),
    (375_000,  391.30),
    (None,     419.30),
]

# RMD Uniform Lifetime Table — key ages
RMD_FACTORS = {
    73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9,
    78: 22.0, 79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5,
    83: 17.7, 84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4,
    88: 13.7, 89: 12.9, 90: 12.2,
}

STRATEGY_TARGETS = {
    "conservative": 0.22,
    "balanced":     0.24,
    "aggressive":   0.32,
    "maximum":      0.37,
}


# ── Bracket Utilities ─────────────────────────────────────────────────────────

def _brackets(filing: str) -> list:
    return FED_BRACKETS_MFJ if filing == "MFJ" else FED_BRACKETS_SINGLE


def marginal_rate(taxable_income: float, filing: str = "MFJ") -> float:
    """Marginal federal rate on the last dollar at taxable_income."""
    for top, rate in _brackets(filing):
        if top is None or taxable_income <= top:
            return rate
    return 0.37


def effective_rate_on_conversion(
    existing_taxable: float,
    conversion: float,
    filing: str = "MFJ",
) -> float:
    """Average effective rate across conversion amount stacked on existing_taxable income."""
    if conversion <= 0:
        return 0.0
    total_tax = 0.0
    remaining = conversion
    cursor = existing_taxable
    prev_top = 0.0
    for top, rate in _brackets(filing):
        if remaining <= 0:
            break
        ceiling = top if top is not None else cursor + remaining + 1e9
        room_in_bracket = max(0.0, ceiling - max(cursor, prev_top))
        taxable_here = min(remaining, max(0.0, ceiling - cursor))
        if taxable_here > 0:
            total_tax += taxable_here * rate
            remaining -= taxable_here
            cursor += taxable_here
        prev_top = ceiling if top is not None else 0.0
    return total_tax / conversion


def bracket_top(target_rate: float, filing: str = "MFJ") -> Optional[float]:
    for top, rate in _brackets(filing):
        if rate == target_rate:
            return top
    return None


def compute_strategy_conversion(
    strategy: str,
    current_taxable: float,
    filing: str = "MFJ",
) -> Tuple[float, float]:
    """Compute (conversion_amount, effective_rate) for a given strategy."""
    target_rate = STRATEGY_TARGETS[strategy]
    top = bracket_top(target_rate, filing)
    headroom = max(0.0, (top if top is not None else 2_000_000.0) - current_taxable)
    if headroom <= 0:
        return 0.0, target_rate
    eff = effective_rate_on_conversion(current_taxable, headroom, filing)
    return headroom, eff


# ── IRMAA Utilities ───────────────────────────────────────────────────────────

def irmaa_annual(magi: float, filing: str = "MFJ", covered: int = 2) -> float:
    """Annual IRMAA surcharge for magi (both persons if covered=2)."""
    tiers = IRMAA_TIERS_MFJ if filing == "MFJ" else IRMAA_TIERS_SINGLE
    monthly = 0.0
    for top, m in tiers:
        if top is None or magi <= top:
            monthly = m
            break
    return monthly * 12 * covered


def irmaa_cliff_info(current_magi: float, filing: str = "MFJ") -> Tuple[float, int]:
    """(headroom_to_next_tier, current_tier_index)."""
    tiers = IRMAA_TIERS_MFJ if filing == "MFJ" else IRMAA_TIERS_SINGLE
    for i, (top, _) in enumerate(tiers):
        if top is None or current_magi <= top:
            return (0.0 if top is None else top - current_magi, i)
    return (0.0, len(tiers) - 1)


# ── Timebomb Classifier ───────────────────────────────────────────────────────

def classify_ira_timebomb(
    projected_trad_ira_at_rmd: float,
    rmd_age: float = 73.0,
) -> Tuple[str, float]:
    """Returns (severity, projected_rmd_year1)."""
    factor = RMD_FACTORS.get(int(rmd_age), 26.5)
    rmd_y1 = projected_trad_ira_at_rmd / factor if factor > 0 else 0.0
    if rmd_y1 > 500_000:   sev = "CRITICAL"
    elif rmd_y1 > 200_000: sev = "SEVERE"
    elif rmd_y1 > 100_000: sev = "MODERATE"
    else:                   sev = "MANAGEABLE"
    return sev, rmd_y1


# ── BETR ──────────────────────────────────────────────────────────────────────

def compute_betr(future_rate: float, after_tax_return: float, years: float) -> float:
    """
    Break-Even Tax Rate (BETR): the threshold current rate below which converting is beneficial.

    For the standard case (tax paid from brokerage):
      Base BETR = future_rate (pay less now vs paying more later is the core decision)

    Adjusted upward for the Roth tax-free compounding advantage:
      Roth avoids tax on all future growth; TRAD (or brokerage) does not.
      This makes Roth worth slightly MORE than the simple rate comparison suggests.
      Adjustment: +0.5% per year of horizon, capped at +20%.

    Practical result:
      BETR > future_rate for long horizons → convert is attractive even if current rate
      is marginally higher than future_rate (Roth compounding advantage compensates).
      Convert if: current_marginal_rate < BETR
    """
    if years <= 0:
        return future_rate
    roth_advantage = min(0.20, 0.005 * years)
    return future_rate * (1.0 + roth_advantage)


def future_rmd_rate(
    projected_rmd_year1: float,
    other_income: float,
    filing: str = "MFJ",
) -> float:
    """Marginal rate on RMD income stacked on other retirement income."""
    std_ded = STD_DED_MFJ if filing == "MFJ" else STD_DED_SINGLE
    taxable = max(0.0, other_income + projected_rmd_year1 - std_ded)
    return marginal_rate(taxable, filing)


def heir_forced_liquidation_rate(
    inherited_ira: float,
    heir_income: float,
    heir_filing: str = "MFJ",
    years: int = 10,
) -> float:
    """Marginal rate heir pays on equal 10-yr forced IRA distributions."""
    annual_dist = inherited_ira / years
    std_ded = STD_DED_MFJ if heir_filing == "MFJ" else STD_DED_SINGLE
    taxable = max(0.0, heir_income + annual_dist - std_ded)
    return marginal_rate(taxable, heir_filing)


# ── Savings Calculation ───────────────────────────────────────────────────────

def pv_tax_savings(
    annual_conversion: float,
    eff_rate: float,
    future_rate: float,
    window_years: int,
    discount_rate: float,
) -> float:
    """Present value of converting now vs deferring to future_rate."""
    if annual_conversion <= 0 or future_rate <= eff_rate:
        return 0.0
    rate_diff = future_rate - eff_rate
    annual_saving = annual_conversion * rate_diff
    if discount_rate > 0:
        pv_factor = (1 - (1 + discount_rate) ** (-window_years)) / discount_rate
    else:
        pv_factor = float(window_years)
    return annual_saving * pv_factor


# ── Portfolio Projection Helpers ──────────────────────────────────────────────

def _trad_ira_at_age(
    portfolio: Dict[str, Any],
    years_arr: List[int],
    current_age: float,
    target_age: float,
) -> float:
    """Extract median TRAD IRA balance from simulation at target_age (current USD)."""
    if not years_arr:
        return 0.0
    target_yr_idx = len(years_arr) - 1
    for i, yr in enumerate(years_arr):
        if current_age + yr >= target_age:
            target_yr_idx = i
            break

    # Try per-account median levels (snapshot structure)
    levels = portfolio.get("inv_nom_levels_med_acct") or {}
    trad_total = 0.0
    for acct, vals in levels.items():
        if isinstance(vals, list) and len(vals) > target_yr_idx:
            if "TRAD" in acct.upper() or "TRADITIONAL" in acct.upper():
                trad_total += float(vals[target_yr_idx])

    if trad_total > 0:
        return trad_total

    # Fallback: proportion of total current_median
    median = portfolio.get("current_median") or []
    if isinstance(median, list) and len(median) > target_yr_idx:
        # TRAD IRA typically ~50% of total in accumulation phase
        return float(median[target_yr_idx]) * 0.50
    return 0.0


def _current_income_estimate(person_cfg: Dict[str, Any]) -> float:
    """
    Estimate current year ordinary income for bracket positioning.
    Uses the injected income_data arrays (year 1 = current year).
    """
    if "estimated_annual_income" in person_cfg:
        return float(person_cfg["estimated_annual_income"])

    income_data = person_cfg.get("income_data") or {}
    total = sum(float(income_data.get(k, 0) or 0)
                for k in ("w2_yr1", "rental_yr1", "ordinary_yr1"))
    return total if total > 0 else 150_000.0


def _retirement_income_estimate(person_cfg: Dict[str, Any]) -> float:
    """Estimate non-RMD retirement income (SS + pension)."""
    income_data = person_cfg.get("income_data") or {}
    ret = float(income_data.get("retirement_income", 0) or 0)
    return ret if ret > 0 else float(person_cfg.get("estimated_retirement_income", 60_000.0))


def _income_at_age(
    person_cfg: Dict[str, Any],
    age: float,
    current_age: float,
    retirement_age: float,
) -> float:
    """
    Return best estimate of ordinary income at a given age.
    Uses injected per-year arrays if available, else phase-based approximation.
    """
    income_data = person_cfg.get("income_data") or {}
    w2_arr       = income_data.get("w2_by_year") or []
    ord_arr      = income_data.get("ordinary_by_year") or []

    yr_idx = int(round(age - current_age)) - 1  # year index (0-based)

    w2_income  = float(w2_arr[yr_idx])  if 0 <= yr_idx < len(w2_arr)  else 0.0
    ord_income = float(ord_arr[yr_idx]) if 0 <= yr_idx < len(ord_arr) else 0.0

    if w2_income + ord_income > 0:
        return w2_income + ord_income

    # Fallback: phase approximation
    if age <= retirement_age:
        return _current_income_estimate(person_cfg)
    else:
        return _retirement_income_estimate(person_cfg)


# ── BETR-Optimal Conversion ───────────────────────────────────────────────────

def compute_betr_optimal_conversion(
    taxable_income: float,
    future_rate: float,
    filing: str = "MFJ",
    avoid_niit: bool = True,
    niit_threshold: float = 250_000.0,
) -> Tuple[float, float]:
    """
    Compute maximum conversion where EVERY marginal dollar is favorable:
    convert up through brackets where (marginal rate + NIIT if applicable) < future_rate.

    Key insight: avoid_niit=True is a user preference, not a hard constraint.
    If paying 32% + 3.8% NIIT = 35.8% now beats future RMD rate of 37%+,
    the optimizer should still recommend it — the NIIT cost is already baked
    into the arbitrage signal.

    Returns (conversion_amount, effective_rate_on_conversion).
    """
    NIIT_RATE = 0.038
    brackets = _brackets(filing)
    total_conv = 0.0
    cursor = taxable_income

    for top, rate in brackets:
        ceiling = top if top is not None else cursor + 10_000_000.0
        headroom = max(0.0, ceiling - cursor)
        if headroom <= 0:
            continue

        # Does this bracket headroom sit above NIIT threshold?
        # If so, effective rate includes NIIT surcharge
        niit_applies = (cursor >= niit_threshold) or (taxable_income >= niit_threshold)
        effective_marginal = rate + (NIIT_RATE if niit_applies else 0.0)

        if effective_marginal >= future_rate:
            break  # no arbitrage — even with NIIT, not worth converting here

        total_conv += headroom
        cursor = ceiling

    if total_conv <= 0:
        return 0.0, 0.0

    eff = effective_rate_on_conversion(taxable_income, total_conv, filing)
    # Add blended NIIT cost if income + conversion exceeds threshold
    if taxable_income >= niit_threshold:
        eff += NIIT_RATE  # entire conversion is in NIIT territory
    elif taxable_income + total_conv > niit_threshold:
        niit_portion = taxable_income + total_conv - niit_threshold
        eff += NIIT_RATE * (niit_portion / total_conv)

    return round(total_conv), round(eff, 4)


# ── Year-by-Year Schedule ─────────────────────────────────────────────────────

def _build_schedule(
    strategy_name: str,
    annual_conversion: float,   # flat amount used for non-betr strategies
    current_age: float,
    retirement_age: float,
    window_years: int,
    current_income: float,      # kept for compat but overridden by _income_at_age
    filing: str,
    person_cfg: Optional[Dict[str, Any]] = None,
    future_rate: float = 0.35,  # used for betr_optimal strategy
) -> List[Dict[str, Any]]:
    """
    Build year-by-year conversion schedule.

    For 'betr_optimal': each year's conversion is computed individually from
    actual income at that age vs the future RMD rate — no fixed bracket cap.
    For other strategies: uses flat annual_conversion with per-year effective rate.
    """
    std_ded = STD_DED_MFJ if filing == "MFJ" else STD_DED_SINGLE
    schedule = []
    cum_conv = cum_tax = 0.0
    is_betr  = (strategy_name == "betr_optimal")

    for yr in range(1, window_years + 1):
        age = current_age + yr

        # Per-year income — use arrays if available
        if person_cfg is not None:
            inc = _income_at_age(person_cfg, age, current_age, retirement_age)
        else:
            inc = current_income if age <= retirement_age else current_income * 0.10

        taxable = max(0.0, inc - std_ded)

        # Withdrawal from schedule
        wd_arr = (person_cfg.get("income_data") or {}).get("withdrawal_by_year") or [] if person_cfg else []
        wd_yr  = float(wd_arr[yr - 1]) if yr - 1 < len(wd_arr) else 0.0

        # Approximate tax on ordinary income alone (no conversion, no RMD)
        # Used only for total_spendable estimate — rough but directionally correct
        _inc_tax_approx = taxable * marginal_rate(taxable, filing) * 0.6  # blended approx

        if is_betr:
            # BETR-optimal: convert everything where marginal rate < future_rate
            conv_yr, eff = compute_betr_optimal_conversion(taxable, future_rate, filing)
        else:
            # Fixed strategy: use flat amount, compute effective rate for this year's income
            conv_yr = annual_conversion
            eff = effective_rate_on_conversion(taxable, conv_yr, filing) if conv_yr > 0 else 0.0

        tax_yr   = round(conv_yr * eff)
        cum_conv += conv_yr
        cum_tax  += tax_yr

        irmaa_delta = 0
        if age >= 63:
            irmaa_delta = round(
                irmaa_annual(inc + conv_yr, filing) - irmaa_annual(inc, filing)
            )

        # Phase label for UI
        if age < retirement_age:
            phase = "working"
        elif age < retirement_age + 1:
            phase = "transition"
        else:
            phase = "retirement"

        schedule.append({
            "year":                 yr,
            "age":                  round(age, 1),
            "phase":                phase,
            "income_estimate":      round(inc),
            "withdrawal":           round(wd_yr),
            "conversion":           round(conv_yr),
            "tax_cost":             tax_yr,
            "effective_rate":       round(eff, 3),
            "irmaa_delta":          irmaa_delta,
            "cumulative_converted": round(cum_conv),
            "cumulative_tax":       round(cum_tax),
            # Total spendable = withdrawal (after-tax take-home) + net income after approx tax
            # Note: withdrawal IS already after-tax; income estimate is pre-tax gross
            "total_spendable":      round(wd_yr + max(0.0, inc - _inc_tax_approx)),
        })
    return schedule


# ── Recommendation Logic ──────────────────────────────────────────────────────

def _compute_conflicts(
    person_cfg: Dict[str, Any],
    current_taxable: float,
    future_rate: float,
    window_years: int,
    atr: float,
    filing: str,
) -> List[Dict[str, Any]]:
    """
    Detect optimization opportunities — both applied (informational) and
    pending (actionable). We never silently override — we explain everything.

    Status values:
      "applied"  — already active in the current run, shown as info
      "pending"  — user setting blocks this, shown with Apply button
    """
    NIIT_RATE    = 0.038
    NIIT_THRESH  = 250_000.0
    conflicts    = []
    pol          = (person_cfg.get("roth_conversion_policy") or {})
    avoid_niit   = bool(pol.get("avoid_niit", False))
    keepit       = str(pol.get("keepit_below_max_marginal_fed_rate", "")).strip().lower()
    std_ded      = STD_DED_MFJ if filing == "MFJ" else STD_DED_SINGLE
    income_data  = (person_cfg.get("income_data") or {})
    w2_by_year   = income_data.get("w2_by_year") or []
    current_age  = float(person_cfg.get("current_age") or 59)
    is_betr      = (keepit == "betr_optimal")

    # ── NIIT during working years ─────────────────────────────────────────────
    # Compute potential savings from converting with NIIT during working years
    niit_savings = 0.0
    for yr_idx, w2 in enumerate(w2_by_year):
        age = current_age + yr_idx + 1
        if age > 75:
            break
        ord_arr = income_data.get("ordinary_by_year") or []
        inc = w2 + float(ord_arr[yr_idx] if yr_idx < len(ord_arr) else 0)
        taxable_y = max(0.0, inc - std_ded)
        if taxable_y < NIIT_THRESH:
            continue
        conv_niit_aware, _ = compute_betr_optimal_conversion(taxable_y, future_rate, filing)
        blocked = max(0.0, NIIT_THRESH - taxable_y)  # = 0 when already over threshold
        extra = max(0.0, conv_niit_aware - blocked)
        if extra > 0:
            eff_niit = effective_rate_on_conversion(taxable_y, extra, filing) + NIIT_RATE
            if eff_niit < future_rate:
                niit_savings += extra * (future_rate - eff_niit)

    if niit_savings > 0:
        pv_niit = round(niit_savings * ((1 - (1+atr)**(-window_years)) / atr if atr > 0 else window_years))
        future_pct = int(future_rate * 100)
        if is_betr:
            # Already applied — show as informational
            conflicts.append({
                "key":    "niit_override",
                "status": "applied",
                "title":  "NIIT included in working-year conversions",
                "explanation": (
                    f"Your income exceeds the ${int(NIIT_THRESH/1000)}K NIIT threshold during "
                    f"working years, so NIIT (3.8%) applies to investment income regardless. "
                    f"BETR-optimal converts through the 32% bracket at ~35.8% effective rate, "
                    f"which still beats your future RMD rate of {future_pct}% — "
                    f"saving ~{int((future_rate - 0.358)*100)}% on every converted dollar."
                ),
                "estimated_savings": pv_niit,
                "apply_field": None, "apply_value": None, "apply_label": None,
            })
        elif avoid_niit:
            # Pending — user has avoid_niit:true and non-betr strategy
            conflicts.append({
                "key":    "niit_override",
                "status": "pending",
                "title":  "Allow NIIT during working-year conversions",
                "explanation": (
                    f"Your income already exceeds the ${int(NIIT_THRESH/1000)}K NIIT threshold "
                    f"during working years — NIIT (3.8%) applies to investment income regardless. "
                    f"Converting through the 32% bracket costs ~35.8% effective but beats your "
                    f"future RMD rate of {future_pct}%. Your avoid_niit setting is blocking "
                    f"profitable conversions in years when NIIT is unavoidable anyway."
                ),
                "estimated_savings": pv_niit,
                "current_setting":   "avoid_niit: true",
                "suggested_setting": "switch to betr_optimal — converts only where total rate < future rate",
                "apply_field":       "keepit_below_max_marginal_fed_rate",
                "apply_value":       "betr_optimal",
                "apply_label":       "Switch to BETR-Optimal strategy",
            })

    # ── Bracket extension ─────────────────────────────────────────────────────
    if keepit not in ("fill the bracket", "none", "", "betr_optimal"):
        try:
            cap_rate = float(keepit.replace("%", "")) / 100.0
        except ValueError:
            cap_rate = None
        if cap_rate is not None and future_rate > cap_rate + 0.02:
            for top, rate in _brackets(filing):
                if rate > cap_rate and future_rate > rate:
                    cap_ceiling  = bracket_top(cap_rate, filing) or 0.0
                    extra_conv   = min((top or 1_500_000) - cap_ceiling, 500_000)
                    if extra_conv > 0:
                        pv_sav = round(extra_conv * (future_rate - rate) *
                                       ((1 - (1+atr)**(-window_years)) / atr if atr > 0 else window_years))
                        conflicts.append({
                            "key":    "bracket_extension",
                            "status": "pending",
                            "title":  f"Extend conversions through {int(rate*100)}% bracket",
                            "explanation": (
                                f"Your policy caps conversions at {int(cap_rate*100)}% but your "
                                f"future RMD rate is {int(future_rate*100)}%. Converting through "
                                f"the {int(rate*100)}% bracket now saves {int((future_rate-rate)*100)}% "
                                f"per dollar vs paying {int(future_rate*100)}% on forced RMDs later."
                            ),
                            "estimated_savings": pv_sav,
                            "current_setting":   f"keepit_below_max_marginal_fed_rate: {int(cap_rate*100)}%",
                            "suggested_setting": f"{int(rate*100)}% (one bracket higher — still beats future rate)",
                            "apply_field":       "keepit_below_max_marginal_fed_rate",
                            "apply_value":       f"{int(rate*100)}%",
                            "apply_label":       f"Extend to {int(rate*100)}% bracket",
                        })
                    break

    return conflicts


def _policy_status(
    person_cfg: Dict[str, Any],
    rec_name: str,
    strategies_out: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare the currently configured roth_conversion_policy against the
    recommendation. Returns fields that let the UI show whether the user
    has already applied the recommendation or needs to act.
    """
    pol = (person_cfg.get("roth_conversion_policy") or {})
    enabled      = bool(pol.get("enabled", False))
    annual_k     = float(pol.get("annual_conversion_k") or 0.0)
    rec_strategy = rec_name  # e.g. "aggressive"
    rec_data     = strategies_out.get(rec_name) or {}
    rec_amount_k = float(rec_data.get("annual_conversion", 0) or 0) / 1000.0  # $ → $K

    if not enabled:
        return {
            "policy_already_applied": False,
            "configured_status": "not_configured",
            "configured_note": "Conversions disabled — click Apply to activate",
        }

    # Tolerance: within 10% of recommended amount counts as "on track"
    tolerance = 0.10
    if rec_amount_k > 0:
        within_tolerance = abs(annual_k - rec_amount_k) / rec_amount_k <= tolerance
    else:
        within_tolerance = annual_k > 0

    if within_tolerance:
        return {
            "policy_already_applied": True,
            "configured_status": "on_track",
            "configured_note": f"Already configured — {rec_strategy.capitalize()} (${annual_k:.0f}K/yr). Re-run to see updated projections.",
        }
    elif annual_k > 0 and annual_k < rec_amount_k * (1 - tolerance):
        return {
            "policy_already_applied": False,
            "configured_status": "under_converting",
            "configured_note": f"Converting ${annual_k:.0f}K/yr — below recommended ${rec_amount_k:.0f}K/yr. Consider increasing.",
        }
    elif annual_k > rec_amount_k * (1 + tolerance):
        return {
            "policy_already_applied": False,
            "configured_status": "over_converting",
            "configured_note": f"Converting ${annual_k:.0f}K/yr — above recommended ${rec_amount_k:.0f}K/yr. Consider reviewing.",
        }
    else:
        return {
            "policy_already_applied": False,
            "configured_status": "configured_different",
            "configured_note": f"Converting ${annual_k:.0f}K/yr (recommended: ${rec_amount_k:.0f}K/yr)",
        }


def _recommend(
    severity: str,
    strategies: Dict[str, Any],
    irmaa_sensitivity: str,
    current_age: float,
) -> Tuple[str, str]:
    severity_map = {
        "CRITICAL":   ("aggressive", "IRA timebomb severity CRITICAL. Projected RMDs force 37% bracket. IRMAA is negligible vs bracket savings. Convert aggressively at 32% now."),
        "SEVERE":     ("aggressive", "IRA timebomb severity SEVERE. Projected RMDs likely 32-35%. Converting to 32% now captures major bracket arbitrage."),
        "MODERATE":   ("balanced",   "IRA timebomb severity MODERATE. Standard 24% bracket-fill converts efficiently without excess tax in any single year."),
        "MANAGEABLE": ("conservative", "IRA timebomb severity MANAGEABLE. Conservative 22% bracket-fill reduces future RMD exposure with minimal current tax impact."),
    }
    base, reason = severity_map.get(severity, ("balanced", "Standard bracket-fill recommended."))

    # Upgrade to betr_optimal if future RMD rate exceeds the aggressive bracket (32%)
    # i.e. there's meaningful arbitrage in the 35% bracket too
    betr_data   = strategies.get("betr_optimal", {})
    betr_future = (betr_data.get("scenarios") or {}).get("self_mfj", {}).get("future_rate", 0)
    if severity in ("CRITICAL", "SEVERE") and betr_future > 0.35:
        base   = "betr_optimal"
        reason = (
            f"IRA timebomb severity {severity}. Future RMD rate {int(betr_future*100)}% exceeds "
            f"the 35% bracket — converting at 35% now saves {int((betr_future - 0.35)*100)}% on "
            f"every dollar vs waiting. Note: even if NIIT (3.8%) applies during working years, "
            f"35.8% effective still beats {int(betr_future*100)}% RMD rate. "
            f"BETR-optimal: convert through brackets where (marginal + NIIT) < future rate, "
            f"varying by year based on actual income."
        )

    # Step down if IRMAA-sensitive and near Medicare age
    if irmaa_sensitivity == "high" and current_age >= 61 and base != "betr_optimal":
        strat_data = strategies.get(base, {})
        if strat_data.get("irmaa_annual_delta", 0) > 0:
            downgrade = {"maximum": "aggressive", "aggressive": "balanced",
                         "balanced": "conservative", "conservative": "conservative"}
            orig = base
            base = downgrade.get(base, base)
            if base != orig:
                reason += f" Stepped down one tier due to IRMAA sensitivity."

    return base, reason


# ── Main Entry Point ──────────────────────────────────────────────────────────

def optimize_roth_conversion_full(
    person_cfg: Dict[str, Any],
    simulation_summary: Dict[str, Any],
    simulation_portfolio: Dict[str, Any],
    withdrawals: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Full BETR 2-pass Roth conversion optimizer.

    person_cfg:           from person.json (includes spouse, beneficiaries)
    simulation_summary:   res["summary"] from run_accounts_new
    simulation_portfolio: res["portfolio"] from run_accounts_new
    withdrawals:          res["withdrawals"] from run_accounts_new

    Returns comprehensive optimization result including 4×4 savings matrix.
    """
    # ── Person context ────────────────────────────────────────────────────────
    birth_year   = int(person_cfg.get("birth_year") or 1980)
    current_year = 2026
    ca_raw = person_cfg.get("current_age")
    if ca_raw and str(ca_raw) != "compute":
        current_age = float(ca_raw)
    else:
        current_age = float(current_year - birth_year)

    filing         = str(person_cfg.get("filing_status", "MFJ"))
    retirement_age = float(person_cfg.get("retirement_age", 65))
    target_age     = float(person_cfg.get("target_age") or person_cfg.get("assumed_death_age") or 88)

    # Spouse
    spouse_cfg = person_cfg.get("spouse") or {}
    spouse_byr = int(spouse_cfg.get("birth_year") or 0)
    spouse_age = float(current_year - spouse_byr) if spouse_byr else current_age - 5.0

    # Optimizer config
    opt_cfg           = person_cfg.get("roth_optimizer_config") or {}
    include_survivor  = bool(opt_cfg.get("include_survivor_scenario", True))
    include_heir      = bool(opt_cfg.get("include_heir_scenario", True))
    irmaa_sensitivity = str(opt_cfg.get("irmaa_sensitivity", "low")).lower()
    spouse_longevity  = float(opt_cfg.get("spouse_expected_longevity",
                                          spouse_cfg.get("expected_longevity", spouse_age + 25)))
    window_years      = int(opt_cfg.get("window_years", min(29, max(5, int(75 - current_age)))))

    # Inheritors from beneficiaries.contingent
    beneficiaries = (person_cfg.get("beneficiaries") or {}).get("contingent") or []
    non_spouse_heirs = [b for b in beneficiaries if b.get("relationship") != "spouse"]
    num_heirs = len(non_spouse_heirs) or 1

    # Heir income — use beneficiary estimated_income fields, or defaults
    heir_mod_income  = 0.0
    heir_high_income = 0.0
    heir_filing      = "MFJ"
    for h in non_spouse_heirs:
        heir_mod_income  = max(heir_mod_income,  float(h.get("estimated_income_moderate", 150_000)))
        heir_high_income = max(heir_high_income, float(h.get("estimated_income_high", 300_000)))
        heir_filing = str(h.get("filing_status", "MFJ"))
    if heir_mod_income  == 0.0: heir_mod_income  = 150_000.0
    if heir_high_income == 0.0: heir_high_income = 300_000.0

    # ── RMD setup ─────────────────────────────────────────────────────────────
    try:
        from rmd_core import rmd_start_age as _rsa
        rmd_age = _rsa(birth_year)
    except ImportError:
        rmd_age = 73.0 if birth_year <= 1959 else 75.0

    years_to_rmd   = max(0.0, rmd_age - current_age)
    years_to_death = max(0.0, target_age - current_age)

    # ── Projected IRA balances from simulation ────────────────────────────────
    years_arr = list(simulation_portfolio.get("years") or [])
    proj_trad_at_rmd  = _trad_ira_at_age(simulation_portfolio, years_arr, current_age, rmd_age)
    proj_trad_at_death = _trad_ira_at_age(simulation_portfolio, years_arr, current_age, target_age)

    # Fallback: compound from known starting balance if sim data missing
    if proj_trad_at_rmd <= 0:
        cagr = max(0.04, float(simulation_summary.get("cagr_nominal_median") or 7.0) / 100.0)
        starting = simulation_portfolio.get("starting") or {}
        trad_start = sum(float(v or 0) for k, v in starting.items()
                         if "TRAD" in k.upper())
        if trad_start <= 0:
            trad_start = 4_800_000.0
        proj_trad_at_rmd   = trad_start * ((1 + cagr) ** years_to_rmd)
        proj_trad_at_death = trad_start * ((1 + cagr) ** years_to_death)

    # ── Timebomb classification ───────────────────────────────────────────────
    severity, projected_rmd_y1 = classify_ira_timebomb(proj_trad_at_rmd, rmd_age)

    # ── Current income / bracket context ─────────────────────────────────────
    current_income   = _current_income_estimate(person_cfg)
    retirement_income = _retirement_income_estimate(person_cfg)
    std_ded          = STD_DED_MFJ if filing == "MFJ" else STD_DED_SINGLE
    current_taxable  = max(0.0, current_income - std_ded)
    current_marg     = marginal_rate(current_taxable, filing)

    # After-tax return for BETR discounting
    atr = max(0.03, float(simulation_summary.get("cagr_real_median") or 5.0) / 100.0)

    # ── Future rates (BETR Pass 2) ────────────────────────────────────────────
    fr_self_mfj  = future_rmd_rate(projected_rmd_y1, retirement_income, "MFJ")
    fr_survivor  = future_rmd_rate(projected_rmd_y1, retirement_income * 0.6, "single") \
                   if include_survivor else fr_self_mfj
    heir_share   = proj_trad_at_death / num_heirs
    fr_heir_mod  = heir_forced_liquidation_rate(heir_share, heir_mod_income,  heir_filing) \
                   if include_heir else 0.0
    fr_heir_high = heir_forced_liquidation_rate(heir_share, heir_high_income, heir_filing) \
                   if include_heir else 0.0

    betr_self    = compute_betr(fr_self_mfj, atr, years_to_rmd)
    betr_surv    = compute_betr(fr_survivor,  atr, years_to_rmd)
    betr_heir_m  = compute_betr(fr_heir_mod,  atr, years_to_death)
    betr_heir_h  = compute_betr(fr_heir_high, atr, years_to_death)

    # ── Compute all 4 fixed strategies + betr_optimal ────────────────────────
    strategies_out = {}
    for name in ("conservative", "balanced", "aggressive", "maximum"):
        conv_amt, eff_rate = compute_strategy_conversion(name, current_taxable, filing)
        tax_cost_y1 = round(conv_amt * eff_rate)

        # IRMAA
        irmaa_relevant = (current_age >= 63) or (current_age + 2 >= 63)
        magi_with_conv = current_income + conv_amt
        delta_irmaa    = round(irmaa_annual(magi_with_conv, filing) -
                               irmaa_annual(current_income, filing)) if irmaa_relevant else 0
        _, irmaa_tier  = irmaa_cliff_info(current_income, filing)

        # Savings per scenario
        def _sav(fr, yrs):
            return round(pv_tax_savings(conv_amt, eff_rate, fr, window_years, atr))

        scenarios = {
            "self_mfj": {
                "future_rate":          round(fr_self_mfj, 4),
                "betr":                 round(betr_self, 4),
                "convert_makes_sense":  current_marg <= betr_self,
                "lifetime_savings":     _sav(fr_self_mfj, years_to_rmd),
                "description":          "Self — both spouses alive (MFJ)",
            },
            "self_survivor": {
                "future_rate":          round(fr_survivor, 4),
                "betr":                 round(betr_surv, 4),
                "convert_makes_sense":  current_marg <= betr_surv,
                "lifetime_savings":     _sav(fr_survivor, years_to_rmd),
                "description":          f"Survivor — single filer from age {int(spouse_longevity)}",
            },
            "heir_moderate": {
                "future_rate":          round(fr_heir_mod, 4),
                "betr":                 round(betr_heir_m, 4),
                "convert_makes_sense":  current_marg <= betr_heir_m,
                "lifetime_savings":     _sav(fr_heir_mod, years_to_death),
                "description":          f"Heir (moderate ~${int(heir_mod_income/1000)}K/yr) — 10yr liquidation",
            },
            "heir_high": {
                "future_rate":          round(fr_heir_high, 4),
                "betr":                 round(betr_heir_h, 4),
                "convert_makes_sense":  current_marg <= betr_heir_h,
                "lifetime_savings":     _sav(fr_heir_high, years_to_death),
                "description":          f"Heir (high earner ~${int(heir_high_income/1000)}K/yr) — 10yr liquidation",
            },
        }

        irmaa_notes = []
        if irmaa_relevant and delta_irmaa > 0:
            irmaa_notes.append(
                f"Pushes MAGI to ${int(magi_with_conv):,} — IRMAA tier {irmaa_tier+1} "
                f"(+${delta_irmaa:,}/yr). "
                + ("Minor vs bracket savings." if irmaa_sensitivity == "low"
                   else "Consider staying below cliff.")
            )
        elif not irmaa_relevant:
            irmaa_notes.append(
                f"Age {int(current_age)}: IRMAA not yet active (relevant from 63). "
                f"{window_years}-yr window mostly pre-IRMAA."
            )

        strategies_out[name] = {
            "annual_conversion":    round(conv_amt),
            "bracket_filled":       f"{int(STRATEGY_TARGETS[name]*100)}%",
            "effective_rate":       round(eff_rate, 4),
            "tax_cost_year1":       tax_cost_y1,
            "irmaa_annual_delta":   delta_irmaa,
            "irmaa_notes":          irmaa_notes,
            "scenarios":            scenarios,
            "betr_primary":         round(betr_self, 4),
        }

    # ── BETR-optimal strategy ─────────────────────────────────────────────────
    # Convert everything where marginal rate NOW < future RMD effective rate.
    # This captures arbitrage even into the 35% bracket when future rate ≥ 37%.
    betr_conv, betr_eff = compute_betr_optimal_conversion(
        current_taxable, fr_self_mfj, filing
    )
    betr_tax_y1 = round(betr_conv * betr_eff)
    betr_magi   = current_income + betr_conv
    betr_irmaa  = round(irmaa_annual(betr_magi, filing) -
                        irmaa_annual(current_income, filing)) if (current_age >= 63) else 0
    # Find which bracket the BETR strategy fills to
    betr_bracket_rate = marginal_rate(current_taxable + betr_conv - 1, filing)
    strategies_out["betr_optimal"] = {
        "annual_conversion":    round(betr_conv),
        "bracket_filled":       f"{int(betr_bracket_rate*100)}% (BETR-driven)",
        "effective_rate":       round(betr_eff, 4),
        "tax_cost_year1":       betr_tax_y1,
        "irmaa_annual_delta":   betr_irmaa,
        "irmaa_notes":          [],
        "scenarios": {
            "self_mfj":      {"future_rate": round(fr_self_mfj, 4), "betr": round(betr_self, 4),
                              "convert_makes_sense": True,
                              "lifetime_savings": round(pv_tax_savings(betr_conv, betr_eff, fr_self_mfj, window_years, atr)),
                              "description": "Self — both spouses alive (MFJ)"},
            "survivor":      {"future_rate": round(fr_survivor, 4), "betr": round(betr_surv, 4),
                              "convert_makes_sense": True,
                              "lifetime_savings": round(pv_tax_savings(betr_conv, betr_eff, fr_survivor, window_years, atr)),
                              "description": "Survivor — single filer after spouse passes"},
            "heir_moderate": {"future_rate": round(fr_heir_mod, 4), "betr": round(betr_heir_m, 4),
                              "convert_makes_sense": True,
                              "lifetime_savings": round(pv_tax_savings(betr_conv, betr_eff, fr_heir_mod, window_years, atr)),
                              "description": "Heir — moderate income"},
            "heir_high":     {"future_rate": round(fr_heir_high, 4), "betr": round(betr_heir_h, 4),
                              "convert_makes_sense": True,
                              "lifetime_savings": round(pv_tax_savings(betr_conv, betr_eff, fr_heir_high, window_years, atr)),
                              "description": "Heir — high income"},
        },
        "betr_primary": round(betr_self, 4),
        "phased": True,  # signals UI that this strategy varies by year
    }

    # ── Recommendation ────────────────────────────────────────────────────────
    rec_name, rec_reason = _recommend(severity, strategies_out, irmaa_sensitivity, current_age)

    # ── Year-by-year schedule for recommended strategy ────────────────────────
    rec_conv = strategies_out[rec_name]["annual_conversion"]
    schedule = _build_schedule(
        rec_name, rec_conv, current_age, retirement_age,
        window_years, current_income, filing,
        person_cfg=person_cfg,
        future_rate=fr_self_mfj,
    )

    # ── Savings matrix (flat, for UI table) — fixed strategies only ──────────
    savings_matrix = {
        strat: {sc: d["lifetime_savings"] for sc, d in sdata["scenarios"].items()}
        for strat, sdata in strategies_out.items()
        if strat != "betr_optimal"  # betr_optimal is phase-varying — shown in schedule
    }

    # ── Global warnings ───────────────────────────────────────────────────────
    warnings = []
    if severity in ("CRITICAL", "SEVERE"):
        warnings.append(
            f"IRA Timebomb {severity}: projected RMD yr1 ~${int(projected_rmd_y1):,} "
            f"forces 37% bracket regardless of other choices. Convert aggressively now."
        )
    if include_heir and fr_heir_high >= 0.37:
        heir_strat = "betr_optimal" if "betr_optimal" in strategies_out else "aggressive"
        heir_sav   = strategies_out[heir_strat]["scenarios"]["heir_high"]["lifetime_savings"]
        warnings.append(
            f"High-earning heir faces {int(fr_heir_high*100)}% rate on 10yr forced liquidation. "
            f"Aggressive strategy saves heirs ~${heir_sav:,}."
        )
    if not non_spouse_heirs:
        warnings.append(
            "No contingent beneficiaries defined. Add beneficiaries.contingent to person.json "
            "for heir scenario analysis."
        )

    return {
        # Classification
        "timebomb_severity":           severity,
        "projected_trad_ira_at_rmd":   round(proj_trad_at_rmd),
        "projected_rmd_year1":         round(projected_rmd_y1),
        "rmd_start_age":               rmd_age,
        "years_to_rmd":                round(years_to_rmd, 1),
        "projected_ira_at_death":      round(proj_trad_at_death),
        "num_heirs":                   num_heirs,

        # Current bracket context
        "current_income":              round(current_income),
        "current_taxable_income":      round(current_taxable),
        "current_marginal_rate":       round(current_marg, 4),
        "after_tax_return_used":       round(atr, 4),

        # Future rates (Pass 2)
        "future_rate_self_mfj":        round(fr_self_mfj, 4),
        "future_rate_survivor":        round(fr_survivor, 4),
        "future_rate_heir_moderate":   round(fr_heir_mod, 4),
        "future_rate_heir_high":       round(fr_heir_high, 4),
        "betr_self_mfj":               round(betr_self, 4),
        "betr_survivor":               round(betr_surv, 4),
        "betr_heir_moderate":          round(betr_heir_m, 4),
        "betr_heir_high":              round(betr_heir_h, 4),

        # Strategies + matrix
        "strategies":                  strategies_out,
        "savings_matrix":              savings_matrix,

        # Recommendation
        "recommended_strategy":        rec_name,
        "recommended_reason":          rec_reason,

        # Optimization conflicts — settings blocking better outcomes
        "conflicts": _compute_conflicts(
            person_cfg, current_taxable, fr_self_mfj,
            window_years, atr, filing,
        ),

        # Current policy status — is the recommendation already configured?
        **_policy_status(person_cfg, rec_name, strategies_out),

        # Schedule
        "year_by_year_schedule":       schedule,
        "conversion_window_years":     window_years,

        # Warnings + metadata
        "warnings":                    warnings,
        "filing_used":                 filing,
        "include_survivor":            include_survivor,
        "include_heir":                include_heir,
    }
