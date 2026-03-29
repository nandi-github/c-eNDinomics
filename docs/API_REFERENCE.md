# eNDinomics API Reference

Base URL: `http://localhost:8000`  
Format: JSON over HTTP. All POST bodies are `application/json`.  
Auth: None (local server). Add auth layer if exposing externally.  
Interactive docs: `http://localhost:8000/docs` (FastAPI auto-generated Swagger UI)

---

## Overview

All simulation results are stored as run artifacts on disk and retrievable via API.
The full workflow for programmatic use:

```
1. POST /run              → run simulation, get run_id
2. GET  /artifact/{profile}/{run_id}/raw_snapshot_accounts.json  → full results JSON
3. POST /roth-optimize    → standalone Roth optimizer (optional)
4. GET  /reports/{profile}→ list all run IDs for a profile
```

No UI required. Every number shown in the browser is in the snapshot JSON.

---

## Endpoints

### System

#### `GET /health`
Server health and market data freshness.

```bash
curl http://localhost:8000/health
```
```json
{
  "status": "ok",
  "market_data_age_days": 2,
  "market_data_stale": false
}
```

#### `GET /manifest`
SHA256 hashes of all tracked source files — used by `--checkupdates` to verify deployments.

```bash
curl http://localhost:8000/manifest | python3 -m json.tool
```
```json
{
  "generated_at": "2026-03-21T12:54:00",
  "app_root": "/path/to/src",
  "files": {
    "api.py": { "sha256_short": "53bd860c", "exists": true, "size_bytes": 45123, "mtime": "2026-03-21T11:00:00" },
    "loaders.py": { ... },
    ...
  }
}
```

---

### Profiles

#### `GET /profiles`
List all available profiles.

```bash
curl http://localhost:8000/profiles
```
```json
{ "profiles": ["default", "Test", "Conservative", "Aggressive"] }
```

#### `POST /profiles/create`
Create a new profile, optionally cloning from another profile or a specific version.

```bash
curl -X POST http://localhost:8000/profiles/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MyProfile",
    "source": "Test",
    "clone_version": 5
  }'
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | New profile name |
| `source` | string | Source profile to clone from, or `"clean"` for empty |
| `clone_version` | int? | Version number to clone from (omit for latest) |

#### `POST /profiles/delete`
Delete a profile and all its run reports.

```bash
curl -X POST http://localhost:8000/profiles/delete \
  -d '{"profile": "MyProfile"}'
```

---

### Profile Configuration

#### `GET /profile-config/{profile}/{filename}`
Read a profile config file. Returns content + field reference (readme).

```bash
curl http://localhost:8000/profile-config/Test/person.json
```
```json
{
  "content": "{ \"birth_year\": 1980, ... }",
  "readme": { "purpose": "...", "fields": {...} }
}
```

Supported filenames: `person.json`, `withdrawal_schedule.json`, `allocation_yearly.json`,
`income.json`, `inflation_yearly.json`, `shocks_yearly.json`, `economic.json`

#### `POST /profile-config`
Save a profile config file. Auto-versions current state before writing.

```bash
curl -X POST http://localhost:8000/profile-config \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "Test",
    "name": "person.json",
    "content": "{\"birth_year\": 1980, ...}",
    "version_note": "updated retirement age",
    "version_source": "user"
  }'
```

| Field | Type | Description |
|-------|------|-------------|
| `profile` | string | Profile name (not `default`) |
| `name` | string | Config filename |
| `content` | string | JSON content as string |
| `version_note` | string? | Label for this version (auto-generated if omitted) |
| `version_source` | string? | `"user"` or `"auto"` |

#### `GET /template/{filename}`
Get the default template for a config file (same as `default` profile content).

```bash
curl http://localhost:8000/template/person.json
```

---

### Profile Versioning

#### `GET /profile/{profile}/versions`
List all saved versions, newest first.

```bash
curl http://localhost:8000/profile/Test/versions
```
```json
{
  "profile": "Test",
  "versions": [
    {
      "v": 7,
      "ts": "2026-03-21T12:27:35",
      "note": "server startup — auto-checkpoint",
      "source": "auto",
      "files_changed": ["person.json", "withdrawal_schedule.json", ...]
    },
    ...
  ]
}
```

#### `GET /profile/{profile}/versions/{v}/{filename}`
Read a specific file from a specific version snapshot.

```bash
curl http://localhost:8000/profile/Test/versions/5/person.json
```
```json
{
  "v": 5,
  "filename": "person.json",
  "content": "{ \"birth_year\": 1980, ... }"
}
```

#### `POST /profile/{profile}/restore/{v}`
Restore profile to version `v`. Auto-saves current state first (always reversible).

```bash
curl -X POST http://localhost:8000/profile/Test/restore/5 \
  -H "Content-Type: application/json" -d '{}'
