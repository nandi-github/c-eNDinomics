# eNDinomics NEXT SESSION — v6.1
*Handoff for session 33 · 2026-03-24*

---

## ⚠️ CRITICAL: Test Suite Architecture — Read Before Every Session

This section is permanent. Every Claude session must understand this before touching any test or profile file.

### Two completely separate test profiles

| | Python suite (G1–G18, G20–G24) | Playwright UI suite (G19) |
|--|-------------------------------|--------------------------|
| Profile | `__system__` | `Test` |
| Visible in UI? | ❌ Hidden (filtered by `list_profiles()` in api.py — any profile starting with `__` is hidden) | ✅ Visible |
| How seeded | `python3 -B test_flags.py --reset-system-profile` | Manually maintained in `profiles/Test/` |
| How reset | `--reset-system-profile` recreates it from scratch | G19 prunes old versions before each Playwright run to prevent MAX_VERSIONS |
| Key person.json values | birth_year varies by test | **birth_year: 1980, target_age: 95 → n_years = 49 rows** |
| Starting balances | Ephemeral per test run | $9.92M total (see profiles/Test/) |
| State | California, MFJ | California, MFJ |

### The n_years = 49 rows invariant (Playwright)

Playwright tests assert **exactly 49 rows** in all YoY tables:
- `target_age: 95`, `birth_year: 1980` → `current_age = 2026 - 1980 = 46` → `n_years = 95 - 46 = 49` ✓

