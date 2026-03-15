# filename: income_core.py


import logging

logger = logging.getLogger(__name__)
from typing import Dict, Tuple
import numpy as np


# Default horizon; callers always pass years explicitly. Do not use in new code.
YEARS = 30


def build_income_streams(
    income_cfg: Dict[str, any],
    years: int = YEARS,
) -> Tuple[
    np.ndarray,  # w2_cur
    np.ndarray,  # rental_cur
    np.ndarray,  # interest_cur
    np.ndarray,  # ordinary_other_cur
    np.ndarray,  # qual_div_cur
    np.ndarray,  # cap_gains_cur
]:
    """
    Build per-year income streams in CURRENT USD from income_cfg, matching
    how the legacy simulator uses income.json.

    income_cfg keys (as in profiles/default/income.json):
      - "w2"
      - "rental"
      - "interest"
      - "ordinary_other"
      - "qualified_div"
      - "cap_gains"

    Each can be a scalar, a short list, or a full YEAR-length list.
    This helper returns 6 numpy arrays of length `years`, with:
      - scalars broadcast,
      - shorter lists extended with their last value,
      - longer lists truncated.

    This mirrors _to_year_vector(...) in spirit, but is explicit for income.
    """

    def _to_year_vec(key: str) -> np.ndarray:
        arr = np.asarray(income_cfg.get(key, 0.0), dtype=float).reshape(-1)
        if arr.size == 0:
            return np.zeros(years, dtype=float)
        if arr.size == 1:
            return np.full(years, float(arr[0]), dtype=float)
        if arr.size < years:
            out = np.empty(years, dtype=float)
            out[: arr.size] = arr
            out[arr.size :] = arr[-1]
            return out
        if arr.size > years:
            return arr[:years]
        return arr

    w2_cur = _to_year_vec("w2")
    rental_cur = _to_year_vec("rental")
    interest_cur = _to_year_vec("interest")
    ordinary_other_cur = _to_year_vec("ordinary_other")
    qual_div_cur = _to_year_vec("qualified_div")
    cap_gains_cur = _to_year_vec("cap_gains")

    return (
        w2_cur,
        rental_cur,
        interest_cur,
        ordinary_other_cur,
        qual_div_cur,
        cap_gains_cur,
    )

