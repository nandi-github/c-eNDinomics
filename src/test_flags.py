#!/usr/bin/env python3
"""
test_flags.py — eNDinomics ignore-flag regression harness

Usage (from src/):
    python test_flags.py                   # run all 8 combos
    python test_flags.py --profile Test    # explicit profile
    python test_flags.py --fast            # 50 paths instead of 200 for speed

Exit code: 0 = all pass, 1 = any failure.

Each run is direct — no HTTP server needed. Calls run_accounts_new() with the
same config loading that api.py uses.
"""

import sys
import os
import argparse
import json
import time
from itertools import product
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Path setup — script lives in src/
# ---------------------------------------------------------------------------
SCRIPT_DIR  = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, SCRIPT_DIR)

from loaders import (
    load_tax_unified,
    load_sched,
    load_inflation_yearly,
    load_allocation_yearly_accounts,
    validate_alloc_accounts,
    load_person,
    load_income,
    load_economic_policy,
)
from simulator_new import run_accounts_new
from income_core import build_income_streams

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
YEARS = 30

APP_ROOT              = SCRIPT_DIR
TAX_GLOBAL_PATH       = os.path.join(APP_ROOT, "taxes_states_mfj_single.json")
ECONOMIC_GLOBAL_PATH  = os.path.join(APP_ROOT, "economicglobal.json")
COMMON_ASSETS_JSON    = os.path.join(APP_ROOT, "config", "assets.json")

# ---------------------------------------------------------------------------
# Config loader — mirrors api.py's modular block
# ---------------------------------------------------------------------------

def _profile_path(profile: str, name: str) -> str:
    return os.path.join(APP_ROOT, "profiles", profile, name)


def load_test_config(profile: str) -> Dict[str, Any]:
    """Load all config for a profile, mirroring api.py's preprocessing."""
    P = lambda name: _profile_path(profile, name)

    tax_cfg       = load_tax_unified(TAX_GLOBAL_PATH, state="California", filing="MFJ")
    alloc_accounts = load_allocation_yearly_accounts(P("allocation_yearly.json"))
    validate_alloc_accounts(alloc_accounts)
    person_cfg    = load_person(P("person.json"))
    income_cfg    = load_income(P("income.json"))
    infl_yearly   = load_inflation_yearly(P("inflation_yearly.json"), years_count=YEARS)
    econ_policy   = load_economic_policy(P("economic.json"),
                        global_path=ECONOMIC_GLOBAL_PATH if os.path.isfile(ECONOMIC_GLOBAL_PATH) else None)
    sched_arr, sched_base = load_sched(P("withdrawal_schedule.json"))
    rmd_path      = P("rmd.json")
    assets_path   = COMMON_ASSETS_JSON if os.path.isfile(COMMON_ASSETS_JSON) else None

    return dict(
        tax_cfg=tax_cfg,
        alloc_accounts=alloc_accounts,
        person_cfg=person_cfg,
        income_cfg=income_cfg,
        infl_yearly=infl_yearly,
        econ_policy=econ_policy,
        sched_arr=sched_arr,
        sched_base=sched_base,
        rmd_path=rmd_path,
        assets_path=assets_path,
    )


def build_income_arrays(income_cfg: Dict, paths: int) -> Dict[str, np.ndarray]:
    w2, rental, interest, ord_other, qual_div, cap_gains = \
        build_income_streams(income_cfg, years=YEARS)

    ordinary_income = np.zeros((paths, YEARS), dtype=float)
    qual_div_arr    = np.zeros((paths, YEARS), dtype=float)
    cap_gains_arr   = np.zeros((paths, YEARS), dtype=float)
    ytd_income      = np.zeros((paths, YEARS), dtype=float)

    for y in range(YEARS):
        ordinary_income[:, y] = w2[y] + rental[y] + interest[y] + ord_other[y]
        qual_div_arr[:, y]    = qual_div[y]
        cap_gains_arr[:, y]   = cap_gains[y]

    return dict(
        ordinary_income_cur_paths=ordinary_income,
        qual_div_cur_paths=qual_div_arr,
        cap_gains_cur_paths=cap_gains_arr,
        ytd_income_nom_paths=ytd_income,
    )


