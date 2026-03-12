#!/usr/bin/env python3
"""
fix_all.py — Run from src/ directory.
Fixes:
  1. api.py: restores truncated tail + removes dead simulator import/else block + adds TAX DIAG
  2. test_flags.py: G11 + G13 patches
"""
import sys, re

def strip_nulls(path):
    data = open(path, "rb").read()
    n = data.count(b"\x00")
    if n:
        open(path, "wb").write(data.replace(b"\x00", b""))
        print(f"  [{path}] stripped {n} null bytes")
    return open(path, "r", encoding="utf-8").read()

# ============================================================
# api.py — restore truncated tail
# ============================================================
print("\n=== Fixing api.py ===")
src = strip_nulls("api.py")

# Remove old simulator import if present
if "from simulator import run_accounts\n" in src:
    src = src.replace("from simulator import run_accounts\n", "", 1)
    print("  Removed old simulator import: OK")

# Find truncation point and replace everything from "    if modular_test:" onwards
TRUNC_MARKER = "    if modular_test:\n"
idx = src.find(TRUNC_MARKER)
if idx == -1:
    print("  ERROR: could not find truncation marker '    if modular_test:'")
    sys.exit(1)

# Keep everything before the marker, then append the full correct tail
src = src[:idx]

TAIL = r'''    if modular_test:
        print("[DEBUG api] Using modular run_accounts_new for Test profile")
        rmds_enabled = not ignore_rmds_flag

        income_cfg = load_income(f"profiles/{profile}/income.json")
        (
            w2_cur,
            rental_cur,
            interest_cur,
            ordinary_other_cur,
            qual_div_cur,
            cap_gains_cur,
        ) = build_income_streams(income_cfg, years=YEARS)

        ordinary_income_cur_paths = np.zeros((paths, YEARS), dtype=float)
        qual_div_cur_paths = np.zeros((paths, YEARS), dtype=float)
        cap_gains_cur_paths = np.zeros((paths, YEARS), dtype=float)
        ytd_income_nom_paths = np.zeros((paths, YEARS), dtype=float)

        for y in range(YEARS):
            ordinary_income_cur_paths[:, y] = (
                w2_cur[y] + rental_cur[y] + interest_cur[y] + ordinary_other_cur[y]
            )
            qual_div_cur_paths[:, y] = qual_div_cur[y]
            cap_gains_cur_paths[:, y] = cap_gains_cur[y]

        sched_for_modular = None
        sched_base_for_modular = None
        apply_withdrawals_flag = False

        if modular_core_only_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_core_withdrawals_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True
        elif modular_rmd_only_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_withdrawals_rmd_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True
        elif modular_core_conv_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_withdrawals_conv_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True
        elif modular_rmd_conv_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_withdrawals_rmd_conv_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True

        acct_names    = list(alloc_accounts.get("per_year_portfolios", {}).keys())
        starting_age  = int(person_cfg.get("current_age", 70)) if person_cfg else 70
        tira_age_gate = float(econ_policy.get("tira_age_gate", 59.5))

        conversion_enabled = bool(
            (person_cfg or {}).get("roth_conversion_policy", {}).get("enabled", False)
        )
        order_good = econ_policy.get("order_good_market", [])
        order_bad  = (
            econ_policy.get("order_bad_market_with_conversion", [])
            if conversion_enabled
            else econ_policy.get("order_bad_market", [])
        )

        def _is_brokerage(n): u = n.upper(); return "BROKERAGE" in u or "TAXABLE" in u
        def _is_trad(n):      u = n.upper(); return ("TRAD" in u or "TRADITIONAL" in u) and "ROTH" not in u
        def _is_roth(n):      return "ROTH" in n.upper()

        def _expand(tmpl, accts, allow_trad, allow_roth):
            seen, result = set(), []
            for token in tmpl:
                t = token.upper()
                if "BROKERAGE" in t or "TAXABLE" in t:
                    for a in accts:
                        if _is_brokerage(a) and a not in seen:
                            result.append(a); seen.add(a)
                elif ("TRAD" in t) and allow_trad:
                    for a in accts:
                        if _is_trad(a) and a not in seen:
                            result.append(a); seen.add(a)
                elif "ROTH" in t and allow_roth:
                    for a in accts:
                        if _is_roth(a) and a not in seen:
                            result.append(a); seen.add(a)
            return result if result else [a for a in accts if _is_brokerage(a)]

        seq_good_per_year = []
        seq_bad_per_year  = []
        for y in range(YEARS):
            age_y      = starting_age + y
            allow_trad = age_y >= tira_age_gate
            allow_roth = age_y >= tira_age_gate
            seq_good_per_year.append(_expand(order_good, acct_names, allow_trad, allow_roth))
            seq_bad_per_year.append( _expand(order_bad,  acct_names, allow_trad, allow_roth))

        withdraw_seq_per_year = seq_good_per_year

        res = run_accounts_new(
            paths=paths,
            spy=steps_per_year,
            infl_yearly=infl_yearly,
            alloc_accounts=alloc_accounts,
            assets_path=assets_path,
            sched=sched_for_modular,
            sched_base=sched_base_for_modular,
            apply_withdrawals=apply_withdrawals_flag,
            withdraw_sequence=withdraw_seq_per_year,
            tax_cfg=tax_cfg,
            ordinary_income_cur_paths=ordinary_income_cur_paths,
            qual_div_cur_paths=qual_div_cur_paths,
            cap_gains_cur_paths=cap_gains_cur_paths,
            ytd_income_nom_paths=ytd_income_nom_paths,
            person_cfg=person_cfg,
            rmd_table_path=rmd_path,
            conversion_per_year_nom=None,
            rmds_enabled=rmds_enabled,
            conversions_enabled=not ignore_conversions_flag,
            shocks_events=shocks_events,
            shocks_mode=str(internal_shocks_mode),
            econ_policy=econ_policy,
            rebalancing_enabled=True,
            override_state         = payload.get("state"),
            override_filing_status = payload.get("filing"),
            override_rmd_table     = payload.get("rmd_table"),
        )

    # -- Tax diagnostic (server log -- remove once tax table confirmed working) --
    _wd_d = res.get("withdrawals", {})
    _cx_d = res.get("conversions", {})
    print("[TAX DIAG] taxes_fed yr20-24:",
          [round(v, 0) for v in (_wd_d.get("taxes_fed_current_mean") or [0]*30)[20:25]])
    print("[TAX DIAG] taxes_state yr20-24:",
          [round(v, 0) for v in (_wd_d.get("taxes_state_current_mean") or [0]*30)[20:25]])
    print("[TAX DIAG] conv_tax yr0-4:",
          [round(v, 0) for v in (_cx_d.get("conversion_tax_cur_mean_by_year") or [0]*30)[0:5]])
    print("[TAX DIAG] ord_income yr0 mean:",
          round(float(ordinary_income_cur_paths[:, 0].mean()), 2))
    print("[TAX DIAG] ord_income yr20 mean:",
          round(float(ordinary_income_cur_paths[:, 20].mean()), 2))

    # 8) Canonical input paths and run_info
    input_paths = {
        "tax": tax_path,
        "withdraw": withdraw_path_effective,
        "inflation": infl_path,
        "shocks": shocks_path_effective,
        "alloc": alloc_path,
        "person": person_path,
        "income": income_path,
        "economic": economic_path_effective,
        "rmd": rmd_path,
        "assets": assets_path or "",
    }

    run_info = {
        "paths": int(paths),
        "steps_per_year": int(steps_per_year),
        "dollars": str(dollars or "current"),
        "base_year": int(base_year),
        "state": state,
        "filing": filing,
        "rmd_table": rmd_table,
        "runtime_overrides": _runtime_overrides,
        "shocks_mode": raw_shocks_mode,
        "flags": {
            "ignore_withdrawals": bool(ignore_withdrawals),
            "ignore_rmds": bool(ignore_rmds),
            "ignore_conversions": bool(ignore_conversions),
        },
    }

    # 9) Snapshot + run_meta
    save_raw_snapshot_accounts(
        out_dir=run_dir,
        res=res,
        run_info=run_info,
        input_paths=input_paths,
        tax_cfg=tax_cfg,
        person_cfg=person_cfg,
        infl_yearly=infl_yearly,
        shocks_events=shocks_events,
        shocks_mode=str(shocks_mode or "augment"),
    )
    _write_run_meta(run_dir=run_dir, profile=profile, run_id=run_id, run_info=run_info)

    # 10) Reporting artifacts (PNGs/CSVs)
    try:
        report_and_plot_accounts(
            res=res,
            args=type(
                "Args",
                (),
                {
                    "paths": paths,
                    "spy": steps_per_year,
                    "dollars": dollars,
                    "base_year": base_year,
                    "rebalance_threshold": rebalance_threshold,
                    "rebalance_brokerage_enabled": rebalance_brokerage_enabled,
                    "rebalance_brokerage_capgain_limit_k": rebalance_brokerage_capgain_limit_k,
                },
            )(),
            out_dir=run_dir,
            alloc_accounts=alloc_accounts,
            tax_cfg=tax_cfg,
            person_cfg=person_cfg,
            benchmarks_path=BENCHMARKS_GLOBAL_PATH
            if os.path.isfile(BENCHMARKS_GLOBAL_PATH)
            else None,
        )
    except Exception:
        pass

    # 11) Compute ending balances per account for UI
    accounts_levels = res.get("returns_acct_levels", {}) or {}
    inv_nom_levels_mean_acct = accounts_levels.get("inv_nom_levels_mean_acct", {}) or {}
    inv_real_levels_mean_acct = accounts_levels.get("inv_real_levels_mean_acct", {}) or {}

    try:
        ending_balances = compute_account_ending_balances(
            inv_nom_levels_mean_acct=inv_nom_levels_mean_acct,
            inv_real_levels_mean_acct=inv_real_levels_mean_acct,
        )
    except Exception:
        ending_balances = []

    return {
        "ok": True,
        "profile": profile,
        "run": run_id,
        "ending_balances": ending_balances,
    }

# --- End of file ---
'''

