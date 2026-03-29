# eNDinomics — Market Data Refresh
## How and when to update the asset model

---

## What needs refreshing and why

| Data | How often | Why it matters |
|------|-----------|----------------|
| ETF holdings | Weekly | Fund managers rebalance — Apple's weight in VTI shifts as market caps move. Stale holdings = wrong look-through analysis |
| Price history | Weekly | New bars for mu/sigma calibration. Monthly is fine for the asset model |
| Sector info | Monthly | GICS classifications rarely change |

---

## The one command

From the repo root (`c-eNDinomics/`):

```bash
./refresh_model.sh
```

That's it. It runs all four steps automatically:
1. Downloads fresh ETF holdings, prices, and sectors → local cache
2. Calibrates asset model (multi-window blend of 5/10/20yr returns)
3. Validates the result (bounds check, correlation matrix, required tickers)
4. Asks you to confirm before writing to `src/config/assets.json`

Takes about 5–6 minutes. The only interaction is typing `y` at the prompt.

---

## How to know when to run it

**Option 1 — Check the health endpoint:**
```
http://localhost:8000/health
```
Returns JSON. If `market_data.is_stale` is `true`, it's time to refresh.
`market_data.last_refresh` shows when data was last fetched.

**Option 2 — Check on server startup:**
The server logs a warning at startup if cache is stale:
```
[api] market_data: 5 fresh, 3 stale entries.
[api] Run: ./refresh_model.sh  to refresh.
```

**Rule of thumb:** Run it once a week, Sunday evening before markets open Monday.

---

## What happens if you skip it

Nothing breaks. The simulator always reads from `assets.json`, which is stable until you explicitly promote a new version. Skipping a week means:
- Holdings look-through uses slightly older ETF weights (usually fine)
- mu/sigma estimates don't reflect the most recent market moves
- Simulation results remain valid — just calibrated to older data

The model won't auto-update. You are always in control.

---

## After running refresh_model.sh

1. **Restart the API server** to pick up the new `assets.json`
2. **Run a simulation** to verify results look sensible
3. **Commit** the updated model:
```bash
git add src/config/assets.json asset-model/promotion_log.json
git commit -m "chore: promote asset model vX.X.X (YYYY-MM-DD)"
git push origin main
```

---

## Flags

```bash
./refresh_model.sh                  # interactive — asks before promoting
./refresh_model.sh --dry-run        # shows cache status, fetches nothing
./refresh_model.sh --no-fetch       # skip download, re-calibrate from existing cache
./refresh_model.sh --validate-only  # check candidate model, never promote
./refresh_model.sh --yes            # skip confirmation prompt (for automation)
```

---

## Current coverage (as of v1.1.0)

| Source | Tickers | Status |
|--------|---------|--------|
| iShares direct CSV | IEF, TLT, LQD, EEM, EFA, TIP | ✅ |
| Vanguard JSON API | VTI, VXUS, BND, VTV, VUG | ✅ |
| SPDR xlsx | SPY, XLE, XLF, XLK | ✅ |
| Nasdaq screener | QQQ | ✅ (approximate weights) |
| Physical commodity | GLD, IAU, DBC, PDBC | ✅ (correct 0 equity holdings) |
| yfinance prices | All 25 tickers | ✅ 5030 bars |
| yfinance sectors | All 25 tickers | ✅ |
| SCHP | Schwab 403 blocked | ⚠ uses stale/prior |

---

*Last updated: March 2026 | See MARKET_DATA_LAYER.md for architecture details*
