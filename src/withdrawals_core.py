# filename: withdrawals_core.py


import logging

logger = logging.getLogger(__name__)
from typing import Dict, List, Tuple
import numpy as np


def apply_withdrawals_nominal_per_account(
    acct_eoy_nom: Dict[str, np.ndarray],
    y: int,
    amount_nom_paths: np.ndarray,
    sequence: List[str],
) -> Tuple[
    np.ndarray,                # realized_total
    np.ndarray,                # shortfall_total
    Dict[str, np.ndarray],     # realized_per_acct
    Dict[str, np.ndarray],     # shortfall_per_acct
    Dict[str, np.ndarray],     # sold_per_acct
]:
    """
    Core withdrawal logic, identical to the legacy helper:
    pull amount_nom_paths from acct_eoy_nom in the given sequence,
    track realized withdrawals, shortfall, and sold amounts per account.
    """
    paths = next(iter(acct_eoy_nom.values())).shape[0]
    remaining = np.where(np.isfinite(amount_nom_paths), amount_nom_paths, 0.0).copy()

    realized_total = np.zeros(paths, dtype=float)
    realized_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros(paths, dtype=float) for acct in acct_eoy_nom.keys()
    }
    shortfall_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros(paths, dtype=float) for acct in acct_eoy_nom.keys()
    }
    sold_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros(paths, dtype=float) for acct in acct_eoy_nom.keys()
    }

    for acct in sequence:
        if acct not in acct_eoy_nom:
            continue
        bal = np.where(
            np.isfinite(acct_eoy_nom[acct][:, y]),
            acct_eoy_nom[acct][:, y],
            0.0,
        )
        take = np.minimum(bal, remaining)
        # Balance deduction is handled by the caller via sold_per_acct.
        # Do NOT mutate acct_eoy_nom here — the caller owns the array lifecycle.
        realized_per_acct[acct] += take
        sold_per_acct[acct] += take
        realized_total += take
        remaining -= take
        if np.all(remaining <= 1e-12):
            break

    shortfall_total = np.maximum(remaining, 0.0)
    return (
        realized_total,
        shortfall_total,
        realized_per_acct,
        shortfall_per_acct,
        sold_per_acct,
    )

