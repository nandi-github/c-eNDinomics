#!/usr/bin/env python3
"""
Applies api.py fixes in-place:
  1. Removes dead 'from simulator import run_accounts'
  2. Removes dead else block that calls run_accounts(...)
  3. Adds [TAX DIAG] server log lines after run_accounts_new()
Run from src/ directory: python3 patch_api.py
"""
import sys

TARGET = "api.py"

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

# ── PATCH 1: remove old import ───────────────────────────────────────────────
OLD_IMPORT = "from simulator import run_accounts\n"
if OLD_IMPORT in src:
    src = src.replace(OLD_IMPORT, "", 1)
    print("PATCH 1 (remove import): OK")
else:
    print("PATCH 1: already removed or not found — skipping")

# ── PATCH 2: remove dead else block ─────────────────────────────────────────
# Find "    else:\n        res = run_accounts(" and remove everything up to the closing paren
import re

# Match the else block: "    else:\n        res = run_accounts(\n ... \n        )\n"
pattern = re.compile(
    r"    else:\n        res = run_accounts\(.*?\n        \)\n",
    re.DOTALL
)
new_src, n_subs = re.subn(pattern, "", src)
if n_subs:
    src = new_src
    print(f"PATCH 2 (remove else block): OK ({n_subs} substitution)")
else:
    print("PATCH 2: else block not found — already removed or pattern mismatch")

# ── PATCH 3: add TAX DIAG after run_accounts_new call ───────────────────────
# Find the line after the closing paren of run_accounts_new(...)
# Look for the unique comment that follows the call
DIAG_MARKER = "    # 8) Canonical input paths and run_info"
DIAG_BLOCK = """\
    # ── Tax diagnostic (server log — remove once confirmed working) ──────────
    _wd = res.get("withdrawals", {})
    _cx = res.get("conversions", {})
    print("[TAX DIAG] taxes_fed yr20-24:",
          [round(v, 0) for v in (_wd.get("taxes_fed_current_mean") or [0]*30)[20:25]])
    print("[TAX DIAG] taxes_state yr20-24:",
          [round(v, 0) for v in (_wd.get("taxes_state_current_mean") or [0]*30)[20:25]])
    print("[TAX DIAG] conv_tax yr0-4:",
          [round(v, 0) for v in (_cx.get("conversion_tax_cur_mean_by_year") or [0]*30)[0:5]])
    print("[TAX DIAG] ord_income yr0 mean:",
          round(float(ordinary_income_cur_paths[:, 0].mean()), 2))
    print("[TAX DIAG] ord_income yr20 mean:",
          round(float(ordinary_income_cur_paths[:, 20].mean()), 2))

"""

if DIAG_MARKER in src and "[TAX DIAG]" not in src:
    src = src.replace(DIAG_MARKER, DIAG_BLOCK + DIAG_MARKER, 1)
    print("PATCH 3 (tax diag): OK")
elif "[TAX DIAG]" in src:
    print("PATCH 3: already present — skipping")
else:
    print("PATCH 3: marker not found — check api.py structure")

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(src)

print("\napi.py patches applied.")
print("Restart your server: ./build-clean-run.sh (or however you start it)")
