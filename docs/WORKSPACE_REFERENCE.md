# eNDinomics — Workspace Reference
**Version:** 6.5 | **Updated:** 2026-03-29  
**Repo:** https://github.com/nandi-github/c-eNDinomics  
**Working dir:** `/Users/satish/ws/c-eNDinomics/src/`  
**Stack:** Python 3.11 (FastAPI + numpy) · React/TypeScript (Vite) · Playwright

---

## Table of Contents
1. [File Structure](#1-file-structure)
2. [Manifest — The Integrity Contract](#2-manifest--the-integrity-contract)
3. [Session Process — Working with Claude](#3-session-process--working-with-claude)
4. [Daily Workflow](#4-daily-workflow)
5. [Build & Server Commands](#5-build--server-commands)
6. [Test Suite](#6-test-suite)
7. [Sanity Command](#7-sanity-command)
8. [Git Workflow & GitHub Safety](#8-git-workflow--github-safety)
9. [Profile System](#9-profile-system)
10. [Configuration File Formats](#10-configuration-file-formats)
11. [Simulation Modes & Phase Engine](#11-simulation-modes--phase-engine)
12. [Architecture Decisions Log](#12-architecture-decisions-log)
13. [Troubleshooting](#13-troubleshooting)
14. [Quick Reference — All Commands](#14-quick-reference--all-commands)

---

## 1. File Structure

```
c-eNDinomics/
└── src/                                ← working root for everything
    │
    ├── sanity.sh                       ← standard test command (run this constantly)
    ├── manifest.lock                   ← SHA256 hashes of all 34 tracked files
    ├── rebuild_manifest.py             ← verify disk state vs manifest
    ├── vcleanbld_ui                    ← full clean build + server start
    │
    ├── ── PYTHON BACKEND ──────────────────────────────────────
    ├── api.py                          ← FastAPI endpoints (all HTTP routes)
    ├── simulator_new.py                ← Monte Carlo + phase inference + waterfall
    ├── simulation_core.py              ← simulate_balances, shock matrix, per-account
    ├── engines.py                      ← GBM return engine, shock application
    ├── engines_assets.py               ← Per-asset return draws, shock matrix builder
    ├── taxes_core.py                   ← Federal/state/NIIT/Medicare tax computation
    ├── roth_optimizer.py               ← BETR analysis, multi-scenario Roth strategy
    ├── roth_conversion_core.py         ← Bracket fill, conversion execution logic
    ├── withdrawals_core.py             ← Per-account withdrawal sequencing
    ├── rmd_core.py                     ← IRS uniform lifetime tables, RMD schedule
    ├── portfolio_analysis.py           ← Diversification, look-through, sector weights
    ├── income_core.py                  ← Income stream assembly from person.json
    ├── loaders.py                      ← All JSON file loading (profiles, config)
    ├── assets_loader.py                ← Asset model loading (assets.json)
    ├── snapshot.py                     ← Result serialization → snapshot JSON
    ├── reporting.py                    ← Report artifact generation
    ├── rebuild_manifest.py             ← Disk vs manifest verification tool
    │
    ├── ── TESTS ───────────────────────────────────────────────
    ├── test_flags.py                   ← 32 functional test groups, 650+ checks
    ├── test_results/
    │   └── regression_baseline.json   ← G18 snapshot regression baseline (tracked)
    │
    ├── ── CONFIG (system-wide, tracked in manifest) ────────────
    ├── config/
    │   ├── assets.json                 ← Asset model (GBM params, correlations, tickers)
    │   ├── taxes_states_mfj_single.json ← Tax brackets by state and filing status
    │   ├── system_shocks.json          ← System shock presets (mild/moderate/severe)
    │   ├── rmd.json                    ← IRS uniform lifetime table (SECURE 2.0)
    │   ├── economicglobal.json         ← Bad-market thresholds, global defaults
    │   └── cape_config.json            ← CAPE ratio config and adjustments
    │
    ├── ── PROFILES ────────────────────────────────────────────
    ├── profiles/
    │   ├── default/                    ← SYSTEM profile — tracked in git, read-only in UI
    │   │   ├── person.json
    │   │   ├── withdrawal_schedule.json
    │   │   ├── allocation_yearly.json
    │   │   ├── income.json
    │   │   ├── inflation_yearly.json
    │   │   ├── shocks_yearly.json
    │   │   └── economic.json
    │   │
    │   ├── __system__*/                ← System test fixtures — tracked in git
    │   ├── __testui__/                 ← Playwright test account — tracked in git
    │   │
    │   └── Experimental-Optimized/    ← USER profile — git-ignored
    │       ├── person.json            ← Personal financial data — NEVER to GitHub
    │       ├── *.json                 ← All other config files
    │       ├── reports/               ← Simulation run artifacts — git-ignored
    │       └── versions.json          ← Version history — git-ignored
    │
    ├── ── UI ──────────────────────────────────────────────────
    ├── ui/
    │   ├── src/
    │   │   ├── App.tsx                 ← Entire React frontend (~8200 lines)
    │   │   ├── styles.css              ← CSS (NOT in manifest — copy manually)
    │   │   └── main.tsx                ← Entry point
    │   ├── tests/
    │   │   ├── smoke.spec.ts           ← 95 Playwright tests
    │   │   ├── global-setup.ts         ← Playwright setup
    │   │   └── global-teardown.ts      ← Playwright teardown
    │   ├── playwright.config.ts
    │   ├── package.json
    │   └── dist/                       ← Built UI — git-ignored
    │
    ├── ── FUTURE (Stream 4 — not yet built) ───────────────────
    ├── system/
    │   └── profiles/
    │       └── default/                ← Will replace profiles/default/ after Stream 4
    └── users/
        └── {userid}/
            ├── _auth.json              ← bcrypt password hash + metadata
            ├── session.lock            ← Active session tab lock
            └── profiles/
                └── {profile-name}/     ← User's private profiles
```

### What is and is NOT tracked in manifest.lock

| Category | Files | Tracked |
|----------|-------|---------|
| Python backend | api.py, loaders.py, simulator_new.py, simulation_core.py, snapshot.py, reporting.py, roth_optimizer.py, roth_conversion_core.py, withdrawals_core.py, portfolio_analysis.py, rmd_core.py, assets_loader.py, engines_assets.py, taxes_core.py, rebuild_manifest.py | ✅ |
| Tests | test_flags.py | ✅ |
| UI | ui/src/App.tsx, ui/tests/smoke.spec.ts, ui/tests/global-setup.ts, ui/tests/global-teardown.ts, ui/playwright.config.ts | ✅ |
| System config | config/assets.json, config/taxes_states_mfj_single.json, config/system_shocks.json, config/rmd.json, config/economicglobal.json, config/cape_config.json | ✅ |
| Default profile | profiles/default/*.json (7 files) | ✅ |
| styles.css | ui/src/styles.css | ❌ Copy manually |
| User profiles | profiles/Experimental-Optimized/ etc. | ❌ Git-ignored |
| Build artifacts | ui/dist/, node_modules/ | ❌ Git-ignored |

**Total tracked: 34 files. Always 34. If len(hashes) ≠ 34, something is wrong.**

---

## 2. Manifest — The Integrity Contract

The manifest is the guarantee that what Claude provided and what's deployed to the server match exactly.

```
manifest.lock["hashes"]       ← Claude's voucher: "these files, these exact hashes"
      ↓
api.py → /manifest endpoint   ← server serves hashes at startup
      ↓
--checkupdates                ← compares server hashes vs local disk
```

### Rules
1. **Claude loads manifest from the uploaded file** — never regenerates from scratch
2. **Claude updates only entries for files it changed** — all others stay untouched
3. **Count must always be 34** — Claude asserts this before every save
4. **Never manually edit hashes** — defeats the integrity check
5. **run `--checkupdates` before every test run** — catches missed copies

```bash
# Verify all 34 deployed files match manifest
python3 -B test_flags.py --checkupdates

# Verify disk state without server (after copying files)
python3 rebuild_manifest.py
```

---

## 3. Session Process — Working with Claude

### What to upload at the START of every session
```
1. src/manifest.lock              ← required — Claude loads this first
2. src/ui/src/App.tsx             ← required if UI work planned
3. SESSION_STATE_vX.md            ← context from last session
4. NEXT_SESSION_vX.md             ← what to work on
5. GRANDPLAN_v2.md                ← overall vision context
6. Any specific file Claude asks for (e.g. simulation_core.py if engine work)
```

### What Claude provides at the END of every session
```
1. Changed .py files             ← deploy to src/
2. Changed App.tsx               ← deploy to src/ui/src/
3. styles.css (if changed)       ← deploy to src/ui/src/ (not in manifest)
4. manifest.lock                 ← deploy to src/ — always
5. SESSION_STATE_vX.md           ← current state doc
6. NEXT_SESSION_vX.md            ← next session brief
7. GRANDPLAN_v2.md               ← updated vision (if decisions made)
```

### Claude's manifest protocol (every session)
```
Step 1: Load manifest from uploaded manifest.lock
Step 2: For each file to edit:
        - verify hash matches manifest entry
        - make changes
        - compute new SHA256 hash
        - update that single entry in manifest
Step 3: Assert len(hashes) == 34
Step 4: Save manifest.lock
Step 5: Ship changed file(s) + manifest.lock together
```

### Verification after deploying Claude's files
```bash
cp ~/Downloads/*.py  src/
cp ~/Downloads/App.tsx  src/ui/src/
cp ~/Downloads/manifest.lock  src/

./vcleanbld_ui                          # rebuild UI + restart server
python3 -B test_flags.py --checkupdates  # verify all 34 match
./sanity.sh                              # full test run
```

---

## 4. Daily Workflow

```bash
# ── START OF DAY ──────────────────────────────────────────────────────────
cd /Users/satish/ws/c-eNDinomics/src
./vcleanbld_ui                           # build UI + start server

# ── AFTER DEPLOYING CLAUDE FILES ─────────────────────────────────────────
python3 -B test_flags.py --checkupdates  # always do this first
./vcleanbld_ui                           # rebuild if any .py or .tsx changed
./sanity.sh                              # full test run

# ── COMMIT WHEN GREEN ────────────────────────────────────────────────────
git add src/api.py src/ui/src/App.tsx src/manifest.lock   # be explicit
git commit -m "v6.x — description of change"
git push
```

---

## 5. Build & Server Commands

```bash
# Full clean build + server start (most common — use this always)
./vcleanbld_ui

# UI only (when .tsx changed but no .py changes)
cd ui && npm run build && cd ..

# UI hot-reload dev server (proxies API to :8000)
cd ui && npm run dev

# Server health check
curl http://localhost:8000/health

# View server's file hashes (what's currently deployed)
curl http://localhost:8000/manifest | python3 -m json.tool

# Install Playwright browsers (one-time)
cd ui && npx playwright install chromium
```

---

## 6. Test Suite

### Run commands
```bash
# Standard sanity (use this — it's the standard gate)
./sanity.sh

# Full suite explicitly
python3 -B test_flags.py --comprehensive-test --update-baseline

# Python tests only (no Playwright)
python3 -B test_flags.py --comprehensive-test --skip-playwright

# Playwright only
cd ui && npx playwright test

# Playwright with visible browser (debug)
cd ui && npx playwright test --headed

# View last Playwright HTML report
cd ui && npx playwright show-report

# Check files before testing
python3 -B test_flags.py --checkupdates
```

### All test groups (32 groups, 650+ checks)

| Group | Checks | Coverage |
|-------|--------|----------|
| G1  | 34 | Ignore-flag matrix (withdrawals, RMDs, conversions, taxes) |
| G2  | 11 | RMDs — SECURE 2.0 ages, factors, schedule |
| G3  | 15 | Roth conversion policy — bracket fill, window years |
| G4  | 26 | Income — W2, rental, interest, SS (age-based format) |
| G5  | 5  | Inflation — rate schedules, real vs nominal |
| G6  | 27 | Withdrawal schedule — age-based, floor, validation |
| G7  | 8  | Allocation — per-account, per-year, overrides |
| G8  | 67 | Shocks — profiles, co-impact, modes (none/augment/replace) |
| G9  | 9  | Ages — current_age, birth_year, compute mode |
| G10 | 5  | Rebalancing — drift, brokerage cap gains, IRA free rebal |
| G11 | 37 | Tax wiring — federal/state/NIIT, standard deductions |
| G12 | 26 | Conversion tax — bracket math, tax cost debit |
| G13 | 33 | YoY sanity — CAGR, real/nominal gap, shock visibility |
| G14 | 15 | Cashflow — balances move correctly with withdrawals/RMDs |
| G15 | 23 | Insights engine — all trigger thresholds |
| G16 | 28 | Dynamic sim years — target_age, 10–60yr clamp |
| G17 | 38 | UI data integrity — snapshot fields, eff rate ≤ 100% |
| G18 | 22 | Snapshot regression — ~25 key numbers vs baseline (5% tol) |
| G19 | 1  | Playwright — 95 browser smoke tests |
| G20 | 24 | Portfolio analysis — holdings, score, weights |
| G21 | 7  | Asset weight sanity |
| G22 | 50 | Roth optimizer — BETR, severity, bracket math |
| G23 | 10 | Versioning — save, list, restore, delete, concurrency |
| G24 | 8  | CAPE ratio — valuation adjustment, expected return |
| G25 | 12 | Bad-market sequencing — withdrawal pivot logic |
| G26 | 6  | Simulation mode switching — automatic/investment/balanced/retirement |
| G27 | 8  | Headroom — floor survival, abundance detection |
| G28 | 11 | Deposits — annual contributions, IRA limits |
| G29 | 9  | Allocation overrides — year ranges, mode aug/replace |
| G30 | 15 | Cashflow year-by-year — W2, SS, rental, withdrawal stacking |
| G31 | 18 | Phase inference — accumulation/transition/distribution/rmd |
| G32 | 10 | W2 surplus waterfall — IRS limits, Roth phase-out, catch-up |

### When to run which groups

| Change made to | Groups to watch |
|---|---|
| `simulator_new.py`, `simulation_core.py` | G1, G13–G16, G25–G32 |
| `taxes_core.py` | G11, G12 |
| `rmd_core.py` | G2 |
| `roth_optimizer.py` | G3, G22 |
| `withdrawals_core.py` | G6, G14 |
| `loaders.py` | G4, G6, G8 |
| `snapshot.py`, `api.py` | G17, G18 |
| `App.tsx`, `smoke.spec.ts` | G19 |

---

## 7. Sanity Command

`./sanity.sh` is the **standard gate** before every commit. It runs:
1. `--checkupdates` — aborts if any file is stale
2. All 32 Python test groups
3. Playwright (G19)
4. `--update-baseline` — refreshes G18 regression snapshot

```bash
# Standard sanity
./sanity.sh

# Equivalent explicit form
python3 -B test_flags.py --comprehensive-test --update-baseline
```

**Rule: green sanity = safe to commit. Never commit on a red sanity.**

---

## 8. Git Workflow & GitHub Safety

### The fundamental rule
**Code → GitHub. User data → local only. Always.**

### .gitignore — what's excluded

```
# User data — NEVER
users/                          # entire user tree (Stream 4+)
profiles/*/                     # all user profiles
profiles/*/reports/             # simulation run artifacts
profiles/*/versions.json        # personal version history
users/*/session.lock            # runtime state

# System profiles — ALLOWED (safe, no personal data)
# (via !profiles/default/, !profiles/__system__*/, !profiles/__testui__/)

# Build artifacts
ui/dist/
ui/node_modules/
__pycache__/
*.pyc
test_results/                   # exception: regression_baseline.json is kept
market_data/cache/

# Secrets
.env
secrets.json
```

### Commit sequence for a session

```bash
# 1. gitignore change ALONE — do this first ever
git add .gitignore
git commit -m "chore: add .gitignore — user profiles never to GitHub"
git push

# 2. Regular session commit
git add src/simulator_new.py src/ui/src/App.tsx src/manifest.lock
git commit -m "v6.5 — Phase inference, waterfall, shock toggle"
git push

# 3. Before starting multi-user work — tag the clean starting point
git tag -a multiuser-start -m "Stream 4 start — multi-user auth and path restructure"
git push origin multiuser-start
```

### Before committing — checklist
```bash
python3 -B test_flags.py --checkupdates   # all 34 files match
./sanity.sh                                # green
git status                                 # nothing unexpected in staging
git status --ignored | grep profiles/Experimental  # confirm personal data ignored
```

### Verify profile protection
```bash
git check-ignore -v profiles/Experimental-Optimized/person.json
# → .gitignore:X profiles/Experimental-Optimized/person.json  ✓

git check-ignore -v profiles/default/person.json
# → (no output) = NOT ignored, system profile ✓
```

---

## 9. Profile System

### Profile types

| Type | Location | GitHub | Editable in UI | Purpose |
|------|----------|--------|----------------|---------|
| System reference | `profiles/default/` | ✅ Tracked | ❌ Read-only | Schema + reference values |
| System test fixtures | `profiles/__system__*/` | ✅ Tracked | ❌ Read-only | Test harness profiles |
| Playwright test | `profiles/__testui__/` | ✅ Tracked | ❌ Read-only | UI smoke tests |
| User profile | `profiles/Experimental-Optimized/` etc. | ❌ Ignored | ✅ Full edit | Personal financial data |

### Profile files (7 versionable files per profile)
```
person.json                  ← who you are, SS, Roth policy, simulation mode
withdrawal_schedule.json     ← how much to draw, floor, age-based schedule
allocation_yearly.json       ← accounts, balances, asset allocation, deposits
income.json                  ← W2, rental, SS, interest income streams
inflation_yearly.json        ← year-relative inflation rate schedule
shocks_yearly.json           ← market shock events (enable/disable per event)
economic.json                ← surplus policy, withdrawal strategy
```

### Profile versioning
```
On every config save:    auto-snapshot → .versions/vN/ with auto-label
On server startup:       auto-snapshot all profiles → "server startup — auto-checkpoint"
On Save Version (UI):    manual snapshot with user label
On Restore:              auto-saves current first, then copies vN back
Max versions: 50         (oldest pruned automatically)
```

### Version management (curl)
```bash
# List versions
curl http://localhost:8000/profile/Test/versions

# View a file from a specific version
curl http://localhost:8000/profile/Test/versions/5/person.json

# Restore a version
curl -X POST http://localhost:8000/profile/Test/restore/5

# Keep last 10, delete older
curl -X DELETE "http://localhost:8000/profile/Test/versions?keep=10"
```

### Keeping default/ in sync with Test/
When you add a new field to `Test/person.json`, you must also add it to `default/person.json`.
```bash
# Quick schema diff
diff \
  <(python3 -c "import json; d=json.load(open('profiles/Test/person.json')); print('\n'.join(sorted(k for k in d if k != 'readme')))") \
  <(python3 -c "import json; d=json.load(open('profiles/default/person.json')); print('\n'.join(sorted(k for k in d if k != 'readme')))")
# No output = schemas match ✓
```

---

## 10. Configuration File Formats

### Age-based format (`withdrawal_schedule.json`, `income.json`)
```json
{ "ages": "47-64", "amount_nom": 350000 }
```
- Ages are inclusive, non-overlapping
- Converted to simulation years using `current_age` from `person.json`
- Overlapping age ranges raise `ValueError`

### Year-relative format (`inflation_yearly.json`, `shocks_yearly.json`)
```json
{ "years": "1-10", "rate_pct": 3.0 }
```
- Year 1 = `current_age + 1` (first simulation year)
- Used for economic conditions — not life-stage events

### Why the difference
Withdrawal amounts are tied to your **age** (W2 stops at 65, SS starts at 67).
Inflation and shocks are tied to the **simulation timeline** (crash in year 3).

### Shock event format
```json
{
  "class": "US_STOCKS",
  "start_year": 5,
  "start_quarter": 1,
  "depth": 0.20,
  "dip_quarters": 4,
  "recovery_quarters": 8,
  "override_mode": "strict",
  "recovery_to": "baseline",
  "dip_profile": { "type": "poly", "alpha": 1.3 },
  "rise_profile": { "type": "poly", "alpha": 1.6 },
  "enabled": true
}
```
- `enabled: false` — event preserved in file but skipped by simulator
- `mode` (top-level): `none` / `augment` / `replace` — syncs to Simulation panel

---

## 11. Simulation Modes & Phase Engine

### Simulation modes

| Mode | Funds withdrawals to | Best for |
|------|---------------------|----------|
| `automatic` | Phase-aware glide path (floor in bad years) | Most users |
| `investment` | Floor only (base_k) — preserve capital | Pure accumulation |
| `balanced` | 50/50 floor and full target | Transition years |
| `retirement` | Full target when sustainable | Distribution phase |

### Lifecycle phases (inferred automatically)
| Phase | Condition | Badge |
|-------|-----------|-------|
| `accumulation` | W2 > withdrawal target × 1.05 | 📈 |
| `transition` | W2 > 0 but ≤ target | 🔄 |
| `distribution` | W2 = 0, drawing from portfolio | 💳 |
| `rmd` | Age ≥ 73 (SECURE 2.0) | 📋 |

### W2 Surplus Waterfall (when `surplus_policy: "waterfall"`)
```
W2 surplus → 401K ($23K/$30.5K catch-up)
           → Roth IRA ($7K/$8K, MAGI phase-out)
           → Backdoor Roth
           → Mega backdoor Roth
           → Brokerage
           → Spend
```

### Why 0% full-plan survival is NOT a failure
In `investment` and `automatic` modes, the simulator funds only the floor in poor years to preserve capital. A 0% full-plan rate with 100% floor survival and large ending balance = ideal outcome. Use `retirement` mode if full target withdrawals every year is the priority.

---

## 12. Architecture Decisions Log

### Decisions made and implemented
| Decision | Detail |
|----------|--------|
| `retirement_age` is a hint, not a hard override | Only used when `retirement_age > current_age AND < current_age + n_years`. Defaults to `current_age` in loaders would cause distribution phase at yr1 — fixed. |
| Shock `enabled` field | Default `true` if absent — backward compatible. `loaders.py` filters on load; `simulation_core.py` guards on `mode="none"`. |
| `shocks_mode` sync | Simulation panel seeds from `shocks_yearly.json` on profile load; `guidedOnSave` syncs immediately on save. |
| Field reference table | Fully flattened — no nested grids. Hierarchical depth shown via left-padding only. Single `<table>` with `28%/72%` columns. |

### Decisions made, not yet implemented
| Decision | Stream | Detail |
|----------|--------|--------|
| Multi-user auth | Stream 4 | bcrypt + JWT, session lock with override |
| System profiles shared read-only | Stream 4 | `system/profiles/default/` — no per-user copying |
| Landing page pre-login | Stream 5 | Conditional render in App.tsx on JWT absence |
| Guided demo fictional user | Stream 5 | NOT "Satish" — use "Alex" or "Jordan" |

---

## 13. Troubleshooting

### Tests fail right after deploying files
```bash
python3 -B test_flags.py --checkupdates    # did you miss a file?
./vcleanbld_ui                              # did you forget to rebuild?
```

### G18 regression fails after intentional change
```bash
./sanity.sh                                 # --update-baseline is built into sanity.sh
# Regenerates baseline from current output automatically
```

### G19 Playwright fails after UI change
```bash
cd ui && npx playwright test --headed      # see browser live
cd ui && npx playwright show-report        # HTML report with screenshots
# Check: did a label or column count change in App.tsx?
```

### `git push` says "Everything up-to-date" but commits exist
SMB shares can corrupt `.git/config`:
```bash
git branch -u origin/main main
git push origin main
```
**Recommendation:** Run the repo from local disk (`~/workspace/`), not an SMB share.

### Server manifest shows fewer than 34 files
Wrong `manifest.lock` on disk when server started. Copy the correct one and restart.
```bash
cp ~/Downloads/manifest.lock  src/manifest.lock
./vcleanbld_ui
```

### Profile restore fails (500 error)
```bash
# Check server console for traceback
# Most common: version snapshot directory missing
ls src/profiles/Test/.versions/vN/
# If missing, the version was pruned (max 50 kept)
```

### Version count too high — test failures
```bash
curl -X DELETE "http://localhost:8000/profile/Test/versions?keep=10"
```

---

## 14. Quick Reference — All Commands

```bash
# ── Server ────────────────────────────────────────────────────────────────
./vcleanbld_ui                                    # clean build + start server
curl http://localhost:8000/health                 # health check
curl http://localhost:8000/manifest               # see deployed file hashes

# ── File integrity ────────────────────────────────────────────────────────
python3 -B test_flags.py --checkupdates          # verify all 34 match
python3 rebuild_manifest.py                       # verify disk vs manifest

# ── Tests ─────────────────────────────────────────────────────────────────
./sanity.sh                                       # ← USE THIS (standard gate)
python3 -B test_flags.py --comprehensive-test     # explicit form
python3 -B test_flags.py --comprehensive-test --skip-playwright
cd ui && npx playwright test                      # UI tests only
cd ui && npx playwright test --headed             # visible browser
cd ui && npx playwright show-report               # HTML report

# ── Git ───────────────────────────────────────────────────────────────────
git status
git log --oneline -5
git add src/file.py src/manifest.lock             # always explicit
git commit -m "v6.x — description"
git push
git tag -a multiuser-start -m "description"       # before Stream 4
git push origin multiuser-start
git status --ignored | grep profiles/Experimental # confirm data is ignored
git check-ignore -v profiles/Experimental-Optimized/person.json  # verify

# ── Profile versioning ────────────────────────────────────────────────────
curl http://localhost:8000/profile/Test/versions
curl http://localhost:8000/profile/Test/versions/5/person.json
curl -X POST http://localhost:8000/profile/Test/restore/5
curl -X DELETE "http://localhost:8000/profile/Test/versions?keep=10"

# ── UI build ──────────────────────────────────────────────────────────────
cd ui && npm run build
cd ui && npm run dev                              # hot-reload dev server
cd ui && npx playwright install chromium          # one-time setup
```