src = src + TAIL
open("api.py", "w", encoding="utf-8").write(src)
lines = src.count("\n")
print(f"  api.py restored: {lines} lines")
print(f"  'return ok' present: {'return {' + chr(10) in src or 'return {\"ok\"' in src}")

# Quick verify
import subprocess
r = subprocess.run(["python3", "-m", "py_compile", "api.py"], capture_output=True)
if r.returncode == 0:
    print("  Syntax check: OK")
else:
    print("  Syntax check: FAILED:", r.stderr.decode())
    sys.exit(1)

# ============================================================
# test_flags.py — G11 + G13 patches
# ============================================================
print("\n=== Fixing test_flags.py ===")
src_tf = strip_nulls("test_flags.py")

# G11
OLD_G11 = (
    "    # TRAD IRA draws are ordinary income \u2192 taxes_fed is non-zero even without income.json income\n"
    "    checks.append(chk(\"Ordinary fed taxes > 0 in conversion window (TRAD draws are taxable)\",\n"
    "                       float(fed_yr.sum()) > 0,\n"
    "                       f\"fed_sum={float(fed_yr.sum()):,.0f} (expected >0 \u2014 TRAD draws are ordinary income)\"))"
)
NEW_G11 = (
    "    # Base profile: bracket-fill converts ~$23,850/yr. Fed std deduction (MFJ) = $31,500\n"
    "    # so fed taxable income = $0 for base profile -- this is CORRECT.\n"
    "    # Verify wiring via res_inc ($60k rental puts income above std deduction).\n"
    "    fed_yr_inc = np.array(_wd_taxes_fed(res_inc)[:20], dtype=float)\n"
    "    checks.append(chk(\"Ordinary fed taxes > 0 with $60k rental income (income > std deduction)\",\n"
    "                       float(fed_yr_inc.sum()) > 0,\n"
    "                       f\"fed_sum={float(fed_yr_inc.sum()):,.0f} (expected >0; base profile correctly zero)\"))"
)

