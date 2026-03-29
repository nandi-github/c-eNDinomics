# eNDinomics — Next Session Brief (v6.2 → v6.3)
**Date written:** 2026-03-27  
**Last commit:** `f777723`  
**Tests:** 630/630 Python ✅ · 95/95 Playwright ✅ · 34/34 files ✅

---

## START OF SESSION CHECKLIST

```bash
# 1. Verify manifest has 34 entries (inflation hash changed)
python3 -c "import json; d=json.load(open('src/manifest.lock')); print(len(d['hashes']), 'entries')"

# 2. Run set_default_inflation.py if not done last session
python3 set_default_inflation.py

# 3. Start server and verify all 34 files
./vcleanbld_ui
python3 -B src/test_flags.py --checkupdates
```

**Upload at session start:**
- `src/manifest.lock` — hash changed after set_default_inflation.py
- `src/api.py` — disk hash `57b67405bc931b2e` (differs from Claude outputs copy `e1435ac762111d06`)

---

## PRIORITY 1 — Asset Allocation Guided Editor (App.tsx)

**This is the most complex editor. Build it account-centric.**

### Current state
The existing `AllocationGuidedEditor` (line ~1008 in App.tsx) has:
- ✅ Starting balances table (editable)
- ✅ Annual contributions table (editable)  
- ❌ Allocation section is **read-only** with "use EDIT tab" message
- ❌ No add/delete accounts
- ❌ No portfolio bucket editing
- ❌ No asset class % editing
- ❌ No ticker/holdings editing
- ❌ No override period editing

### JSON structure to support fully
```
accounts[]              → name, type
starting{}              → balance per account
deposits_yearly[]       → {years, acct1, acct2, ...}
global_allocation{}     → per account:
  portfolios{}          → GROWTH, FOUNDATIONAL
    weight_pct          → % of account (sum to 100 across buckets)
    classes_pct{}       → asset class weights (sum to 100)
    holdings_pct{}      → [{ticker, pct}] per class (sum to 100, display only)
overrides[]             → {years, mode, acct: {portfolios: ...}}
```

### UI design
**Per account card** (collapsible, color-coded by type):
- Account name (editable) | Type selector | Delete button
- Starting Balance input
- Portfolio buckets (GROWTH / FOUNDATIONAL / any named bucket):
  - Bucket name | weight % input | delete bucket button
  - Asset classes within bucket:
    - Class name selector (US_STOCKS, INTL_STOCKS, GOLD, COMMOD, LONG_TREAS, INT_TREAS, TIPS, CASH)
    - Class % input
    - Expandable ticker list: ticker input + % input + delete row
    - Add ticker button
  - Add class button
  - Bucket weight sum validator (must = 100)
  - Class % sum validator per bucket (must = 100)
- Add portfolio bucket button

**Sections:**
1. Accounts & Starting Balances (has add account button)
2. Annual Contributions (unchanged from current)
3. Default Allocation — account cards as above
4. Overrides — collapsible section, each override shows year range + mode + which accounts differ

**Annual Contributions clarification note** (add to description):
> "Use for tax-advantaged accounts (IRA, Roth) only. Brokerage surplus from W2/rental/SS income above spending target is auto-routed via excess_income_policy in economic.json — do NOT enter brokerage deposits here."

### Available asset classes
`US_STOCKS`, `INTL_STOCKS`, `GOLD`, `COMMOD`, `LONG_TREAS`, `INT_TREAS`, `TIPS`, `CASH`

### Account type colors (already defined in App.tsx)
```
taxable:         #1d4ed8  (blue)
traditional_ira: #b45309  (amber)
roth_ira:        #15803d  (green)
```

---

## PRIORITY 2 — Inflation Editor Commit

The `loaders.py` and `App.tsx` inflation changes were built but **not committed** last session pending `set_default_inflation.py` being run.

After running the script:
```bash
git add src/loaders.py \
        src/ui/src/App.tsx \
        src/profiles/default/inflation_yearly.json \
        src/manifest.lock

git commit -m "feat: inflation default_rate_pct — visible and editable in guided UI"
git push origin main
```

---

## PRIORITY 3 — Withdrawal Strategy (economic.json) Review

The `EconomicGuidedEditor` already exists and covers withdrawal sequence reordering. Verify it's complete:
- [ ] Order good market / bad market / bad market + conversion — drag reorder ✅
- [ ] excess_income_policy (brokerage surplus routing) — needs verification
- [ ] Any missing fields?

---

## TEST SUITE STATE

| Group | Checks | What it covers |
|-------|--------|----------------|
| G1–G18 | 503 | Flags, RMDs, conversions, tax, allocation, shocks, YoY |
| G19 | 3 | Playwright gate |
| G20–G27 | 168 | Portfolio analysis, asset weights, Roth optimizer, SS, excess income, IRA rules |
| G28 | 10 | Income dollar_type (current vs future $) |
| G29 | 6 | Spending plan: sort, floor, min/target gap, income offset |

**After Asset Allocation editor:** add group30 covering:
- Balance totals correct after account add/delete
- Allocation weight sums validated (Growth + Foundational = 100)
- Class % sums validated per bucket
- Override period applied correctly vs global

---

## MANIFEST PROTOCOL (repeat every session)

**Claude must follow this every time a file is edited:**

1. Load manifest from **uploaded** `src/manifest.lock` (never from outputs)
2. Verify hash of file being edited matches manifest entry before touching it
3. Edit the file
4. Compute new hash of edited file
5. Update **only that entry** in manifest
6. Assert `len(hashes) == 34` before saving
7. Present both the changed file and updated manifest.lock

---

## DEFERRED ITEMS

### D-series display fixes
| # | Item |
|---|------|
| D1 | W2/SS column wrong in year-by-year schedule |
| D2 | Total Spendable formula wrong |
| D3 | BETR vs 32% bracket explanation missing |
| D4 | Marginal rate wrong for $450K W2 |
| D5 | SS start age not gating income |

### Architecture
| # | Item |
|---|------|
| A1 | SS start age recommendation in Roth optimizer |
| A2 | State residency advisory |
| A3 | IRMAA as real cash outflow |
| A4 | Cost basis in allocation.json |
| A5 | income_offset_tax_rate per-source accuracy |

### Shocks & Windfalls
Deferred to JSON-only — users who need it edit directly. No guided editor planned.

---

## FILES CHANGED THIS SESSION (for git reference)

| File | Change |
|------|--------|
| `src/api.py` | MANIFEST_FILES from manifest.lock; dollar_type deflation; manifest integrity check |
| `src/loaders.py` | default_rate_pct in load_inflation_yearly |
| `src/test_flags.py` | _income_arrays deflation; group28/29; check_updates manifest count guard |
| `src/ui/src/App.tsx` | Income Sources dollar_type column; Spending Plan Apply/Sort; Inflation default rate UI |
| `src/ui/tests/smoke.spec.ts` | 5 Spending Plan Playwright tests |
| `src/manifest.lock` | 34 entries (was 8) |
| `DEVELOPER_GUIDE.md` | Manifest system documented; deploy workflow updated |
| `set_default_inflation.py` | New utility — run from repo root |