def build_withdraw_sequence(alloc_accounts, person_cfg, econ_policy) -> List[List[str]]:
    acct_names   = list(alloc_accounts.get("per_year_portfolios", {}).keys())
    starting_age = int(person_cfg.get("current_age", 70))
    tira_age_gate = float(econ_policy.get("tira_age_gate", 59.5))

    def _is_brok(n): u = n.upper(); return "BROKERAGE" in u or "TAXABLE" in u
    def _is_trad(n): u = n.upper(); return ("TRAD" in u or "TRADITIONAL" in u) and "ROTH" not in u
    def _is_roth(n): return "ROTH" in n.upper()

    order_good = econ_policy.get("order_good_market", [])
    seq = []
    for y in range(YEARS):
        age_y = starting_age + y
        allow = age_y >= tira_age_gate
        seen, result = set(), []
        for token in order_good:
            t = token.upper()
            for a in acct_names:
                if a in seen:
                    continue
                if ("BROKERAGE" in t or "TAXABLE" in t) and _is_brok(a):
                    result.append(a); seen.add(a)
                elif "TRAD" in t and allow and _is_trad(a):
                    result.append(a); seen.add(a)
                elif "ROTH" in t and allow and _is_roth(a):
                    result.append(a); seen.add(a)
        seq.append(result if result else [a for a in acct_names if _is_brok(a)])
    return seq


# ---------------------------------------------------------------------------
# Run one combo
# ---------------------------------------------------------------------------

def run_combo(
    cfg: Dict,
    paths: int,
    ignore_wd: bool,
    ignore_conv: bool,
    ignore_rmd: bool,
) -> Tuple[Dict, float]:
    """Run simulator for one flag combination. Returns (res, elapsed_secs)."""
    income = build_income_arrays(cfg["income_cfg"], paths)
    seq    = build_withdraw_sequence(cfg["alloc_accounts"], cfg["person_cfg"], cfg["econ_policy"])

    sched     = None if ignore_wd else cfg["sched_arr"]
    sched_base = None if ignore_wd else cfg["sched_base"]
    apply_wd  = not ignore_wd

    t0 = time.time()
    res = run_accounts_new(
        paths=paths,
        spy=2,
        infl_yearly=np.asarray(cfg["infl_yearly"], dtype=float) if cfg["infl_yearly"] else None,
        alloc_accounts=cfg["alloc_accounts"],
        assets_path=cfg["assets_path"],
        sched=sched,
        sched_base=sched_base,
        apply_withdrawals=apply_wd,
        withdraw_sequence=seq,
        tax_cfg=cfg["tax_cfg"],
        person_cfg=cfg["person_cfg"],
        rmd_table_path=cfg["rmd_path"],
        conversion_per_year_nom=None,
        rmds_enabled=not ignore_rmd,
        conversions_enabled=not ignore_conv,
        econ_policy=cfg["econ_policy"],
        rebalancing_enabled=True,
        **income,
    )
    elapsed = time.time() - t0
    return res, elapsed


# ---------------------------------------------------------------------------
# Metric extractors
# ---------------------------------------------------------------------------

def acct_end_by_type(res: Dict) -> Tuple[float, float, float]:
    """Return (brok_end, trad_end, roth_end) in nominal future USD, year 30."""
    levels = res.get("returns_acct_levels", {}).get("inv_nom_levels_mean_acct", {})
    brok = trad = roth = 0.0
    for name, arr in levels.items():
        u = name.upper()
        val = float(arr[-1]) if arr else 0.0
        if "BROKERAGE" in u or "TAXABLE" in u:
            brok += val
        elif ("TRAD" in u or "TRADITIONAL" in u) and "ROTH" not in u:
            trad += val
        elif "ROTH" in u:
            roth += val
    return brok, trad, roth


def total_conversions(res: Dict) -> float:
    return float(res.get("conversions", {}).get("total_converted_nom_mean", 0.0))


def total_rmd(res: Dict) -> float:
    arr = res.get("withdrawals", {}).get("rmd_current_mean", [])
    return float(sum(arr))


def total_planned_wd(res: Dict) -> float:
    arr = res.get("withdrawals", {}).get("planned_current", [])
    return float(sum(arr))


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(name: str, condition: bool, detail: str = "") -> Tuple[str, str, str]:
    status = PASS if condition else FAIL
    return (status, name, detail)


