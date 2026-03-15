# filename: cli.py
# --- Begin of file ---

import argparse
import os
import sys
import json
import numpy as np
from typing import Any, Dict, Optional

from loaders import (
    load_tax_unified,
    load_sched,
    load_inflation_yearly,
    load_shocks,
    load_allocation_yearly_accounts,
    validate_alloc_accounts,
    load_person,
    load_income,
    load_economic_policy,
)
# simulator.py is obsolete — all runs route through run_accounts_new
from simulator_new import run_accounts_new
from income_core import build_income_streams
from snapshot import save_raw_snapshot_accounts
from reporting import report_and_plot_accounts

YEARS = 30


def _read_json(path: Optional[str]) -> Dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser("eNDinomics CLI")

    # Profile convenience (resolve all paths under profiles/<n>/)
    ap.add_argument("--profile", help="Profile name under ./profiles to resolve JSON paths")

    # Explicit paths (optional if --profile is used)
    ap.add_argument("--tax",          help="Path to taxes_states_mfj_single.json")
    ap.add_argument("--state",        help="State name (e.g., California)")
    ap.add_argument("--filing",       help="Filing status (MFJ | Single | HeadOfHousehold)")
    ap.add_argument("--withdraw",     help="Path to withdrawal_schedule.json")
    ap.add_argument("--inflation",    help="Path to inflation_yearly.json")
    ap.add_argument("--shocks",       help="Path to shocks_yearly.json")
    ap.add_argument("--alloc-yearly", help="Path to allocation_yearly.json")
    ap.add_argument("--person",       help="Path to person.json")
    ap.add_argument("--income",       help="Path to income.json")
    ap.add_argument("--economic",     help="Path to economic.json")
    ap.add_argument("--assets",       help="Optional path to assets.json")

    # Runtime options
    ap.add_argument("--paths",           type=int, default=500,     help="Simulation paths")
    ap.add_argument("--steps-per-year",  type=int, dest="spy", default=2, help="Steps per year")
    ap.add_argument("--dollars",         choices=["current", "future"], default="current")
    ap.add_argument("--base-year",       type=int, default=2026,    help="Base year metadata")
    ap.add_argument("--shocks-mode",     choices=["augment", "override"], help="Override shocks JSON mode")

    # UI-like flags
    ap.add_argument("--ignore-withdrawals",  action="store_true")
    ap.add_argument("--ignore-rmds",         action="store_true")
    ap.add_argument("--ignore-conversions",  action="store_true")

    # Rebalancing controls
    ap.add_argument("--rebalance-threshold",                 type=float, default=0.10)
    ap.add_argument("--rebalance-brokerage-enabled",         action="store_true")
    ap.add_argument("--rebalance-brokerage-capgain-limit-k", type=float, default=0.0)

    # Output directory
    ap.add_argument("--out", help="Output directory for reports/run_YYYYMMDD_HHMMSS")

    args = ap.parse_args()

    # RMD table is global (IRS law) — always read from config/, never per-profile
    _cli_root = os.path.abspath(os.path.dirname(__file__))
    rmd_path = os.path.join(_cli_root, "config", "rmd.json")

    # Resolve all paths via profile if provided
    if args.profile:
        base = os.path.abspath(os.path.join(os.getcwd(), "profiles", args.profile))

        def P(name: str) -> str:
            return os.path.join(base, name)

        args.tax          = args.tax          or P("taxes_states_mfj_single.json")
        args.withdraw     = args.withdraw     or P("withdrawal_schedule.json")
        args.inflation    = args.inflation    or P("inflation_yearly.json")
        args.shocks       = args.shocks       or P("shocks_yearly.json")
        args.alloc_yearly = args.alloc_yearly or P("allocation_yearly.json")
        args.person       = args.person       or P("person.json")
        args.income       = args.income       or P("income.json")
        args.economic     = args.economic     or P("economic.json")
        if not args.out:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            args.out = os.path.join(base, "reports", f"run_{ts}")

    # Validate required inputs
    missing = []
    for k, v in [
        ("--tax",        args.tax),
        ("--state",      args.state),
        ("--filing",     args.filing),
        ("--withdraw",   args.withdraw),
        ("--inflation",  args.inflation),
        ("--shocks",     args.shocks),
        ("--alloc-yearly", args.alloc_yearly),
        ("--person",     args.person),
        ("--income",     args.income),
        ("--economic",   args.economic),
        ("--out",        args.out),
    ]:
        if not v:
            missing.append(k)
    if missing:
        print(f"error: missing required arguments: {' '.join(missing)}", file=sys.stderr)
        return 2

    # Prepare output directory
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    # Shocks override (mirror api.py behavior)
    shocks_path = args.shocks
    if args.shocks_mode in ("augment", "override"):
        base_shocks = _read_json(shocks_path) or {"mode": "augment", "events": []}
        base_shocks["mode"] = args.shocks_mode
        shocks_path = os.path.join(out_dir, "shocks_override.json")
        with open(shocks_path, "w", encoding="utf-8") as f:
            json.dump(base_shocks, f, indent=2)

    # Withdrawals override if ignoring
    withdraw_path = args.withdraw
    if args.ignore_withdrawals:
        base_w = _read_json(withdraw_path) or {"floor_k": 0, "schedule": []}
        base_w["schedule"] = []
        withdraw_path = os.path.join(out_dir, "withdraw_override.json")
        with open(withdraw_path, "w", encoding="utf-8") as f:
            json.dump(base_w, f, indent=2)

    # Economic override marker if ignoring RMDs or conversions
    economic_path = args.economic
    if args.ignore_rmds or args.ignore_conversions:
        base_e = _read_json(economic_path) or {"defaults": {}, "overrides": []}
        economic_path = os.path.join(out_dir, "economic_override.json")
        with open(economic_path, "w", encoding="utf-8") as f:
            json.dump(base_e, f, indent=2)

    # Load configs
    tax_cfg     = load_tax_unified(args.tax, state=args.state, filing=args.filing)
    sched_arr, sched_base = load_sched(withdraw_path)
    infl_yearly = load_inflation_yearly(args.inflation, years_count=YEARS)

    shocks_events, shocks_mode_file, _ = (
        load_shocks(shocks_path) if shocks_path and os.path.isfile(shocks_path)
        else ([], "augment", [])
    )
    shocks_mode = args.shocks_mode if args.shocks_mode else shocks_mode_file

    alloc_accounts = load_allocation_yearly_accounts(args.alloc_yearly)
    try:
        validate_alloc_accounts(alloc_accounts)
    except Exception as e:
        print(f"error: allocation validation failed: {e}", file=sys.stderr)
        return 2

    person_cfg  = load_person(args.person)
    income_cfg  = load_income(args.income)
    econ_policy = load_economic_policy(economic_path)

    # Build income path arrays
    (w2_cur, rental_cur, interest_cur, ordinary_other_cur,
     qual_div_cur, cap_gains_cur) = build_income_streams(income_cfg, years=YEARS)

    paths = int(args.paths)
    ordinary_income_cur_paths = np.zeros((paths, YEARS), dtype=float)
    qual_div_cur_paths        = np.zeros((paths, YEARS), dtype=float)
    cap_gains_cur_paths       = np.zeros((paths, YEARS), dtype=float)
    ytd_income_nom_paths      = np.zeros((paths, YEARS), dtype=float)

    for y in range(YEARS):
        ordinary_income_cur_paths[:, y] = (
            w2_cur[y] + rental_cur[y] + interest_cur[y] + ordinary_other_cur[y]
        )
        qual_div_cur_paths[:, y]  = qual_div_cur[y]
        cap_gains_cur_paths[:, y] = cap_gains_cur[y]

    # Withdrawal schedule flags
    apply_withdrawals  = not args.ignore_withdrawals
    sched_for_run      = sched_arr   if apply_withdrawals else None
    sched_base_for_run = sched_base  if apply_withdrawals else None

    # Build per-year age-gated withdrawal sequence from economic policy
    acct_names    = list(alloc_accounts.get("per_year_portfolios", {}).keys())
    starting_age  = int(person_cfg.get("current_age", 70)) if person_cfg else 70
    tira_age_gate = float(econ_policy.get("tira_age_gate", 59.5))
    order_good    = econ_policy.get("order_good_market", [])

    def _is_brok(n): u = n.upper(); return "BROKERAGE" in u or "TAXABLE" in u
    def _is_trad(n): u = n.upper(); return ("TRAD" in u or "TRADITIONAL" in u) and "ROTH" not in u
    def _is_roth(n): return "ROTH" in n.upper()

    def _expand(tmpl, accts, allow_trad, allow_roth):
        seen, result = set(), []
        for token in tmpl:
            t = token.upper()
            if "BROKERAGE" in t or "TAXABLE" in t:
                for a in accts:
                    if _is_brok(a) and a not in seen:
                        result.append(a); seen.add(a)
            elif "TRAD" in t and allow_trad:
                for a in accts:
                    if _is_trad(a) and a not in seen:
                        result.append(a); seen.add(a)
            elif "ROTH" in t and allow_roth:
                for a in accts:
                    if _is_roth(a) and a not in seen:
                        result.append(a); seen.add(a)
        return result if result else [a for a in accts if _is_brok(a)]

    withdraw_sequence = [
        _expand(order_good, acct_names,
                (starting_age + y) >= tira_age_gate,
                (starting_age + y) >= tira_age_gate)
        for y in range(YEARS)
    ]

    # Execute simulation
    res = run_accounts_new(
        paths=paths,
        spy=int(args.spy),
        infl_yearly=infl_yearly,
        alloc_accounts=alloc_accounts,
        assets_path=args.assets,
        sched=sched_for_run,
        sched_base=sched_base_for_run,
        apply_withdrawals=apply_withdrawals,
        withdraw_sequence=withdraw_sequence,
        tax_cfg=tax_cfg,
        ordinary_income_cur_paths=ordinary_income_cur_paths,
        qual_div_cur_paths=qual_div_cur_paths,
        cap_gains_cur_paths=cap_gains_cur_paths,
        ytd_income_nom_paths=ytd_income_nom_paths,
        person_cfg=person_cfg,
        rmd_table_path=rmd_path,
        conversion_per_year_nom=None,
        rmds_enabled=not args.ignore_rmds,
        conversions_enabled=not args.ignore_conversions,
        shocks_events=shocks_events,
        shocks_mode=str(shocks_mode or "augment"),
        econ_policy=econ_policy,
        rebalancing_enabled=True,
    )

    # Canonical paths and run_info for snapshot
    input_paths = {
        "tax":      args.tax,
        "withdraw": withdraw_path,
        "inflation": args.inflation,
        "shocks":   shocks_path,
        "alloc":    args.alloc_yearly,
        "person":   args.person,
        "income":   args.income,
        "economic": economic_path,
        "rmd":      rmd_path,
        "assets":   args.assets or "",
    }

    run_info = {
        "paths":          int(args.paths),
        "steps_per_year": int(args.spy),
        "dollars":        str(args.dollars or "current"),
        "base_year":      int(args.base_year),
        "state":          args.state,
        "filing":         args.filing,
        "shocks_mode":    str(shocks_mode or "augment"),
        "flags": {
            "ignore_withdrawals": bool(args.ignore_withdrawals),
            "ignore_rmds":        bool(args.ignore_rmds),
            "ignore_conversions": bool(args.ignore_conversions),
        },
    }

    save_raw_snapshot_accounts(
        out_dir=out_dir,
        res=res,
        run_info=run_info,
        input_paths=input_paths,
        tax_cfg=tax_cfg,
        person_cfg=person_cfg,
        infl_yearly=infl_yearly,
        shocks_events=shocks_events,
        shocks_mode=str(shocks_mode or "augment"),
    )

    try:
        report_and_plot_accounts(
            res=res,
            args=type("Args", (), {
                "paths":                             args.paths,
                "spy":                               args.spy,
                "dollars":                           args.dollars,
                "base_year":                         args.base_year,
                "rebalance_threshold":               args.rebalance_threshold,
                "rebalance_brokerage_enabled":       args.rebalance_brokerage_enabled,
                "rebalance_brokerage_capgain_limit_k": args.rebalance_brokerage_capgain_limit_k,
            })(),
            out_dir=out_dir,
            alloc_accounts=alloc_accounts,
            tax_cfg=tax_cfg,
            person_cfg=person_cfg,
        )
    except Exception as e:
        print(f"[cli] reporting error (non-fatal): {e}", file=sys.stderr)

    print(f"[cli] run complete → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# --- End of file ---
