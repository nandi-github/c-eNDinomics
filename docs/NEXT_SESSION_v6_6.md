# eNDinomics — Next Session Brief (v6.5 → v6.6)
**Date written:** 2026-03-29  
**Tests:** All passing ✅ · 34/34 files ✅  
**Streams 1 & 2 complete. Stream 3 next. Multi-user starts after Stream 3.**

---

## BEFORE STARTING — ONE-TIME SETUP (do this now if not done)

### Step 1: Deploy .gitignore first
```bash
cp .gitignore src/.gitignore   # from this session's outputs

# Verify protection
cd src
git check-ignore -v profiles/Experimental-Optimized/person.json
# → .gitignore:... profiles/Experimental-Optimized/person.json  ✓ ignored

git check-ignore -v profiles/default/person.json
# → (no output) = NOT ignored, system profile pushes ✓

# Commit gitignore ALONE before anything else
git add .gitignore
git commit -m "chore: add .gitignore — user profiles/reports never go to GitHub"
git push
```

### Step 2: Commit v6.5 code
```bash
git add -A
git commit -m "v6.5 — Phase inference, waterfall, shock toggle, headroom fix, field reference, sanity script"
git push
```

### Step 3: Tag the multi-user starting point (before Stream 4 begins)
```bash
# Do this right before writing any Stream 4 code — gives a clean "before" snapshot
git tag -a multiuser-start -m "Stream 4 start — multi-user auth and path restructure"
git push origin multiuser-start
```

---

## GITIGNORE RULES SUMMARY

| Path | GitHub | Why |
|------|--------|-----|
| `users/` | ❌ Never | All user accounts — real financial data |
| `profiles/*/` | ❌ Never | User profiles |
| `profiles/default/` | ✅ Yes | System reference — no personal info |
| `profiles/__system__*/` | ✅ Yes | Test fixtures |
| `profiles/__testui__/` | ✅ Yes | Playwright test account |
| `profiles/*/reports/` | ❌ Never | Simulation results — personal + large |
| `profiles/*/versions.json` | ❌ Never | Personal version history |
| `users/*/session.lock` | ❌ Never | Runtime state |
| `test_results/` | ❌ Never | Exception: `regression_baseline.json` is kept |
| `market_data/cache/` | ❌ Never | Auto-regenerated, large |
| `ui/dist/`, `ui/node_modules/` | ❌ Never | Build artifacts |
| `.env`, `secrets.json` | ❌ Never | Secrets — absolute rule |

**Simple rule: Code → GitHub. Data → local only.**

---

## START OF SESSION CHECKLIST

```bash
# 1. Verify manifest (34 entries, all match)
cd src && python3 -B test_flags.py --checkupdates

# 2. Build and start
./vcleanbld_ui

# 3. Sanity
./sanity.sh
```

**Upload at session start:**
- `src/manifest.lock`
- `src/ui/src/App.tsx` — hash `ae176175968ce770`

---

## STREAM 3 — BETR Early Accumulation Roth Optimization

### What BETR Is
**Break-Even Tax Rate** — the future effective tax rate at which a Roth conversion today is neutral. If projected future rate (RMDs + SS) exceeds BETR, convert now.

Currently only computed for the distribution/RMD window. Stream 3 extends it to the **accumulation phase** — W2 income is high but bracket gaps exist.

### The Problem
- User: $400K W2, age 46–58, in 32–35% bracket
- At 73: RMDs force $400K+/yr ordinary income at 37%
- Converting $50K/yr at 24% now vs 37% forced later = obvious win
- Current optimizer doesn't evaluate pre-retirement windows

### What Changes

**`roth_optimizer.py`**
- Extend `compute_betr_optimal_strategy()` to pre-retirement years
- Bracket gap = headroom between W2 income and next bracket ceiling
- New strategy: `betr_accumulation` — converts bracket gap each accumulation year
- Per-year output with phase label (`accumulation` / `distribution`)

**`simulator_new.py`**
- When `phase_by_year[y] == "accumulation"` AND mode != `investment`: check bracket gap, apply conversion
- Existing `window_years: ["now-75"]` respects phase

**`App.tsx` — Roth Conversion Insights**
- Accumulation-phase rows in conversion schedule table
- BETR banner: "Current marginal rate: 24% vs projected RMD rate: 37% → Convert ✓"
- Phase badge 📈 on accumulation-phase conversion rows

**`test_flags.py` — G33**
- 33a: accumulation + bracket gap → conversion fires
- 33b: accumulation + no gap (top bracket) → no conversion
- 33c: betr_accumulation lowers lifetime taxes vs baseline
- 33d: phase transition — stops at retirement, resumes in distribution window
- 33e: W2 stops mid-sim → distribution mode kicks in correctly