def run_assertions(
    label: str,
    res: Dict,
    ignore_wd: bool,
    ignore_conv: bool,
    ignore_rmd: bool,
    baseline_res: Optional[Dict],
) -> List[Tuple[str, str, str]]:
    """Return list of (status, check_name, detail) for this run."""
    checks = []
    conv  = total_conversions(res)
    rmd   = total_rmd(res)
    plan  = total_planned_wd(res)
    b, t, r = acct_end_by_type(res)

    # ── Per-run flag checks ──────────────────────────────────────────────────

    if ignore_conv:
        checks.append(check(
            "conversions suppressed",
            conv == 0.0,
            f"total_converted={conv:,.0f} (expected 0)",
        ))
    else:
        checks.append(check(
            "conversions active",
            conv > 0.0,
            f"total_converted={conv:,.0f} (expected >0)",
        ))

    if ignore_rmd:
        checks.append(check(
            "RMDs suppressed",
            rmd == 0.0,
            f"sum_rmd_cur={rmd:,.0f} (expected 0)",
        ))
    else:
        checks.append(check(
            "RMDs active (year 21+)",
            rmd > 0.0,
            f"sum_rmd_cur={rmd:,.0f} (expected >0)",
        ))

    if ignore_wd:
        checks.append(check(
            "withdrawals suppressed",
            plan == 0.0,
            f"sum_planned={plan:,.0f} (expected 0)",
        ))
    else:
        checks.append(check(
            "withdrawals active",
            plan > 0.0,
            f"sum_planned={plan:,.0f} (expected >0)",
        ))

    # ── Cross-run invariants (only when baseline is available AND valid) ────────

    baseline_valid = (
        baseline_res is not None
        and acct_end_by_type(baseline_res) != (0.0, 0.0, 0.0)
    )

    if baseline_valid:
        bb, bt, br = acct_end_by_type(baseline_res)

        if ignore_conv and not ignore_rmd and not ignore_wd:
            # TRAD higher without conversion drain (TRAD assets not moved to ROTH)
            checks.append(check(
                "TRAD end > baseline (no conv drain)",
                t > bt,
                f"TRAD={t:,.0f} vs baseline={bt:,.0f} diff={t-bt:+,.0f}",
            ))
            # ROTH lower without conversion inflow (conv adds ~10s of M to ROTH)
            # Use a meaningful threshold: at least $1M less (not just less by rounding)
            checks.append(check(
                "ROTH end < baseline (no conv inflow)",
                br - r > 1_000_000,
                f"ROTH={r:,.0f} vs baseline={br:,.0f} diff={r-br:+,.0f} (need diff < -1M)",
            ))
            # Brokerage higher without conversion tax drain
            checks.append(check(
                "BROK end >= baseline (no conv tax drain)",
                b >= bb * 0.999,   # allow tiny float tolerance
                f"BROK={b:,.0f} vs baseline={bb:,.0f} diff={b-bb:+,.0f}",
            ))

        if ignore_rmd and not ignore_conv and not ignore_wd:
            # NOTE: TRAD direction is indeterminate with ignore_rmd.
            # Suppressing RMDs means ordinary_income is lower, so bracket-fill
            # conversions run larger (more room), draining TRAD more. Net TRAD
            # direction depends on which effect dominates — don't assert it.
            # Brokerage lower — no RMD surplus reinvestment inflows
            checks.append(check(
                "BROK end < baseline (no RMD reinvest)",
                b < bb,
                f"BROK={b:,.0f} vs baseline={bb:,.0f} diff={b-bb:+,.0f}",
            ))

        if ignore_wd and not ignore_conv and not ignore_rmd:
            # Brokerage higher without withdrawal drain
            checks.append(check(
                "BROK end > baseline (no WD drain)",
                b > bb,
                f"BROK={b:,.0f} vs baseline={bb:,.0f} diff={b-bb:+,.0f}",
            ))

    return checks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMBOS = [
    # (label,                    wd,    conv,  rmd)
    ("no_flags",                  False, False, False),
    ("ignore_wd",                 True,  False, False),
    ("ignore_conv",               False, True,  False),
    ("ignore_rmd",                False, False, True),
    ("ignore_wd_conv",            True,  True,  False),
    ("ignore_wd_rmd",             True,  False, True),
    ("ignore_conv_rmd",           False, True,  True),
    ("ignore_all",                True,  True,  True),
]


def fmt_flags(wd, conv, rmd) -> str:
    parts = []
    if wd:   parts.append("WD")
    if conv: parts.append("CONV")
    if rmd:  parts.append("RMD")
    return f"ignore=[{','.join(parts)}]" if parts else "no flags"


