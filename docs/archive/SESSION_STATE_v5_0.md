# eNDinomics — Session State v5.0
## As of March 22, 2026 | Sessions 1–25 complete

---

## Repository
- **Repo:** https://github.com/nandi-github/c-eNDinomics
- **Local:** `/Users/satish/workspace/research/c-eNDinomics/`
- **Last commit:** session 25 — real return deflator fix, core inflation, income pipeline
- **Branch:** main, clean working tree

---

## Test State
```
Python:     503/503 passing  (G1–G22, 22 groups)
Playwright: 23/23 passing
```

**Run commands:**
```bash
cd src
python3 -B test_flags.py --checkupdates           # always first
python3 -B test_flags.py --comprehensive-test      # full suite
cd ui && npx playwright test                       # Playwright only
```

---

## Session 25 — What Was Fixed

### 1. Investment return only (real) deflator bug — `simulator_new.py`
**Bug:** `inflation_yearly.json` defines 30 years; Test profile runs 49 years.
The core deflator had a conditional that fell back to `np.ones()` when
`len(_infl_arr) < n_years` — making nominal = real for years 31–49.
**Fix:** Pad `_infl_arr` to `n_years` (same pattern as main STEP 1 deflator).
**Result:** "Investment return only (real)" now correctly ~2% below nominal.

### 2. Income pipeline verified + G4 XFAIL labels removed — `test_flags.py`
Income was already wired correctly since session 24a. XFAIL labels were stale.
Removed `[XFAIL]` prefixes, strengthened assertions:
- `conv_base > conv_w2` — W2 reduces headroom
- `conv_base >= 2 * conv_w2` — W2 reduces it materially
G4: 26 checks (unchanged count — one XFAIL removed, one assertion split in two).

### 3. Core inflation single source of truth — `loaders.py` + `economicglobal.json`
**Before:** `INFL_BASELINE_ANNUAL = 0.035` hardcoded in loaders.py.
**After:** `economicglobal.json defaults.core_inflation_pct = 2.5` is the
single source. `load_inflation_yearly()` reads it via `econ_global` param.
Fallback constant updated to 2.5% (was 3.5%).

### 4. File deployment workflow clarified
- `git show origin/main:src/<file> > src/<file>` is the reliable copy method
- macOS iCloud/Finder interferes with Downloads → CLI copy
- Always use CLI (`cp`) not Finder for file operations

---

## Architecture (Locked — unchanged from v4.0)

1. GBM math identical across simulation modes
2. `api.py` injection point for simulation_mode
3. `floor_success_rate` always computed
4. Age-based for income/withdrawal; year-relative for inflation/shocks
5. All file writes via `os.replace(tmp, dst)` — SMB compatibility
6. No `window.confirm` — all confirmations inline
7. `VERSIONABLE_FILES` = all 7 config JSONs
8. `--checkupdates` before every test run
9. Default profile schema must match Test profile schema

---

## Key Numbers (Test Profile, March 2026)
```
Starting portfolio:     $9.92M (BROKERAGE $750K, TRAD_IRA $4.8M, ROTH $370K)
current_age:            46 / retirement_age: 65 / target_age: 95 (49 yrs)
simulation_mode:        automatic

Floor survival rate:    100.00%
Investment YoY nominal: 7.34% median
Investment YoY real:    ~5.0% median  ← now correctly deflated
Composite score:        83.7/100
Ending balance median:  $64.1M today's $

Core inflation fallback: 2.5% (from economicglobal.json)
```

---

## Files to Provide at Session Start
1. `DEVELOPER_GUIDE.md` ← always read first
2. `SESSION_STATE_v5_0.md` (this file)
3. `NEXT_SESSION_v5_0.md`
4. `src/simulator_new.py`
5. `src/loaders.py`
6. `src/test_flags.py`
7. `src/api.py`
8. `src/ui/src/App.tsx`
9. `src/ui/tests/smoke.spec.ts`

*Version 5.0 | March 22, 2026 | Sessions 1–25 complete*
