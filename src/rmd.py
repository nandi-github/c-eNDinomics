# filename: rmd.py


import logging

logger = logging.getLogger(__name__)
"""
RMD utilities:
- Load IRS Uniform Lifetime Table (or other tables) from JSON.
- Provide a uniform_factor(age, table) lookup.
- Fallback to a built-in minimal Uniform Lifetime table if no file is supplied.

Expected JSON schema (example):
{
  "uniform_lifetime": {
    "factors": [
      { "age": 73, "factor": 26.5 },
      { "age": 74, "factor": 25.5 },
      ...
      { "age": 115, "factor": 1.9 }
    ]
  }
}

Notes:
- For single life or joint life tables, you may extend this file with additional loaders
  and choose the appropriate table based on person configuration.
- Factors should be positive; the RMD amount = prior_year_balance / factor.
"""

from typing import Dict, Any
import json
import os

# Minimal built-in Uniform Lifetime table (partial; extend as needed)
# Values below reflect the IRS Uniform Lifetime Table (effective 2023) rough reference.
# You can replace with your exact official factors by loading from JSON.
_BUILTIN_UNIFORM_FACTORS = {
    73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0, 79: 21.1,
    80: 20.3, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0, 86: 15.2,
    87: 14.4, 88: 13.7, 89: 12.9, 90: 12.2, 91: 11.5, 92: 10.8, 93: 10.1,
    94: 9.5,  95: 8.9,  96: 8.4,  97: 7.8,  98: 7.3,  99: 6.8,  100: 6.4,
    101: 6.0, 102: 5.6, 103: 5.2, 104: 4.9, 105: 4.6, 106: 4.3, 107: 4.1,
    108: 3.8, 109: 3.6, 110: 3.4, 111: 3.1, 112: 2.9, 113: 2.7, 114: 2.5,
    115: 2.3
}


def load_rmd_table(path: str) -> Dict[str, Any]:
    """
    Load an RMD table JSON file.

    Returns a dict with:
      { "uniform_lifetime": { "factors": [ { "age": int, "factor": float }, ... ] } }

    If the file is missing or invalid, returns a dict using the built-in Uniform table.
    """
    if not path or not os.path.isfile(path):
        return _default_uniform_table()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _default_uniform_table()

    # Support two JSON schemas:
    #
    #   Schema A — legacy list under uniform_lifetime.factors:
    #     {"uniform_lifetime": {"factors": [{"age": 73, "factor": 26.5}, ...]}}
    #
    #   Schema B — flat dict at top level (profile rmd.json):
    #     {"table_name": "...", "factors": {"73": 26.5, "74": 25.5, ...}}
    #
    # Schema B is tried first; Schema A is the fallback.

    out_map = {}

    # --- Schema B: flat dict {"factors": {"73": 26.5, ...}} ---
    top_factors = data.get("factors")
    if isinstance(top_factors, dict) and top_factors:
        for age_str, factor_val in top_factors.items():
            try:
                age = int(str(age_str).rstrip("+"))  # handle "120+" keys
                factor = float(factor_val)
            except Exception:
                continue
            if age > 0 and factor > 0.0:
                out_map[age] = factor

    # --- Schema A: nested list under uniform_lifetime.factors ---
    if not out_map:
        ul = (data.get("uniform_lifetime", {}) or {})
        factors = ul.get("factors")
        if isinstance(factors, list) and len(factors) > 0:
            for row in factors:
                try:
                    age = int(row.get("age"))
                    factor = float(row.get("factor"))
                except Exception:
                    continue
                if age > 0 and factor > 0.0:
                    out_map[age] = factor

    if not out_map:
        return _default_uniform_table()

    return { "uniform_lifetime": { "map": out_map } }


def _default_uniform_table() -> Dict[str, Any]:
    """
    Build a default table dict from built-in uniform factors.
    """
    return { "uniform_lifetime": { "map": dict(_BUILTIN_UNIFORM_FACTORS) } }


def uniform_factor(age: int, table: Dict[str, Any]) -> float:
    """
    Lookup the Uniform Lifetime factor for a given age.
    - If exact age not found, will attempt nearest lower age.
    - Returns 0.0 if no suitable factor is available.

    RMD amount = prior_year_balance / factor
    """
    if age <= 0:
        return 0.0

    ul = (table.get("uniform_lifetime", {}) or {})
    fmap = ul.get("map", {})

    if not isinstance(fmap, dict) or not fmap:
        return 0.0

    # Exact match first
    if age in fmap:
        return float(fmap[age])

    # Find nearest lower age (graceful fallback)
    lower_ages = [a for a in fmap.keys() if isinstance(a, int) and a <= age]
    if not lower_ages:
        return 0.0
    nearest = max(lower_ages)
    return float(fmap.get(nearest, 0.0))

# --- End of file ---

