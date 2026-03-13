# filename: roth_conversion_core.py

import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

YEARS = 30


def parse_roth_conversion_policy(person_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize the Roth conversion policy from person_cfg.

    Expected structure in person.json (Test profile example):

      "roth_conversion_policy": {
        "enabled": true,
        "window_years": ["now-75"],
        "keepit_below_max_marginal_fed_rate": "fill the bracket",
        "avoid_niit": true,
        "rmd_assist": "convert",
        "tax_payment_source": "BROKERAGE",
        "irmaa_guard": { "enabled": false }
      }

    For now we only normalize a few key flags and the conversion window.
    More detailed bracket / NIIT / IRMAA logic can be layered on later.
    """
    policy = person_cfg.get("roth_conversion_policy", {}) or {}
    enabled = bool(policy.get("enabled", False))

    # Window: e.g. ["now-75"] → convert from current_year .. age 75
    window_years = policy.get("window_years", [])
    window_end_age = None
    if isinstance(window_years, list) and window_years:
        token = str(window_years[0]).strip()
        if token.startswith("now-"):
            try:
                window_end_age = float(token.split("now-")[1])
            except Exception:
                window_end_age = None

    return {
        "enabled": enabled,
        "window_end_age": window_end_age,
        # Keep hooks for future policy refinements:
        "avoid_niit": bool(policy.get("avoid_niit", False)),
        "tax_payment_source": str(policy.get("tax_payment_source", "BROKERAGE")),
        "rmd_assist": str(policy.get("rmd_assist", "")),
        "raw": policy,
    }


def compute_conversion_window_years(
    current_age: float,
    window_end_age: float,
    years: int = YEARS,
) -> Tuple[int, int]:
    """
    Given a current_age and window_end_age, compute [window_start_y, window_end_y)
    indices for conversion, in 0-based year indices.

    For ["now-75"] with current_age=73, this would be roughly years 0,1,2.
    """
    if window_end_age is None:
        # If no explicit window, default to all years for lab tests
        return 0, years

    # "now" is year 0
    window_start_y = 0
    window_end_y = max(0, int(window_end_age - current_age) + 1)
    window_end_y = min(window_end_y, years)
    return window_start_y, window_end_y


def compute_bracket_headroom(
    ytd_income: float,
    target_bracket_rate: float,
    fed_ord_brackets: List[Dict[str, Any]],
) -> float:
    """
    Compute how much more ordinary income can be added before crossing
    the ceiling of the bracket at `target_bracket_rate`.

    If ytd_income is already above that bracket, returns 0.
    If target_bracket_rate is the top bracket (up_to=None), returns a
    large cap so we don't convert into infinity.

    Parameters
    ----------
    ytd_income          : income already committed this year (nominal $)
    target_bracket_rate : the rate ceiling to stay below (e.g. 0.22)
    fed_ord_brackets    : [{"up_to": float|None, "rate": float}, ...]
                          sorted by increasing up_to

    Returns
    -------
    headroom : float — how much more income fits before crossing the ceiling
    """
    brackets = sorted(
        [b for b in (fed_ord_brackets or []) if b.get("up_to") is not None],
        key=lambda b: float(b["up_to"])
    )
    # Find the ceiling of the target bracket
    ceiling = None
    for b in brackets:
        if abs(float(b.get("rate", 0.0)) - target_bracket_rate) < 1e-6:
            ceiling = float(b["up_to"])
            break

    if ceiling is None:
        # target_bracket_rate is top bracket — cap at a large but finite amount
        # to avoid runaway conversions. $500k cap is conservative.
        ceiling = ytd_income + 500_000.0

    return max(0.0, ceiling - ytd_income)


def compute_bracket_fill_conversion_paths(
    ordinary_income_cur_paths: np.ndarray,   # (paths,) income already this year
    deflator_y: float,                        # deflate nominal→current for this year
    tax_cfg: Dict[str, Any],
    roth_policy: Dict[str, Any],
    trad_total_paths: np.ndarray,            # (paths,) total TRAD balance available
    paths: int,
) -> np.ndarray:
    """
    Compute per-path Roth conversion amounts using bracket-fill logic.

    Strategy:
      1. Find the target bracket ceiling from policy
         ("fill the bracket" = stay below the NEXT bracket above current income)
      2. Compute headroom = ceiling - current_ordinary_income
         Both income and ceilings are scaled to year-y nominal $ by deflator_y,
         so the real bracket structure is inflation-stable (no bracket creep).
      3. Conversion = min(headroom, trad_balance, niit_guard)
      4. Cannot convert more than the TRAD balance

    Parameters
    ----------
    ordinary_income_cur_paths : income already committed this year, current $
                                 (RMDs + wages + SS + other)
    deflator_y                : cumprod inflation deflator for year y
    tax_cfg                   : tax configuration with FED_ORD brackets
    roth_policy               : parsed policy from parse_roth_conversion_policy()
    trad_total_paths          : total TRAD IRA balance (nominal $) for this year
    paths                     : number of simulation paths

    Returns
    -------
    conv_cur_paths : (paths,) conversion amounts in CURRENT dollars
    """
    fed_ord_brackets = tax_cfg.get("FED_ORD", [])
    avoid_niit       = bool(roth_policy.get("avoid_niit", False))
    niit_thresh      = float(tax_cfg.get("NIIT_THRESH", 250_000.0))
    raw_policy       = roth_policy.get("raw", {}) or {}

    # Resolve target bracket ceiling
    # "fill the bracket" = fill up to the ceiling of the CURRENT bracket
    # Alternatively: policy can specify an explicit max rate to not cross
    max_rate_str = str(raw_policy.get("keepit_below_max_marginal_fed_rate", "fill the bracket")).strip().lower()

    conv_cur_paths = np.zeros(paths, dtype=float)

    # Tax bracket ceilings are in BASE-YEAR nominal $ (static from tax table).
    # ordinary_income_cur_paths is in CURRENT $ (deflated by cumulative inflation).
    # We must compare them in the SAME currency — convert income to nominal first,
    # compute headroom in nominal, then convert conversion amount back to current.
    #
    # BRACKET CREEP PREVENTION: Without adjustment, inflation grows inc_nom each year
    # (inc_nom = inc_cur × deflator_y) while bracket ceilings stay fixed. This causes
    # income to cross bracket boundaries over time purely due to inflation — not real
    # income growth — producing erratic headroom (e.g. W2 spills into 24% bracket,
    # giving MORE headroom than the no-income base case).
    #
    # Fix: also scale bracket ceilings and the NIIT threshold by deflator_y, so that
    # the real bracket structure is consistent across all simulation years. Income and
    # ceilings inflate together → headroom is purely a function of real income, not
    # of how far along in the simulation we are.
    deflator_y = max(deflator_y, 1e-12)

    # Pre-scale: inflate bracket ceilings and NIIT threshold to year-y nominal $.
    # IMPORTANT: preserve None for the top bracket (up_to=null in JSON).
    # Previously `b.get("up_to") or 1e12` converted null → 1e12, then × deflator_y
    # produced a ~$1.38T ceiling that bypassed _find_current_bracket_ceiling's
    # top-bracket fallback, causing runaway conversions equal to the full TRAD
    # balance in years when ordinary income (e.g. RMDs) exceeded all real brackets.
    scaled_brackets = [
        {**b, "up_to": (float(b["up_to"]) * deflator_y if b.get("up_to") is not None else None)}
        for b in fed_ord_brackets
    ]
    niit_thresh_scaled = niit_thresh * deflator_y

    for p in range(paths):
        inc_cur = float(ordinary_income_cur_paths[p])
        trad_nom = float(trad_total_paths[p])

        if trad_nom <= 1e-12:
            continue

        # Convert current income → nominal for bracket comparison
        inc_nom = inc_cur * deflator_y

        # Determine target bracket ceiling (scaled nominal $)
        if max_rate_str == "fill the bracket":
            target_ceiling_nom = _find_current_bracket_ceiling(inc_nom, scaled_brackets)
        else:
            try:
                rate_val = float(max_rate_str.replace("%", "")) / (
                    100.0 if "%" in max_rate_str else 1.0
                )
            except ValueError:
                rate_val = None
            if rate_val is not None:
                target_ceiling_nom = _find_rate_bracket_ceiling(rate_val, scaled_brackets)
            else:
                target_ceiling_nom = _find_current_bracket_ceiling(inc_nom, scaled_brackets)

        # Headroom in nominal $
        headroom_nom = max(0.0, target_ceiling_nom - inc_nom)

        # NIIT guard: use inflation-scaled threshold so the guard is consistent
        # across simulation years (same real income level triggers it each year).
        if avoid_niit and inc_nom < niit_thresh_scaled:
            niit_headroom_nom = max(0.0, niit_thresh_scaled - inc_nom)
            headroom_nom = min(headroom_nom, niit_headroom_nom)

        # Cap at available TRAD balance (nominal $)
        conv_nom = min(headroom_nom, trad_nom)

        # Return in current $ for consistency with caller
        conv_cur_paths[p] = max(0.0, conv_nom / deflator_y)

    return conv_cur_paths


def _find_current_bracket_ceiling(income: float, brackets: List[Dict[str, Any]]) -> float:
    """Find the ceiling of the bracket that income currently sits in."""
    sorted_br = sorted(
        [b for b in (brackets or []) if b.get("up_to") is not None],
        key=lambda b: float(b["up_to"])
    )
    for b in sorted_br:
        ceiling = float(b["up_to"])
        if income < ceiling:
            return ceiling
    # Already in top bracket — cap at income + $500k
    return income + 500_000.0


def _find_rate_bracket_ceiling(rate: float, brackets: List[Dict[str, Any]]) -> float:
    """Find the ceiling (up_to) of the bracket with the given rate."""
    for b in (brackets or []):
        if abs(float(b.get("rate", 0.0)) - rate) < 1e-6:
            up_to = b.get("up_to")
            if up_to is not None:
                return float(up_to)
    # Top bracket has no ceiling — return large cap
    return 999_999_999.0


def compute_conversion_tax_paths(
    conv_nom_paths: np.ndarray,              # (paths,) conversion in NOMINAL $
    ordinary_income_cur_paths: np.ndarray,   # (paths,) income in current $ (unused — ytd used)
    tax_cfg: Dict[str, Any],
    ytd_income_nom_paths: np.ndarray,        # (paths,) prior income in nominal $
) -> np.ndarray:
    """
    Compute the marginal federal + state tax cost of converting conv_nom_paths.

    Both conv_nom_paths and ytd_income_nom_paths must be in NOMINAL (base-year) $
    to match the bracket table ceilings correctly.

    Returns
    -------
    tax_cost_nom_paths : (paths,) total tax owed on the conversion, in NOMINAL $
    """
    from engines import calc_progressive_tax

    fed_ord_br   = tax_cfg.get("FED_ORD",   [])
    state_ord_br = tax_cfg.get("STATE_ORD", [])
    state_type   = str(tax_cfg.get("STATE_TYPE", "none"))

    paths = conv_nom_paths.shape[0]
    tax_cost = np.zeros(paths, dtype=float)

    for p in range(paths):
        conv_nom = float(conv_nom_paths[p])
        if conv_nom <= 1e-12:
            continue
        ytd_nom = float(ytd_income_nom_paths[p])
        # Federal marginal tax on nominal conversion amount
        fed   = calc_progressive_tax(conv_nom, ytd_nom, fed_ord_br)
        # State marginal tax
        state = calc_progressive_tax(conv_nom, ytd_nom, state_ord_br) if state_type != "none" else 0.0
        tax_cost[p] = fed + state

    return tax_cost  # nominal $


def apply_simple_conversions(
    trad_ira_balances_nom: Dict[str, np.ndarray],
    roth_ira_balances_nom: Dict[str, np.ndarray],
    conversion_per_year_nom: float,
    window_start_y: int,
    window_end_y: int,
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], np.ndarray]:
    """
    Simple conversion policy for testing:
    - For each year y in [window_start_y, window_end_y), convert up to
      `conversion_per_year_nom` nominal from TRAD IRAs to ROTH IRAs,
      pro-rata across TRAD accounts based on balances at that year.

    Inputs:
        trad_ira_balances_nom: {acct_name -> (paths x YEARS)} nominal TRAD balances
        roth_ira_balances_nom: {acct_name -> (paths x YEARS)} nominal ROTH balances
        conversion_per_year_nom: target total conversion per year (nominal USD)
        window_start_y: first year index (0-based) to convert
        window_end_y:   one past last year index (0-based) to convert

    Returns:
        updated_trad_balances_nom: {acct_name -> (paths x YEARS)} with conversions subtracted
        updated_roth_balances_nom: {acct_name -> (paths x YEARS)} with conversions added
        conversion_nom_paths:      (paths x YEARS) total converted amount per path/year
    """
    if not trad_ira_balances_nom or not roth_ira_balances_nom:
        # Nothing to convert
        paths = 0
    else:
        paths = next(iter(trad_ira_balances_nom.values())).shape[0]

    # Copy balances so we don't mutate inputs
    updated_trad = {
        acct: np.array(bal, dtype=float)
        for acct, bal in trad_ira_balances_nom.items()
    }
    updated_roth = {
        acct: np.array(bal, dtype=float)
        for acct, bal in roth_ira_balances_nom.items()
    }

    conversion_nom_paths = np.zeros((paths, YEARS), dtype=float)

    trad_accts = list(trad_ira_balances_nom.keys())
    roth_accts = list(roth_ira_balances_nom.keys())
    if not trad_accts or not roth_accts or paths == 0:
        return updated_trad, updated_roth, conversion_nom_paths

    # Precompute growth multipliers from original inputs (same cascade logic as
    # apply_bracket_fill_conversions — see _calc_growth_factors docstring).
    trad_gf = _calc_growth_factors(trad_ira_balances_nom, paths)
    roth_gf = _calc_growth_factors(roth_ira_balances_nom, paths)

    # For each year in the window, convert up to conversion_per_year_nom pro-rata
    for y in range(window_start_y, min(window_end_y, YEARS)):
        # Compute total trad balance across all TRAD accounts and paths for this year
        total_trad_y = np.zeros(paths, dtype=float)
        for acct in trad_accts:
            bal_y = np.where(
                np.isfinite(updated_trad[acct][:, y]),
                updated_trad[acct][:, y],
                0.0,
            )
            total_trad_y += bal_y

        # If no TRAD balances, skip this year
        if not np.any(total_trad_y > 1e-12):
            continue

        # We target a fixed conversion_per_year_nom per path (lab simplification)
        target_conv_per_path = float(conversion_per_year_nom)
        # But cannot convert more than total trad balance
        max_conv_per_path = total_trad_y
        conv_per_path = np.minimum(target_conv_per_path, max_conv_per_path)

        # Record total conversion for this year
        conversion_nom_paths[:, y] = conv_per_path

        # Snapshot balances before this year's conversion (for cascade delta)
        trad_y_before = {a: updated_trad[a][:, y].copy() for a in trad_accts}
        roth_y_before = {a: updated_roth[a][:, y].copy() for a in roth_accts}

        # Distribute conversion pro-rata across trad accounts
        for acct in trad_accts:
            bal_y = np.where(
                np.isfinite(updated_trad[acct][:, y]),
                updated_trad[acct][:, y],
                0.0,
            )
            share = np.where(total_trad_y > 1e-12, bal_y / total_trad_y, 0.0)
            acct_conv = conv_per_path * share
            updated_trad[acct][:, y] = bal_y - acct_conv

        # Add converted amounts to ROTH accounts (uniformly for now)
        # You could also spread these pro-rata by existing Roth balances.
        n_roth = len(roth_accts)
        if n_roth > 0:
            conv_per_roth = conv_per_path / float(n_roth)
            for acct in roth_accts:
                bal_y = np.where(
                    np.isfinite(updated_roth[acct][:, y]),
                    updated_roth[acct][:, y],
                    0.0,
                )
                updated_roth[acct][:, y] = bal_y + conv_per_roth

        # ── Cascade deltas forward (Phase 2) ────────────────────────────────
        for acct in trad_accts:
            delta = updated_trad[acct][:, y] - trad_y_before[acct]
            if not np.any(np.abs(delta) > 1e-12):
                continue
            running = delta.copy()
            for yy in range(y + 1, YEARS):
                running = running * trad_gf[acct][:, yy]
                updated_trad[acct][:, yy] = np.maximum(
                    updated_trad[acct][:, yy] + running, 0.0
                )
        for acct in roth_accts:
            delta = updated_roth[acct][:, y] - roth_y_before[acct]
            if not np.any(np.abs(delta) > 1e-12):
                continue
            running = delta.copy()
            for yy in range(y + 1, YEARS):
                running = running * roth_gf[acct][:, yy]
                updated_roth[acct][:, yy] += running
        # ─────────────────────────────────────────────────────────────────────

    return updated_trad, updated_roth, conversion_nom_paths



def _calc_growth_factors(
    balances: Dict[str, np.ndarray],
    paths: int,
    years: int = YEARS,
) -> Dict[str, np.ndarray]:
    """
    Compute year-over-year growth multipliers from a pre-computed balance matrix.

    g[acct][:, y] = bal[:, y] / bal[:, y-1]   for y >= 1
    g[acct][:, 0] = 1.0                         (no prior year)

    These multipliers capture the Monte Carlo asset returns embedded in
    simulate_balances output.  They are balance-independent (same path, same
    return) so we can apply them to conversion deltas to cascade effects forward
    without re-running the full simulation.

    Parameters
    ----------
    balances : {acct: (paths x years)} — raw simulate_balances output (unmodified)
    paths    : number of simulation paths
    years    : simulation horizon (default YEARS=30)

    Returns
    -------
    gf : {acct: (paths x years)} growth multipliers
    """
    gf: Dict[str, np.ndarray] = {}
    for a, bal in balances.items():
        g = np.ones((paths, years), dtype=float)
        for y in range(1, years):
            prev = bal[:, y - 1]
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(
                    np.abs(prev) > 1e-12,
                    bal[:, y] / np.maximum(np.abs(prev), 1e-12),
                    1.0,
                )
            g[:, y] = ratio
        gf[a] = g
    return gf


def apply_bracket_fill_conversions(
    trad_ira_balances_nom: Dict[str, np.ndarray],
    roth_ira_balances_nom: Dict[str, np.ndarray],
    brokerage_balances_nom: Dict[str, np.ndarray],
    ordinary_income_cur_paths: np.ndarray,    # (paths, YEARS) — mutated in place
    ytd_income_nom_paths: np.ndarray,         # (paths, YEARS)
    tax_cfg: Dict[str, Any],
    roth_policy: Dict[str, Any],
    deflator: np.ndarray,                     # (YEARS,) cumulative inflation
    window_start_y: int,
    window_end_y: int,
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """
    Bracket-fill Roth conversion with tax payment from brokerage.

    For each year in the conversion window, per path:
      1. Compute bracket-fill conversion amount (current $)
      2. Convert that amount from TRAD → ROTH (nominal)
      3. Add conversion to ordinary_income_cur_paths (taxed at marginal rate)
      4. Compute tax cost of conversion
      5. Debit tax cost from brokerage account (tax_payment_source)

    Parameters
    ----------
    trad_ira_balances_nom    : {acct: (paths x YEARS)} — modified in place copy
    roth_ira_balances_nom    : {acct: (paths x YEARS)} — modified in place copy
    brokerage_balances_nom   : {acct: (paths x YEARS)} — modified in place copy
    ordinary_income_cur_paths: (paths x YEARS) — conversion added here
    ytd_income_nom_paths     : (paths x YEARS) — used for bracket positioning
    tax_cfg                  : tax configuration
    roth_policy              : from parse_roth_conversion_policy()
    deflator                 : (YEARS,) cumulative inflation deflator
    window_start_y           : first year (0-based) to convert
    window_end_y             : one past last year (0-based) to convert

    Returns
    -------
    updated_trad       : {acct: (paths x YEARS)}
    updated_roth       : {acct: (paths x YEARS)}
    updated_brokerage  : {acct: (paths x YEARS)}
    conversion_nom_paths : (paths x YEARS) total converted per path/year (nominal $)
    tax_cost_cur_paths   : (paths x YEARS) tax paid from brokerage (current $)
    conv_out_per_trad  : {acct: (paths x YEARS)} nominal $ debited from each TRAD account
    conv_in_per_roth   : {acct: (paths x YEARS)} nominal $ credited to each ROTH account
    conv_tax_per_brok  : {acct: (paths x YEARS)} nominal $ tax debited from each brokerage account
    """
    paths = next(iter(trad_ira_balances_nom.values())).shape[0]

    updated_trad = {a: np.array(b, dtype=float) for a, b in trad_ira_balances_nom.items()}
    updated_roth = {a: np.array(b, dtype=float) for a, b in roth_ira_balances_nom.items()}
    updated_brok = {a: np.array(b, dtype=float) for a, b in brokerage_balances_nom.items()}

    trad_accts = list(trad_ira_balances_nom.keys())
    roth_accts = list(roth_ira_balances_nom.keys())
    brok_accts = list(brokerage_balances_nom.keys())

    # Tax payment source: first brokerage account by default
    tax_source_acct = roth_policy.get("tax_payment_source", "BROKERAGE")
    paying_acct = _find_paying_account(tax_source_acct, brok_accts)

    conversion_nom_paths = np.zeros((paths, YEARS), dtype=float)
    tax_cost_cur_paths   = np.zeros((paths, YEARS), dtype=float)

    # Per-account conversion flow tracking (nominal $, mean emitted in STEP 6)
    conv_out_per_trad: Dict[str, np.ndarray] = {
        a: np.zeros((paths, YEARS), dtype=float) for a in trad_accts
    }
    conv_in_per_roth: Dict[str, np.ndarray] = {
        a: np.zeros((paths, YEARS), dtype=float) for a in roth_accts
    }
    conv_tax_per_brok: Dict[str, np.ndarray] = {
        a: np.zeros((paths, YEARS), dtype=float) for a in brok_accts
    }

    # ── Phase 2: cascade growth factors ──────────────────────────────────────
    # Precompute year-to-year return multipliers from the raw simulate_balances
    # output (the ORIGINAL inputs — before any modifications).  These are the
    # Monte Carlo asset returns; they are independent of balance level so we
    # can apply them to conversion deltas to cascade effects into future years.
    trad_gf = _calc_growth_factors(trad_ira_balances_nom, paths)
    roth_gf = _calc_growth_factors(roth_ira_balances_nom, paths)
    brok_gf = _calc_growth_factors(brokerage_balances_nom, paths)
    # ─────────────────────────────────────────────────────────────────────────

    for y in range(window_start_y, min(window_end_y, YEARS)):
        deflator_y = float(deflator[y]) if y < len(deflator) else 1.0

        # Total TRAD balance this year (nominal)
        trad_total = np.zeros(paths, dtype=float)
        for acct in trad_accts:
            trad_total += np.where(
                np.isfinite(updated_trad[acct][:, y]),
                updated_trad[acct][:, y], 0.0
            )

        if not np.any(trad_total > 1e-12):
            continue

        # Bracket-fill conversion amount (current $)
        conv_cur = compute_bracket_fill_conversion_paths(
            ordinary_income_cur_paths=ordinary_income_cur_paths[:, y],
            deflator_y=deflator_y,
            tax_cfg=tax_cfg,
            roth_policy=roth_policy,
            trad_total_paths=trad_total,
            paths=paths,
        )

        # Convert current $ → nominal for balance adjustments
        conv_nom = conv_cur * deflator_y

        # Cap at available TRAD balance (nominal)
        conv_nom = np.minimum(conv_nom, trad_total)
        conv_cur = conv_nom / max(deflator_y, 1e-12)

        if not np.any(conv_nom > 1e-12):
            continue

        # Record conversion
        conversion_nom_paths[:, y] = conv_nom

        # Add conversion to ordinary income (already in current $)
        ordinary_income_cur_paths[:, y] += conv_cur

        # Compute tax cost (returns nominal $)
        # ytd_income_nom_paths must be in nominal $ — it already is
        # conv_nom is in nominal $ — matches bracket table
        tax_cost_nom = compute_conversion_tax_paths(
            conv_nom_paths=conv_nom,
            ordinary_income_cur_paths=ordinary_income_cur_paths[:, y],
            tax_cfg=tax_cfg,
            ytd_income_nom_paths=ytd_income_nom_paths[:, y],
        )
        # Store tax cost in current $ for UI reporting
        tax_cost_cur_paths[:, y] = tax_cost_nom / max(deflator_y, 1e-12)

        # ── Snapshot year-y balances BEFORE this year's conversion ──────────
        # Used below to compute the incremental delta to cascade forward.
        trad_y_before = {a: updated_trad[a][:, y].copy() for a in trad_accts}
        roth_y_before = {a: updated_roth[a][:, y].copy() for a in roth_accts}
        brok_y_before = (
            updated_brok[paying_acct][:, y].copy()
            if (paying_acct and paying_acct in updated_brok)
            else None
        )
        # ─────────────────────────────────────────────────────────────────────

        # Debit TRAD pro-rata
        for acct in trad_accts:
            bal = np.where(np.isfinite(updated_trad[acct][:, y]),
                           updated_trad[acct][:, y], 0.0)
            share = np.where(trad_total > 1e-12, bal / trad_total, 0.0)
            acct_debit = conv_nom * share
            conv_out_per_trad[acct][:, y] = acct_debit          # track nominal debit
            updated_trad[acct][:, y] = np.maximum(bal - acct_debit, 0.0)

        # Credit ROTH pro-rata (by existing Roth balance weight, or equally)
        roth_total = np.zeros(paths, dtype=float)
        for acct in roth_accts:
            roth_total += np.where(np.isfinite(updated_roth[acct][:, y]),
                                   updated_roth[acct][:, y], 0.0)
        for acct in roth_accts:
            bal = np.where(np.isfinite(updated_roth[acct][:, y]),
                           updated_roth[acct][:, y], 0.0)
            share = np.where(roth_total > 1e-12, bal / roth_total,
                             1.0 / max(len(roth_accts), 1))
            acct_credit = conv_nom * share
            conv_in_per_roth[acct][:, y] = acct_credit          # track nominal credit
            updated_roth[acct][:, y] = bal + acct_credit

        # Debit tax from brokerage (already nominal $)
        if paying_acct and paying_acct in updated_brok:
            bal = np.where(np.isfinite(updated_brok[paying_acct][:, y]),
                           updated_brok[paying_acct][:, y], 0.0)
            conv_tax_per_brok[paying_acct][:, y] = tax_cost_nom  # track nominal tax
            updated_brok[paying_acct][:, y] = np.maximum(bal - tax_cost_nom, 0.0)
            logger.debug(
                "[roth] y=%d paths_converting=%d mean_conv_nom=$%.0f "
                "mean_tax_nom=$%.0f paying_acct=%s",
                y + 1, int(np.sum(conv_nom > 1e-12)),
                float(conv_nom[conv_nom > 1e-12].mean()) if np.any(conv_nom > 1e-12) else 0.0,
                float(tax_cost_nom[tax_cost_nom > 1e-12].mean()) if np.any(tax_cost_nom > 1e-12) else 0.0,
                paying_acct,
            )
        elif paying_acct:
            logger.warning("[roth] tax_payment_source '%s' not found in brokerage accounts %s",
                           paying_acct, brok_accts)

        # ── Phase 2: cascade year-y deltas forward into years y+1 … YEARS-1 ─
        #
        # For each account, delta = (balance after conversion) - (balance before).
        # That delta earns the same market returns as the rest of the balance, so
        # we propagate it forward using the precomputed growth multipliers.
        #
        # Successive conversion years each produce their own incremental delta;
        # they superimpose correctly because the balance at year y+1 already
        # includes the cascade from year y (updated_trad[a][:, y+1] was mutated
        # in-place), so each year's bracket-fill computation sees the right
        # post-conversion balance.

        # Cascade TRAD debit (delta is negative — balance decreased)
        for acct in trad_accts:
            delta = updated_trad[acct][:, y] - trad_y_before[acct]
            if not np.any(np.abs(delta) > 1e-12):
                continue
            running = delta.copy()
            for yy in range(y + 1, YEARS):
                running = running * trad_gf[acct][:, yy]
                updated_trad[acct][:, yy] = np.maximum(
                    updated_trad[acct][:, yy] + running, 0.0
                )

        # Cascade ROTH credit (delta is positive — balance increased)
        for acct in roth_accts:
            delta = updated_roth[acct][:, y] - roth_y_before[acct]
            if not np.any(np.abs(delta) > 1e-12):
                continue
            running = delta.copy()
            for yy in range(y + 1, YEARS):
                running = running * roth_gf[acct][:, yy]
                updated_roth[acct][:, yy] += running

        # Cascade brokerage tax debit (delta is negative — tax paid)
        if paying_acct and paying_acct in updated_brok and brok_y_before is not None:
            delta = updated_brok[paying_acct][:, y] - brok_y_before
            if np.any(np.abs(delta) > 1e-12):
                running = delta.copy()
                for yy in range(y + 1, YEARS):
                    running = running * brok_gf[paying_acct][:, yy]
                    updated_brok[paying_acct][:, yy] = np.maximum(
                        updated_brok[paying_acct][:, yy] + running, 0.0
                    )
        # ─────────────────────────────────────────────────────────────────────

    return updated_trad, updated_roth, updated_brok, conversion_nom_paths, tax_cost_cur_paths, \
           conv_out_per_trad, conv_in_per_roth, conv_tax_per_brok


def _find_paying_account(tax_source: str, brok_accts: List[str]) -> Optional[str]:
    """
    Find the brokerage account to debit for conversion taxes.
    Matches by name prefix or returns first brokerage account.
    """
    src = str(tax_source).upper()
    for acct in brok_accts:
        if src in acct.upper() or acct.upper() in src:
            return acct
    return brok_accts[0] if brok_accts else None
