# filename: rmd_core.py

from typing import Dict, Tuple
import numpy as np

from rmd import load_rmd_table, uniform_factor

YEARS = 30


def build_rmd_factors(
    rmd_table_path: str,
    owner_current_age: float,
    years: int = YEARS,
) -> np.ndarray:
    rmd_table = load_rmd_table(rmd_table_path)
    factors = np.zeros(years, dtype=float)




    for y in range(years):
        owner_age_y = owner_current_age + y
        try:
            f = float(uniform_factor(int(owner_age_y), rmd_table))
        except Exception:
            f = 0.0

        factors[y] = f if np.isfinite(f) and f > 0.0 else 0.0

    # DEBUG: inspect mapping from year index to age and factor
    print(
        "[DEBUG RMD core] owner_current_age:", owner_current_age,
        "years:", years
    )
    print(
        "[DEBUG RMD core] first 10 ages & factors:",
        [(int(owner_current_age + y), factors[y]) for y in range(min(10, years))]
    )

    return factors


def compute_rmd_schedule_nominal(
    trad_ira_balances_nom: Dict[str, np.ndarray],
    rmd_factors: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """
    Given nominal TRAD IRA balances per account, per year (paths x YEARS), and
    per-year RMD factors, compute the nominal RMD amounts:

        RMD = balance / factor   (where factor > 0)

    Inputs:
        trad_ira_balances_nom: {acct_name -> (paths x YEARS)}
        rmd_factors: length-YEARS array from build_rmd_factors()

    Returns:
        total_rmd_nom_paths: (paths x YEARS) total RMD per path/year
        rmd_nom_per_acct:    {acct_name -> (paths x YEARS)} per-account RMD
    """
    if not trad_ira_balances_nom:
        paths = 0
    else:
        paths = next(iter(trad_ira_balances_nom.values())).shape[0]

    total_rmd_nom_paths = np.zeros((paths, YEARS), dtype=float)
    rmd_nom_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, YEARS), dtype=float)
        for acct in trad_ira_balances_nom.keys()
    }

    for y in range(YEARS):
        f = rmd_factors[y]
        if f <= 0.0:
            continue  # no RMD for this year/age
        for acct, bal in trad_ira_balances_nom.items():
            bal_y = np.where(np.isfinite(bal[:, y]), bal[:, y], 0.0)
            rmd_y = bal_y / f
            rmd_nom_per_acct[acct][:, y] = rmd_y
            total_rmd_nom_paths[:, y] += rmd_y

    return total_rmd_nom_paths, rmd_nom_per_acct

