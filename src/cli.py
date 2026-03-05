# filename: cli.py
# --- Begin of file ---

import argparse
import os
import sys
import json
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
from simulator import run_accounts
from snapshot import save_raw_snapshot_accounts
from reporting import report_and_plot_accounts


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

    # Profile convenience (resolve all paths under profiles/<name>/)
    ap.add_argument("--profile", help="Profile name under ./profiles to resolve JSON paths")

    # Explicit paths (optional if --profile is used)
    ap.add_argument("--tax", help="Path to taxes_states_mfj_single.json")
    ap.add_argument("--state", help="State name (e.g., California)")
    ap.add_argument("--filing", help="Filing status (MFJ | Single | HeadOfHousehold)")
    ap.add_argument("--withdraw", help="Path to withdrawal_schedule.json")
    ap.add_argument("--inflation", help="Path to inflation_yearly.json")
    ap.add_argument("--shocks", help="Path to shocks_yearly.json")
    ap.add_argument("--alloc-yearly", help="Path to allocation_yearly.json")
    ap.add_argument("--person", help="Path to person.json")
    ap.add_argument("--income", help="Path to income.json")
    ap.add_argument("--rmd", help="Path to rmd.json")
    ap.add_argument("--economic", help="Path to economic.json")
    ap.add_argument("--assets", help="Optional path to assets.json")

    # Runtime options
    ap.add_argument("--paths", type=int, default=500, help="Simulation paths")
    ap.add_argument("--steps-per-year", type=int, dest="spy", default=2, help="Steps per year")
    ap.add_argument("--dollars", choices=["current", "future"], default="current", help="Dollar mode")
    ap.add_argument("--base-year", type=int, default=2026, help="Base year metadata")
    ap.add_argument("--shocks-mode", choices=["augment", "override"], help="Override shocks JSON mode")

    # UI-like flags
    ap.add_argument("--ignore-withdrawals", action="store_true", help="Clear the withdrawals schedule")
    ap.add_argument("--ignore-rmds", action="store_true", help="Mark economic override (display-only unless modeled)")
    ap.add_argument("--ignore-conversions", action="store_true", help="Mark economic override (display-only unless modeled)")

    # Rebalancing controls
    ap.add_argument("--rebalance-threshold", type=float, default=0.10, help="Max drift before rebalancing")
    ap.add_argument("--rebalance-brokerage-enabled", action="store_true", help="Enable cap-gain-limited brokerage rebalancing")
    ap.add_argument("--rebalance-brokerage-capgain-limit-k", type=float, default=0.0, help="Brokerage sell cap per year (thousands)")

    # Output directory
    ap.add_argument("--out", help="Output directory for reports/run_YYYYMMDD_HHMMSS")

    args = ap.parse_args()

    # Resolve all paths via profile if provided
    if args.profile:
        base = os.path.abspath(os.path.join(os.getcwd(), "profiles", args.profile))

        def P(name: str) -> str:
            return os.path.join(base, name)

        args.tax = args.tax or P("taxes_states_mfj_single.json")
        args.withdraw = args.withdraw or P("withdrawal_schedule.json")
        args.inflation = args.inflation or P("inflation_yearly.json")
        args.shocks = args.shocks or P("shocks_yearly.json")
        args.alloc_yearly = args.alloc_yearly or P("allocation_yearly.json")
        args.person = args.person or P("person.json")
        args.income = args.income or P("income.json")
        args.rmd = args.rmd or P("rmd.json")
        args.economic = args.economic or P("economic.json")
        if not args.out:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            args.out = os.path.join(base, "reports", f"run_{ts}")

    # Validate required inputs
    missing = []
    for k, v in [
        ("--tax", args.tax), ("--state", args.state), ("--filing", args.filing),
        ("--withdraw", args.withdraw), ("--inflation", args.inflation),
        ("--shocks", args.shocks), ("--alloc-yearly", args.alloc_yearly),
        ("--person", args.person), ("--income", args.income),
        ("--rmd", args.rmd), ("--economic", args.economic),
        ("--out", args.out),
    ]:
        if not v:
            missing.append(k)
    if missing:
        print(f"error: missing required arguments: {' '.join(missing)}", file=sys.stderr)
        return 2

    # Prepare output directory
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    # Shocks override (mirror run-retire behavior)
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
    tax_cfg = load_tax_unified(args.tax, state=args.state, filing=args.filing)
    sched_arr, floor_k = load_sched(withdraw_path)
    infl_yearly = load_inflation_yearly(args.inflation, years_count=30)

    shocks_events, shocks_mode_file, _ = load_shocks(shocks_path) if shocks_path else ([], "augment", [])
    shocks_mode = args.shocks_mode if args.shocks_mode else shocks_mode_file

    # Allocation — loaders expand begin+overrides to per_year_portfolios automatically
    alloc_accounts = load_allocation_yearly_accounts(args.alloc_yearly)

    # Validate allocation
    try:
        validate_alloc_accounts(alloc_accounts)
    except Exception as e:
        print(f"error: allocation validation failed: {e}", file=sys.stderr)
        return 2

    person_cfg = load_person(args.person)
    income_cfg = load_income(args.income)
    econ_policy = load_economic_policy(economic_path)

    # Execute simulation
    res = run_accounts(
        paths=int(args.paths),
        spy=int(args.spy),
        tax_cfg=tax_cfg,
        sched=sched_arr,
        floor_k=float(floor_k),
        shocks_events=shocks_events,
        shocks_mode=str(shocks_mode or "augment"),
        infl_yearly=infl_yearly,
        alloc_accounts=alloc_accounts,
        person_cfg=person_cfg,
        income_cfg=income_cfg,
        dollars=str(args.dollars or "current"),
        rmd_table_path=args.rmd,
        base_year=int(args.base_year),
        rebalance_drift_threshold=float(args.rebalance_threshold),
        rebalance_brokerage_enabled=bool(args.rebalance_brokerage_enabled),
        rebalance_brokerage_capgain_limit_k=float(args.rebalance_brokerage_capgain_limit_k),
        economic_policy=econ_policy,
        assets_path=args.assets,
    )

    # Canonical paths and run_info for snapshot
    input_paths = {
        "tax": args.tax,
        "withdraw": withdraw_path,
        "inflation": args.inflation,
        "shocks": shocks_path,
        "alloc": args.alloc_yearly,
        "person": args.person,
        "income": args.income,
        "economic": economic_path,
        "rmd": args.rmd,
        "assets": args.assets or "",
    }

    run_info = {
        "paths": int(args.paths),
        "steps_per_year": int(args.spy),
        "dollars": str(args.dollars or "current"),
        "base_year": int(args.base_year),
        "state": args.state,
        "filing": args.filing,
        "shocks_mode": str(shocks_mode or "augment"),
        "flags": {
            "ignore_withdrawals": bool(args.ignore_withdrawals),
            "ignore_rmds": bool(args.ignore_rmds),
            "ignore_conversions": bool(args.ignore_conversions),
        },
    }

    # Snapshot using canonical run_info so UI and CLI see the same values
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

    # Reporting
    try:
        report_and_plot_accounts(
            res=res,
            args=args,
            out_dir=out_dir,
            alloc_accounts=alloc_accounts,
            tax_cfg=tax_cfg,
            person_cfg=person_cfg,
            benchmarks_path=os.path.join(os.getcwd(), "benchmarks.json") if os.path.isfile("benchmarks.json") else None,
        )
    except Exception as e:
        print(f"[WARN] Reporting failed: {e}")

    print(f"\nSnapshot written to: {os.path.join(out_dir, 'raw_snapshot_accounts.json')}")
    print(f"Output folder: {out_dir}")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
        sys.exit(rc)
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)

# --- End of file ---