**If any Playwright table test fails with `Received: 36` (or any number ≠ 49):**
- Someone deployed a `person.json` with the wrong `birth_year` into `profiles/Test/`
- `birth_year: 1967` → age 59 → n_years = 36 (the Experiment profile's numbers)
- **Fix:** restore `"birth_year": 1980` in `profiles/Test/person.json`, then run `--reset-manifest`
- This happened in session 31 when SS block work deployed person.json files — Test profile was accidentally overwritten with Experiment profile values

### Test profile canonical values (never change these)
```json
{
  "birth_year": 1980,
  "target_age": 95,
  "filing_status": "MFJ",
  "state": "California",
  "retirement_age": 65,
  "simulation_mode": "automatic"
}
```
n_years = 95 - (2026 - 1980) = 95 - 46 = **49 rows** ← Playwright hardcodes this

### DO NOT cross-contaminate profiles
- Never copy Experiment or default `person.json` into `profiles/Test/`
- Never copy `profiles/Test/` files into Experiment or default profiles
- When deploying session work, always list files explicitly — never glob-copy profile dirs
- After any profile JSON change: run `python3 -B test_flags.py --reset-manifest` then `--checkupdates`

### Session start checklist (always run in this order)
```bash
cd ~/ws/c-eNDinomics/src
python3 -B test_flags.py --checkupdates          # verify all hashes match
python3 -B test_flags.py --comprehensive-test     # confirm 534/534 Python
cd ui && npx playwright test                       # confirm 23/23 Playwright
```
If Playwright shows row count failures → check `profiles/Test/person.json` birth_year first.

---

## Session 32 Completed Work

### Tax Landscape Reference Tool
Created `tax_landscape.html` — interactive calculator covering all tax types:
- Three scenarios: Working years, Retirement gap, RMD era
- Federal income tax (progressive brackets + LTCG)
- State CA income tax
- NIIT 3.8%
- SS provisional income (proper iterative method vs flat 85%)
- FICA / payroll taxes (informational — not in simulator)
- IRMAA Medicare surcharges (not yet in simulator)
- Additional Medicare Tax 0.9% on wages >$250K MFJ (not yet in simulator)

### Tax Gap Analysis — Modeled vs Missing

| Tax | Status | Priority |
|-----|--------|----------|
| Federal income (ordinary + LTCG) | ✅ In `taxes_core.py` | — |
| State CA (progressive, CG as ordinary) | ✅ In `taxes_core.py` | — |
| NIIT 3.8% | ✅ In `taxes_core.py` | — |
| SS taxable inclusion (flat 85%) | ⚠️ Partial — hardcoded | P1 |
| SS provisional income (proper method) | ❌ Not built | P1 |
| Additional Medicare Tax (0.9% on wages >$250K) | ❌ Missing | P2 |
| IRMAA Medicare surcharges | ❌ Not in simulator | P3 |
| Medicare Part B/D baseline premium | ❌ Not in simulator | P3 |
| FICA payroll taxes | ℹ️ Informational only (W2 entered gross) | P4 |

### Planned Tax Work (Priority Order)

**P1 — SS Provisional Income** (`api.py`)
Replace flat 85% with proper iterative provisional income computation:
```python
def _ss_taxable_fraction(provisional_income, filing):
    lo, hi = (32_000, 44_000) if filing == "MFJ" else (25_000, 34_000)
    if provisional_income < lo: return 0.0
    if provisional_income < hi:
        return min(0.5 * gross_ss, 0.5 * (provisional_income - lo)) / gross_ss
    return 0.85
```
Challenge: circular dependency (SS taxable is part of AGI which determines provisional income).
Use iterative approach (converges in 3–5 iterations) or conservative estimate.
Note: differences are small once RMDs dominate — matters most in retirement gap years (ages 66–74).

**P2 — Additional Medicare Tax** (`taxes_core.py`)
0.9% on wages (W2) above $250K MFJ threshold. This IS a federal income tax (Form 8959),
NOT FICA — belongs in `compute_annual_taxes()` alongside NIIT computation.
Impact: ~$1,800/yr on $450K W2. Currently missing from federal tax total.

**P3 — IRMAA + Medicare Premiums** (`simulator_new.py` + `taxes_core.py`)
Real cash outflow from brokerage. Two components:
1. Part B baseline: ~$2,100/yr per person ($4,200/yr couple) even at lowest tier
2. IRMAA surcharges: $0–$10K+ per year depending on MAGI tier (uses MAGI from 2 years prior)

IRMAA 2024 tiers (MFJ, annual per couple):
- ≤$206K: $4,194/yr (base only)
- $206K–$258K: $5,873/yr
- $258K–$322K: $8,093/yr
- $322K–$386K: $10,313/yr
- $386K–$750K: $12,466/yr
- >$750K: $13,414/yr

Implementation approach:
- Add `irmaa_annual` field to `taxes_core.compute_annual_taxes()` return
- Debit from brokerage in `simulator_new.py` alongside existing tax debits
- Show in Tax table as new column "Medicare/IRMAA"
- `person.json` `irmaa_guard.enabled` already exists as policy hook

**P4 — Tax Table UI** (`App.tsx`)
Add Medicare/IRMAA column to 9-col tax table → 10 cols.
Update `smoke.spec.ts` index assertions accordingly.

---

## Priority 1 Fix Needed Before Session 33 Work

### Playwright Test Fix — profiles/Test/person.json
The Test profile `person.json` was accidentally overwritten with `birth_year: 1967`
(Experiment profile values) during session 31 SS block deployment.

Fix: restore `birth_year: 1980` in `profiles/Test/person.json`:
```bash
# After fixing person.json:
python3 -B test_flags.py --reset-manifest
python3 -B test_flags.py --checkupdates
cd ui && npx playwright test  # should show 23/23
```

---

## Current State (end of session 32)

### Test State
```
Python:     533/534 ✅  (G19 Playwright wrapper failed — root cause: Test/person.json birth_year)
Playwright: 19/23  ❌  (4 row-count failures — all same root cause, fix above)
```

### Open Bugs / Known Issues
1. **Test/person.json birth_year** — Fix first thing next session (5-minute fix)
2. **Roth badge text** — BETR gate fix deployed but verify in UI
3. **Total Take-Home column** — needs `net_spendable_median_path` from backend
4. **SS 85% inclusion** — flat 85% used. Full provisional income computation is P1 tax work
5. **IRMAA** — advisory only in optimizer. Not deducted as real simulation expense (P3 tax work)

### TODO Backlog (prioritized)

| Item | Priority |
|------|----------|
| Fix Test/person.json birth_year → 1980 | 🔴 Immediate |
| SS provisional income computation (proper iterative) | P1 |
| Additional Medicare Tax (0.9% on wages >$250K) | P2 |
| IRMAA + Medicare premiums as real cash expense | P3 |
| Tax table: add Medicare/IRMAA column (10 cols) | P4 |
| Total Take-Home column (backend net_spendable field) | Near-term |
| IRMAA as real simulation expense | P3 |
| User config CRC sidecar (.crc per profile) | Deferred |
| Investment Tab Phase 2 — signal computation | Deferred |
| SS full retirement age by birth year for phase labels | Deferred |

### Profile State (Experiment-2-OptimisedRMD)
```
birth_year: 1967 (current_age: ~59)
retirement_age: 65, target_age: 95, n_years: 36
W2: $450K ages 47-64, $160K age 65
SS: $53K ordinary_other ages 66-95 (income.json)
    + SS block in person.json ($2,500/$1,800 at 67) — api.py injects this
TRAD IRA: $5.7M starting ($3.5M + $2.2M)
roth_conversion_policy: enabled, 32% cap, avoid_niit=true
annual_conversion_k: 83 (optimizer output)
```

### Architecture Notes Carried Forward

**Tax pipeline:**
```
taxes_core.compute_annual_taxes_paths()
  → taxes_fed/state/niit/excise_cur_paths computed on ordinary_income_cur_paths
  → SNAPSHOT ordinary_income_cur_paths here (_taxable_income_snapshot)
  → effective_tax_rate_median_path = total_taxes / max(0, snapshot - std_ded)
  → stored in withdrawals dict → API response → App.tsx reads directly
```

**SS injection (api.py):**
```python
# Between load_income() and build_income_streams()
# Reads person.json social_security block
# Applies FRA adjustment (early/delayed)
# Currently applies flat 85% inclusion — TO BE REPLACED with provisional income method
# Overrides income_cfg["ordinary_other"]
```

**BETR Gate (roth_optimizer.py):**
```python
if current_marg > betr_self + 0.01:
    return "aggressive", "defer now, convert at retirement..."
else:
    return severity_map[severity]
```

**Manifest system:**
```
src/manifest.lock → 30 tracked files + _self_crc
api.py reads at startup, warns if corrupt
test_flags.py --reset-manifest recomputes CRC
```

---

*Last updated: 2026-03-24 · Session 32*
*Next: Fix Test/person.json → then SS provisional income → then Additional Medicare Tax → then IRMAA*
