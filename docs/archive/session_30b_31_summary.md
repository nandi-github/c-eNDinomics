# eNDinomics Sessions 30b-31 — Complete State

## Repository
- **Repo:** https://github.com/nandi-github/c-eNDinomics
- **Last commits:** `a5bc44d` (session 30c), `da39448` (TRAD IRA eff rate fix)
- **Branch:** main, clean

## Test State (last known good)
```
Python:     534/534 passing
Playwright: 23/23 passing (Test profile, not __system__)
```

## Sessions 30b-31 — Completed Work

### Manifest.lock
- `src/manifest.lock` — 30 tracked files with SHA256 self-CRC
- `api.py` reads manifest.lock at startup, exposes `/manifest` endpoint
- `update_manifest_lock()` public function for asset model updater
- `test_flags.py --reset-manifest` CLI to recompute CRC
- `config/assets.json` excluded (external asset pricing module)
- `profiles/default/` tracked (not `profiles/Test/`)
- `__system__` hidden from UI dropdown; Playwright uses `Test` profile

### System Profile Independence
- `__system__` hidden from UI dropdown (api.py `list_profiles()` filters `__`)
- Playwright reverted to `Test` profile (visible to users)
- G19 prunes `Test` versions before Playwright run (prevents MAX_VERSIONS)
- `__system__` seeded by `--reset-system-profile`, used only by Python suite

### Effective Tax Rate — Backend Computation
- `simulator_new.py` snapshots `ordinary_income_cur_paths` immediately after tax computation
- `effective_tax_rate_median_path` computed in backend (not client-side)
- Denominator = taxable income = gross income − standard deduction (MFJ: $31,500, Single: $15,750)
- `total_ordinary_income_median_path` uses tax-computation snapshot (correct, not post-simulation modified array)
- Removed broken TRAD WD double-counting addition
- `App.tsx` reads `W.effective_tax_rate_median_path[i]` directly; legacy fallback for old snapshots

### Tax Table UI
- Removed "Taxable Income" column (unreliable partial data)
- Tax table back to 9 clean columns: Federal | State | NIIT | Excise | Total | Portfolio WD | Eff. rate
- Right-aligned numbers, font-size 12, overflow-x auto (horizontal scroll on narrow viewports)
- "Tax Cost" → "Conv. Tax" in Roth schedule table (clarifies it's conversion-only marginal cost)
- Portfolio WD labeled "(after-tax)" in header
- Table description updated: "Effective rate = total taxes ÷ taxable income (gross − std deduction)"

### SWR + Upside Scaling Fields (G24)
- `safe_withdrawal_rate_p10_pct` = mean planned withdrawal / starting portfolio
- `upside_scaling_enabled` = from econ_scaling_params (default false)
- Both now in withdrawals dict, available to API consumers

### TRAD IRA Withdrawals in Effective Rate
- Added TRAD IRA discretionary withdrawals to ordinary_income_cur_paths during withdrawal loop
- Corrected double-counting of RMDs (removed, reverted)
- Final approach: snapshot at tax computation point (captures W2+SS+RMDs+conversions)

### Phase Labels Fix
- `_build_schedule` uses person.json signals:
  - 💼 working: age < retirement_age
  - 🔄 transition: age == retirement_age
  - 🌅 retire gap: retirement_age < age < ss_start_age
  - 📬 SS active: ss_start_age <= age < rmd_start_age
  - 📋 RMD era: age >= rmd_start_age
- SS start age derived from first non-zero value in ordinary_by_year

### Roth Optimizer — BETR Gate Fix
- `_recommend()` now has BETR gate as primary check:
  - If current_marg > betr_self + 1% → "defer now, convert at retirement"
  - Otherwise → severity-based strategy
- `warnings[]` gated on BETR: "defer until retirement" instead of "convert aggressively now" when rate is wrong
- App.tsx badge text: "defer now, convert aggressively at retirement when your rate drops" when deferring better

### Social Security in person.json
- `api.py` SS injection block between `load_income` and `build_income_streams`
- `person.json` `social_security` block:
  ```json
  {
    "self_benefit_monthly": 2500,
    "self_start_age": 67,
    "spouse_benefit_monthly": 1800,
    "spouse_start_age": 67,
    "exclude_from_plan": false
  }
  ```
- Early/delayed adjustment: FRA=67 (born 1960+), 8%/yr delayed, 5/9% per month early
- 85% inclusion rule applied by default
- `exclude_from_plan: true` zeros out SS for portfolio-only sufficiency test
- Backward compatible: if no `social_security` block, `income.json` `ordinary_other` used as-is
- `default/person.json` updated with SS defaults ($2,000/$1,500 at age 67)

## PENDING — Deploy Queue

```bash
# Files from this session
cp ~/Downloads/api.py             src/api.py
cp ~/Downloads/roth_optimizer.py  src/roth_optimizer.py
cp ~/Downloads/simulator_new.py   src/simulator_new.py
cp ~/Downloads/App.tsx            src/ui/src/App.tsx
cp ~/Downloads/smoke.spec.ts      src/ui/tests/smoke.spec.ts
cp ~/Downloads/test_flags.py      src/test_flags.py
cp ~/Downloads/manifest.lock      src/manifest.lock
cp ~/Downloads/default_person.json profiles/default/person.json
# person.json for active profile (optional — adds SS block)
cp ~/Downloads/person.json        profiles/Experiment-2-OptimisedRMD/person.json

cd src && ./vcleanbld_ui
python3 -B test_flags.py --reset-system-profile
python3 -B test_flags.py --comprehensive-test
```

## Known Open Items (Session 32+)

| Item | Priority |
|------|----------|
| Roth optimizer: "Active Strategy" badge — verify fix works post-deploy | Immediate |
| Total Take-Home column in Tax table — needs backend `net_spendable_median_path` field | Near-term |
| SS 85% inclusion rule — full provisional income computation (not flat 85%) | Near-term |
| IRMAA as real simulation expense (not advisory-only) | Near-term |
| User config CRC sidecar (.crc per profile, warn on mismatch) | Deferred |
| SS full retirement age by birth year in schedule phases | Deferred |
| Investment Tab Phase 2 — signal computation | Deferred |

## Key Architecture Notes

### Effective Tax Rate Pipeline
```
taxes_core.compute_annual_taxes_paths()
  → taxes_fed/state/niit/excise_cur_paths computed on ordinary_income_cur_paths
  → SNAPSHOT ordinary_income_cur_paths here (_taxable_income_snapshot)
  → effective_tax_rate_median_path = total_taxes / max(0, snapshot - std_ded)
  → stored in withdrawals dict → API response → App.tsx reads directly
```

### BETR Gate Logic
```python
if current_marg > betr_self + 0.01:
    # Timebomb real but defer until income drops
    return "aggressive", "defer now, convert at retirement..."
else:
    # Convert based on severity
    return severity_map[severity]
```

### Social Security Injection
```python
# api.py — between load_income() and build_income_streams()
_ss_cfg = person_cfg.get("social_security") or {}
if _ss_cfg and not _ss_cfg.get("exclude_from_plan"):
    # Compute per-year SS with early/delayed adjustment
    # Apply 85% inclusion rule
    # Override income_cfg["ordinary_other"]
```

### manifest.lock Self-CRC
```json
{
  "_self_crc": "SHA256(tracked_list, sort_keys=True)[:16]",
  "tracked": ["api.py", "loaders.py", ..., "config/assets.json", ...]
}
```
Asset model updater must call `update_manifest_lock()` after writing `config/assets.json`.
