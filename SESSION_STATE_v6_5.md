# eNDinomics Session State v6.5
**Date:** 2026-03-29  
**Repo:** https://github.com/nandi-github/c-eNDinomics  
**Working dir:** `/Users/satish/ws/c-eNDinomics/src/`  
**Commit message:** `v6.5 — Phase inference, waterfall deposits, shock enable/disable, field reference, headroom fix, retirement_age default fix`

---

## Test Suite Status

| Layer | Result |
|-------|--------|
| Python comprehensive (32 groups) | **✅ PASS** (all groups green after --sanity) |
| Playwright UI | **95/95 ✅** |
| checkupdates | **34/34 files ✅** |

**Standard sanity command (new this session):**
```bash
./sanity.sh
# Equivalent to: python3 -B test_flags.py --comprehensive-test --update-baseline
```

---

## Manifest State (34 tracked files — CURRENT)

| File | Hash |
|------|------|
| api.py | c1edc4338fa3e715 |
| assets_loader.py | a6b4dc5cb4d3ed17 |
| config/assets.json | 5048b5214a431069 |
| config/cape_config.json | 8f3929fb14a10ac1 |
| config/economicglobal.json | b662238c5d000e07 |
| config/rmd.json | fca500e7fb73d88c |
| config/system_shocks.json | b63171ada432cb05 |
| config/taxes_states_mfj_single.json | 70bbc74e8ee69721 |
| engines_assets.py | 6e230b012a752cf2 |
| loaders.py | 3f17fbed7e593d2d |
| portfolio_analysis.py | ca785d2f87c5bc54 |
| profiles/default/allocation_yearly.json | b935bd6bcf0bf234 |
| profiles/default/economic.json | fd2a6cc8cfd04e1a |
| profiles/default/income.json | 9bf8b50ad6bded3a |
| profiles/default/inflation_yearly.json | 7e543c03e8682953 |
| profiles/default/person.json | 126a3a7c71518888 |
| profiles/default/shocks_yearly.json | 00d841442c9cc0c1 |
| profiles/default/withdrawal_schedule.json | 80c4371ee6fcd164 |
| rebuild_manifest.py | bf735102872dadf2 |
| reporting.py | ea328a157ffc6b24 |
| rmd_core.py | e1ab2e4eb5e16350 |
| roth_conversion_core.py | d10d4233837528e4 |
| roth_optimizer.py | c98f14dbe9019ee3 |
| simulation_core.py | e0574d4acbf8b170 |
| simulator_new.py | cb19bd6dd9ea1520 |
| snapshot.py | d59916e67d4fc2d7 |
| taxes_core.py | 479fb4808ab8044c |
| test_flags.py | b11f7beb220eaa07 |
| ui/playwright.config.ts | b4d013b46bf7ddb4 |
| ui/src/App.tsx | ae176175968ce770 |
| ui/tests/global-setup.ts | 16b4790e640b153e |
| ui/tests/global-teardown.ts | b49600b2b2430ec2 |
| ui/tests/smoke.spec.ts | 1159d1fc979917c9 |
| withdrawals_core.py | 4929111e619830f1 |

**Not in manifest (copy manually):**
- `ui/src/styles.css` — field reference table layout fix

---

## What Was Done This Session (v6.3 → v6.5)

### Stream 1 — Phase Inference Engine ✅
**`simulator_new.py`**
- `infer_lifecycle_phases()` — derives per-year lifecycle phase from W2 income vs spending target
  - `accumulation` — W2 > withdrawal target × 1.05
  - `transition` — W2 > 0 but ≤ target
  - `distribution` — W2 = 0, drawing from portfolio
  - `rmd` — age ≥ rmd_start_age (75 SECURE 2.0)
