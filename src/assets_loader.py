# filename: assets_loader.py
"""
Load per-asset model parameters and correlations for Monte Carlo.
Schema supports base parameters and optional overrides.

Expected JSON (assets.json):
{
  "assets": {
    "SPY": {
      "class": "US_STOCKS",
      "mu_annual": 0.065,
      "sigma_annual": 0.16,
      "expense_ratio": 0.0009,
      "tracking_error": 0.01,
      "dist": { "yield_annual": 0.018, "qualified_ratio": 0.90 }
    },
    ...
  },
  "correlations": {
    "assets_order": ["SPY", "VGT", "VXUS", "TLT", "GLD"],
    "matrix": [[1,0.8,...], ...]
  },
  "overrides": [
    { "where": { "assets": ["VGT"] }, "set": { "mu_annual": 0.080, "sigma_annual": 0.24 } }
  ]
}
"""

import json
import os
from typing import Any, Dict, List, Optional
import numpy as np

CANONICAL_CLASSES = (
    "US_STOCKS", "INTL_STOCKS", "LONG_TREAS", "INT_TREAS", "TIPS", "GOLD", "COMMOD", "OTHER"
)

def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _safe_num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _apply_overrides(base_assets: Dict[str, Dict[str, Any]], overrides: List[Dict[str, Any]], profile_tag: Optional[str]) -> Dict[str, Dict[str, Any]]:
    out = {k: dict(v) for k, v in base_assets.items()}
    for ov in overrides or []:
        where = ov.get("where", {}) or {}
        setv = ov.get("set", {}) or {}
        wh_assets = where.get("assets")
        wh_profile = where.get("profile")
        if isinstance(wh_profile, str) and profile_tag and wh_profile != profile_tag:
            continue
        targets = list(out.keys()) if not isinstance(wh_assets, list) else [a for a in wh_assets if a in out]
        for a in targets:
            dst = out[a]
            for k, v in setv.items():
                if k in ("mu_annual", "sigma_annual", "expense_ratio", "tracking_error"):
                    dst[k] = _safe_num(v, dst.get(k, 0.0))
                elif k.startswith("dist."):
                    _, subk = k.split(".", 1)
                    dist = dst.get("dist", {}) or {}
                    dist[subk] = _safe_num(v, dist.get(subk, 0.0))
                    dst["dist"] = dist
                elif k == "class":
                    if str(v) in CANONICAL_CLASSES:
                        dst["class"] = str(v)
                elif k in ("global_scale_mu", "global_scale_sigma"):
                    if k == "global_scale_mu":
                        dst["mu_annual"] = _safe_num(dst.get("mu_annual", 0.0), 0.0) * _safe_num(v, 1.0)
                    else:
                        dst["sigma_annual"] = _safe_num(dst.get("sigma_annual", 0.0), 0.0) * _safe_num(v, 1.0)
    return out

def _validate_spd(corr: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    B = (corr + corr.T) / 2.0
    w, V = np.linalg.eigh(B)
    w_clamped = np.maximum(w, eps)
    B_spd = V @ np.diag(w_clamped) @ V.T
    d = np.sqrt(np.diag(B_spd))
    D_inv = np.diag(1.0 / np.maximum(d, 1e-12))
    C = D_inv @ B_spd @ D_inv
    return C

def load_assets_model(path: Optional[str], profile_tag: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns:
      {
        "assets": { ticker: {class, mu_annual, sigma_annual, expense_ratio, tracking_error, dist{yield_annual,qualified_ratio}} },
        "order": [tickers],
        "corr": np.ndarray (KxK, SPD, diag=1.0)
      }
    If path is None or missing, returns empty model.
    """
    if not path or not os.path.isfile(path):
        return {"assets": {}, "order": [], "corr": np.zeros((0, 0), dtype=float)}
    data = _load_json(path)
    assets = data.get("assets", {}) or {}
    overrides = data.get("overrides", []) or []
    corr_blk = data.get("correlations", {}) or {}
    order = corr_blk.get("assets_order", list(assets.keys()))
    M = corr_blk.get("matrix")
    if isinstance(M, list) and len(M) == len(order):
        corr = np.array(M, dtype=float)
    else:
        corr = np.eye(len(order), dtype=float)

    base = {}
    for t, cfg in assets.items():
        cls = str(cfg.get("class", "OTHER"))
        base[t] = {
            "class": cls if cls in CANONICAL_CLASSES else "OTHER",
            "mu_annual": _safe_num(cfg.get("mu_annual", 0.0), 0.0),
            "sigma_annual": _safe_num(cfg.get("sigma_annual", 0.0), 0.0),
            "expense_ratio": _safe_num(cfg.get("expense_ratio", 0.0), 0.0),
            "tracking_error": _safe_num(cfg.get("tracking_error", 0.0), 0.0),
            "dist": {
                "yield_annual": _safe_num((cfg.get("dist", {}) or {}).get("yield_annual", 0.0), 0.0),
                "qualified_ratio": _safe_num((cfg.get("dist", {}) or {}).get("qualified_ratio", 0.0), 0.0),
            }
        }
    model_assets = _apply_overrides(base, overrides, profile_tag)

    order2 = [t for t in order if t in model_assets] or list(model_assets.keys())
    if not order2:
        return {"assets": {}, "order": [], "corr": np.zeros((0, 0), dtype=float)}
    idx_map = {t: i for i, t in enumerate(order)}
    if corr.shape[0] == len(order):
        sel = [idx_map[t] for t in order2]
        corr2 = corr[np.ix_(sel, sel)]
    else:
        corr2 = np.eye(len(order2), dtype=float)
    corr2 = _validate_spd(corr2)

    return {"assets": model_assets, "order": order2, "corr": corr2}

# --- End of file ---

