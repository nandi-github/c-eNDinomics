# eNDinomics Session State v6.3
**Date:** 2026-03-27  
**Repo:** https://github.com/nandi-github/c-eNDinomics  
**Working dir:** `/Users/satish/ws/c-eNDinomics/src/`  
**Last commit:** (commit after this session — see below)

---

## Test Suite Status

| Layer | Result |
|-------|--------|
| Python comprehensive | **630/630 ✅** (29 groups) |
| Playwright UI | **95/95 ✅** |
| checkupdates | **34/34 files ✅** |

---

## Manifest State (34 tracked files)

| File | Hash |
|------|------|
| api.py | 57b67405bc931b2e |
| loaders.py | ce55ee62804f07a4 |
| simulator_new.py | eba4d82c38ae1c1c |
| snapshot.py | 7a68ea20b50e7a86 |
| reporting.py | ea328a157ffc6b24 |
| roth_optimizer.py | c98f14dbe9019ee3 |
| roth_conversion_core.py | d10d4233837528e4 |
| withdrawals_core.py | 4929111e619830f1 |
| portfolio_analysis.py | ca785d2f87c5bc54 |
| rmd_core.py | e1ab2e4eb5e16350 |
| test_flags.py | db2fe2020f64d70d |
| assets_loader.py | a6b4dc5cb4d3ed17 |
| engines_assets.py | 6e230b012a752cf2 |
| simulation_core.py | b8595b67f765701f |
| taxes_core.py | 479fb4808ab8044c |
| rebuild_manifest.py | bf735102872dadf2 |
| ui/src/App.tsx | fa158c95880828eb |
| ui/tests/smoke.spec.ts | f794b294e7cad51f |
| ui/tests/global-setup.ts | 16b4790e640b153e |
| ui/tests/global-teardown.ts | b49600b2b2430ec2 |
| ui/playwright.config.ts | b4d013b46bf7ddb4 |
| config/economicglobal.json | b662238c5d000e07 |
| config/system_shocks.json | b63171ada432cb05 |
| config/rmd.json | fca500e7fb73d88c |
| config/taxes_states_mfj_single.json | 70bbc74e8ee69721 |
| config/cape_config.json | 8f3929fb14a10ac1 |
| config/assets.json | 5048b5214a431069 |
| profiles/default/person.json | 126a3a7c71518888 |
| profiles/default/withdrawal_schedule.json | 5444a7a6b5e8e4cb |
| profiles/default/income.json | 9bf8b50ad6bded3a |
| profiles/default/allocation_yearly.json | d9b6483b2ee4a326 |
| profiles/default/inflation_yearly.json | 7e543c03e8682953 |
| profiles/default/shocks_yearly.json | e3b5debb99887328 |
| profiles/default/economic.json | fd2a6cc8cfd04e1a |

---

## What Was Done This Session (v6.2 → v6.3)

### 1. Asset Allocation Guided Editor (Priority 1 from v6.2 — COMPLETE)
`ui/src/App.tsx` — replaced read-only stub with fully editable component.

**Accounts & Starting Balances:**
- Type dropdown (editable per row, color-coded)
- `✕ Delete` button per row (red pill, confirm dialog)
- Three typed Add buttons: `+ Add Taxable Brokerage`, `+ Add Traditional IRA`, `+ Add Roth IRA`

**Default Asset Allocation (fully editable):**
- All accounts shown expanded — no click-to-open required
- Per account: portfolio buckets with editable name, weight % input, live sum badge (green ✓ / red warning)
- Per bucket: asset class table with class selector (unused only), % input, sum badge
- **Tickers always visible** — inline pill display with `+ ticker` per class, editable ticker+%, ✕ remove. Shows `no tickers` in grey when empty
- `+ Add asset class`, `+ Add portfolio bucket` buttons
- Validation before save: bucket weights must = 100%, class % must = 100%

**Annual Contributions:** gains row-delete button, IRA-only note added

**Override periods:** read-only summary (edit in EDIT tab)

### 2. Taxes by Type — Full Picture (Results tab)
`ui/src/App.tsx` — replaced 9-column table with 10-column version.