---

## PRIORITY 2 — SS Provisional Income (A6)

Full spec in `NEXT_SESSION_v6_3.md`. Summary:
- IRS §86: provisional income = AGI + 0.5 × gross SS
- MFJ thresholds: $32K (0%), $32–44K (50%), >$44K (85%)
- Build from `person.json` social_security block (already stored there)
- G34 test group

---

## PRIORITY 3 — IRMAA as Real Cash Outflow (A3)

Full spec in `NEXT_SESSION_v6_3.md`. Summary:
- Engine debits IRMAA from brokerage each year age 65+
- Config-driven brackets in `taxes_states_mfj_single.json`
- 2-year lookback approximated with current year income (conservative)
- G35 test group

---

## STREAM 4 — Multi-User Auth + Path Restructure

### Architecture
```
src/
  system/
    profiles/
      default/          ← read-only, shared by all users, never editable in UI
  users/
    {userid}/
      _auth.json        ← {password_hash, created_at, last_login}
      session.lock      ← {tab_id, started_at, ip, expires_at}
      profiles/
        MyRetirement/
        Conservative/
```

### Key Decisions Made
- System profiles shared read-only — no copying on registration
- New users see `system/profiles/` immediately in the dropdown (read-only badge)
- Session lock — one active session per user; override kills other tab with warning banner: *"Your session was taken over. Save your work."*
- Auth: bcrypt passwords + JWT tokens (stateless — server holds no session state)
- All `profile_dir()` calls → `resolve_profile_dir(userid, profile)` (~40 sites in `api.py`)
- Migration: existing `profiles/Experimental-Optimized/` → `users/satish/profiles/Experimental-Optimized/`
- Test harness system user bypasses auth — `__system__*` and `__testui__` stay in `system/profiles/`

### GitHub Safety
- `.gitignore` excludes `users/` entirely — no user data ever touches GitHub
- `system/profiles/` is tracked (reference data, no personal info)
- `profiles/__system__*/` and `profiles/__testui__/` tracked (test fixtures)

### Scope Estimate
| Component | Lines |
|-----------|-------|
| Auth endpoints (register/login/logout) | ~150 api.py |
| JWT middleware — inject userid into requests | ~50 api.py |
| `resolve_profile_dir(userid, profile)` + call sites | ~100 api.py |
| Session lock (acquire/check/override) | ~80 api.py |
| Frontend login screen + session banner + logout | ~200 App.tsx |
| Migration script | ~30 shell |
| Test harness system user bypass | ~20 test_flags.py |

---

## STREAM 5 — Landing Page + Guided Demo

### Approach
- Pre-login state in existing `App.tsx` — JWT absence → render landing instead of tabs
- No separate HTML file or route — conditional render

### Landing Page
```
Header: eNDinomics                              [Login] [Sign Up]

Hero: "Your retirement, modeled honestly"
Subhead: What the tool does in 2 sentences

Feature cards (6):
  Monte Carlo · Tax-aware · RMD + Roth
  Sequence risk · Phase engine · Scenario shocks

Three Models section:
  Financial Engine | Retirement Planner | Investment Assistant
  (brief description + link to GrandPlan)

CTA: [Start your plan →]  [Watch Demo]

Footer: disclaimer — not financial advice, not a registered advisor
```

### Guided Demo
- Auto-play modal overlay, advances every 4 seconds, pause/forward controls
- Fictional user: **NOT Satish** — use "Alex Chen" or "Jordan Mills" or similar
- 5 steps: Configure → Simulate → Results → Roth Insights → Investment tease
- Ends with "Build your own plan →" CTA

### GrandPlan Page
- `/grandplan` route rendered inside App.tsx — no separate file
- Summarizes all three models + roadmap + philosophy

---

## MANIFEST PROTOCOL (every session)

1. Load manifest from **uploaded** `src/manifest.lock`
2. Verify hash of file being edited matches manifest before touching
3. Edit, compute new hash, update only that entry
4. Assert `len(hashes) == 34` before saving
5. Ship changed file + updated manifest.lock together

---

## Files To Deploy for v6.5

| File | Destination |
|------|-------------|
| `.gitignore` | `src/` ← **do this first** |
| `simulator_new.py` | `src/` |
| `simulation_core.py` | `src/` |
| `loaders.py` | `src/` |
| `test_flags.py` | `src/` |
| `App.tsx` | `src/ui/src/` |
| `smoke.spec.ts` | `src/ui/tests/smoke.spec.ts` |
| `styles.css` | `src/ui/src/` |
| `shocks_yearly.json` | `src/profiles/default/` |
| `manifest.lock` | `src/` |
| `sanity.sh` | `src/` |