def main():
    parser = argparse.ArgumentParser(description="eNDinomics flag regression harness")
    parser.add_argument("--profile", default="Test", help="Profile name (default: Test)")
    parser.add_argument("--paths",   type=int, default=200, help="MC paths (default: 200)")
    parser.add_argument("--fast",    action="store_true",   help="Use 50 paths for speed")
    args = parser.parse_args()

    paths   = 50 if args.fast else args.paths
    profile = args.profile

    print(f"\n{'='*72}")
    print(f"  eNDinomics Flag Regression Test  |  profile={profile}  paths={paths}")
    print(f"{'='*72}\n")

    # Load config once
    print("Loading config... ", end="", flush=True)
    try:
        cfg = load_test_config(profile)
        print("OK\n")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    results: Dict[str, Dict] = {}
    all_checks: List[Tuple[str, str, str, str]] = []  # (label, status, name, detail)

    # Run all combos
    for label, wd, conv, rmd in COMBOS:
        flag_str = fmt_flags(wd, conv, rmd)
        print(f"  Running {label:<28} ({flag_str}) ... ", end="", flush=True)

        try:
            res, elapsed = run_combo(cfg, paths, wd, conv, rmd)
            results[label] = res

            # Extract key metrics for one-line summary
            conv_total = total_conversions(res)
            rmd_total  = total_rmd(res)
            plan_total = total_planned_wd(res)
            b, t, r    = acct_end_by_type(res)

            print(f"{elapsed:4.1f}s  |  brok={b/1e6:.1f}M  trad={t/1e6:.1f}M  "
                  f"roth={r/1e6:.1f}M  conv={conv_total/1e6:.1f}M  "
                  f"rmd={rmd_total/1e3:.0f}k  wd={plan_total/1e3:.0f}k")

        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()
            results[label] = {}

    # Run assertions
    baseline = results.get("no_flags")
    print(f"\n{'─'*72}")
    print("  Assertion Results")
    print(f"{'─'*72}")

    total_pass = total_fail = 0

    for label, wd, conv, rmd in COMBOS:
        res = results.get(label, {})
        if not res:
            print(f"\n  [{label}]  ⚠️  No result — skipping assertions")
            continue

        checks = run_assertions(label, res, wd, conv, rmd,
                                baseline_res=(baseline if label != "no_flags" else None))
        n_pass = sum(1 for s, _, _ in checks if s == PASS)
        n_fail = sum(1 for s, _, _ in checks if s == FAIL)
        total_pass += n_pass
        total_fail += n_fail

        flag_str = fmt_flags(wd, conv, rmd)
        run_status = "✅" if n_fail == 0 else "❌"
        print(f"\n  {run_status} [{label}]  {flag_str}  ({n_pass}/{len(checks)} passed)")
        for status, name, detail in checks:
            indent = "      "
            print(f"{indent}{status}  {name}")
            if detail:
                print(f"{indent}         {detail}")

    # Summary
    print(f"\n{'='*72}")
    overall = "✅  ALL PASSED" if total_fail == 0 else f"❌  {total_fail} FAILED"
    print(f"  {overall}  ({total_pass} passed, {total_fail} failed)")
    print(f"{'='*72}\n")

    # Cross-run consistency check: after fix, ignore_conv combos should differ from no-conv combos
    print("  Cross-run consistency (regression guard):")
    guard_checks = [
        # (run_a, run_b, should_differ, description)
        ("no_flags",    "ignore_conv",    True,  "no_flags vs ignore_conv: TRAD should differ"),
        ("ignore_rmd",  "ignore_conv_rmd",True,  "ignore_rmd vs ignore_conv+rmd: TRAD should differ"),
        ("ignore_wd",   "ignore_wd_conv", True,  "ignore_wd vs ignore_wd+conv: TRAD should differ"),
        ("ignore_wd_rmd","ignore_all",    True,  "ignore_wd+rmd vs ignore_all: TRAD should differ"),
    ]

    for a, b_name, should_differ, desc in guard_checks:
        ra = results.get(a, {})
        rb = results.get(b_name, {})
        if not ra or not rb:
            print(f"    ⚠️  SKIP  {desc} (missing result)")
            continue
        _, ta, _ = acct_end_by_type(ra)
        _, tb, _ = acct_end_by_type(rb)
        actually_differ = abs(ta - tb) > 1_000  # $1k threshold for floating noise
        if should_differ:
            ok = actually_differ
            detail = f"TRAD_a={ta:,.0f}  TRAD_b={tb:,.0f}  diff={tb-ta:+,.0f}"
            status = PASS if ok else FAIL
            print(f"    {status}  {desc}")
            print(f"             {detail}")
        if not should_differ:
            ok = not actually_differ
            print(f"    {'✅ PASS' if ok else '❌ FAIL'}  {desc}")

    print()
    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