- **Tax composition summary cards** — 30-year totals per type with mini bars
- **IRMAA column** (col 7) — estimated from `total_ordinary_income_median_path` vs 2025 IRMAA tiers, orange, shows "std" when Medicare-age but below surcharge tier, dash under 65
- **Additional Medicare Tax footnote** — 0.9% on W2 > $250K MFJ included in Federal column
- Footer notes: IRMAA 2-year lookback caveat, standard Part B premium note
- Eff. rate column index updated: 8 → 9 (shifted right by IRMAA insertion)

### 3. Tax Engine — Medicare Split
`taxes_core.py` — `compute_annual_taxes` now returns **5-tuple**: `(fed_brackets, state, niit, excise, medicare)`.
- Additional Medicare Tax 0.9% returned separately (callers sum fed+medicare for total federal)
- `compute_annual_taxes_paths` also returns 5 arrays

`simulator_new.py` line 583 — unpacks 5 values, folds `_medicare_y` into `taxes_fed_cur_paths`

### 4. Test Suite Updates
`test_flags.py` — G11: all 9 calls to `compute_annual_taxes` / `compute_annual_taxes_paths` updated to 5-tuple. Named results computed as `_fb + _m` to match simulator behavior.

`smoke.spec.ts` — `COLS.taxes` 9→10, test name updated, eff rate column index 8→9.

---

## Tax Coverage Status

| Tax | Engine | UI Display |
|-----|--------|-----------|
| Federal ordinary income brackets | ✅ | ✅ in Federal col |
| LTCG / Qualified dividends | ✅ | ✅ in Federal col |
| State income tax | ✅ | ✅ State col |
| State CG excise (WA etc.) | ✅ | ✅ Excise col |
| NIIT 3.8% | ✅ | ✅ NIIT col |
| Additional Medicare Tax 0.9% (W2) | ✅ wired | ✅ footnote in Federal col |
| IRMAA (Medicare premium surcharge) | ⚠️ display only | ✅ IRMAA col (estimated) |
| SS provisional income (0–85% taxable) | ❌ user manual | ❌ no auto-compute |
| SE tax / SECA | ❌ not wired | ❌ |

---

## Guided Editor Walkthrough Status

| Section | Status | Notes |
|---------|--------|-------|
| ✅ Personal Profile | Done + tested | 35 Playwright tests |
| ✅ Income Sources | Done + tested | dollar_type, outside-portfolio clarity |
| ✅ Spending Plan | Done + tested | Apply/Sort, floor, validation |
| ✅ Asset Allocation | Done + tested | Full editor: accounts, buckets, classes, tickers |
| ✅ Withdrawal Strategy | Done + tested | Sequence reorder, TIRA age gate, Roth last resort |
| ✅ Inflation | Done + tested | default_rate_pct, period overrides |
| ⏸ Shocks & Windfalls | JSON-only | User decision to keep JSON-only |

**All 7 guided editors are complete.**

---

## D-Series Display Fixes (still deferred)

| # | Item |
|---|------|
| D1 | W2/SS column shows wrong amount in year-by-year schedule |
| D2 | Total Spendable formula wrong |
| D3 | BETR vs 32% bracket explanation missing |
| D4 | Current marginal rate wrong for $450K W2 |
| D5 | SS start age not gating income in simulator |

---

## Architecture / Features (deferred)

| # | Item | Notes |
|---|------|-------|
| A1 | SS start age recommendation in Roth optimizer | |
| A2 | State residency advisory | |
| A3 | IRMAA as real cash outflow | Engine + deduction from portfolio |
| A4 | Cost basis in allocation.json | Phase 3 |
| A5 | income_offset_tax_rate per-source accuracy | Phase 2 |
| A6 | SS provisional income auto-compute (0–85%) | Next priority — see NEXT_SESSION |
| A7 | SE tax / SECA | |

---

## Session Start Checklist for Next Session

1. Upload `src/manifest.lock` (hash: see table above)
2. Upload `src/ui/src/App.tsx` — **use the output file from this session** (hash `fa158c95880828eb`), NOT the currently deployed file. The deployed file IS correct; just confirm hash matches.
3. Verify with `python3 -B test_flags.py --checkupdates`
4. Start with SS provisional income (A6) or IRMAA as real cashflow (A3)

**CRITICAL:** Always upload the Claude output `App.tsx`, not the file that was in `ui/src/` before the session. They should match after a clean deploy — use `--checkupdates` to confirm before starting.