```
```json
{
  "ok": true,
  "restored_to": 5,
  "auto_saved_as": 8,
  "files_restored": ["person.json", "withdrawal_schedule.json", ...]
}
```

#### `POST /profile/{profile}/snapshot`
Create a manual version checkpoint without modifying any files.

```bash
curl -X POST http://localhost:8000/profile/Test/snapshot \
  -H "Content-Type: application/json" \
  -d '{"note": "before running scenario A", "source": "user"}'
```
```json
{ "ok": true, "v": 9, "note": "before running scenario A" }
```

#### `DELETE /profile/{profile}/versions/{v}`
Delete a single version from history.

```bash
curl -X DELETE http://localhost:8000/profile/Test/versions/3
```

#### `DELETE /profile/{profile}/versions?keep=N`
Bulk delete — keep last N versions, delete older ones. `keep=0` deletes all.

```bash
# Keep last 10
curl -X DELETE "http://localhost:8000/profile/Test/versions?keep=10"

# Delete everything
curl -X DELETE "http://localhost:8000/profile/Test/versions"
```

---

### Simulation

#### `POST /run`
Run a simulation. Returns summary + stores full results as artifacts.

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "Test",
    "paths": 500,
    "steps_per_year": 2,
    "simulation_mode": "automatic",
    "state": "California",
    "filing": "MFJ"
  }'
```

**Request parameters:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `profile` | string | `"default"` | Profile to simulate |
| `paths` | int | 500 | Monte Carlo paths (200 for quick, 1000+ for production) |
| `steps_per_year` | int | 2 | GBM steps per year (2 sufficient, 12 for high accuracy) |
| `simulation_mode` | string | `"automatic"` | `automatic`, `investment`, `balanced`, `retirement` |
| `state` | string | `"California"` | State for income tax |
| `filing` | string | `"MFJ"` | `MFJ`, `single`, `MFS`, `HOH` |
| `shocks_mode` | string | `"augment"` | `augment`, `override`, `none` |
| `ignore_withdrawals` | bool | false | Skip withdrawal logic |
| `ignore_rmds` | bool | false | Skip RMD logic |
| `ignore_conversions` | bool | false | Skip Roth conversions |
| `ignore_taxes` | bool | false | Skip tax computation |
| `rebalance_threshold` | float | 0.10 | Drift threshold for rebalancing (0.10 = 10%) |

**Response:**

```json
{
  "run_id": "run_20260321_124355",
  "profile": "Test",
  "summary": {
    "success_rate": 0.0,
    "success_rate_label": "Floor survival rate",
    "floor_success_rate": 1.0,
    "composite_score": 83.7,
    "simulation_mode": "investment",
    "investment_weight": 1.0,
    "cagr_nominal_median": 0.0734,
    "cagr_nominal_mean": 0.0736,
    "cagr_nominal_p10": 0.0674,
    "cagr_nominal_p90": 0.0805,
    "cagr_real_median": 0.0500,
    "cagr_real_mean": 0.0502,
    "cagr_real_p10": 0.0441,
    "cagr_real_p90": 0.0570,
    "drawdown_p90": 0.0317,
    "ending_balance_median": 64100000
  },
  "portfolio": {
    "years": [1, 2, ..., 49],
    "future_median": [9950000, ...],
    "future_p10": [...],
    "future_p90": [...],
    "current_median": [...]
  },
  "roth_optimizer": { ... }
}
```

**Note on survival rates:**
- `success_rate` = full-plan survival (% of paths meeting `amount_k` every year)
- `floor_success_rate` = floor survival (% of paths staying above `base_k`)
- In investment/automatic mode, `floor_success_rate` is the meaningful metric
- `success_rate = 0` in investment mode is expected for healthy portfolios (see Simulation Modes)

---

### Artifacts (Full Results)

