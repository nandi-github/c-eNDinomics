# filename: roth_conversion_core.py

from typing import Dict, Any, Tuple
import numpy as np

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

    return updated_trad, updated_roth, conversion_nom_paths