- `compute_mode_weights_for_year()` — derives investment/retirement weight blend from phase
- `_compute_waterfall_deposits()` — routes W2 surplus through IRS-limited buckets (Stream 2)
- **Critical bug fixed:** `retirement_age` defaulted to `current_age` when absent (via `loaders.py`'s `load_person`), causing distribution phase at yr1 for all profiles without explicit `retirement_age`. Fixed: only use as override when `retirement_age > current_age AND < current_age + n_years`
- `phase_by_year` and `weights_by_year` stored in `run_params` in snapshot

**`App.tsx` — Results tab**
- Phase badge column added to Total Portfolio table (📈/🔄/💳/📋)
- Auto-expand: Insights, Drawdown, Roth Insights auto-expand on critical/warn findings

### Stream 2 — W2 Surplus Waterfall ✅
**`simulator_new.py`**
- `_compute_waterfall_deposits()`: 401K → Roth → backdoor Roth → mega backdoor → brokerage → spend
- IRS limits: 401K $23K/$30.5K catch-up; IRA $7K/$8K catch-up; Roth MAGI phase-out enforced
- Wired into pre-simulation surplus injection when `surplus_policy: "waterfall"`

**`App.tsx` — Withdrawal Strategy guided editor**
- Surplus Routing card picker: reinvest_in_brokerage / waterfall / spend
- Waterfall order shown when waterfall selected

### Shock Enable/Disable Toggle ✅
**`loaders.py`** — `load_shocks()` now filters `enabled: false` events before returning

**`simulation_core.py`** — `shocks_mode="none"` guard: empties events list before `build_shock_matrix_from_json`

**`App.tsx`** — ShocksGuidedEditor:
- Per-row iOS-style sliding toggle (green=enabled, grey=disabled)
- Shock Mode now has three options: none / augment / replace (with per-mode explanation card)
- Mode syncs to Simulation panel on profile load AND on save
- JSON field reference table at bottom of Shocks editor

**`profiles/default/shocks_yearly.json`** — `enabled: true` added to all events; readme updated with `none` mode and `enabled` field docs

### UI Fixes ✅
- **Total Portfolio table columns:** Phase col was dropping `futMed` — fixed; correct field mapping established (`future_*` = nominal, `current_*` = real)
- **Withdrawals table:** horizontal scroll + sticky Year/Age columns; headroom beats shortfall in priority; diff warning suppressed when headroom active
- **Headroom tier:** proportional shortfall threshold (>1% of planned, min $1K); depletion cap abundance bypass (portfolio > 5× planned)
- **Depletion cap:** per-path + >10% systemic stress threshold + portfolio abundance bypass
- **Configure EDIT/VIEW panel:** right column `minWidth: 0` prevents layout escape
- **Field Reference panel:** complete rewrite — flattened two-column table with indentation, `auto 1fr` columns, no nested grid exhaustion. `styles.css` updated.
- **Sanity script:** `sanity.sh` added; `--sanity` flag in `test_flags.py` (= `--comprehensive-test --update-baseline`)
- **Retirement Age tooltip:** updated to explain coarse hint role

### Test Suite ✅
- **G31** (18 checks): phase inference — accumulation/transition/distribution/rmd detection
- **G32** (10 checks): waterfall routing — IRS limits, Roth phase-out, catch-up, spend policy
- **G8t/8u** (8 checks): shocks_mode none/replace
- **G18:** reset baseline via `--sanity`
- **G19 Playwright:** Portfolio col index 2→3 (Phase col shifted)
- **smoke.spec.ts:** Various col count and assertion fixes

---

## Architecture Decisions Made This Session

### Multi-user / Auth (design agreed, not coded)
- Each user: `src/users/{userid}/profiles/...`
- System profiles: `src/system/profiles/default/` — read-only for all users, no copying
- Session lock: `users/{userid}/session.lock` — one active session per user, override button to kill other session
- Auth: bcrypt passwords in `users/{userid}/_auth.json`, JWT session tokens
- New users see system profiles immediately — no seeding needed
- **Queued as Stream 4**

### Landing page + Demo (design agreed, not coded)
- Pre-login state renders landing page in existing App.tsx (no separate HTML)
- Hero: eNDinomics tagline + 3-model description (Financial Engine / Retirement Planner / Investment Assistant)
- Guided auto-play demo (Option A) — steps through fictional user's profile, simulation, results
- Fictional demo user — NOT "Satish" — a good gender-neutral or neutral fictional name
- GrandPlan narrative link — links to `/grandplan` page summarizing the vision
- **Queued as Stream 5**

### Three Model Architecture (clarified this session)
| Model | Question | Time horizon | Tab |
|-------|----------|-------------|-----|
| Financial Engine | What is my wealth trajectory? | 30–50 years | Simulation |
| Retirement Planner | How do I draw down safely? | Now → death | Simulation (retirement mode) |
| Investment Assistant | What do I do Monday? | Week/quarter | Investment |

---

## Files Changed This Session (git reference)

| File | Type | Change |
|------|------|--------|
| `simulator_new.py` | Changed | Phase inference, waterfall deposits, retirement_age fix, depletion cap |
| `simulation_core.py` | **New to manifest** | shocks_mode=none guard |
| `loaders.py` | **New to manifest** | load_shocks enabled filter |
| `test_flags.py` | Changed | G31, G32, G8t/u, --sanity flag |
| `ui/src/App.tsx` | Changed | All UI changes above |
| `ui/tests/smoke.spec.ts` | Changed | Col index fixes |
| `profiles/default/shocks_yearly.json` | **New to manifest** | enabled field + readme |
| `ui/src/styles.css` | NOT in manifest | Field reference table CSS |
| `sanity.sh` | New file | Standard sanity command |

---

## Pending / Deferred

| # | Item | Priority |
|---|------|----------|
| S3 | BETR — Early accumulation Roth optimization | **Next stream** |
| S4 | Multi-user auth + path restructure | After S3 |
| S5 | Landing page + guided demo | After S4 |
| A3 | IRMAA as real cash outflow | After S3 |
| A6 | SS provisional income auto-compute | After S3 |
| D1–D5 | Display fixes | Ongoing |

---

## Session Start Checklist for Next Session

```bash
# 1. Upload manifest.lock and App.tsx from this session's outputs
# 2. Verify
cd src && python3 -B test_flags.py --checkupdates

# 3. Build and start
./vcleanbld_ui

# 4. Sanity check
./sanity.sh
```

**Upload at session start:**
- `src/manifest.lock`
- `src/ui/src/App.tsx` (hash: `ae176175968ce770`)

**CRITICAL:** Always upload Claude's output files, not files from disk before the session. Use `--checkupdates` to confirm before starting any coding.
