# filename: roth_optimizer.py
"""
Roth Conversion Optimizer
=========================
Computes the optimal annual Roth conversion schedule to minimize
lifetime federal tax burden for the target user profile:
  - Large TRAD IRA balance (the RMD timebomb)
  - Retirement income gap window between retirement and RMD start
  - Goal: pre-pay taxes at lower bracket rates before RMDs force higher rates

Design
------
The optimizer does NOT run a Monte Carlo. It works on a single deterministic
projection of TRAD IRA growth to find the annually-optimal bracket fill.

Key insight: The window between retirement (income stops) and RMD start
(age 73 or 75) is the prime Roth conversion window — ordinary income is
low so the effective rate on conversions is also low.

Output
------
  {
    "optimal_annual_conversion":    float,    # recommended $ to convert each year
    "bracket_to_fill":              str,       # e.g. "22%"
    "estimated_rmd_reduction":      float,    # how much lower RMDs will be at RMD start
    "estimated_lifetime_tax_savings": float,  # vs doing nothing, in today's $
    "year_by_year_schedule":        List[dict],
    "warnings":                     List[str],  # IRMAA, NIIT triggers
    "do_nothing_rmd_at_start":      float,    # RMD in first year without conversions
    "optimized_rmd_at_start":       float,    # RMD in first year with conversions
    "window_years_available":       int,      # years in the prime conversion window
  }

Usage
-----
    from roth_optimizer import optimize_roth_conversion
    from loaders import load_tax_unified

    tax_cfg = load_tax_unified(tax_path, state="California", filing="MFJ")
    result  = optimize_roth_conversion(
        trad_ira_balance = 4_800_000,
        current_age      = 46,
        retirement_age   = 65,
        rmd_start_age    = 75,
        target_death_age = 95,
        annual_growth_rate = 0.074,
        current_income   = 0,
        filing_status    = "MFJ",
        state            = "California",
        existing_roth_policy = {},
        tax_cfg          = tax_cfg,
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# IRMAA income thresholds (2026, MFJ) — 2-year lookback
# Surcharges apply to Medicare Part B/D premiums
_IRMAA_TIERS_MFJ = [
    194_000,   # Tier 1 threshold
    246_000,   # Tier 2 threshold
    306_000,   # Tier 3 threshold
    750_000,   # Tier 4 threshold
]
_IRMAA_TIERS_SINGLE = [
    97_000,
    123_000,
    153_000,
    183_000,
    500_000,
]

# NIIT threshold (2026)
_NIIT_THRESHOLD_MFJ    = 250_000
_NIIT_THRESHOLD_SINGLE = 200_000


# ---------------------------------------------------------------------------
# Tax helpers
# ---------------------------------------------------------------------------

def _calc_marginal_rate(
    income: float,
    brackets: List[Dict[str, Any]],
    std_ded: float,
) -> float:
    """Return the marginal tax rate at income (post-standard-deduction)."""
    taxable = max(0.0, income - std_ded)
    for br in sorted(brackets, key=lambda b: float(b.get("up_to") or 1e15)):
        cap = br.get("up_to")
        if cap is None or taxable <= float(cap):
            return float(br.get("rate", 0.0))
    return float(brackets[-1].get("rate", 0.0)) if brackets else 0.0


def _calc_bracket_ceiling(
    income: float,
    brackets: List[Dict[str, Any]],
    std_ded: float,
) -> Optional[float]:
    """
    Return the ceiling of the bracket income currently sits in.
    None = top bracket (no ceiling).
    Returns the gross income ceiling (before standard deduction subtraction).
    """
    taxable = max(0.0, income - std_ded)
    for br in sorted(brackets, key=lambda b: float(b.get("up_to") or 1e15)):
        cap = br.get("up_to")
        if cap is None:
            return None
        if taxable <= float(cap):
            # ceiling in gross terms
            return float(cap) + std_ded
    return None


def _calc_tax_on_amount(
    amount: float,
    income_before: float,
    brackets: List[Dict[str, Any]],
    std_ded: float,
) -> float:
    """
    Marginal tax on `amount` stacked on top of `income_before`.
    Uses progressive bracket math.
    """
    if amount <= 0:
        return 0.0
    taxable_before = max(0.0, income_before - std_ded)
    taxable_after  = max(0.0, income_before + amount - std_ded)
    tax_before = _tax_progressive(taxable_before, brackets)
    tax_after  = _tax_progressive(taxable_after, brackets)
    return max(0.0, tax_after - tax_before)


def _tax_progressive(taxable: float, brackets: List[Dict[str, Any]]) -> float:
    """Total tax on taxable income (post-deduction)."""
    tax = 0.0
    prev = 0.0
    for br in sorted(brackets, key=lambda b: float(b.get("up_to") or 1e15)):
        cap  = br.get("up_to")
        rate = float(br.get("rate", 0.0))
        if cap is None:
            tax += max(0.0, taxable - prev) * rate
            break
        band = max(0.0, min(taxable, float(cap)) - prev)
        tax += band * rate
        prev = float(cap)
        if taxable <= float(cap):
            break
    return tax


# ---------------------------------------------------------------------------
# IRMAA / NIIT guard helpers
# ---------------------------------------------------------------------------

def _irmaa_nearest_tier(income: float, filing_status: str) -> Optional[float]:
    """
    Return the nearest IRMAA tier above current income (2-year lookback warning).
    None if already above all tiers.
    """
    tiers = _IRMAA_TIERS_MFJ if filing_status.upper() in ("MFJ", "MFS") else _IRMAA_TIERS_SINGLE
    for t in sorted(tiers):
        if income < t:
            return float(t)
    return None


def _niit_threshold(filing_status: str) -> float:
    return float(
        _NIIT_THRESHOLD_MFJ
        if filing_status.upper() in ("MFJ",)
        else _NIIT_THRESHOLD_SINGLE
    )


# ---------------------------------------------------------------------------
# Core optimizer
# ---------------------------------------------------------------------------

def optimize_roth_conversion(
    trad_ira_balance: float,
    current_age: int,
    retirement_age: int,
    rmd_start_age: int,
    target_death_age: int,
    annual_growth_rate: float,
    current_income: float,
    filing_status: str,
    state: str,
    existing_roth_policy: Dict[str, Any],
    tax_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute the optimal annual Roth conversion schedule.

    Parameters
    ----------
    trad_ira_balance    : current TRAD IRA balance ($)
    current_age         : primary owner's current age
    retirement_age      : age when W2/earned income stops
    rmd_start_age       : age when RMDs begin (73 or 75 per SECURE 2.0)
    target_death_age    : final planning age
    annual_growth_rate  : expected nominal annual return (e.g. 0.074)
    current_income      : annual W2 + other ordinary income (current $)
    filing_status       : "MFJ" | "Single" | ...
    state               : state name (for state tax)
    existing_roth_policy: person.json roth_conversion_policy block
    tax_cfg             : loaded tax config from load_tax_unified()
                          If None, uses simplified federal-only estimate.

    Returns
    -------
    Dict with optimal schedule and lifetime tax savings estimate.
    """
    warnings: List[str] = []

    # ── Resolve tax config ────────────────────────────────────────────────
    if tax_cfg is None:
        # Minimal fallback — federal brackets only (2026 MFJ approximation)
        tax_cfg = {
            "FED_ORD": [
                {"up_to":  23_200, "rate": 0.10},
                {"up_to":  94_300, "rate": 0.12},
                {"up_to": 201_050, "rate": 0.22},
                {"up_to": 383_900, "rate": 0.24},
                {"up_to": 487_450, "rate": 0.32},
                {"up_to": 731_200, "rate": 0.35},
                {"up_to":    None, "rate": 0.37},
            ],
            "FED_STD_DED":  29_200 if filing_status.upper() == "MFJ" else 14_600,
            "STATE_TYPE":   "none",
            "STATE_ORD":    [],
            "STATE_STD_DED": 0.0,
            "NIIT_THRESH":  _niit_threshold(filing_status),
            "NIIT_RATE":    0.038,
        }

    fed_brackets = tax_cfg.get("FED_ORD", [])
    fed_std_ded  = float(tax_cfg.get("FED_STD_DED", 29_200))
    state_type   = tax_cfg.get("STATE_TYPE", "none")
    state_bracks = tax_cfg.get("STATE_ORD", [])
    state_std    = float(tax_cfg.get("STATE_STD_DED", 0.0))
    niit_thresh  = float(tax_cfg.get("NIIT_THRESH", _niit_threshold(filing_status)))

    # ── Determine conversion window ───────────────────────────────────────
    # Prime window: retirement_age → rmd_start_age (income is lowest)
    # Secondary: current_age → retirement_age (if already retired)
    prime_start = max(int(current_age), int(retirement_age))
    prime_end   = int(rmd_start_age) - 1     # last year before RMDs force distributions
    window_years = max(0, prime_end - prime_start + 1)

    # ── Project TRAD IRA without conversions (do-nothing baseline) ───────
    years_to_rmd  = max(0, int(rmd_start_age) - int(current_age))
    years_total   = max(0, int(target_death_age) - int(current_age))

    balance_at_rmd_no_conv = float(trad_ira_balance) * (
        (1.0 + float(annual_growth_rate)) ** years_to_rmd
    )
    # RMD factor at rmd_start_age (IRS Uniform Lifetime Table)
    _rmd_factors = {
        73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9,
        78: 22.0, 79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5,
    }
    rmd_factor = float(_rmd_factors.get(int(rmd_start_age), 26.5))
    do_nothing_rmd_yr1 = balance_at_rmd_no_conv / rmd_factor

    # ── Determine annual conversion amount ────────────────────────────────
    # Strategy: fill to top of current bracket, subject to guards.
    # In the prime window, ordinary income is ~0 (retired, pre-RMD).
    # We fill up to the top of the 22% federal bracket (or policy cap).
    policy_rate_str = str(
        existing_roth_policy.get("keepit_below_max_marginal_fed_rate", "fill the bracket")
    ).strip().lower()

    # Determine baseline ordinary income during prime window
    prime_income = 0.0 if current_age >= retirement_age else float(current_income)

    # Bracket ceiling in the prime window
    ceiling = _calc_bracket_ceiling(prime_income, fed_brackets, fed_std_ded)

    if policy_rate_str == "fill the bracket":
        # Fill to the top of whichever bracket we're in
        if ceiling is not None:
            conversion_room = max(0.0, ceiling - prime_income)
        else:
            conversion_room = max(0.0, 200_000.0)   # cap at $200k if top bracket
    elif policy_rate_str.endswith("%"):
        try:
            target_rate = float(policy_rate_str.rstrip("%")) / 100.0
            # Find ceiling of that specific bracket
            for br in sorted(fed_brackets, key=lambda b: float(b.get("up_to") or 1e15)):
                if abs(float(br.get("rate", 0.0)) - target_rate) < 1e-6:
                    cap = br.get("up_to")
                    ceiling = (float(cap) + fed_std_ded) if cap is not None else None
                    break
            conversion_room = max(0.0, (ceiling or prime_income + 200_000) - prime_income)
        except Exception:
            conversion_room = 100_000.0
    else:
        conversion_room = 100_000.0   # sensible fallback

    # IRMAA guard: warn if conversion would cross a tier (Medicare surcharge kicks
    # in 2 years later — relevant when age ≥ 63 in the window)
    irmaa_age_threshold = 63
    irmaa_warn_age = prime_start if prime_start >= irmaa_age_threshold else irmaa_age_threshold
    if irmaa_warn_age <= prime_end:
        irmaa_tier = _irmaa_nearest_tier(prime_income + conversion_room, filing_status)
        if irmaa_tier is not None and (prime_income + conversion_room) >= irmaa_tier * 0.95:
            conversion_room = min(conversion_room, max(0.0, irmaa_tier - prime_income - 1))
            warnings.append(
                f"IRMAA guard: conversion capped to avoid crossing ${irmaa_tier:,.0f} "
                f"threshold (2-year Medicare premium surcharge lookback)."
            )

    # NIIT guard
    if existing_roth_policy.get("avoid_niit", False):
        if (prime_income + conversion_room) > niit_thresh:
            capped = max(0.0, niit_thresh - prime_income - 1)
            if capped < conversion_room:
                conversion_room = capped
                warnings.append(
                    f"NIIT guard: conversion capped at ${niit_thresh:,.0f} "
                    f"threshold to avoid 3.8% net investment income tax."
                )

    optimal_annual_conversion = max(0.0, float(conversion_room))

    # Cap at what TRAD IRA will actually hold (can't convert more than balance)
    if window_years > 0:
        max_conv_by_balance = float(trad_ira_balance) / window_years
        optimal_annual_conversion = min(optimal_annual_conversion, max_conv_by_balance * 2)

    # ── Determine which bracket we're filling ────────────────────────────
    bracket_rate = _calc_marginal_rate(
        prime_income + optimal_annual_conversion / 2,
        fed_brackets,
        fed_std_ded,
    )
    bracket_label = f"{int(round(bracket_rate * 100))}%"

    # ── Build year-by-year schedule ───────────────────────────────────────
    schedule: List[Dict[str, Any]] = []
    running_trad = float(trad_ira_balance)
    running_roth = 0.0
    lifetime_tax_do_nothing = 0.0
    lifetime_tax_optimized  = 0.0

    for yr in range(years_total):
        age = int(current_age) + yr
        is_prime_window = prime_start <= age <= prime_end
        year_income = 0.0 if age >= retirement_age else float(current_income)

        # RMD for this year (if applicable)
        rmd_age = int(rmd_start_age)
        rmd_factor_yr = float(_rmd_factors.get(age, 0.0))
        if age >= rmd_age and rmd_factor_yr > 0:
            rmd_amount = running_trad / rmd_factor_yr
        else:
            rmd_amount = 0.0

        # Conversion for this year
        if is_prime_window and optimal_annual_conversion > 0:
            conv_amount = min(optimal_annual_conversion, max(0.0, running_trad))
        else:
            conv_amount = 0.0

        # Taxes on conversion + ordinary income (federal + state)
        total_ordinary = year_income + rmd_amount + conv_amount
        fed_tax  = _calc_tax_on_amount(conv_amount, year_income + rmd_amount, fed_brackets, fed_std_ded)
        if state_type != "none" and state_bracks:
            st_tax = _calc_tax_on_amount(conv_amount, year_income + rmd_amount, state_bracks, state_std)
        else:
            st_tax = 0.0
        conv_tax = fed_tax + st_tax

        # Do-nothing tax (no conversion, just income + RMD)
        fed_tax_dn = _tax_progressive(max(0.0, year_income + rmd_amount - fed_std_ded), fed_brackets)
        st_tax_dn  = (_tax_progressive(max(0.0, year_income + rmd_amount - state_std), state_bracks)
                      if state_type != "none" else 0.0)
        tax_do_nothing = fed_tax_dn + st_tax_dn

        # Optimized total tax (income + RMD + conversion)
        fed_tax_opt = _tax_progressive(max(0.0, total_ordinary - fed_std_ded), fed_brackets)
        st_tax_opt  = (_tax_progressive(max(0.0, total_ordinary - state_std), state_bracks)
                       if state_type != "none" else 0.0)
        tax_optimized = fed_tax_opt + st_tax_opt

        lifetime_tax_do_nothing += tax_do_nothing
        lifetime_tax_optimized  += tax_optimized

        # Update balances
        running_trad = max(0.0, running_trad - conv_amount - rmd_amount)
        running_trad *= (1.0 + float(annual_growth_rate))
        running_roth += conv_amount
        running_roth *= (1.0 + float(annual_growth_rate))

        if age <= prime_end + 5 or (age >= rmd_age and age <= rmd_age + 5):
            schedule.append({
                "year":           yr + 1,
                "age":            age,
                "in_prime_window": bool(is_prime_window),
                "trad_ira_bal":   round(running_trad, 0),
                "roth_bal":       round(running_roth, 0),
                "rmd_amount":     round(rmd_amount, 0),
                "conversion":     round(conv_amount, 0),
                "conv_tax":       round(conv_tax, 0),
                "total_ordinary": round(total_ordinary, 0),
                "effective_rate": round(
                    (conv_tax / conv_amount * 100) if conv_amount > 1 else 0.0,
                    1
                ),
            })

    # ── Compute optimized TRAD balance at RMD start ───────────────────────
    balance_at_rmd_optimized = float(trad_ira_balance)
    for yr in range(years_to_rmd):
        age = int(current_age) + yr
        if prime_start <= age <= prime_end:
            balance_at_rmd_optimized = max(0.0,
                balance_at_rmd_optimized - optimal_annual_conversion)
        balance_at_rmd_optimized *= (1.0 + float(annual_growth_rate))

    optimized_rmd_yr1 = balance_at_rmd_optimized / rmd_factor

    rmd_reduction = max(0.0, do_nothing_rmd_yr1 - optimized_rmd_yr1)

    # Lifetime tax savings (rough estimate in today's dollars)
    # Compares total taxes paid over planning horizon: do-nothing vs optimized
    # Simplified: does not discount future dollars — directionally correct
    lifetime_savings = max(0.0, lifetime_tax_do_nothing - lifetime_tax_optimized)

    # ── Assemble warnings ─────────────────────────────────────────────────
    if window_years == 0:
        warnings.append(
            "No prime conversion window available — RMD start age is at or before "
            "retirement age. Consider converting now or within the next few years."
        )
    if do_nothing_rmd_yr1 > 200_000:
        warnings.append(
            f"RMD timebomb: without conversions, year-1 RMD at age {rmd_start_age} "
            f"is estimated at ${do_nothing_rmd_yr1:,.0f}, which will likely push "
            f"your marginal federal rate to 32%+."
        )

    return {
        "optimal_annual_conversion":      round(optimal_annual_conversion, 0),
        "bracket_to_fill":                bracket_label,
        "estimated_rmd_reduction":        round(rmd_reduction, 0),
        "estimated_lifetime_tax_savings": round(lifetime_savings, 0),
        "year_by_year_schedule":          schedule,
        "warnings":                       warnings,
        "do_nothing_rmd_at_start":        round(do_nothing_rmd_yr1, 0),
        "optimized_rmd_at_start":         round(optimized_rmd_yr1, 0),
        "window_years_available":         window_years,
        "prime_window":                   f"age {prime_start}–{prime_end}" if window_years > 0 else "none",
        "trad_ira_at_rmd_do_nothing":     round(balance_at_rmd_no_conv, 0),
        "trad_ira_at_rmd_optimized":      round(balance_at_rmd_optimized, 0),
    }
