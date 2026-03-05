# filename: verify-ui-results.sh

#!/usr/bin/env sh
set -eu

API="http://127.0.0.1:8000"

PROFILE="${1:-default}"

echo "== Verify UI Results for profile: $PROFILE =="

# 1) List runs for the profile
echo "-- GET /reports/$PROFILE"
curl -s "$API/reports/$PROFILE" | tee /tmp/reports.json
RUN_ID="$(python3 - <<'PY'
import json,sys
d=json.load(open('/tmp/reports.json'))
rs=d.get('runs') or []
print(rs[-1] if rs else '')
PY
)"

if [ -z "$RUN_ID" ]; then
  echo "No runs found. Run a simulation first in the UI or CLI."
  exit 1
fi

echo "Latest run_id: $RUN_ID"

# 2) Fetch run_meta.json (UI headers)
META_URL="$API/artifact/$PROFILE/$RUN_ID/run_meta.json"
echo "-- GET $META_URL"
curl -s "$META_URL" | tee /tmp/run_meta.json >/dev/null || true

# 3) Fetch raw_snapshot_accounts.json (UI tables/charts)
SNAP_URL="$API/artifact/$PROFILE/$RUN_ID/raw_snapshot_accounts.json"
echo "-- GET $SNAP_URL"
curl -s "$SNAP_URL" | tee /tmp/snapshot.json >/dev/null || true

# 4) Extract key fields to confirm consistency
echo "-- Parse key fields"
python3 - <<'PY'
import json
try:
    meta=json.load(open('/tmp/run_meta.json'))
    snap=json.load(open('/tmp/snapshot.json'))
except Exception as e:
    print(f"Failed to parse artifacts: {e}")
    raise

ri = meta.get('run_info', {})
print("Run Info:")
print("  profile:", meta.get('profile'))
print("  run_id:", meta.get('run_id'))
print("  dollars:", ri.get('dollars'))
print("  base_year:", ri.get('base_year'))
print("  paths:", ri.get('paths'))
print("  steps_per_year:", ri.get('steps_per_year'))
print("  state:", ri.get('state'))
print("  filing:", ri.get('filing'))
print("  shocks_mode:", ri.get('shocks_mode'))

P = (snap.get('portfolio') or {})
years = P.get('years') or snap.get('years') or []
fm = P.get('future_mean') or []
cm = P.get('current_mean') or []
print("\nPortfolio arrays:")
print("  years:", len(years), "entries")
print("  future_mean:", len(fm), "entries")
print("  current_mean:", len(cm), "entries")
if years and fm:
    print("  first-year future_mean:", fm[0])
if years and cm:
    print("  first-year current_mean:", cm[0])

W = (snap.get('withdrawals') or {})
print("\nWithdrawals arrays present:",
      "planned_current" in W,
      "realized_current_mean" in W,
      "realized_future_mean" in W)
PY

echo
echo "If the arrays show non-zero lengths and run_info looks correct, your UI must read these two URLs for Results."
echo "If Results is still empty, the UI is not persisting selection; add saveSelection(profile, runId) after POST /run and restore it in Results."

