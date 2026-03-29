# eNDinomics Session State v6.2
**Date:** 2026-03-27  
**Repo:** https://github.com/nandi-github/c-eNDinomics  
**Working dir:** `/Users/satish/ws/c-eNDinomics/src/`  
**Last commit:** `f777723` — feat: income sources + spending plan guided editor

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
| simulator_new.py | 435ccfc3ae3dd627 |
| snapshot.py | 7a68ea20b50e7a86 |
| reporting.py | ea328a157ffc6b24 |
| roth_optimizer.py | c98f14dbe9019ee3 |
| roth_conversion_core.py | d10d4233837528e4 |
| withdrawals_core.py | 4929111e619830f1 |
| portfolio_analysis.py | ca785d2f87c5bc54 |
| rmd_core.py | e1ab2e4eb5e16350 |
| test_flags.py | d101895c8d9c3834 |
| assets_loader.py | a6b4dc5cb4d3ed17 |
| engines_assets.py | 6e230b012a752cf2 |
| simulation_core.py | b8595b67f765701f |
| taxes_core.py | ef276bce9b4992b7 |
| rebuild_manifest.py | bf735102872dadf2 |
| ui/src/App.tsx | 54f957bb854bcbab |
| ui/tests/smoke.spec.ts | 5b60ce9e966014ec |
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
| profiles/default/inflation_yearly.json | **UPDATE after set_default_inflation.py** |
| profiles/default/shocks_yearly.json | e3b5debb99887328 |
| profiles/default/economic.json | fd2a6cc8cfd04e1a |

**NOTE:** `profiles/default/inflation_yearly.json` hash will change after running `set_default_inflation.py`. Upload `src/manifest.lock` at next session start.

**CRITICAL manifest rules:**
- Always load from uploaded `src/manifest.lock` before any update
- Update only changed file entries — count must stay at 34
- Assert count == 34 before saving

---

## What Was Done This Session

### Manifest System Fixed (major)
- `api.py` — `MANIFEST_FILES` now reads from `manifest.lock` at startup (was hardcoded 8 files)
- Server startup log now shows all 34 tracked files
- `check_updates()` — fails fast with clear message if server tracks <30 files
- `rebuild_manifest.py` — utility for verifying disk vs Claude hashes (do NOT use `--write` on files Claude didn't provide)
- `DEVELOPER_GUIDE.md` — manifest system fully documented

### Guided Editor — Income Sources (complete)
- `dollar_type` column added to all income type tables (Current $ / Future $) with Tip ⓘ
- Outside-portfolio context clarified in all type descriptions
- `dollar_type="future"` deflation **actually wired** in both `api.py` and `test_flags.py`
  - `loaders.py` computes `_is_future` arrays — `api.py` applies cumulative deflator before simulator
  - `_income_arrays()` in test harness applies same logic
- group28: 10/10 ✅ — current vs future dollar handling

### Guided Editor — Spending Plan (complete)
- **Apply & Sort by Age** button — validates min≤target, sorts rows by age start
- `localRows`/`localFloor` state for staged editing before committing to draft
- Sort on save as final safety net
- group29: 6/6 ✅ — floor, sort, gap, spike, income offset

### Inflation — default_rate_pct (in progress)
- `loaders.py` — reads `default_rate_pct` from JSON before falling back to hardcoded 3.5%
- `App.tsx` — Inflation editor shows Default Rate at top (was hidden in loaders.py)
- `set_default_inflation.py` — interactive script to set default per profile
- **NOT YET COMMITTED** — needs `set_default_inflation.py` to be run, then commit

### Test Suite
- 29 groups, 630 checks, 95 Playwright tests
- group27: IRA contribution rules (13/13)
- group28: income dollar_type (10/10)
- group29: spending plan logic (6/6)

---

## Guided Editor Walkthrough Status

| Section | Status | Notes |
|---------|--------|-------|
| ✅ Personal Profile | Done + tested | 35 Playwright tests |
| ✅ Income Sources | Done + tested | dollar_type, outside-portfolio clarity |
| ✅ Spending Plan | Done + tested | Apply/Sort, floor, validation |
| 🔲 Asset Allocation | **Next** | Most complex — see design below |
| 🔲 Withdrawal Strategy | Pending | economic.json — sequence reorder done |
| 🔲 Inflation | 90% done | default_rate_pct — needs set_default_inflation.py run + commit |
| ⏸ Shocks & Windfalls | Deferred | JSON-only for now (user decision) |

---

## Asset Allocation — Design (ready to build)

**JSON structure** (`allocation_yearly.json`):
```
accounts[]              → name, type (taxable/traditional_ira/roth_ira)
starting{}              → balance per account
deposits_yearly[]       → {years, acct1, acct2, ...} rows
global_allocation{}     → per account:
  portfolios{}          → GROWTH, FOUNDATIONAL (etc.)
    weight_pct          → % of account in this bucket (must sum to 100)
    classes_pct{}       → US_STOCKS, INTL_STOCKS, GOLD, COMMOD,
                          LONG_TREAS, INT_TREAS, TIPS, CASH (sum to 100)
    holdings_pct{}      → per class: [{ticker, pct}] (sum to 100, display only)
overrides[]             → {years, mode, acct: {portfolios: ...}}
```

**UI design (account-centric):**
- Each account = collapsible card (color-coded by type)
- Inside card: balance input | Delete account button
- Portfolio buckets: weight % + class % inputs
- Each class: % input + expandable ticker list (add/remove)
- "Add account" button (name + type selector)
- Deposit table: unchanged
- Overrides: separate collapsible section at bottom

**Available asset classes:** US_STOCKS, INTL_STOCKS, GOLD, COMMOD, LONG_TREAS, INT_TREAS, TIPS, CASH

---

## D-Series Display Fixes (deferred)

| # | Item |
|---|------|
| D1 | W2/SS column shows wrong amount in year-by-year schedule |
| D2 | Total Spendable formula wrong |
| D3 | BETR vs 32% bracket explanation missing |
| D4 | Current marginal rate wrong for $450K W2 |
| D5 | SS start age not gating income in simulator |

---

## Architecture / Features (deferred)

| # | Item |
|---|------|
| A1 | SS start age recommendation in Roth optimizer |
| A2 | State residency advisory |
| A3 | IRMAA as real cash outflow |
| A4 | Cost basis in allocation.json (Phase 3) |
| A5 | income_offset_tax_rate per-source accuracy (Phase 2) |

---

## Key Files Not in Manifest (provided this session, not tracked)

- `set_default_inflation.py` — run from repo root, interactive per-profile
- `DEVELOPER_GUIDE.md` — committed to repo root (not src/)

---

## Session Start Checklist for Next Session

1. Upload `src/manifest.lock` (hash changed after set_default_inflation.py)
2. Upload `src/api.py` (hash `57b67405bc931b2e` — different from outputs copy)
3. Run `python3 rebuild_manifest.py` to verify disk matches
4. Start with Asset Allocation guided editor
