# eNDinomics NEXT SESSION — v6.0
*Handoff for session 32 · 2026-03-24*

## Start-of-Session Checklist
```bash
cd ~/ws/c-eNDinomics/src
python3 -B test_flags.py --checkupdates      # verify all hashes match
python3 -B test_flags.py --comprehensive-test # confirm 534/534
cd ui && npx playwright test                  # confirm 23/23
```

## Priority 1 — Verify BETR Gate Fix
Run the profile with $450K W2 and check Roth Insights:

**Expected (was broken):**
- ✅ Active Strategy badge says "defer now, convert aggressively at retirement when your rate drops"
- No contradiction between "✗ Deferring may be better" and the strategy panel
- Warning says "defer until retirement, then convert" NOT "Convert aggressively now"

**If still broken** — check that `roth_optimizer.py` was deployed. The fix is in `_recommend()`:
```python
if current_marg > betr_self + 0.01:
    return "aggressive", "defer now, convert at retirement..."
```

## Priority 2 — Test SS Block
After deploying `person.json` with `social_security` block:

```bash
# Verify SS injection fires
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"profile": "Experiment-2-OptimisedRMD", "paths": 10}' | \
  python3 -c "import json,sys; r=json.load(sys.stdin); \
  print('ordinary_other yr7 (age 66):', r.get('withdrawals',{}).get('ordinary_other_current_mean',[0]*10)[6])"
```

Expected: year 7 (age 66) shows ~$45,900 ($53,850 = $2,500×12×0.85 + $1,800×12×0.85 adjusted)

## Priority 3 — Total Take-Home Column
Add `net_spendable_median_path` to `simulator_new.py` withdrawals dict:

```python
# After withdrawal loop — compute net spendable per year
# net_spendable = realized_withdrawal (after-tax from accounts)
#               + net external income (W2+SS+rental net of taxes)
# net_external = ordinary_income - total_taxes (on external income only)
# Approximation: total_taxes * (external_income / total_income)
```

Then surface in Tax table as "Total Take-Home" column (index 9, between Portfolio WD and Eff. rate).

## Priority 4 — SS Provisional Income (Proper 85% Rule)
Replace flat 85% with proper threshold computation in `api.py`:

```python
# Provisional income = AGI + 50% of gross SS
# MFJ thresholds: $32K (0%), $44K (50%), above $44K (85%)
# Single thresholds: $25K (0%), $34K (50%), above $34K (85%)
def _ss_taxable_fraction(provisional_income, filing):
    if filing == "MFJ":
        if provisional_income < 32_000: return 0.0
        if provisional_income < 44_000: return 0.50
        return 0.85
    else:
        if provisional_income < 25_000: return 0.0
        if provisional_income < 34_000: return 0.50
        return 0.85
```

The challenge: provisional income includes AGI which includes the SS itself (circular). Use iterative approach or conservative estimate.

## Priority 5 — Commit Session 31 Work
If not yet committed:
```bash
cd ~/ws/c-eNDinomics
git add src/api.py \
        src/roth_optimizer.py \
        src/simulator_new.py \
        src/test_flags.py \
        src/manifest.lock \
        src/ui/src/App.tsx \
        src/ui/tests/smoke.spec.ts \
        profiles/default/person.json

git commit -m "feat: session 31 — BETR gate fix, SS in person.json, eff rate denominator, tax table cleanup, phase labels"
git push origin main
```

## Context for New Claude Session
**What this codebase is:** eNDinomics — a retirement financial simulator with Monte Carlo engine, Roth conversion optimizer, and React UI. Python FastAPI backend, React/TypeScript frontend, Playwright + custom test suite.

**Key files:**
- `src/api.py` — FastAPI server, profile management, simulation orchestration
- `src/simulator_new.py` — Monte Carlo simulation engine
- `src/roth_optimizer.py` — Roth conversion optimizer (BETR-optimal)
- `src/roth_conversion_core.py` — bracket fill computation
- `src/ui/src/App.tsx` — entire React UI (~4500 lines)
- `src/test_flags.py` — comprehensive test suite (24 groups, 534 tests)
- `src/manifest.lock` — tracked file hashes (30 files)

**Test commands:**
```bash
cd src
python3 -B test_flags.py --checkupdates        # verify deployment
python3 -B test_flags.py --comprehensive-test  # 534 tests
python3 -B test_flags.py --reset-system-profile # re-seed __system__
python3 -B test_flags.py --reset-manifest      # recompute manifest CRC
cd ui && npx playwright test                   # 23 UI tests
```

**Deploy pattern:** Always include `manifest.lock` in every deploy. Run `--checkupdates` before testing.

**Session state transcript:** `/mnt/transcripts/` — check `journal.txt` for index.
