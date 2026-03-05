# filename: run-retire

#!/usr/bin/env bash
# eNDinomics CLI runner (flag-based, profile-aware)
# Usage examples:
#   ./run-retire --profile "profile-1"
#   ./run-retire --profile "profile-1" --dollars future --spy 4 --paths 300 --base_year 2029 \
#                --state Washington --filing Single --shocks_mode override --ignore_withdrawals \
#                --debug on
#
# Notes:
# - The operator must create the 'profile' directory under profiles/ and place all required JSONs there.
# - Outputs (snapshot, PNGs, CSVs, console log) are written to profiles/<profile>/reports/run_YYYYMMDD_HHMMSS/.
# - --debug on/off maps to SIM_DEBUG=1/0 (default off).

set -euo pipefail

# Defaults
PROFILE=""
PATHS=200
SPY=2
DOLLARS="current"               # current|future
BASE_YEAR=2026
STATE="California"
FILING="MFJ"                    # MFJ|Single|HeadOfHousehold
SHOCKS_MODE=""                  # augment|override (optional)
IGNORE_WITHDRAWALS=0            # 1 to zero out schedule
IGNORE_RMDS=0                   # 1 (display flag)
IGNORE_CONVERSIONS=0            # 1 (display flag)
DEBUG_FLAG="off"                # on|off → SIM_DEBUG=1|0

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-}"; shift 2;;
    --paths)
      PATHS="${2:-200}"; shift 2;;
    --spy|--steps-per-year)
      SPY="${2:-2}"; shift 2;;
    --dollars)
      DOLLARS="${2:-current}"; shift 2;;
    --base_year|--base-year)
      BASE_YEAR="${2:-2026}"; shift 2;;
    --state)
      STATE="${2:-California}"; shift 2;;
    --filing)
      FILING="${2:-MFJ}"; shift 2;;
    --shocks_mode|--shocks-mode)
      SHOCKS_MODE="${2:-}"; shift 2;;
    --ignore_withdrawals|--ignore-withdrawals)
      IGNORE_WITHDRAWALS=1; shift 1;;
    --ignore_rmds|--ignore-rmds)
      IGNORE_RMDS=1; shift 1;;
    --ignore_conversions|--ignore-conversions)
      IGNORE_CONVERSIONS=1; shift 1;;
    --debug)
      DEBUG_FLAG="${2:-off}"; shift 2;;
    --help|-h)
      echo "Usage: $0 --profile <name> [--paths N] [--spy N] [--dollars current|future] [--base_year YYYY]"
      echo "             [--state NAME] [--filing MFJ|Single|HeadOfHousehold]"
      echo "             [--shocks_mode augment|override] [--ignore_withdrawals] [--ignore_rmds] [--ignore_conversions]"
      echo "             [--debug on|off]"
      exit 0;;
    *)
      echo "Unknown option: $1"; exit 1;;
  esac
done

if [[ -z "$PROFILE" ]]; then
  echo "Error: --profile is required."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
PROFILES_DIR="$REPO_DIR/profiles/$PROFILE"

# Verify profile directory
if [[ ! -d "$PROFILES_DIR" ]]; then
  echo "Profile directory not found: $PROFILES_DIR"
  echo "Create it and place required JSONs before running."
  exit 1
fi

# Required JSON paths
ALLOC_JSON="$PROFILES_DIR/allocation_yearly.json"
WITHDRAW_JSON="$PROFILES_DIR/withdrawal_schedule.json"
INFLATION_JSON="$PROFILES_DIR/inflation_yearly.json"
SHOCKS_JSON="$PROFILES_DIR/shocks_yearly.json"
TAX_JSON="$PROFILES_DIR/taxes_states_mfj_single.json"
PERSON_JSON="$PROFILES_DIR/person.json"
INCOME_JSON="$PROFILES_DIR/income.json"
RMD_JSON="$PROFILES_DIR/rmd.json"
ECON_JSON="$PROFILES_DIR/economic.json"

# Check required files exist
for f in "$ALLOC_JSON" "$WITHDRAW_JSON" "$INFLATION_JSON" "$SHOCKS_JSON" "$TAX_JSON" "$PERSON_JSON" "$INCOME_JSON" "$RMD_JSON" "$ECON_JSON"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required file: $f"
    exit 1
  fi
done

# Prepare output run directory
TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$PROFILES_DIR/reports/run_${TS}"
mkdir -p "$RUN_DIR"

# Build overrides if needed
WITHDRAW_ARG="$WITHDRAW_JSON"
if [[ "$IGNORE_WITHDRAWALS" -eq 1 ]]; then
  WITHDRAW_OVERRIDE="$RUN_DIR/withdraw_override.json"
  cat > "$WITHDRAW_OVERRIDE" <<EOF
{
  "floor_k": 0,
  "schedule": []
}
EOF
  WITHDRAW_ARG="$WITHDRAW_OVERRIDE"
fi

SHOCKS_ARG="$SHOCKS_JSON"
if [[ -n "$SHOCKS_MODE" ]]; then
  SHOCKS_OVERRIDE="$RUN_DIR/shocks_override.json"
  if command -v jq >/dev/null 2>&1; then
    jq --arg mode "$SHOCKS_MODE" '.mode=$mode' "$SHOCKS_JSON" > "$SHOCKS_OVERRIDE"
  else
    # Fallback: minimal override file
    cat > "$SHOCKS_OVERRIDE" <<EOF
{
  "mode": "$SHOCKS_MODE",
  "events": []
}
EOF
  fi
  SHOCKS_ARG="$SHOCKS_OVERRIDE"
fi

CONSOLE_LOG="$RUN_DIR/console_output.log"

# Map --debug to SIM_DEBUG env
if [[ "$DEBUG_FLAG" == "on" ]]; then
  SIM_DEBUG=1
else
  SIM_DEBUG=0
fi

# Build CLI command
CMD=(
  env SIM_DEBUG="$SIM_DEBUG"
  python3 "$REPO_DIR/cli.py"
  --tax "$TAX_JSON"
  --state "$STATE"
  --filing "$FILING"
  --withdraw "$WITHDRAW_ARG"
  --inflation "$INFLATION_JSON"
  --shocks "$SHOCKS_ARG"
  --alloc-yearly "$ALLOC_JSON"
  --person "$PERSON_JSON"
  --income "$INCOME_JSON"
  --rmd "$RMD_JSON"
  --economic "$ECON_JSON"
  --paths "$PATHS"
  --steps-per-year "$SPY"
  --dollars "$DOLLARS"
  --base-year "$BASE_YEAR"
  --out "$RUN_DIR"
)

# Flags
if [[ -n "$SHOCKS_MODE" ]]; then
  CMD+=( --shocks-mode "$SHOCKS_MODE" )
fi
if [[ "$IGNORE_WITHDRAWALS" -eq 1 ]]; then
  CMD+=( --ignore-withdrawals )
fi
if [[ "$IGNORE_RMDS" -eq 1 ]]; then
  CMD+=( --ignore-rmds )
fi
if [[ "$IGNORE_CONVERSIONS" -eq 1 ]]; then
  CMD+=( --ignore-conversions )
fi

echo "Output folder: $RUN_DIR"
echo "Console is mirrored to: $CONSOLE_LOG"
echo "SIM_DEBUG: $SIM_DEBUG (${DEBUG_FLAG})"
echo
echo "Running:"
printf ' %q' "${CMD[@]}"
echo

(
  cd "$REPO_DIR"
  "${CMD[@]}" 2>&1 | tee "$CONSOLE_LOG"
)

echo
echo "Artifacts:"
ls -1 "$RUN_DIR" || true

# --- End of file ---

