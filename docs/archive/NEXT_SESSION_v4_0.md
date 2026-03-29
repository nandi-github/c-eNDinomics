# eNDinomics — Next Session Build Plan v4.0
## March 21, 2026 | Sessions 25+

---

## Context for New Chat
- Repo: https://github.com/nandi-github/c-eNDinomics
- **Read DEVELOPER_GUIDE.md first** — Claude startup checklist + all conventions
- All tests green: 503/503 Python + 23/23 Playwright
- Last commit: `63f4b74` — session 24b complete
- See SESSION_STATE_v4_0.md for complete current state

---

## IMMEDIATE (Session 25 — do in order)

### 1. Income Pipeline Fix (3 XFAILs → passing)
**Files:** `src/roth_conversion_core.py`, `src/simulator_new.py`

**Problem:** `ordinary_income_cur_paths` computed but not fully wired to bracket-fill conversion logic. W2 income ($350K) should narrow Roth headroom during working years (ages 47–64) — currently does not.

**Impact:** With $350K W2, marginal rate is 24% and conversion headroom is very limited during working years. After retirement (ages 66–74), SS only $19.5K taxable → $375K/yr headroom to 24% bracket. This is the prime Roth window.

**What to fix:** Wire `ordinary_income_cur_paths` through to `apply_bracket_fill_conversions()` so W2/income actually affects conversion headroom.

**Test verification:** 3 XFAILs in G4 should pass after fix.

---

### 2. Commit Session State Docs to Repo
```bash
cp SESSION_STATE_v4_0.md  /path/to/repo/SESSION_STATE_v4_0.md
cp NEXT_SESSION_v4_0.md   /path/to/repo/NEXT_SESSION_v4_0.md
git add SESSION_STATE_v4_0.md NEXT_SESSION_v4_0.md DEVELOPER_GUIDE.md API_REFERENCE.md
git commit -m "docs: session state v4.0, next session v4.0, developer guide, API reference"
git push origin main
```

---

### 3. Playwright Tests — Remaining Coverage
**File:** `src/ui/tests/smoke.spec.ts`

Add tests for features added in session 24b:
- T24: Withdrawal table shows mode note in investment/automatic mode
- T25: Help panel contains simulation modes table

---

## NEAR-TERM (Sessions 25–27)

### 4. Pure Investment Return Metric
**Files:** `src/simulator_new.py`, `src/snapshot.py`

Current "Investment YoY" includes RMD reinvestment, inflating CAGR.
Add: "Pure Asset Return" = portfolio return excluding all cash flows.
G13 addition: verify pure return ≤ Investment YoY.

---

### 5. Investment Tab Phase 2 — Signal Computation
**New file:** `market_data/signal_computation.py`

Reads market_data cache, computes per ticker:
- CMF (21-day Chaikin Money Flow)
- Wyckoff phase detection
- OBV divergence
- CAPE from FRED API
- Bayesian regime posterior (expansion/slowdown/contraction/recovery)

Outputs: `market_signals.json` — auto-populated by `refresh_model.sh`

---

### 6. File Integrity — Tiers 2 & 3

**Tier 2** (`--checkupdates --full`):
- Walk all `.py/.ts/.tsx` in `src/`
- Hash everything, show unexpected additions/deletions

**Tier 3** (`--checkmodel`):
- `manifest.lock` committed to git (SHA256 of assets.json, rmd.json, cape_config.json, economicglobal.json)
- `promote_model.py` writes lock on promotion
- Server verifies on startup

---

## MEDIUM-TERM

### 7. Tax-Efficient Transfer Detection
Appreciated low-basis brokerage + dependents in 0% LTCG → gift opportunity.
Requires `cost_basis.json` Phase 1.

### 8. Investment Tab Phase 3 — Action Generator
`src/investment_engine.py` — signals + strategy → ordered action list with Kelly sizing.

### 9. Options Overlay Modeling
PUT protection, covered CALL income, collar cost, assignment → redeployment.

### 10. SEC EDGAR Fundamentals
FCF yield, debt/equity, revenue growth → fundamental quality score for look-through.

---

## Architecture Decisions (Locked — Do Not Debate)

1. GBM math identical across modes — only measurement changes
2. `api.py` injection point for simulation_mode
3. `floor_success_rate` always computed
4. Age-based for income/withdrawal; year-relative for inflation/shocks
5. All file writes via `os.replace(tmp, dst)` — SMB compatibility
6. No `window.confirm` — all confirmations inline
7. `VERSIONABLE_FILES` = all 7 config JSONs
8. Default profile schema must match Test profile schema
9. Investment tab separate from simulation mode — different time horizon
10. Cost basis introduced only at Investment Phase 3

---

## Known Technical Debt

| Item | Location | Priority |
|------|----------|----------|
| Income pipeline (3 XFAILs) | G4, roth_conversion_core.py | Session 25 #1 |
| Pure investment return | simulator_new.py | Session 25 #4 |
| Playwright T24–T25 | smoke.spec.ts | Session 25 #3 |
| manifest.lock | promote_model.py | Near-term |
| SCHP holdings | market_data | Low (acceptable proxy) |
| git tracking phantom +1 | local only | Cosmetic — resolves on next push |

---

## Files to Provide at Session Start
1. `DEVELOPER_GUIDE.md` ← **always read first**
2. `SESSION_STATE_v4_0.md`
3. `NEXT_SESSION_v4_0.md` (this file)
4. `src/ui/src/App.tsx`
5. `src/api.py`
6. `src/loaders.py`
7. `src/test_flags.py`
8. `src/ui/tests/smoke.spec.ts`
9. `src/roth_conversion_core.py` ← needed for #1
10. `src/simulator_new.py` ← needed for #1

*Version 4.0 | March 21, 2026 | Sessions 1–24b complete | Session 25 ready*
