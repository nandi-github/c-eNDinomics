# eNDinomics Developer Guide

Last updated: Session 24b — March 2026  
Repo: `https://github.com/nandi-github/c-eNDinomics`  
Working dir: `/Volumes/My Shared Files/workspace/research/c-eNDinomics/`

---

## Table of Contents

1. [Daily Workflow](#1-daily-workflow)
2. [Server — Start, Stop, Restart](#2-server--start-stop-restart)
3. [Build — UI and Full Stack](#3-build--ui-and-full-stack)
4. [Deployment — Copying Claude-Provided Files](#4-deployment--copying-claude-provided-files)
5. [File Integrity — --checkupdates](#5-file-integrity----checkupdates)
6. [Test Suite Reference](#6-test-suite-reference)
7. [Profile Versioning](#7-profile-versioning)
8. [Git Workflow](#8-git-workflow)
9. [Configuration File Formats](#9-configuration-file-formats)
10. [Default Profile — Canonical Reference](#10-default-profile--canonical-reference)
11. [Simulation Modes](#11-simulation-modes)
12. [Model / Reference Data Integrity](#12-model--reference-data-integrity)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Daily Workflow

Standard session workflow — from opening terminal to committing:

```bash
# 1. Start server (builds UI + starts API)
cd /Volumes/My\ Shared\ Files/workspace/research/c-eNDinomics/src
./vcleanbld_ui

# 2. After Claude provides files — verify ALL are deployed
python3 -B test_flags.py --checkupdates

# 3. If stale files found — copy them, restart server
cp ~/Downloads/<file>  src/<path>
./vcleanbld_ui

# 4. Run full test suite
python3 -B test_flags.py --comprehensive-test

# 5. Run Playwright UI tests separately if needed
cd ui && npx playwright test && cd ..

# 6. Commit when green
git add <files>
git commit -m "feat: ..."
git push origin main
```

---

## 2. Server — Start, Stop, Restart

```bash
# Start (builds UI, starts API server on :8000)
cd src && ./vcleanbld_ui

# Start with hot-reload (development — auto-restarts on .py changes)
# Requires watchfiles: pip install watchfiles
# Without watchfiles, --reload crashes when test harness creates/deletes ephemeral profiles
cd src && pip install watchfiles && uvicorn api:app --reload --port 8000

# Stop
Ctrl+C

# Check server is up
curl http://localhost:8000/health

# View server manifest (all tracked file hashes)
curl http://localhost:8000/manifest | python3 -m json.tool
```

**On every server start**, the API automatically:
1. Computes SHA256 hashes of all tracked source files → logs to console
2. Snapshots all user profiles to `.versions/` → creates a restore point for the session

---

## 3. Build — UI and Full Stack

```bash
# Full clean build + server start (most common)
cd src && ./vcleanbld_ui

# UI only (no server restart)
cd src/ui && npm run build

# UI dev server (hot-reload, proxies API to :8000)
cd src/ui && npm run dev

# Install Playwright browsers (one-time setup)
cd src/ui && npx playwright install chromium
```

The `vcleanbld_ui` script runs `npm run build` then starts `uvicorn`. It's the canonical way to deploy any change that touches `App.tsx` or other UI files.

---

## 4. Deployment — Copying Claude-Provided Files

Claude may provide any combination of these files in a session. **All must be copied** before running tests — a missed file causes hard-to-diagnose failures.

### Backend files
```bash
cp ~/Downloads/api.py           src/api.py
cp ~/Downloads/loaders.py       src/loaders.py
cp ~/Downloads/simulator_new.py src/simulator_new.py
cp ~/Downloads/snapshot.py      src/snapshot.py
cp ~/Downloads/roth_optimizer.py src/roth_optimizer.py
cp ~/Downloads/test_flags.py    src/test_flags.py
```

### UI files (require UI rebuild after copy)
```bash
cp ~/Downloads/App.tsx          src/ui/src/App.tsx
cp ~/Downloads/smoke.spec.ts    src/ui/tests/smoke.spec.ts
```

### Profile config files
```bash
cp ~/Downloads/person.json              src/profiles/Test/person.json
cp ~/Downloads/withdrawal_schedule.json src/profiles/Test/withdrawal_schedule.json
cp ~/Downloads/income.json              src/profiles/Test/income.json
cp ~/Downloads/allocation_yearly.json   src/profiles/Test/allocation_yearly.json
cp ~/Downloads/inflation_yearly.json    src/profiles/Test/inflation_yearly.json
cp ~/Downloads/shocks_yearly.json       src/profiles/Test/shocks_yearly.json
cp ~/Downloads/economic.json            src/profiles/Test/economic.json
```

### After copying — always restart
```bash
cd src && ./vcleanbld_ui   # for any .tsx change
# OR just restart uvicorn for .py-only changes
```

---

## 5. File Integrity — --checkupdates

Checks that every file deployed to the running server matches your local copy. Catches missed file copies before they cause confusing test failures.

```bash
# Check all tracked files against running server
python3 -B test_flags.py --checkupdates

# Check against a non-default server
python3 -B test_flags.py --checkupdates --server http://localhost:8001
```

### Sample output

```
========================================================================
  eNDinomics --checkupdates  |  server: http://localhost:8000
  Tracks all files Claude provides — catches missed copies before testing

  Python backend
  File                                     Local hash         Server hash        Status
  ---------------------------------------- ------------------ ------------------ ------
  api.py                                   a3f2b1c9d4e5f6a7   a3f2b1c9d4e5f6a7   ✅ match
  loaders.py                               b8c9d0e1f2a3b4c5   OLD_HASH_HERE      ❌ STALE

  UI files
  File                                     Local hash         Server hash        Status
  ui/src/App.tsx                           c4d5e6f7a8b9c0     c4d5e6f7a8b9c0     ✅ match

  Profile configs
  profiles/Test/income.json                e6f7a8b9c0d1e2     e6f7a8b9c0d1e2     ✅ match

  ❌ 1 file(s) out of date — copy and restart server:

     cp ~/Downloads/loaders.py  src/loaders.py

  Then restart: cd src && ./vcleanbld_ui
========================================================================
```

### Tracked files
The manifest covers all 16 files Claude may provide:
- 6 Python backend files
- 2 UI files (App.tsx, smoke.spec.ts)
- 7 Test profile JSON configs
- test_flags.py

**Rule:** Always run `--checkupdates` before `--comprehensive-test`. A stale file is always the first thing to check when test results don't match expectations.

### Planned extensions (future sessions)
- `--checkupdates --full` — hash every `.py`/`.ts`/`.tsx` in `src/`
- `--checkmodel` — verify reference data (`assets.json`, `rmd.json`, `cape_config.json`) against `manifest.lock`

---

## 6. Test Suite Reference

### Run commands

```bash
# Full suite (Python G1-G22 + Playwright G19) — server must be running
python3 -B test_flags.py --comprehensive-test

# Python only — no server/browser needed
python3 -B test_flags.py --comprehensive-test --skip-playwright

# Playwright only
cd ui && npx playwright test

# Playwright with visible browser (debug)
cd ui && npx playwright test --headed

# View last Playwright HTML report
cd ui && npx playwright show-report

# Update G18 regression baseline (after intentional number changes)
python3 -B test_flags.py --comprehensive-test --update-baseline

# Verify deployed files before testing
python3 -B test_flags.py --checkupdates
```

### Test groups

| Group | Checks | Coverage |
|-------|--------|----------|
| G1  | 34 | Ignore-flag matrix (withdrawals, RMDs, conversions, taxes) |
| G2  | 11 | RMDs — SECURE 2.0 ages, factors, schedule |
| G3  | 15 | Roth conversion policy — bracket fill, window years |
| G4  | 26 | Income — W2, rental, interest, SS (age-based format) |
| G5  | 5  | Inflation — rate schedules, real vs nominal |
| G6  | 27 | Withdrawal schedule — age-based format, floor, validation |
| G7  | 8  | Allocation — per-account, per-year, overrides |
| G8  | 59 | Shocks — all preset levels, co-impact, augment/override |
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
| G19 | 1  | Playwright — 23 browser smoke tests |
| G20 | 24 | Portfolio analysis — holdings, score, weights |
| G21 | 7  | Asset weight sanity |
| G22 | 50 | Roth optimizer — BETR, severity, bracket math |

**Current target: 503/503 Python + 23/23 Playwright**

### When to run which groups

| Change made to | Groups to watch |
|---|---|
| `simulator_new.py`, `taxes_core.py`, `rmd_core.py` | G1–G16 |
| `snapshot.py`, `api.py` | G17, G18 |
| `loaders.py` | G4, G6 |
| `roth_optimizer.py` | G22 |
| `App.tsx`, `smoke.spec.ts` | G19 |

---

## 7. Profile Versioning

Every profile edit is auto-versioned. Key behaviors:

```
On every config save:      auto-snapshot → .versions/vN/ with auto-label
On server startup:         auto-snapshot all profiles → "server startup — auto-checkpoint"
On Save Version (UI):      manual snapshot with user label
On Restore:                auto-saves current state first, then copies vN back
```

### Versionable files (all 7)
`person.json`, `withdrawal_schedule.json`, `allocation_yearly.json`,
`income.json`, `inflation_yearly.json`, `shocks_yearly.json`, `economic.json`

### Version history API (admin/curl)

```bash
# List versions for a profile
curl http://localhost:8000/profile/Test/versions | python3 -m json.tool

# View a specific file from a specific version
curl http://localhost:8000/profile/Test/versions/5/person.json

# Restore a version (auto-saves current first)
curl -X POST http://localhost:8000/profile/Test/restore/5

# Delete a single version
curl -X DELETE http://localhost:8000/profile/Test/versions/5

# Delete all versions (admin cleanup)
curl -X DELETE "http://localhost:8000/profile/Test/versions"

# Keep last 3, delete older
curl -X DELETE "http://localhost:8000/profile/Test/versions?keep=3"
```

### Version storage
```
src/profiles/Test/
  .versions/                   ← git-ignored
    profile_history.json       ← manifest (v, ts, note, source, files_changed)
    v1/
      person.json
      withdrawal_schedule.json
      ...
    v2/
      ...
```

**MAX_VERSIONS = 50** — oldest auto-pruned beyond this.

---

## 8. Git Workflow

### Commit after every green test run

```bash
git add <specific files>    # never git add -A — be explicit
git commit -m "feat/fix/chore: description

- bullet what changed
- bullet why"
git push origin main
```

### .gitignore — what's excluded

```
src/profiles/*/.versions/     ← version history (local only)
src/profiles/*/reports/       ← simulation run outputs
src/ui/dist/                  ← built UI
node_modules/
test_results/                 ← test output JSON
market_data/cache/store/      ← market data cache
logs/
```

### Checking repo state

```bash
git status                    # clean working tree?
git log --oneline -5          # last 5 commits
git status --ignored | grep .versions   # confirm versions are ignored
```

### If git push says "Everything up-to-date" but you have local commits

```bash
git fetch origin
git log --oneline origin/main -3   # check what GitHub actually has
git push origin HEAD:main           # explicit push
```

---

## 9. Configuration File Formats

### Age-based format (withdrawal_schedule.json, income.json)
```json
{ "ages": "47-64", "amount_nom": 350000 }
```
- Ages are **inclusive, exclusive non-overlapping**
- Converted to simulation years using `current_age` from `person.json`
- Overlapping ranges raise `ValueError`
- Year-based (`"years": "1-18"`) still accepted for backward compat

### Year-relative format (inflation_yearly.json, shocks_yearly.json)
```json
{ "years": "1-10", "rate_pct": 3.0 }
```
- Year 1 = `current_age + 1` (first simulation year)
- These use years **by design** — they describe economic conditions, not life-stage events

### Why the difference
- Withdrawal amounts and income are tied to your age (W2 stops at 65, SS starts at 67)
- Inflation and shocks are tied to the simulation timeline (crash in year 3, not "at age 49")

---

## 10. Default Profile — Canonical Reference

The `default` profile is the reference template for all new profiles. It must stay in sync with any schema changes made to the Test profile.

**Always update `default` when:**

| Change | Example |
|--------|---------|
| New field added to any config JSON | Added `roth_optimizer_config` to person.json |
| Field removed | Removed deprecated field |
| Format change | `"years"` → `"ages"` in income.json or withdrawal_schedule.json |
| README/field reference updated | New field documented in readme block |
| New config file added | New `cape_config.json` template |

**Do NOT update `default` for:**
- Profile-specific values (Test profile's $9.92M balances, birth_year 1980)
- Field reordering (cosmetic)
- Test-specific scenario configurations

**Sync check after every session:**
```bash
# Compare top-level keys between Test and default person.json
diff <(python3 -c "import json; d=json.load(open('src/profiles/Test/person.json')); print('\n'.join(sorted(k for k in d if k != 'readme')))") \
     <(python3 -c "import json; d=json.load(open('src/profiles/default/person.json')); print('\n'.join(sorted(k for k in d if k != 'readme')))")
# No output = schemas match
```

**Files that must stay in sync (schema, not values):**
```
src/profiles/Test/person.json              ↔  src/profiles/default/person.json
src/profiles/Test/withdrawal_schedule.json ↔  src/profiles/default/withdrawal_schedule.json
src/profiles/Test/income.json              ↔  src/profiles/default/income.json
src/profiles/Test/allocation_yearly.json   ↔  src/profiles/default/allocation_yearly.json
src/profiles/Test/inflation_yearly.json    ↔  src/profiles/default/inflation_yearly.json
src/profiles/Test/shocks_yearly.json       ↔  src/profiles/default/shocks_yearly.json
src/profiles/Test/economic.json            ↔  src/profiles/default/economic.json
```

---

## 11. Simulation Modes

Set in `person.json → simulation_mode` or on the Simulation tab.

| Mode | Withdrawal funded to | Primary metric | Best for |
|------|---------------------|----------------|----------|
| `automatic` | Floor (base_k) in poor years, full target otherwise — glide path | Floor survival rate | Most users |
| `investment` | Floor only (base_k) — preserves capital always | Floor survival rate + CAGR | Accumulation phase |
| `balanced` | 50/50 blend of floor and full target | Composite score | Transition years |
| `retirement` | Full target when sustainable; floor when survival at risk | Full-plan survival rate | Distribution phase |

### Why investment/automatic modes show 0% full-plan survival

**This is expected and correct.** In investment and automatic modes, the simulator deliberately funds only the floor (base_k) in poor years to preserve capital for recovery and long-term growth. Since almost no simulation path funds 100% of withdrawals in every single year over 49 years, the full-plan rate will be near 0%.

A 0% full-plan rate alongside:
- 100% floor survival rate
- Large ending balance ($64M median)

...is the **ideal outcome** in investment/automatic mode, not a failure.

**All modes** fall back to the floor when paying the full target would risk portfolio depletion — the difference is how aggressively: investment-first funds only the floor even in good years; retirement-first funds the full target whenever sustainable.

Switch to `retirement` mode if consistent full withdrawal amounts are the priority.

---

## 12. Model / Reference Data Integrity

### Current approach (manual)
Model files (`assets.json`, `rmd.json`, `cape_config.json`, `economicglobal.json`) are updated via `promote_model.py` and committed to git. Changes are tracked in `promotion_log.json`.

```bash
# View model promotion history
cat src/promotion_log.json | python3 -m json.tool | head -40

# Promote a new asset model candidate
cd src && python3 promote_model.py --candidate asset-model/candidate/assets.json
```

### Planned: manifest.lock (future session)
A `manifest.lock` file committed to git will track SHA256 hashes of all reference data. Server will verify on startup. `--checkmodel` flag will compare against lock.

```bash
# Future command
python3 -B test_flags.py --checkmodel
```

---

## 13. Troubleshooting

### Tests fail but you just deployed files
```bash
# Always check this first
python3 -B test_flags.py --checkupdates
# Did you forget a file? Did you rebuild the UI after App.tsx change?
cd src && ./vcleanbld_ui
```

### SMB permission errors (PermissionError on /Volumes/My Shared Files/)
The API uses `os.replace(tmp, dst)` for all writes — creates a temp file then atomically renames. If you see PermissionError, check:
- Is the server process the one that owns the file?
- Try restarting the server — sometimes SMB locks need clearing

### G19 Playwright tests fail after a UI change
```bash
cd src/ui
npx playwright test --headed   # run with visible browser to see what's happening
npx playwright show-report      # view screenshots/video of failures
```

Common cause: a label or selector changed in `App.tsx`. Check the test against the new label.

### Versioning tests (G21-G23) fail
Usually means the Test profile hit MAX_VERSIONS (50). The tests auto-delete the oldest version to make room, but if 48+ versions exist they need a brief cleanup:
```bash
# Keep last 10 versions
curl -X DELETE "http://localhost:8000/profile/Test/versions?keep=10"
```

### git push says "Everything up-to-date" but commits exist locally
The SMB share can corrupt `.git/config` with duplicate `branch.main.merge` entries,
causing push to think nothing needs sending even when you're ahead of origin.

```bash
git branch -u origin/main main   # reset to single clean tracking ref
git push origin main              # now sends correctly
```

Verify it worked: `git status` should show "Your branch is up to date with 'origin/main'".
If this recurs frequently, consider migrating the repo to local disk (see below).

---

### Should you move the repo off the SMB share?

**SMB share issues seen in practice:**
- `git push` silently drops commits (`branch.main.merge` corruption)
- `git add` sometimes doesn't stage files
- `PermissionError` on file writes (fixed by temp+replace pattern in api.py)
- iCloud/Finder interferes with file copies from Downloads

**Recommendation: yes, move to local disk for the git repo.**

```bash
# Clone fresh to local disk
cd ~/workspace   # or wherever you want it
git clone https://github.com/nandi-github/c-eNDinomics.git
cd c-eNDinomics

# Verify everything is there
git log --oneline -5
python3 -B test_flags.py --comprehensive-test
```

Keep the SMB share as a **backup/archive only** — do all active development
from the local clone. The SMB share's main value was network accessibility;
the GitHub remote serves that purpose better.

**After moving:** update the working dir path in this guide:
```
Working dir: ~/workspace/c-eNDinomics/
```
All destructive actions use inline confirmation — no `window.confirm` anywhere in the codebase. If you see a browser native dialog, it's a regression. Search `App.tsx` for `window.confirm` — should return zero results.

### G18 snapshot regression fails after intentional change
```bash
python3 -B test_flags.py --comprehensive-test --update-baseline
# This clears the baseline — next run regenerates it from current output
```

### Server manifest shows "missing" for a file
The file doesn't exist on the server path. Check `MANIFEST_FILES` in `api.py` — the path is relative to `APP_ROOT` (the `src/` directory). For UI files, `ui/src/App.tsx` means `src/ui/src/App.tsx` on disk.

### Profile restore fails (500 error)
Check server console for the traceback. Common causes:
- SMB permission on existing file → should be fixed by temp+replace pattern
- Version snapshot directory missing → check `.versions/vN/` exists
- `logger` not defined → should be fixed (uses `print()` now)

---

## Appendix: All Dev Commands Quick Reference

```bash
# ── Server ────────────────────────────────────────────────────────────────
cd src && ./vcleanbld_ui                          # clean build + start server
curl http://localhost:8000/health                 # server health check
curl http://localhost:8000/manifest               # file hashes (startup snapshot)

# ── File integrity ────────────────────────────────────────────────────────
python3 -B test_flags.py --checkupdates           # verify all deployed files
python3 -B test_flags.py --checkupdates --server http://localhost:8001

# ── Tests ─────────────────────────────────────────────────────────────────
python3 -B test_flags.py --comprehensive-test      # full suite (503 checks)
python3 -B test_flags.py --comprehensive-test --skip-playwright
python3 -B test_flags.py --comprehensive-test --update-baseline
cd ui && npx playwright test                       # UI tests only (23 tests)
cd ui && npx playwright test --headed              # visible browser
cd ui && npx playwright show-report                # HTML report

# ── Profile versioning (curl) ─────────────────────────────────────────────
curl http://localhost:8000/profile/Test/versions
curl http://localhost:8000/profile/Test/versions/5/person.json
curl -X POST http://localhost:8000/profile/Test/restore/5
curl -X POST http://localhost:8000/profile/Test/snapshot \
     -H "Content-Type: application/json" \
     -d '{"note": "before experiment", "source": "user"}'
curl -X DELETE http://localhost:8000/profile/Test/versions/5
curl -X DELETE "http://localhost:8000/profile/Test/versions?keep=10"

# ── Git ───────────────────────────────────────────────────────────────────
git status
git log --oneline -5
git add src/api.py src/ui/src/App.tsx             # always explicit, never -A
git commit -m "feat: description"
git push origin main
git status --ignored | grep .versions             # confirm versions ignored

# ── Market data / model ───────────────────────────────────────────────────
cd src && bash refresh_model.sh                   # refresh market data
cd src && python3 promote_model.py --candidate asset-model/candidate/assets.json
cat src/promotion_log.json | python3 -m json.tool # view promotion history

# ── UI dev ────────────────────────────────────────────────────────────────
cd src/ui && npm run dev                          # hot-reload dev server
cd src/ui && npm run build                        # production build only
cd src/ui && npx playwright install chromium      # one-time browser setup
```
