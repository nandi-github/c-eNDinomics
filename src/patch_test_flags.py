#!/usr/bin/env python3
"""
Applies G11 and G13 patches to test_flags.py in-place.
Run from src/ directory: python3 patch_test_flags.py
"""
import sys

TARGET = "test_flags.py"

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

# ── G11 PATCH ────────────────────────────────────────────────────────────────
OLD_G11 = (
    "    # TRAD IRA draws are ordinary income → taxes_fed is non-zero even without income.json income\n"
    "    checks.append(chk(\"Ordinary fed taxes > 0 in conversion window (TRAD draws are taxable)\",\n"
    "                       float(fed_yr.sum()) > 0,\n"
    "                       f\"fed_sum={float(fed_yr.sum()):,.0f} (expected >0 — TRAD draws are ordinary income)\"))"
)
NEW_G11 = (
    "    # Base profile: bracket-fill converts ~$23,850/yr (10% bracket ceiling).\n"
    "    # Federal standard deduction (MFJ) = $31,500 > $23,850 → fed taxable income = $0.\n"
    "    # This is CORRECT for base profile. Verify wiring fires via res_inc ($60k rental income\n"
    "    # puts ordinary income well above the $31,500 std deduction).\n"
    "    fed_yr_inc = np.array(_wd_taxes_fed(res_inc)[:20], dtype=float)\n"
    "    checks.append(chk(\"Ordinary fed taxes > 0 with $60k rental income (income > std deduction)\",\n"
    "                       float(fed_yr_inc.sum()) > 0,\n"
    "                       f\"fed_sum={float(fed_yr_inc.sum()):,.0f} (expected >0; base profile correctly zero)\"))"
)

if OLD_G11 not in src:
    print("ERROR: G11 target text not found — already patched or file mismatch")
    sys.exit(1)
src = src.replace(OLD_G11, NEW_G11, 1)
print("G11 patch: OK")

# ── G13 PATCH A — replace nom_inv / real_inv aliases ─────────────────────────
OLD_G13A = (
    "    nom_inv   = nom_port              # use portfolio for all geo/std/shock tests\n"
    "    real_inv  = real_port             # use portfolio real for inflation-gap test"
)
NEW_G13A = (
    "    # Use pre-withdrawal investment YoY for geo/std/shock tests.\n"
    "    # Portfolio YoY (nom_port) is the mean-of-means — its std is inherently tiny\n"
    "    # (~0.3-0.5%) because per-year means converge, not because paths are flat.\n"
    "    _inv_nom_raw  = _inv_nom_yoy(res)\n"
    "    _inv_real_raw = _inv_real_yoy(res)\n"
    "    nom_inv  = _inv_nom_raw  if len(_inv_nom_raw)  == YEARS else nom_port\n"
    "    real_inv = _inv_real_raw if len(_inv_real_raw) == YEARS else real_port"
)

if OLD_G13A not in src:
    print("ERROR: G13A target text not found — already patched or file mismatch")
    sys.exit(1)
src = src.replace(OLD_G13A, NEW_G13A, 1)
print("G13A patch: OK")

# ── G13 PATCH B — replace shock baseline source ──────────────────────────────
OLD_G13B = (
    "    res_sh, t = ephemeral_run(\"g13h_shock\", paths, shocks=sh); elapsed += t\n"
    "    nom_sh = _port_nom_yoy(res_sh)   # portfolio YoY — reliably populated\n"
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

if OLD_G13B not in src:
    print("ERROR: G13B target text not found — already patched or file mismatch")
    sys.exit(1)
src = src.replace(OLD_G13B, NEW_G13B, 1)
print("G13B patch: OK")

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(src)

print("\nAll patches applied. Run: python -B test_flags.py --comprehensive-test --fast")