if OLD_G11 in src_tf:
    src_tf = src_tf.replace(OLD_G11, NEW_G11, 1); print("  G11: OK")
elif "fed_yr_inc" in src_tf:
    print("  G11: already applied")
else:
    # Try with ASCII arrow/dash variants
    v = OLD_G11.replace("\u2192", "->").replace("\u2014", "--")
    if v in src_tf:
        src_tf = src_tf.replace(v, NEW_G11, 1); print("  G11 (ascii variant): OK")
    else:
        print("  G11: TARGET NOT FOUND -- showing context:")
        i = src_tf.find("TRAD IRA draws are ordinary income")
        print("  ", repr(src_tf[i:i+250]) if i >= 0 else "  (not found at all)")

# G13A
OLD_G13A = (
    "    nom_inv   = nom_port              # use portfolio for all geo/std/shock tests\n"
    "    real_inv  = real_port             # use portfolio real for inflation-gap test"
)
NEW_G13A = (
    "    # Use pre-withdrawal investment YoY for geo/std/shock tests.\n"
    "    # Portfolio YoY (nom_port) mean-of-means has inherently tiny std.\n"
    "    _inv_nom_raw  = _inv_nom_yoy(res)\n"
    "    _inv_real_raw = _inv_real_yoy(res)\n"
    "    nom_inv  = _inv_nom_raw  if len(_inv_nom_raw)  == YEARS else nom_port\n"
    "    real_inv = _inv_real_raw if len(_inv_real_raw) == YEARS else real_port"
)

