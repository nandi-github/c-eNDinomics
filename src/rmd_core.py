# filename: rmd_core.py

import logging
from typing import Dict, Optional, Tuple
import numpy as np

from rmd import load_rmd_table, uniform_factor

logger = logging.getLogger(__name__)

YEARS = 30


def rmd_start_age(birth_year: Optional[int]) -> float:
    """
    Return the RMD start age based on owner birth year, per SECURE / SECURE 2.0.

    IRS rules (as of 2026):
      Born <= 1950   -> 70.5  (pre-SECURE legacy)
      Born 1951-1959 -> 73    (SECURE Act 2019)
      Born >= 1960   -> 75    (SECURE 2.0 Act 2022)

    birth_year is used only to determine this bracket — it is independent of
    current_age, which sets the simulation starting point.

    If birth_year is unknown (None or 0), conservatively defaults to 73.
    """
    if birth_year is None or birth_year <= 0:
        return 73.0
    if birth_year <= 1950:
        return 70.5
    if birth_year <= 1959:
        return 73.0
    return 75.0


def build_rmd_factors(
    rmd_table_path: str,
    owner_current_age: float,
    years: int = YEARS,
    owner_birth_year: Optional[int] = None,
) -> np.ndarray:
    """
    Build per-year RMD distribution factors for the simulation horizon.

    owner_current_age  : simulation starting age (year 1 = this age)
    owner_birth_year   : used only to determine RMD start age via SECURE 2.0 rules
                         (independent of current_age — intentional misalignment is allowed)

    Returns a length-`years` float array:
      factor[y] == 0.0  -> no RMD required that simulation year
      factor[y]  > 0.0  -> RMD = prior_year_balance / factor[y]
    """
    rmd_table = load_rmd_table(rmd_table_path)
    factors = np.zeros(years, dtype=float)

    start_age = rmd_start_age(owner_birth_year)

    for y in range(years):
        owner_age_y = owner_current_age + y
        if int(owner_age_y) < int(start_age):  # 70.5 rule: int(70.5)=70, fires at age 70
            factors[y] = 0.0
            continue
        try:
            f = float(uniform_factor(int(owner_age_y), rmd_table))
        except Exception:
            f = 0.0
        factors[y] = f if np.isfinite(f) and f > 0.0 else 0.0

    logger.debug(
        "[RMD] current_age=%s  birth_year=%s  -> start_age=%s",
        owner_current_age, owner_birth_year, start_age,
    )
    logger.debug(
        "[RMD] first 10 (sim_year, age, factor): %s",
        [(y + 1, int(owner_current_age + y), factors[y]) for y in range(min(10, years))],
    )

    return factors


def compute_rmd_schedule_nominal(
    trad_ira_balances_nom: Dict[str, np.ndarray],
    rmd_factors: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """
    Given nominal TRAD IRA balances per account (paths x YEARS) and per-year
    RMD factors, compute nominal RMD amounts:

        RMD[y] = balance[y] / factor[y]   (where factor[y] > 0)

    Returns:
        total_rmd_nom_paths : (paths x YEARS) total RMD across all TRAD accounts
        rmd_nom_per_acct    : {acct_name -> (paths x YEARS)} per-account breakdown
    """
    if not trad_ira_balances_nom:
        paths = 0
    else:
        paths = next(iter(trad_ira_balances_nom.values())).shape[0]

    _n = len(rmd_factors)  # use actual sim length, not module constant
    total_rmd_nom_paths = np.zeros((paths, _n), dtype=float)
    rmd_nom_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, _n), dtype=float)
        for acct in trad_ira_balances_nom.keys()
    }

    for y in range(_n):
        f = rmd_factors[y]
        if f <= 0.0:
            continue  # no RMD required this year
        for acct, bal in trad_ira_balances_nom.items():
            bal_y = np.where(np.isfinite(bal[:, y]), bal[:, y], 0.0)
            rmd_y = bal_y / f
            rmd_nom_per_acct[acct][:, y] = rmd_y
            total_rmd_nom_paths[:, y] += rmd_y

    return total_rmd_nom_paths, rmd_nom_per_acct
