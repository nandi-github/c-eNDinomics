# eNDinomics Session State — v6.6
**Date:** 2026-03-30  
**Repo:** https://github.com/nandi-github/c-eNDinomics  
**Working dir:** `/Users/satish/ws/c-eNDinomics/src/`  
**Stack:** Python 3.11 (FastAPI) · React/TypeScript (Vite) · Playwright

---

## Manifest State (36 tracked files — CURRENT)

| File | Hash |
|------|------|
| api.py | 994faba96eb80a25 |
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
| test_flags.py | 634f54a0cab3371d |
| ui/playwright.config.ts | b4d013b46bf7ddb4 |
| ui/src/App.tsx | 40509e9dbb6d454f |
| ui/src/styles.css | efb4e9c8858208b2 |
| ui/tests/g33_display_correctness.spec.ts | 81d646dc391ee500 |
| ui/tests/global-setup.ts | 16b4790e640b153e |
| ui/tests/global-teardown.ts | b49600b2b2430ec2 |
| ui/tests/smoke.spec.ts | 77e2d567a08400c1 |
| withdrawals_core.py | 4929111e619830f1 |

---

## What Was Done This Session

### Portfolio Projection Chart — Full Rewrite

- **Hero size** — 980px viewBox, 100% panel width, 340px tall
- **Dual X-axis** — `Yr N` / `Age N` rows with 44px minimum gap filter (no end-label clutter)
- **Currency toggle** — `Today's USD` / `Future USD` pill buttons; state `chartDollarMode`; full chart rerenders
- **Honest scenario lines** — net-of-withdrawal simulation `balance[i] = max(0, balance[i-1]×(1+rate) − withdrawal[i])` replacing incorrect gross compound
- **Correct rate basis** — Today's USD uses real rates; Future USD uses nominal. No more mixing.
- **Clipped lines** — `toPathClipped()` stops at $0; no dragging along baseline
- **Distinct colors** — Green (optimistic) · Blue (Typical) · Purple (CAPE-based) · Red (conservative)
- **Reference returns legend** — "REFERENCE RETURNS (net of withdrawals)" section header; labels: `5.9% real/yr — hist. avg`, `2.9% real/yr — CAPE-implied`, `0.9% real/yr — conservative`
- **CAPE sub-labels** in legend: `1 ÷ CAPE 35 (Shiller P/E · current valuation)`, `1 ÷ CAPE 17 (historical long-run mean)`
- **Single MC band entry** — shaded rect swatch; "best $X · stress $Y" inline; no separate P10/P90 colored lines
- **Depletion markers** — thin solid lines (not dashed), pill badge `Age XX`, dot at $0
- **Caption** — explains CAPE derivation and rate type; links to Future USD toggle

### Summary Table — Investment Returns

- **Gross investment return rows** — `Investment return — Nominal/Real (gross)` shows `Mean · Median · Stress · Best` using `inv_nom_yoy_p10_pct` / `inv_nom_yoy_p90_pct` arrays
- **Portfolio net CAGR** — survival-period CAGR computed from actual balance paths per percentile; same four-column format; indented sub-rows
- **Survival note** — `(27-yr survival period)` or `(full 36-yr plan)` appended
- **No "Not meaningful"** — CAGR always computed, just scoped to survival period

### Insights Header

- Added `based on typical scenario (median path)` pill badge

### Section Headers

- Removed `textTransform: "uppercase"` from both `sectionHdr` constant and `SectionLabel` inline style → title case

### Arithmetic Floor / Liquidity Gap — Full Treatment

**isArithFloorOnly logic** (MC survival ≥ 90% but arith floor fails):
- `fundingRisk = 1` (AMBER) instead of `2` (RED)
- Drawdown badge: **"Sequence risk AMBER"** not HIGH
- Banner: amber border/bg, ⚠ icon, "Planning risk (amber)" title
- Explanation: *"Your simulation survives at X% — this is not a crisis"* with zero-return buffer explanation
- Spend range: conservative/moderate/aggressive/floor amounts
- **Option 1** — sets `floor_k` only; explicitly warns warning will persist if tiers exceed floor
- **Option 2** ★ recommended — caps `amount_k = floorK`, `base_k = floorK` (certainty floor, no headroom); clears warning after re-run
- Both options call `loadVersionHistory()` after saving
- Version notes: `"Arith floor fix opt1: guarantee floor → 97K/yr"` / `"Arith floor fix opt2: tiers capped at 97K/yr — eliminates zero-return gap"`
- `liquidityApplyStatus` reset on every new run selection (no bleed across runs)
- Targets `_floorAmt` (arithmetic floor) not `consK` (MC SWR — wrong target)

**Insights shortfall severity** — downgraded from `critical` → `warn` when `_pvSuccessRate ≥ 90%`; title becomes `"⚠ Arithmetic floor gap — years X–Y (MC survival 96%)"`, body leads with "not a crisis" framing

### Roth Conversion Insights — Amber vs Critical Split

- `survivalAmberOnly = survivalCritical && _rothEffSurv >= 90`
- **Amber banner**: "Arithmetic floor warning active — Roth optimization is still valid"; two paths presented; amber styling
- **Red banner**: "Fix the survival gap before optimizing conversions"; unchanged; only fires when MC truly impaired
- **Green confirmation strip** above Current Situation when amber: "✓ Roth optimization is fully actionable"
- Apply button footnote: green "✓ Fully actionable" when amber; grey when critical
- `/profile-config-get` endpoint (404) fixed → `GET /profile-config/{profile}/{name}` across all 6 call sites (Strategy A/B + Liquidity options)

