# eNDinomics — Next Session Build Plan v5.0
## March 22, 2026 | Session 26+

---

## Context for New Chat
- Repo: https://github.com/nandi-github/c-eNDinomics
- **Read DEVELOPER_GUIDE.md first** — Claude startup checklist + all conventions
- All tests green: 503/503 Python + 23/23 Playwright
- Last commit: session 25 — real return deflator fix, core inflation, income pipeline
- See SESSION_STATE_v5_0.md for complete current state

---

## IMMEDIATE (Session 26 — do in order)

### 1. G13 — Add real vs nominal YoY assertion
**File:** `src/test_flags.py`

Now that the deflator is fixed, add a G13 check:
```python
# inv_real_yoy < inv_nom_yoy in every year (inflation > 0)
# gap should match inflation rate: ~2-3% for Test profile
```
This guards against regression of the session 25 deflator fix.

---

### 2. Playwright Tests T24–T25
**File:** `src/ui/tests/smoke.spec.ts`

Add tests for features from session 24b:
- T24: Withdrawals table shows investment mode note (ℹ️ badge)
- T25: Help panel contains simulation modes table

---

### 3. Pure Investment Return Metric
**Files:** `src/simulator_new.py`, `src/snapshot.py`

Current "Investment YoY" includes RMD reinvestment which inflates CAGR.
Add: "Pure Asset Return" = portfolio return excluding ALL cash flows.
- Strip RMD reinvestment, deposits, withdrawals from return calculation
- G13 addition: verify pure return ≤ Investment YoY (RMDs inflate it)

---

### 4. File Integrity Tier 2 — `--checkupdates --full`
**File:** `src/test_flags.py`

Walk all `.py/.ts/.tsx` in `src/`, hash everything.
Show unexpected additions/deletions vs known file set.
Catches orphaned files and accidental edits to non-session files.

---

## NEAR-TERM (Sessions 26–28)

### 5. Investment Tab Phase 2 — Signal Computation
**New file:** `market_data/signal_computation.py`

Reads market_data cache, computes per ticker:
- CMF (21-day Chaikin Money Flow)
- Wyckoff phase detection
- OBV divergence
- Bayesian regime posterior

Outputs: `market_signals.json` — auto-populated by `refresh_model.sh`

### 6. File Integrity Tier 3 — `--checkmodel`
`manifest.lock` committed to git (SHA256 of assets.json, rmd.json,
cape_config.json, economicglobal.json). `promote_model.py` writes lock.

---

## Known Technical Debt

| Item | Location | Priority |
|------|----------|----------|
| G13 real < nominal assertion | test_flags.py | Session 26 #1 — ✅ done |
| Playwright T24–T25 | smoke.spec.ts | Session 26 #2 — ✅ done |
| Pure investment return metric | simulator_new.py | Session 26 #3 — ✅ done |
| --checkupdates --full (Tier 2) | test_flags.py | ✅ done session 26 |
| manifest.lock (Tier 3) | promote_model.py | Near-term |
| SCHP holdings | market_data | Low |
| Dynamic upside withdrawal scaling | simulator_new.py, economicglobal.json | Near-term |

---

## Dynamic Upside Withdrawal Scaling (new — session 26)

When the portfolio meaningfully outperforms the expected median path, the
simulator currently does nothing — the user keeps withdrawing the planned
`amount_k` even when they could afford more.

**What exists today (downside only):**
- `shock_scaling_enabled` + `min_scaling_factor: 0.65` — scales withdrawals
  down linearly as portfolio drawdown worsens, flooring at `base_k`
- `makeup_enabled` + `makeup_ratio: 0.3` — recovers 30% of missed withdrawals
  in subsequent good years (reactive catch-up, not proactive upside)

**What is missing (upside):**
> When portfolio is significantly ahead of the expected median path (e.g. >15%
> above baseline), raise the effective withdrawal above `amount_k` up to a
> configurable ceiling.

**Proposed config in `economicglobal.json`:**
```json
"upside_scaling": {
  "enabled": false,
  "outperformance_threshold": 0.15,
  "max_upside_factor": 1.25,
  "scale_curve": "linear"
}
```

**Modes:** `automatic` and `retirement` only. `investment-first` already
maximizes capital — raising withdrawals defeats the purpose.

**Note:** This is proactive upside, not makeup. The two are additive —
makeup recovers past shortfalls; upside scaling raises the bar when ahead.

---

## Important: File Deployment
**Always use git show to restore files — not Finder/Downloads:**
```bash
git show origin/main:src/<file> > src/<file>
```
macOS iCloud interferes with file copies from Downloads folder.

---

## Files to Provide at Session Start
1. `DEVELOPER_GUIDE.md` ← always read first
2. `SESSION_STATE_v5_0.md`
3. `NEXT_SESSION_v5_0.md` (this file)
4. `src/simulator_new.py`
5. `src/test_flags.py`
6. `src/ui/tests/smoke.spec.ts`
7. `src/ui/src/App.tsx`
8. `src/loaders.py`

*Version 5.0 | March 22, 2026 | Sessions 1–25 complete | Session 26 ready*
