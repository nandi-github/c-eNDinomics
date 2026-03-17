"""
promote_model.py
=================
Validation gate between candidate model and production assets.json.

Validates:
  - All required tickers present
  - mu/sigma within per-class bounds
  - Correlation matrix is symmetric positive semi-definite
  - No NaN or Inf values
  - Layer 5 holdings present for ETF tickers (warning only)

On success: copies candidate → src/config/assets.json and logs promotion.
On failure: prints failures, exits non-zero. Nothing is written.

Usage:
    python3 src/promote_model.py                        # validate + prompt
    python3 src/promote_model.py --yes                  # validate + promote without prompt
    python3 src/promote_model.py --validate-only        # validate, never promote
    python3 src/promote_model.py --candidate path/to/assets.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import shutil
import sys
from typing import Dict, List, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE          = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT     = os.path.abspath(os.path.join(_HERE, ".."))
_CANDIDATE_IN  = os.path.join(_REPO_ROOT, "asset-model", "candidate", "assets.json")
_PRODUCTION    = os.path.join(_HERE, "config", "assets.json")
_PROMO_LOG     = os.path.join(_REPO_ROOT, "asset-model", "promotion_log.json")

# ---------------------------------------------------------------------------
# Bounds (must match asset_calibration.py)
# ---------------------------------------------------------------------------

MU_BOUNDS: Dict[str, Tuple[float, float]] = {
    "US_STOCKS":   (-0.05, 0.22),
    "INTL_STOCKS": (-0.05, 0.20),
    "LONG_TREAS":  (-0.05, 0.12),
    "INT_TREAS":   (-0.03, 0.10),
    "TIPS":        (-0.03, 0.09),
    "GOLD":        (-0.05, 0.15),
    "COMMOD":      (-0.06, 0.18),
    "REIT":        (-0.04, 0.16),
    "CASH":        (0.00,  0.08),
}

SIGMA_BOUNDS: Dict[str, Tuple[float, float]] = {
    "US_STOCKS":   (0.08, 0.65),   # wide upper bound: individual stocks (NVDA ~0.47) are valid
    "INTL_STOCKS": (0.08, 0.55),
    "LONG_TREAS":  (0.04, 0.25),
    "INT_TREAS":   (0.02, 0.18),
    "TIPS":        (0.02, 0.15),
    "GOLD":        (0.08, 0.40),
    "COMMOD":      (0.10, 0.55),
    "REIT":        (0.08, 0.45),
    "CASH":        (0.00, 0.06),
}

# Tickers that MUST be in the model for it to be promotable
REQUIRED_TICKERS = {
    "VTI", "VXUS", "IEF", "TLT", "SCHP", "GLD", "DBC", "QQQ",
}

# ETF tickers expected to have look-through data (warning, not error)
ETF_TICKERS_EXPECTED_HOLDINGS = {
    "VTI", "VXUS", "QQQ", "IEF", "TLT", "SCHP", "GLD", "DBC",
    "VUG", "VTV", "XLK", "XLF", "XLE", "EEM", "EFA",
}


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

class ValidationFailure:
    def __init__(self, ticker: str, check: str, detail: str, fatal: bool = True):
        self.ticker = ticker
        self.check  = check
        self.detail = detail
        self.fatal  = fatal   # False = warning only

    def __str__(self):
        level = "ERROR" if self.fatal else "WARN"
        return f"[{level}] {self.ticker}: {self.check} — {self.detail}"


def validate(candidate: dict) -> Tuple[List[ValidationFailure], bool]:
    """
    Run all validation checks on the candidate model.
    Returns (failures, is_promotable).
    is_promotable is True if no fatal failures.
    """
    failures: List[ValidationFailure] = []
    assets = candidate.get("assets", {})

    # ── 1. Required tickers ───────────────────────────────────────────────
    present = set(assets.keys())
    for req in REQUIRED_TICKERS:
        if req not in present:
            failures.append(ValidationFailure(
                req, "required_ticker", f"{req} missing from candidate model"
            ))

    # ── 2. Per-ticker mu/sigma bounds ─────────────────────────────────────
    for ticker, cfg in assets.items():
        cls   = cfg.get("class", "US_STOCKS")
        mu    = cfg.get("mu_annual", None)
        sigma = cfg.get("sigma_annual", None)

        if mu is None or sigma is None:
            failures.append(ValidationFailure(
                ticker, "missing_params", "mu_annual or sigma_annual missing"
            ))
            continue

        if not math.isfinite(mu) or not math.isfinite(sigma):
            failures.append(ValidationFailure(
                ticker, "non_finite", f"mu={mu} sigma={sigma}"
            ))
            continue

        mu_lo, mu_hi = MU_BOUNDS.get(cls, (-0.10, 0.30))
        if not (mu_lo <= mu <= mu_hi):
            failures.append(ValidationFailure(
                ticker, "mu_out_of_bounds",
                f"mu={mu:.4f} not in [{mu_lo}, {mu_hi}] for class {cls}"
            ))

        sig_lo, sig_hi = SIGMA_BOUNDS.get(cls, (0.01, 0.60))
        if not (sig_lo <= sigma <= sig_hi):
            failures.append(ValidationFailure(
                ticker, "sigma_out_of_bounds",
                f"sigma={sigma:.4f} not in [{sig_lo}, {sig_hi}] for class {cls}"
            ))

        # Yield sanity
        yield_est = cfg.get("dist", {}).get("yield_annual", 0.0)
        if not (0.0 <= yield_est <= 0.25):
            failures.append(ValidationFailure(
                ticker, "yield_out_of_bounds",
                f"yield={yield_est:.4f} not in [0, 0.25]"
            ))

    # ── 3. Correlation matrix SPD check ───────────────────────────────────
    corr_block = candidate.get("correlations", {})
    matrix     = corr_block.get("matrix", [])
    if matrix:
        try:
            C = np.array(matrix, dtype=float)
            n = C.shape[0]
            # Must be square and symmetric
            if C.shape != (n, n):
                failures.append(ValidationFailure(
                    "correlations", "not_square", f"shape={C.shape}"
                ))
            else:
                sym_err = float(np.max(np.abs(C - C.T)))
                if sym_err > 1e-6:
                    failures.append(ValidationFailure(
                        "correlations", "not_symmetric", f"max_asymmetry={sym_err:.2e}"
                    ))
                # Eigenvalue check: all eigenvalues >= -1e-6 (allow tiny numerical error)
                eigvals = np.linalg.eigvalsh(C)
                min_eig = float(np.min(eigvals))
                if min_eig < -1e-4:
                    failures.append(ValidationFailure(
                        "correlations", "not_psd",
                        f"min_eigenvalue={min_eig:.4f} (matrix not positive semi-definite)"
                    ))
                # Diagonal must be 1.0
                diag_err = float(np.max(np.abs(np.diag(C) - 1.0)))
                if diag_err > 1e-6:
                    failures.append(ValidationFailure(
                        "correlations", "diagonal_not_one", f"max_diag_error={diag_err:.2e}"
                    ))
        except Exception as e:
            failures.append(ValidationFailure(
                "correlations", "matrix_parse_error", str(e)
            ))

    # ── 4. Layer 5 warnings (non-fatal) ──────────────────────────────────
    for ticker in ETF_TICKERS_EXPECTED_HOLDINGS:
        if ticker in assets:
            if not assets[ticker].get("top_holdings"):
                failures.append(ValidationFailure(
                    ticker, "missing_look_through",
                    "top_holdings not populated — run weekly_job.py then re-calibrate",
                    fatal=False,
                ))

    # ── 5. Status must be "candidate" ─────────────────────────────────────
    if candidate.get("status") != "candidate":
        failures.append(ValidationFailure(
            "model", "wrong_status",
            f"status='{candidate.get('status')}' expected 'candidate'"
        ))

    fatal_failures  = [f for f in failures if f.fatal]
    is_promotable   = len(fatal_failures) == 0

    return failures, is_promotable


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------

def promote(candidate: dict, candidate_path: str, production_path: str,
            log_path: str) -> str:
    """
    Promote candidate to production. Returns new model version string.
    Backs up previous production model before overwriting.
    """
    os.makedirs(os.path.dirname(production_path), exist_ok=True)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # Backup current production
    if os.path.isfile(production_path):
        backup_path = production_path + f".bak.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(production_path, backup_path)
        print(f"Backed up production model to: {backup_path}")

    # Mark as production and write
    candidate["status"] = "production"
    candidate["promoted_at"] = datetime.datetime.now().isoformat()
    with open(production_path, "w") as f:
        json.dump(candidate, f, indent=2)

    # Append to promotion log
    log = []
    if os.path.isfile(log_path):
        try:
            with open(log_path) as f:
                log = json.load(f)
        except Exception:
            log = []

    log.append({
        "version":      candidate.get("model_version", "?"),
        "promoted_at":  candidate["promoted_at"],
        "from_candidate": candidate_path,
        "to_production":  production_path,
        "training":     candidate.get("training", {}),
        "n_tickers":    len(candidate.get("assets", {})),
    })
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    return candidate.get("model_version", "?")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Validate and promote candidate asset model to production"
    )
    p.add_argument("--candidate",      default=_CANDIDATE_IN,
                   help="Path to candidate assets.json")
    p.add_argument("--production",     default=_PRODUCTION,
                   help="Production assets.json path to write")
    p.add_argument("--log",            default=_PROMO_LOG,
                   help="Promotion log path")
    p.add_argument("--validate-only",  action="store_true",
                   help="Run validation only, never promote")
    p.add_argument("--yes",            action="store_true",
                   help="Promote without interactive prompt")
    args = p.parse_args()

    # Load candidate
    if not os.path.isfile(args.candidate):
        print(f"ERROR: candidate not found at {args.candidate}")
        print(f"Run: python3 src/asset_calibration.py  first.")
        sys.exit(1)

    with open(args.candidate) as f:
        candidate = json.load(f)

    version    = candidate.get("model_version", "?")
    n_tickers  = len(candidate.get("assets", {}))
    data_through = candidate.get("training", {}).get("data_through", "?")

    print(f"\n{'='*60}")
    print(f"  eNDinomics Model Promotion Gate")
    print(f"  Candidate: v{version}  |  {n_tickers} tickers  |  data through {data_through}")
    print(f"{'='*60}\n")

    # Validate
    failures, is_promotable = validate(candidate)

    errors   = [f for f in failures if f.fatal]
    warnings = [f for f in failures if not f.fatal]

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  {w}")
        print()

    if errors:
        print(f"VALIDATION FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        print()
        print("Fix errors and re-run asset_calibration.py before promoting.")
        sys.exit(1)

    print(f"Validation PASSED — {len(warnings)} warning(s), 0 errors.\n")

    if args.validate_only:
        print("--validate-only: skipping promotion.")
        sys.exit(0)

    # Confirm promotion
    if not args.yes:
        print(f"Promoting v{version} → {args.production}")
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    # Promote
    new_version = promote(candidate, args.candidate, args.production, args.log)
    print(f"\nPromoted v{new_version} to production: {args.production}")
    print(f"Promotion logged to: {args.log}")
    print(f"\nRestart the API server to pick up the new model.")


if __name__ == "__main__":
    main()