All simulation data is stored in run artifact files. The most important is `raw_snapshot_accounts.json`.

#### `GET /artifact/{profile}/{run_id}/{filename}`
Retrieve any artifact file from a completed run.

```bash
# Full results JSON
curl http://localhost:8000/artifact/Test/run_20260321_124355/raw_snapshot_accounts.json \
  | python3 -m json.tool > results.json

# List available artifacts
curl http://localhost:8000/reports/Test
```

**Key artifact files per run:**

| File | Contents |
|------|----------|
| `raw_snapshot_accounts.json` | Complete simulation results — all tables, all years, all paths |
| `run_meta.json` | Run parameters, timestamps, profile used |
| `aggregate_total_current.png` | Portfolio projection chart |
| `aggregate_brokerage_current.png` | Brokerage account chart |
| `aggregate_traditional_ira_current.png` | TRAD IRA chart |
| `aggregate_roth_ira_current.png` | Roth IRA chart |
| `rmd_current_components.png` | RMD breakdown chart |

#### `raw_snapshot_accounts.json` structure

```json
{
  "meta": {
    "profile": "Test",
    "run_id": "run_20260321_124355",
    "years": 49,
    "paths": 500,
    "simulation_mode": "investment"
  },
  "summary": { ... },           // same as /run response summary
  "portfolio": {
    "years": [1..49],
    "future_median": [...],     // total portfolio in nominal $, median path
    "future_p10": [...],        // 10th percentile
    "future_p90": [...],        // 90th percentile
    "current_median": [...]     // total portfolio in today's $, median path
  },
  "accounts": {
    "BROKERAGE-1": {
      "future_median": [...],
      "future_p10": [...],
      "future_p90": [...],
      "current_median": [...]
    },
    "TRAD_IRA-1": { ... },
    "ROTH_IRA-1": { ... },
    ...
  },
  "withdrawals": {
    "planned_median_path": [...],      // target withdrawal (amount_k), today's $
    "for_spending_median_path": [...],  // actual spending, today's $
    "diff_vs_plan_median_path": [...],  // shortfall (0 = fully met)
    "for_spending_future_median_path": [...],  // nominal $
    "rmd_median_path": [...],           // RMD amount
    "rmd_future_median_path": [...],    // RMD nominal $
    "total_withdraw_median_path": [...],
    "total_withdraw_future_median_path": [...],
    "rmd_reinvested_median_path": [...],
    "rmd_reinvested_future_median_path": [...],
    "roth_conversion_median_path": [...],
    "conversion_tax_cost_median_path": [...]
  },
  "taxes": {
    "fed_cur_median_path": [...],
    "state_cur_median_path": [...],
    "niit_cur_median_path": [...],
    "total_tax_cur_median_path": [...],
    "effective_rate_median_path": [...],
    "total_ordinary_income_median_path": [...],
    "ordinary_income_breakdown": { ... }
  },
  "ages": [47, 48, ..., 95],
  "insights": [ { "severity": "warn", "body": "...", "detail": "..." }, ... ],
  "portfolio_analysis": {
    "score": 72,
    "holdings": [...],
    "per_account": [...]
  },
  "roth_optimizer": {
    "severity": "CRITICAL",
    "recommended_strategy": "aggressive",
    "strategies": { ... },
    "year_by_year": [...]
  }
}
```

---

### Reports (Run History)

#### `GET /reports/{profile}`
List all run IDs for a profile, oldest first.

```bash
curl http://localhost:8000/reports/Test
```
```json
{ "runs": ["run_20260320_014822", "run_20260321_112812", "run_20260321_124355"] }
```

#### `GET /reports`
List runs across all profiles.

#### `DELETE /reports/{profile}` or `POST /reports/clear`
Delete all run reports for a profile.

```bash
curl -X DELETE http://localhost:8000/reports/Test
# or
curl -X POST http://localhost:8000/reports/clear -d '{"profile": "Test"}'
```

---

### Roth Optimizer (Standalone)

#### `POST /roth-optimize`
Run the Roth conversion optimizer standalone — uses snapshot balances if `run_id` provided,
otherwise uses current profile balances.

```bash
curl -X POST http://localhost:8000/roth-optimize \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "Test",
    "run_id": "run_20260321_124355"
  }'
```

