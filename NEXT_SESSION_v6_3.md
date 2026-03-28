# eNDinomics — Next Session Brief (v6.3 → v6.4)
**Date written:** 2026-03-27  
**Tests:** 630/630 Python ✅ · 95/95 Playwright ✅ · 34/34 files ✅  
**All 7 guided editors complete.**

---

## START OF SESSION CHECKLIST

```bash
# 1. Verify manifest matches (34 entries)
python3 -c "import json; d=json.load(open('src/manifest.lock')); print(len(d['hashes']), 'entries')"

# 2. Checkupdates before anything
cd src && python3 -B test_flags.py --checkupdates

# 3. Start server
./vcleanbld_ui
```

**Upload at session start:**
- `src/manifest.lock` — hash `5dfba4b625bd25a8` (_self_crc)
- `src/ui/src/App.tsx` — hash `fa158c95880828eb` (the output from v6.3 session)

---

## PRIORITY 1 — SS Provisional Income Auto-Compute

### Problem
Social Security income is currently entered in `income.json` under `ordinary_other` with the user manually computing their taxable fraction (typically 85%). This is inaccurate and unintuitive. The correct treatment is:

**IRS SS Taxation Rules (§86):**
- **Provisional income** = AGI + tax-exempt interest + 0.5 × gross SS benefit
- Below $25K (single) / $32K (MFJ): 0% of SS is taxable
- $25K–$34K (single) / $32K–$44K (MFJ): up to 50% taxable
- Above $34K (single) / $44K (MFJ): up to 85% taxable (the maximum)

### What needs to change

**`person.json` / `loaders.py`:**
SS benefit already stored in `social_security.self_benefit_monthly` and `social_security.self_start_age`. Need to:
1. Read gross annual SS = `self_benefit_monthly * 12 * adjustment_for_start_age`
   - Start age 62: × 0.70 (30% reduction vs FRA 67)
   - Start age 67: × 1.00 (FRA)
   - Start age 70: × 1.24 (+24% delayed credits)
2. Compute provisional income per year = ordinary_income + 0.5 × gross_SS
3. Compute taxable_ss_fraction from the thresholds above (0, 0.50, or 0.85)
4. Add taxable SS to ordinary income for tax engine

**`simulator_new.py` / `api.py`:**
- Build SS income arrays from person.json (year-by-year, gated by `self_start_age`)
- Apply provisional income computation when stacking against W2/rental/etc.
- Replace the manual `ordinary_other` SS entry with auto-computed taxable SS

**`income.json` / `IncomeGuidedEditor`:**
- Add note clarifying: "If SS is configured in Personal Profile, do NOT enter SS here — it will be double-counted"
- The `ordinary_other` type label already says "If SS is configured in Personal Profile, those years are handled automatically" — ensure the auto-computation actually fires

**`taxes_core.py`:**
No changes needed — taxable SS flows into `ordinary_income_cur` as always.

### Test additions (group30)
- SS below threshold: 0% taxable (provisional income < $32K MFJ)
- SS in 50% band: correct fraction applied
- SS above threshold: 85% cap applied
- SS start age gating: income = 0 before start age, correct after
- SS excluded from plan: flag zeros SS entirely
- No double-count: SS in personal profile + SS in income.json = error or override

---

## PRIORITY 2 — IRMAA as Real Cash Outflow (A3)

Currently IRMAA is display-only (estimated in the UI from income tiers). It needs to be an actual deduction from the portfolio each year age 65+.

### Design

**`taxes_core.py` or new `medicare_core.py`:**
```python
IRMAA_BRACKETS_MFJ = [
    {"above": 206_000, "annual_surcharge_per_person": 734.40},
    {"above": 258_000, "annual_surcharge_per_person": 1_835.80},
    {"above": 322_000, "annual_surcharge_per_person": 2_937.80},
    {"above": 386_000, "annual_surcharge_per_person": 4_039.60},
    {"above": 750_000, "annual_surcharge_per_person": 4_340.60},
]
# 2-year look-back: IRMAA in year Y is based on MAGI in year Y-2
# For simulation: use current year income as proxy (conservative)
```

**`simulator_new.py`:**
- Post-tax deduction: `irmaa_cur_paths[:, y] = compute_irmaa(income_paths, age, filing)`
- Deducted from brokerage (same as tax deduction)
- Added to `withdrawals` block in res dict: `irmaa_current_mean`, `irmaa_current_median_path`

**`snapshot.py` / `SnapshotWithdrawals` type:**
- Add `irmaa_current_mean?: number[]` and `irmaa_current_median_path?: number[]` fields

**`App.tsx` — Results:**
- IRMAA column in tax table already shows estimate — replace with actual from snapshot
- Add IRMAA to total out-of-pocket in portfolio cashflow section

**`config/taxes_states_mfj_single.json`:**
- Add IRMAA brackets as a config block (not hardcoded) so they can be updated annually

### Test additions
- IRMAA = 0 before age 65
- IRMAA fires at correct tier given income
- IRMAA debited from brokerage (balance decreases by IRMAA amount)
- Bracket upgrade: income crosses tier → higher surcharge
- MFJ 2 enrollees vs single 1 enrollee

---

## PRIORITY 3 — D-Series Display Fixes

| # | Item | Fix |
|---|------|-----|
| D1 | W2/SS column shows wrong amount in year-by-year schedule | Check `inv_nom_levels_mean_acct` key for SS+W2 columns |
| D2 | Total Spendable formula wrong | Review `total_spendable` computation in withdrawals block |
| D3 | BETR vs 32% bracket explanation missing | Add tooltip/note in Roth Insights table |
| D4 | Marginal rate wrong for $450K W2 | Debug tax engine with high W2 scenario |
| D5 | SS start age not gating income | Fixed by Priority 1 above |

---

## Tax Coverage Target (v6.4)

| Tax | Engine Target | Notes |
|-----|--------------|-------|
| Federal brackets | ✅ done | |
| LTCG / Qualified div | ✅ done | |
| State income | ✅ done | |
| State CG excise | ✅ done | |
| NIIT 3.8% | ✅ done | |
| Additional Medicare 0.9% | ✅ done | |
| IRMAA | → v6.4 engine | Currently display-only |
| SS provisional income | → v6.4 engine | Currently manual |
| SE tax / SECA | future | Not in current profiles |

---

## MANIFEST PROTOCOL (every session)

1. Load manifest from **uploaded** `src/manifest.lock` (never from outputs)
2. Verify hash of file being edited matches manifest entry before touching it
3. Edit the file
4. Compute new hash of edited file
5. Update **only that entry** in manifest
6. Assert `len(hashes) == 34` before saving
7. Present both the changed file and updated manifest.lock

---

## Files Changed This Session (for git reference)

| File | Change |
|------|--------|
| `src/ui/src/App.tsx` | AllocationGuidedEditor full editor; Taxes 10-col with IRMAA |
| `src/taxes_core.py` | 5-tuple return — Medicare split out |
| `src/simulator_new.py` | 5-tuple unpack + medicare fold into fed total |
| `src/test_flags.py` | G11: all 9 unpacks updated to 5-tuple with fed+medicare fold |
| `src/ui/tests/smoke.spec.ts` | COLS.taxes 9→10; test name; eff rate col 8→9 |
| `profiles/default/inflation_yearly.json` | Updated content |