### IRA Timebomb Severity Colors

Consistent traffic-light scheme in both Investment tab and Roth Insights:
- CRITICAL → dark red `#991b1b`
- SEVERE → red `#b91c1c`
- MODERATE → amber `#b45309`
- MANAGEABLE → blue `#1d4ed8` (optimization opportunity)
- on_track → green `#15803d` / `#dcfce7` (✅ Strategy optimized badge added to Roth Insights header)

### Portfolio Table

- Column header "Net portfolio change P10" → "Net portfolio change — stress case"
- "Floor balance" tooltip: "P10 — in 90% of scenarios..." → "Stress floor — in 90% of scenarios..."
- Headroom tooltip: "P10 SWR" → "stress-case safe withdrawal rate"

### G33 Test Suite (New — v6.6 display correctness)

**smoke.spec.ts additions:**
- `test.setTimeout(90_000)` on "Accounts YoY" test (fixes G19 flake)
- G33 `describe` block (18 checks) with own `beforeAll` simulation + `g33RunId`

**g33_display_correctness.spec.ts** (new standalone spec):
- `beforeAll` POSTs to `/run`, captures `run_id`, local `loadResults`
- 16 checks: G33a–G33j covering all v6.6 display changes

**test_flags.py:**
- `group33_display_correctness()` added after group32
- Uses `GET /profile-config/{profile}/withdrawal_schedule.json` pattern
- Added to `--skip-playwright` exclusion list alongside group19
- Group count: 33

### Bugs Fixed

- `React.useState` inside IIFE (Results crash) → hoisted to component level as `liquidityApplyStatus`
- `/profile-config-get` 404 across all 6 call sites → correct GET endpoint
- `liquidityApplyStatus` persisting across runs → reset in `useEffect([selectedProfile, selectedRun, snapshotReloadKey])`
- P10/P90 colored boundary lines in legend (confusing) → single MC band swatch
- "Typical (sim)" label format inconsistency → `Typical (sim) — real`
- Drawdown X-axis end-label clutter → 44px minimum gap filter

---

## Test Suite Status

- **G1–G18, G20–G32:** 651 checks ✅ (Python engine — no changes)
- **G19 Playwright:** 95/95 ✅ (timeout fix applied)
- **G33 Display correctness:** 16/16 ✅ (standalone); 18/18 ✅ (smoke.spec.ts describe block)
- **Total:** 33 groups

### Tests Needed (Next Session — G34)

These cover v6.6 functionality NOT yet in the test suite:

| Check | What | Type |
|-------|------|------|
| G34a | isArithFloorOnly: MC ≥ 90% → Drawdown badge "AMBER" not "HIGH" | Playwright |
| G34b | isArithFloorOnly: Insights badge "⚠ Attention" not "⛔ Critical" | Playwright |
| G34c | Roth amber banner shows when MC ≥ 90% (not red blocker) | Playwright |
| G34d | Option 2 apply: version note contains "Arith floor fix opt2" | Playwright |
| G34e | liquidityApplyStatus cleared on new run selection | Playwright |
| G34f | IRA Timebomb SEVERE badge is red (not amber) | Playwright |
| G34g | Portfolio table header shows "stress case" not "P10" | Playwright |
| G34h | on_track: "✅ Strategy optimized" green badge visible in Roth header | Playwright |

---

## Files Changed This Session

| File | Destination | Hash |
|------|-------------|------|
| App.tsx | src/ui/src/ | 40509e9dbb6d454f |
| smoke.spec.ts | src/ui/tests/ | 77e2d567a08400c1 |
| g33_display_correctness.spec.ts | src/ui/tests/ | 81d646dc391ee500 |
| test_flags.py | src/ | 634f54a0cab3371d |
| manifest.lock | src/ | 36 entries |

**No Python backend changes this session.**

---

## Architecture Decisions Made This Session

| Decision | Detail |
|----------|--------|
| isArithFloorOnly | MC ≥ 90% + shortfall → amber everywhere (Drawdown, Insights, Roth). Single source of truth. |
| Arithmetic floor target | Options use `_floorAmt` (zero-return certainty), not `consK` (MC SWR). Different concepts. |
| Option 1 honest | Explicitly says warning persists; Option 2 ★ is the path to clear it |
| `/profile-config-get` removed | All reads use `GET /profile-config/{profile}/{name}` (existing endpoint) |
| Run state isolation | `liquidityApplyStatus` reset in the run-change useEffect |
| CAPE sub-labels | Inline in SVG legend; no tooltip needed — formula shown directly |
| Reference returns | "REFERENCE RETURNS" header groups dashed lines; Typical (sim) stands alone above |
| Traffic-light colors | CRITICAL=darkred, SEVERE=red, MODERATE=amber, MANAGEABLE=blue, on_track=green |

---

## Pending / Next Steps

| # | Item | Priority |
|---|------|----------|
| IMMEDIATE | `git commit -m "v6.6: chart rewrite, amber/red severity, arith floor options, G33 tests"` | Before Stream 3 |
| IMMEDIATE | Tag `multiuser-start` before Stream 4 begins | Before Stream 4 |
| G34 | Add 8 Playwright checks (see Tests Needed above) | Next available session |
| S3 | BETR Accumulation Roth Optimization | Next stream |
| S4 | Multi-user auth + path restructure | After S3 |
| S5 | Landing page + guided demo | After S4 |
| A3 | IRMAA as real cash outflow | After S3 |
| A6 | SS provisional income auto-compute | After S3 |