Returns the full Roth optimizer result including BETR analysis, severity rating,
strategy comparison (conservative/balanced/aggressive/maximum), 4×4 savings matrix,
and year-by-year conversion schedule.

---

## Programmatic Workflow Examples

### Run simulation and extract results

```python
import requests, json

BASE = "http://localhost:8000"

# Run simulation
resp = requests.post(f"{BASE}/run", json={
    "profile": "Test",
    "paths": 500,
    "simulation_mode": "investment",
    "state": "California",
    "filing": "MFJ"
})
result = resp.json()
run_id = result["run_id"]
print(f"Run: {run_id}")
print(f"Floor survival: {result['summary']['floor_success_rate']:.1%}")
print(f"Nominal CAGR median: {result['summary']['cagr_nominal_median']:.2%}")

# Get full snapshot
snap = requests.get(f"{BASE}/artifact/Test/{run_id}/raw_snapshot_accounts.json").json()

# Extract withdrawal table
for i, (yr, planned, actual, diff) in enumerate(zip(
    snap["ages"],
    snap["withdrawals"]["planned_median_path"],
    snap["withdrawals"]["for_spending_median_path"],
    snap["withdrawals"]["diff_vs_plan_median_path"]
), 1):
    print(f"Year {i:2d} Age {yr}: planned=${planned:,.0f}  actual=${actual:,.0f}  diff={diff:+,.0f}")

# Portfolio trajectory
for i, (yr, bal) in enumerate(zip(range(1, 50), snap["portfolio"]["current_median"]), 1):
    print(f"Year {i:2d}: ${bal/1e6:.1f}M today's $")
```

### Scenario comparison (multiple runs)

```python
import requests

BASE = "http://localhost:8000"
modes = ["investment", "balanced", "retirement"]
results = {}

for mode in modes:
    r = requests.post(f"{BASE}/run", json={
        "profile": "Test", "paths": 200, "simulation_mode": mode
    }).json()
    results[mode] = {
        "floor_survival": r["summary"]["floor_success_rate"],
        "cagr_median": r["summary"]["cagr_nominal_median"],
        "composite": r["summary"]["composite_score"],
        "ending_median": r["summary"]["ending_balance_median"],
        "run_id": r["run_id"]
    }

for mode, r in results.items():
    print(f"{mode:12s}: floor={r['floor_survival']:.1%}  "
          f"CAGR={r['cagr_median']:.2%}  "
          f"score={r['composite']}  "
          f"ending=${r['ending_median']/1e6:.1f}M")
```

### Profile management

```python
import requests, json

BASE = "http://localhost:8000"

# Create a new profile from an existing one
requests.post(f"{BASE}/profiles/create", json={"name": "Aggressive", "source": "Test"})

# Update a config field
config = requests.get(f"{BASE}/profile-config/Aggressive/person.json").json()
person = json.loads(config["content"])
person["simulation_mode"] = "investment"
requests.post(f"{BASE}/profile-config", json={
    "profile": "Aggressive",
    "name": "person.json",
    "content": json.dumps(person),
    "version_note": "set investment mode"
})

# Run and compare
r = requests.post(f"{BASE}/run", json={"profile": "Aggressive", "paths": 200}).json()
print(f"Aggressive: floor={r['summary']['floor_success_rate']:.1%}, "
      f"CAGR={r['summary']['cagr_nominal_median']:.2%}")
```

---

## Notes for Programmatic Use

**All results are persisted.** Every `/run` stores complete results to disk. You can retrieve any past run at any time via `/artifact/{profile}/{run_id}/raw_snapshot_accounts.json`. Runs are never auto-deleted unless you call `DELETE /reports/{profile}`.

**Simulation modes affect which metric matters.** In `investment` and `automatic` modes, use `floor_success_rate` as the success metric. In `retirement` mode, use `success_rate`. See Simulation Modes in DEVELOPER_GUIDE.md.

**Rate limiting.** No built-in rate limiting. Each `/run` with 500 paths takes ~2-5 seconds. Batch scenario analysis should use 200 paths for speed, 1000+ for publication-quality results.

**Config changes are versioned.** Every `POST /profile-config` auto-snapshots the previous state. Use `GET /profile/{profile}/versions` to audit config history.

**FastAPI interactive docs.** `http://localhost:8000/docs` provides a Swagger UI where you can explore and test all endpoints interactively, with full request/response schemas.
