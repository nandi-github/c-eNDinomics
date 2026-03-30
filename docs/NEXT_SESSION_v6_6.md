# NEXT_SESSION — eNDinomics Stream 4 (Multi-user)
**Starting from:** v6.6 (committed end of Stream 3)  
**Goal:** Multi-user auth + profile path restructure  
**Tag before starting:** `git tag multiuser-start`

---

## Session Start Checklist

```bash
# 1. Upload manifest.lock and App.tsx to Claude
# 2. Verify all files match
cd src && python3 -B test_flags.py --checkupdates

# 3. Build and start
./vcleanbld_ui

# 4. Sanity
./sanity.sh
```

**Upload at session start:**
- `src/manifest.lock` (36 entries)
- `src/ui/src/App.tsx` (hash: 40509e9dbb6d454f)
- `src/test_flags.py` (hash: 634f54a0cab3371d)

**Expected sanity:** 33 groups, 0 failed (G19 and G33 both ✅ when server running)

---

## Critical Context for Next Session

### What we just finished (v6.6)
- Portfolio chart full rewrite — currency toggle, reference returns, CAPE labels, clipped lines
- Arithmetic floor amber/red severity split — consistent across Drawdown, Insights, Roth
- Liquidity gap Option 1/2 apply buttons — fix `/profile-config-get` 404, correct floor target
- IRA Timebomb traffic-light colors — SEVERE=red, MANAGEABLE=blue, on_track=green
- G33 test suite — 16+18 checks for all v6.6 display changes

### G34 tests to write before Stream 4 work begins
See SESSION_STATE_v6_6.md for the 8 checks needed (G34a–G34h).
Write these first, get them passing, then proceed to multiuser.

---

## Stream 4 — Multi-user Auth Plan (from GRANDPLAN_v2)

### Phase 1: Path restructure (no auth yet)
Current: `profiles/{name}/` flat structure  
Target: `profiles/{user_id}/{name}/` nested structure

Files to modify:
- `api.py` — all profile endpoints
- `loaders.py` — profile loading
- `App.tsx` — profile API calls

### Phase 2: Auth layer
- Simple JWT or session-based auth
- Login page (minimal — email + password)
- User registration endpoint
- Profile isolation by user_id

### Phase 3: Admin view
- View all users
- Impersonate for support
- Usage metrics

### Key constraint
- Keep `default/` profile structure for the demo/guest user
- Backward-compatible migration for existing profiles
- All 36 manifest files must still match after restructure

---

## Files NOT Changed in v6.6 (Python engine intact)

All Python engine files have identical hashes to v6.5:
`api.py, simulator_new.py, snapshot.py, reporting.py, roth_optimizer.py,`  
`roth_conversion_core.py, withdrawals_core.py, portfolio_analysis.py, rmd_core.py,`  
`taxes_core.py, simulation_core.py, engines_assets.py, loaders.py, assets_loader.py`

No regression risk from Python side.

---

## Commit Message for v6.6

```
git add -A
git commit -m "v6.6: portfolio chart rewrite, amber/red severity, arith floor options, G33

- Portfolio chart: currency toggle, reference returns legend, CAPE sub-labels,
  clipped depletion lines, net-of-withdrawal scenario lines, correct rate basis
- Arithmetic floor: isArithFloorOnly logic, amber/red split in Drawdown/Insights/Roth
- Liquidity gap: Option 1/2 apply buttons, correct floor target, loadVersionHistory
- IRA Timebomb: SEVERE=red, MODERATE=amber, MANAGEABLE=blue, on_track=green
- Portfolio table: P10 -> stress case labels
- Run state: liquidityApplyStatus reset on new run selection
- Fixes: profile-config-get 404 (6 sites), React.useState in IIFE crash
- G33 test suite: 34 new Playwright checks for v6.6 display correctness
- smoke.spec.ts: Accounts YoY timeout fix (G19 flake resolved)"

git tag v6.6
```
