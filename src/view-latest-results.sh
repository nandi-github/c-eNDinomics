# filename: view-latest-results.sh
#!/usr/bin/env sh
set -eu

API="http://127.0.0.1:8000"
PROFILE="${1:-default}"

echo "== View Latest Results for profile: $PROFILE =="

RUNS_URL="$API/reports/$PROFILE"
echo "-- GET $RUNS_URL"
RUNS_RAW="$(curl -sS "$RUNS_URL")" || { echo "Failed to fetch runs."; exit 1; }
echo "Raw response:"; echo "$RUNS_RAW"; echo

# Extract latest run id
LATEST_RUN_ID=""
if command -v jq >/dev/null 2>&1; then
  LATEST_RUN_ID="$(printf "%s" "$RUNS_RAW" | jq -r '.runs | if length>0 then .[-1] else "" end')"
else
  # Fallback: grep/sed to pull the last run in the array
  LATEST_RUN_ID="$(echo "$RUNS_RAW" \
    | sed -n 's/.*"runs":\[\(.*\)\].*/\1/p' \
    | awk -F',' '{print $NF}' \
    | sed 's/[" \t\n]*//g')"
fi

[ -n "$LATEST_RUN_ID" ] || { echo "No runs found. Run a simulation first."; exit 1; }
echo "Latest run_id: $LATEST_RUN_ID"

META_URL="$API/artifact/$PROFILE/$LATEST_RUN_ID/run_meta.json"
SNAP_URL="$API/artifact/$PROFILE/$LATEST_RUN_ID/raw_snapshot_accounts.json"

echo "-- GET $META_URL"
curl -sS "$META_URL" || { echo "Failed to fetch meta."; exit 1; }
echo
echo "-- GET $SNAP_URL"
curl -sS "$SNAP_URL" || { echo "Failed to fetch snapshot."; exit 1; }
echo

# Open in browser
if command -v open >/dev/null 2>&1; then
  open "$META_URL" && open "$SNAP_URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$META_URL" >/dev/null 2>&1 || true
  xdg-open "$SNAP_URL" >/dev/null 2>&1 || true
else
  echo "Open these URLs:"
  echo "  $META_URL"
  echo "  $SNAP_URL"
fi

echo "Done."

