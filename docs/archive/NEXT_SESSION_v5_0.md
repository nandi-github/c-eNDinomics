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

## IMMEDIATE (Session 27 — do in order)

### 0. Bad Market Response — Wire Everything (HIGHEST PRIORITY)
**Files:** `src/api.py`, `src/simulator_new.py`

**Background:** `economicglobal.json` defines a complete bad market response
system. NONE of it is wired. Every setting is config-only dead code:

| Config field | Purpose | Status |
|---|---|---|
| `order_bad_market` | Switch withdrawal sequence in bad markets | ❌ built but never assigned (api.py line 1416) |
| `shock_scaling_enabled` | Scale withdrawal amounts down in bad markets | ❌ never read |
| `min_scaling_factor: 0.65` | Floor at 65% of target in bad markets | ❌ never applied |
| `scale_curve: linear` | Gradient from full→floor as drawdown worsens | ❌ never applied |
| `makeup_enabled` | Recover missed withdrawals in good years | ❌ never applied |
| `makeup_ratio: 0.3` | Recover 30% of deficit per good year | ❌ never applied |

**What actually happens today:**
```
Market crashes → portfolio drops correctly (shocks ARE wired for returns)
             → person keeps spending FULL amount regardless
             → withdrawal sequence stays on order_GOOD_market always
             → no makeup in recovery years
```

**What should happen:**
```
Year y: total_nom_paths[:, y] drops > drawdown_threshold from peak
     OR cross-sectional P10 return[y] < p10_threshold (-2%)
         ↓
bad_market_flag[path, y] = True
         ↓
1. Switch withdrawal sequence → seq_bad_per_year
2. Scale withdrawal amount:
   scale = 1.0 - (drawdown / max_drawdown) × (1 - min_scaling_factor)
   scale = clip(scale, min_scaling_factor, 1.0)
   effective_amount = max(base_k, scale × amount_k)
         ↓
Recovery year (bad_market_flag = False, prev year had deficit):
   makeup = min(deficit_cur × makeup_ratio, amount_k × makeup_cap_per_year)
   effective_amount = amount_k + makeup
```

**Implementation plan:**

**Step 1 — `simulator_new.py` (STEP 3 withdrawal loop):**
```python
# Before withdrawal loop — compute cross-sectional P10 return per year
# (uses pre-cashflow core paths already computed)
p10_return_by_year = np.nanpercentile(
    inv_nom_yoy_paths_core_shifted, 10, axis=0
)  # shape (n_years,) — one number per year, shared across all paths

# Compute running peak per path (for drawdown detection)
running_peak = np.maximum.accumulate(total_nom_paths_core, axis=1)

# In withdrawal loop year y:
drawdown_y = 1.0 - total_nom_paths[:, y] / np.maximum(running_peak[:, y], 1e-12)
p10_signal_y = p10_return_by_year[y] < p10_threshold  # scalar bool

bad_market_flag_y = (drawdown_y > drawdown_threshold) | p10_signal_y

# Scale amount
scale_y = np.where(
    bad_market_flag_y,
    np.clip(1.0 - drawdown_y * (1.0 - min_scaling_factor) / drawdown_threshold,
            min_scaling_factor, 1.0),
    1.0
)
effective_amount_y = np.maximum(sched_base[y] * deflator[y],
                                scale_y * extra_nom)

# Switch sequence
seq_y = seq_bad[y] if bad_market_flag_y.mean() > 0.5 else seq_good[y]
```

**Step 2 — `api.py`:**
- Line 1416: pass BOTH `seq_good_per_year` AND `seq_bad_per_year` to simulator
- Pass `econ_policy` scaling params explicitly (already passed at line 1443)

**Step 3 — makeup in recovery years:**
```python
# Track cumulative deficit per path
deficit_nom_paths = np.zeros((paths, n_years), dtype=float)
# In year y: if was bad last year, recover makeup_ratio × cumulative_deficit
```

**Step 4 — P10 threshold config:**
```json
// economicglobal.json — add to bad_market:
"p10_return_threshold_pct": -2.0,
"p10_signal_enabled": true
```

**Testing:**
- G1: bad market sequence switches in shock years
- G6: withdrawal amounts scale down in shock years, recover after
- G13: new check — with severe shock, realized withdrawals < planned in shock years
- New G23: bad market response functional test

---


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
| **Bad market withdrawal scaling** | simulator_new.py, api.py | **Session 27 #0 — HIGHEST** |
| **Bad market sequence switching** | api.py line 1416 | **Session 27 #0 — HIGHEST** |
| **Makeup in recovery years** | simulator_new.py | **Session 27 #0 — HIGHEST** |
| **P10 cross-sectional bad market signal** | simulator_new.py | **Session 27 #0 — HIGHEST** |
| G13 real < nominal assertion | test_flags.py | Session 26 #1 — ✅ done |
| Playwright T24–T25 | smoke.spec.ts | Session 26 #2 — ✅ done |
| Pure investment return metric | simulator_new.py | Session 26 #3 — ✅ done |
| --checkupdates --full (Tier 2) | test_flags.py | ✅ done session 26 |
| manifest.lock (Tier 3) | promote_model.py | Near-term |
| SCHP holdings | market_data | Low |
| Dynamic upside withdrawal scaling | simulator_new.py, economicglobal.json | After bad market |
| Safe withdrawal rate at P10 | simulator_new.py | After bad market |

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
