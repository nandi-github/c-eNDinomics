# filename: taxes_core.py

from typing import Dict, Tuple
import numpy as np

from engines import (
    compute_dividend_taxes_components,
    compute_gains_taxes_components,
)


def compute_annual_taxes(
    ordinary_income_cur: float,
    qual_div_cur: float,
    cap_gains_cur: float,
    tax_cfg: Dict[str, any],
    ytd_income_nom: float,
) -> Tuple[float, float, float, float]:
    """
    Compute annual taxes in CURRENT USD given:
      - ordinary income (wages, interest, rental, other + RMD + conversions),
      - qualified dividends,
      - capital gains (realized from withdrawals/rebalancing/conversions),
    and a given year-to-date income figure (ytd_income_nom) for bracket calculations.

    Uses the same logic as the legacy simulator, but wrapped in one function.

    Returns:
        taxes_fed_cur:     federal income + CG taxes
        taxes_state_cur:   state income + CG taxes
        taxes_niit_cur:    net investment income tax
        taxes_excise_cur:  state CG excise tax (if configured)
    """

    # Extract needed config from tax_cfg
    fed_ord_br = tax_cfg.get("FED_ORD", [])
    fed_qual_br = tax_cfg.get("FED_QUAL", [])
    state_ord_br = tax_cfg.get("STATE_ORD", [])
    state_type = str(tax_cfg.get("STATE_TYPE", "none"))

    niit_rate = float(tax_cfg.get("NIIT_RATE", 0.0))
    niit_thresh_nom = float(tax_cfg.get("NIIT_THRESH", 0.0))

    excise_cfg = (tax_cfg.get("STATE_CG_EXCISE", {}) or {})
    excise_rate_nom = float(excise_cfg.get("rate", 0.0))

    # --- Dividends: compute fed/state/NIIT on ordinary + qualified dividends ---
    comp_div = compute_dividend_taxes_components(
        ordinary_div_nom=float(ordinary_income_cur),
        qualified_div_nom=float(qual_div_cur),
        fed_ord_brackets=fed_ord_br,
        fed_qual_brackets=fed_qual_br,
        state_type=state_type,
        state_ord_brackets=state_ord_br,
        niit_rate=niit_rate,
        niit_threshold_nom=niit_thresh_nom,
        ytd_income_nom=float(ytd_income_nom),
    )

    # comp_div is a mapping; legacy code picks keys from it
    # From your simulator you can inspect the exact keys; for now we assume:
    taxes_fed_div_cur = float(comp_div.get("fed", 0.0))
    taxes_state_div_cur = float(comp_div.get("state", 0.0))
    taxes_niit_div_cur = float(comp_div.get("niit", 0.0))

    # --- Gains: compute fed/state/NIIT/excise on realized capital gains ---
    comp_gains = compute_gains_taxes_components(
        realized_gains_nom=float(cap_gains_cur),
        fed_qual_brackets=fed_qual_br,
        state_ord_brackets=state_ord_br,
        niit_rate=niit_rate,
        niit_threshold_nom=niit_thresh_nom,
        ytd_income_nom=float(ytd_income_nom),
        excise_rate_nom=excise_rate_nom,
    )

    taxes_fed_gains_cur = float(comp_gains.get("fed_qual", 0.0))
    taxes_state_gains_cur = float(comp_gains.get("state", 0.0))
    taxes_niit_gains_cur = float(comp_gains.get("niit", 0.0))
    taxes_excise_cur = float(comp_gains.get("excise", 0.0))

    taxes_fed_cur = taxes_fed_div_cur + taxes_fed_gains_cur
    taxes_state_cur = taxes_state_div_cur + taxes_state_gains_cur
    taxes_niit_cur = taxes_niit_div_cur + taxes_niit_gains_cur

    return taxes_fed_cur, taxes_state_cur, taxes_niit_cur, taxes_excise_cur



def compute_annual_taxes_paths(
    ordinary_income_cur_paths: np.ndarray,  # shape (paths,)
    qual_div_cur_paths: np.ndarray,         # shape (paths,)
    cap_gains_cur_paths: np.ndarray,        # shape (paths,)
    tax_cfg: Dict[str, any],
    ytd_income_nom_paths: np.ndarray,       # shape (paths,)
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized wrapper around compute_annual_taxes for one year:
    takes per-path arrays of current USD incomes and returns per-path arrays
    of fed, state, NIIT, excise taxes (current USD).
    """
    ordinary_income_cur_paths = np.asarray(ordinary_income_cur_paths, dtype=float)
    qual_div_cur_paths = np.asarray(qual_div_cur_paths, dtype=float)
    cap_gains_cur_paths = np.asarray(cap_gains_cur_paths, dtype=float)
    ytd_income_nom_paths = np.asarray(ytd_income_nom_paths, dtype=float)

    paths = ordinary_income_cur_paths.shape[0]

    taxes_fed_cur_paths = np.zeros(paths, dtype=float)
    taxes_state_cur_paths = np.zeros(paths, dtype=float)
    taxes_niit_cur_paths = np.zeros(paths, dtype=float)
    taxes_excise_cur_paths = np.zeros(paths, dtype=float)

    for p in range(paths):
        taxes_fed_cur_paths[p], taxes_state_cur_paths[p], taxes_niit_cur_paths[p], taxes_excise_cur_paths[p] = compute_annual_taxes(
            ordinary_income_cur=float(ordinary_income_cur_paths[p]),
            qual_div_cur=float(qual_div_cur_paths[p]),
            cap_gains_cur=float(cap_gains_cur_paths[p]),
            tax_cfg=tax_cfg,
            ytd_income_nom=float(ytd_income_nom_paths[p]),
        )

    return taxes_fed_cur_paths, taxes_state_cur_paths, taxes_niit_cur_paths, taxes_excise_cur_paths

