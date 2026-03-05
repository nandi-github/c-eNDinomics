# filename: engines_assets.py
"""
Asset-level stochastic return engine and shock layering.
- Draw correlated annual log-returns per asset.
- Convert class shock step matrices to yearly log adjustments (sum of ln multipliers).
"""

from typing import Dict, List, Tuple
import numpy as np

def cholesky_from_corr_sigma(corr: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """
    Build covariance from corr and sigma, then return Cholesky factor L (cov = L L^T).
    """
    cov = np.outer(sigma, sigma) * corr
    jitter = 1e-12 * np.eye(cov.shape[0])
    return np.linalg.cholesky(cov + jitter)

def draw_asset_log_returns(paths: int,
                           years: int,
                           asset_order: List[str],
                           assets_cfg: Dict[str, Dict],
                           corr: np.ndarray,
                           seed: int = 42) -> Tuple[np.ndarray, List[str]]:
    """
    Returns:
      R: shape (paths, years, K) → per-asset annual log-return draws (Normal with drift μ and cov).
      order: asset tickers order
    """
    K = len(asset_order)
    if K == 0 or years <= 0 or paths <= 0:
        return np.zeros((paths, years, 0), dtype=float), asset_order
    mu = np.array([assets_cfg[a]["mu_annual"] for a in asset_order], dtype=float)
    sigma = np.array([assets_cfg[a]["sigma_annual"] for a in asset_order], dtype=float)
    L = cholesky_from_corr_sigma(corr, sigma)
    rng = np.random.default_rng(seed)
    R = np.zeros((paths, years, K), dtype=float)
    for y in range(years):
        Z = rng.standard_normal((paths, K))
        R[:, y, :] = Z @ L + mu
    return R, asset_order

def shock_yearly_log_adjustments(shock_mats: Dict[str, np.ndarray], years: int, spy: int, paths: int) -> Dict[str, np.ndarray]:
    """
    Convert per-class per-step multiplicative shock matrices into yearly log adjustments:
      log_adj[paths, years] = sum_{steps in year} ln(step_multiplier)
    """
    out: Dict[str, np.ndarray] = {}
    steps = years * spy
    for cls, mat in (shock_mats or {}).items():
        if mat is None or mat.shape != (paths, steps):
            out[cls] = np.zeros((paths, years), dtype=float)
            continue
        arr = mat.reshape(paths, years, spy)
        year_mult = arr.prod(axis=2)
        out[cls] = np.log(np.maximum(year_mult, 1e-12))
    return out

# --- End of file ---

