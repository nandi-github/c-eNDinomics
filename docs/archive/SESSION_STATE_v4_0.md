# eNDinomics — Session State v4.0
## As of March 21, 2026 | Sessions 1–24b complete

---

## Repository
- **Repo:** https://github.com/nandi-github/c-eNDinomics
- **Local:** `/Volumes/My Shared Files/workspace/research/c-eNDinomics/`
- **Last commit:** `63f4b74` — "feat: session 24b complete — versioning UX, tests, docs, fixes"
- **Branch:** main (GitHub clean; local tracking ref shows phantom +1 — cosmetic, ignore)

---

## Test State
```
Python:     503/503 passing  (G1–G22, 22 groups)
Playwright: 23/23 passing
```

**Run commands:**
```bash
cd src
python3 -B test_flags.py --checkupdates           # verify all files deployed first
python3 -B test_flags.py --comprehensive-test      # full suite (Python + Playwright)
cd ui && npx playwright test                       # Playwright only
```

---

## Key Files (Claude reads DEVELOPER_GUIDE.md at session start)

| File | Purpose |
|------|---------|
| `DEVELOPER_GUIDE.md` | **Read first** — dev commands, conventions, SMB pattern, locked decisions |
| `API_REFERENCE.md` | Complete programmatic API docs (25 endpoints) |
| `src/api.py` | FastAPI server — all endpoints, versioning, manifest |
| `src/loaders.py` | Config loaders — age-based income/withdrawal |
| `src/simulator_new.py` | Simulation orchestrator |
| `src/roth_optimizer.py` | BETR 2-pass, IRA timebomb, 4×4 matrix |
| `src/snapshot.py` | Snapshot assembly |
| `src/test_flags.py` | 503 checks, G1–G22, --checkupdates |
| `src/ui/src/App.tsx` | Full React UI |
| `src/ui/tests/smoke.spec.ts` | 23 Playwright smoke tests |

---

## What Was Built — Sessions 1–24b

### Sessions 1–21 (see SESSION_STATE_v3_0.md for detail)
- Core simulation engine, GBM, taxes, RMDs, Roth conversions
- Market data layer (yfinance, ETF providers, CAPE)
- Asset model v1.3.0 with CAPE adjustment
- Portfolio look-through analysis (Layer 5)
- 4 tabs: Configure | Simulation | Investment | Results
- Simulation mode transformer (automatic/investment/balanced/retirement)
- CAPE scenario bands (live from cape_config.json)
- Roth Conversion Insights (BETR, severity, 4×4 matrix)
- Help panel

### Session 22–23b
- Roth optimizer BETR 2-pass, IRA timebomb classifier
- Age-based withdrawal schedules
- Roth Insights UX (collapsible, Apply to profile button)
- **Profile versioning** — View/Restore/Delete, Save Version, auto-label, dirty guard
- Clone dialog with version selector
- All inline confirmations (no browser dialogs anywhere)
- Playwright tests 17–23

### Session 24a
- Age-based income format (`load_income` with `current_age`/`max_years`)
- Realistic Test profile income.json (W2 $350K ages 47–64, SS $51K ages 66+)
- Format consistency: income/withdrawal = age-based, inflation/shocks = year-relative
- Help panel: simulation modes table + format explanation
- G4 updated to age-based (26 checks)

### Session 24b
- **File integrity** — `--checkupdates` flag, `/manifest` endpoint
- Server startup auto-snapshot (throttled to 1/hr, MAX_VERSIONS=50)
- `loadRuns` race condition fixed (profile-guarded clear + `snapshotReloadKey`)
- Results tab loads correctly after simulation and profile switch
- Floor survival rate: correct metric per mode; 0% full-plan explained
- Withdrawals table: mode-aware note
- `DEVELOPER_GUIDE.md` — full dev commands + Claude startup checklist
- `API_REFERENCE.md` — complete programmatic API (25 endpoints)
- Default profile sync rules documented

---

## Architecture (Locked)

1. GBM math identical across simulation modes — only success measurement changes
2. `api.py` injection point for `simulation_mode`
3. `floor_success_rate` always computed regardless of mode
4. Age-based for income/withdrawal; year-relative for inflation/shocks (by design)
5. All file writes via `os.replace(tmp, dst)` — SMB compatibility
6. No `window.confirm` — all confirmations inline
7. `VERSIONABLE_FILES` = all 7 config JSONs
8. `--checkupdates` before every test run
9. Default profile schema must match Test profile schema (values differ, fields same)

---

## Key Numbers (Test Profile, March 2026)
```
Starting portfolio:     $9.92M (BROKERAGE $750K, TRAD_IRA $4.8M, ROTH $370K)
current_age:            46 (birth_year 1980)
retirement_age:         65 / target_age: 95 (49 sim years)
simulation_mode:        automatic

Floor survival rate:    100.00%
Investment YoY nominal: 7.34% median
Composite score:        83.7/100
Ending balance median:  $64.1M today's $

Income: W2 $350K ages 47–64, SS $51K taxable ages 66+
Roth:   CRITICAL — RMD $439–526K/yr at age 75; Aggressive (32%) recommended
```

---

## SMB Write Pattern (Critical)
```python
import tempfile, os
with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                  dir=os.path.dirname(dst), delete=False, suffix=".tmp") as tmp:
    tmp.write(content); tmp_path = tmp.name
os.replace(tmp_path, dst)
# Never: open(dst, "w") on existing files → PermissionError on SMB
```

---

## Default Profile Sync Rule
Schema changes to Test configs must be mirrored to default (values differ, fields same).
```bash
diff <(python3 -c "import json; d=json.load(open('src/profiles/Test/person.json')); \
  print('\n'.join(sorted(k for k in d if k != 'readme')))") \
     <(python3 -c "import json; d=json.load(open('src/profiles/default/person.json')); \
  print('\n'.join(sorted(k for k in d if k != 'readme')))")
# No output = schemas match
```

*Version 4.0 | March 21, 2026 | Sessions 1–24b complete*