if OLD_G13A in src_tf:
    src_tf = src_tf.replace(OLD_G13A, NEW_G13A, 1); print("  G13A: OK")
elif "_inv_nom_raw" in src_tf:
    print("  G13A: already applied")
else:
    print("  G13A: TARGET NOT FOUND")
    i = src_tf.find("nom_inv   = nom_port")
    print("  ", repr(src_tf[i:i+150]) if i >= 0 else "  (not found)")

# G13B
OLD_G13B = (
    "    res_sh, t = ephemeral_run(\"g13h_shock\", paths, shocks=sh); elapsed += t\n"
    "    nom_sh = _port_nom_yoy(res_sh)   # portfolio YoY \u2014 reliably populated\n"
    "    if len(nom_sh) >= 8 and len(nom_port) >= 8:\n"
    "        shock_region_base = float(np.mean([float(v) for v in nom_port[3:8]]))"
)
NEW_G13B = (
    "    res_sh, t = ephemeral_run(\"g13h_shock\", paths, shocks=sh); elapsed += t\n"
    "    _inv_sh_raw = _inv_nom_yoy(res_sh)\n"
    "    nom_sh = _inv_sh_raw if len(_inv_sh_raw) == YEARS else _port_nom_yoy(res_sh)\n"
    "    if len(nom_sh) >= 8 and len(nom_inv) >= 8:\n"
    "        shock_region_base = float(np.mean([float(v) for v in nom_inv[3:8]]))"
)

if OLD_G13B in src_tf:
    src_tf = src_tf.replace(OLD_G13B, NEW_G13B, 1); print("  G13B: OK")
elif "_inv_sh_raw" in src_tf:
    print("  G13B: already applied")
else:
    v = OLD_G13B.replace("\u2014", "--")
    if v in src_tf:
        src_tf = src_tf.replace(v, NEW_G13B, 1); print("  G13B (ascii variant): OK")
    else:
        print("  G13B: TARGET NOT FOUND")
        i = src_tf.find("g13h_shock")
        print("  ", repr(src_tf[i:i+300]) if i >= 0 else "  (not found)")

open("test_flags.py", "w", encoding="utf-8").write(src_tf)
print(f"  test_flags.py written: {src_tf.count(chr(10))} lines")

print("\n=== ALL DONE ===")
print("Next steps:")
print("  1. ./vcleanbld_ui   (restart server)")
print("  2. python -B test_flags.py --comprehensive-test --fast")
