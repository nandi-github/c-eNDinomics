# eNDinomics SESSION STATE — v6.0
*Generated end of session 31 · 2026-03-24*

## Repository
- **Repo:** https://github.com/nandi-github/c-eNDinomics
- **Last commits:** `a5bc44d` session 30c · `da39448` TRAD IRA eff rate
- **Branch:** main — clean (nothing to commit after session 31 deploy)

## Test State
```
Python:     534/534 ✅  (24 groups)
Playwright: 23/23  ✅  (Test profile)
```

## File Hashes (post session 31 deploy)
All files in `--checkupdates` show ✅ match after deploy.
Key changed files this session:
- `api.py` — SS injection, manifest.lock reader, income_data injection fix
- `roth_optimizer.py` — BETR gate fix, phase labels, conflicts framework
- `simulator_new.py` — effective rate backend, SWR/upside fields, tax snapshot
- `App.tsx` — tax table 9 cols, Conv. Tax label, BETR badge text fix
- `smoke.spec.ts` — taxes 9 cols index 8, Test profile (not __system__)
- `test_flags.py` — G22/G23/G24 fixes, system profile, --reset-manifest
- `manifest.lock` — 30 tracked files, self-CRC

## Architecture State

### Income Pipeline
```
income.json → load_income() → income_cfg
     ↓
api.py SS injection block (if person.json has social_security block)
  - reads self/spouse benefit_monthly, start_age
  - applies early/delayed FRA adjustment
  - applies 85% SS inclusion rule
  - override income_cfg["ordinary_other"]
  - exclude_from_plan=true → zero out SS
     ↓
build_income_streams() → w2_cur, ordinary_other_cur, ...
     ↓
ordinary_income_cur_paths (W2 + SS + rental + interest)
     ↓
STEP 0: RMDs added to ordinary_income_cur_paths
STEP 0: Conversions added (bracket fill)
     ↓
taxes_core.compute_annual_taxes_paths() — tax computation
     ↓
SNAPSHOT → _taxable_income_snapshot (correct denominator)
     ↓
effective_tax_rate_median_path = total_taxes / (snapshot - std_ded)
```

### Roth Optimizer Decision Tree
```
BETR gate (PRIMARY):
  if current_marg > betr_self + 1%:
    → "defer now, convert aggressively at retirement"
    → badge: "defer now, convert at retirement when rate drops"
  else:
    → severity_map: CRITICAL/SEVERE→aggressive, MODERATE→balanced, MANAGEABLE→conservative
    → upgrade to betr_optimal if future_rate > 35%
    → downgrade if IRMAA-sensitive and near 63

Warnings:
  SEVERE + deferring → "defer until retirement, then convert"
  SEVERE + converting now → "Convert aggressively now"

on_track = configured_amount ≈ recommended_amount (within 10%)
```

### Manifest System
```
src/manifest.lock → 30 tracked files + _self_crc
api.py _load_manifest_lock() → verifies CRC at startup → warns if corrupt
api.py /manifest endpoint → serves hashes to --checkupdates
test_flags.py --reset-manifest → recomputes CRC
asset model updater → must call update_manifest_lock() after assets.json
```

### System Profile / Playwright
```
__system__ → Python test suite only (hidden from UI dropdown)
Test       → Playwright target (visible, pruned before each run by G19)
profiles/default/ → tracked in manifest.lock (not Test/)
```

### Tax Table (9 cols)
```
Year | Age | Federal | State | NIIT | Excise | Total | Portfolio WD (after-tax) | Eff. rate
```
- Right-aligned numbers, font-size 12, overflow-x auto
- Eff. rate denominator: gross income − std_deduction (MFJ $31,500, Single $15,750)
- "Conv. Tax" in Roth schedule = conversion marginal tax only (not full year bill)

### person.json social_security block
```json
"social_security": {
  "self_benefit_monthly": 2500,
  "self_start_age": 67,
  "spouse_benefit_monthly": 1800,
  "spouse_start_age": 67,
  "exclude_from_plan": false
}
```
- FRA = 67 (born 1960+), 66 (born 1943-1959)
- Delayed credit: +8%/yr past FRA up to 70
- Early reduction: -5/9%/mo first 36mo, -5/12%/mo beyond
- 85% inclusion rule default (conservative)
- Backward compatible: if no block → income.json ordinary_other used as-is

## Open Bugs / Known Issues
1. **Roth badge text** — BETR gate fix deployed but not yet tested in UI
2. **Total Take-Home column** — removed (was wrong). Needs `net_spendable_median_path` from backend
3. **SS 85% inclusion** — flat 85% used. Full provisional income computation deferred
4. **IRMAA** — advisory only in optimizer schedule. Not deducted as real simulation expense

## TODO Backlog (prioritized)

| Item | Priority |
|------|----------|
| Verify BETR gate fix in UI (Roth Insights section) | Immediate |
| Total Take-Home column (backend net_spendable field) | Near-term |
| SS provisional income computation (proper 50%/85% thresholds) | Near-term |
| IRMAA as real cash expense in simulation | Near-term |
| User config CRC sidecar (.crc per profile) | Deferred |
| Investment Tab Phase 2 — signal computation | Deferred |
| SS full retirement age by birth year for phase labels | Deferred |

## Profile State (Experiment-2-OptimisedRMD)
```json
birth_year: 1967 (current_age: ~59)
retirement_age: 65
target_age: 95
W2: $450K ages 47-64, $160K age 65
SS: $53K ordinary_other ages 66-95 (manual, in income.json)
     → SS block added to person.json this session ($2,500/$1,800 at 67)
TRAD IRA: $5.7M starting ($3.5M + $2.2M)
roth_conversion_policy: enabled, 32% cap, avoid_niit=true, $83K/yr
```
