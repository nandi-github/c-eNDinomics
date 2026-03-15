#!/usr/bin/env bash
# filename: run-ui-tests.sh
#
# eNDinomics UI Smoke Test Runner
#
# Usage:
#   ./run-ui-tests.sh              # run all smoke tests
#   ./run-ui-tests.sh --headed     # run with visible browser (debug)
#   ./run-ui-tests.sh --install    # install playwright + chromium only
#
# Prerequisites:
#   - Python venv set up (build-clean.sh already run)
#   - Node/npm available
#
# What this does:
#   1. Installs @playwright/test if missing
#   2. Installs chromium browser if missing
#   3. Starts FastAPI server on port 8000
#   4. Runs playwright smoke tests
#   5. Stops the server when done
#   6. Prints pass/fail summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$SCRIPT_DIR/ui"
VENV_DIR="$SCRIPT_DIR/venv"
API_PORT=8000
API_PID_FILE="$SCRIPT_DIR/.api_test_pid"

HEADED="${1:-}"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${YELLOW}== eNDinomics UI Smoke Tests ==${NC}"

# ── 1) Install playwright if needed ──────────────────────────────────────────
cd "$UI_DIR"

if [[ ! -d node_modules/@playwright ]]; then
  echo "-- Installing @playwright/test --"
  npm install --save-dev @playwright/test
fi

if [[ "$HEADED" == "--install" ]]; then
  echo "-- Installing Playwright browsers --"
  npx playwright install chromium
  echo -e "${GREEN}Playwright installed.${NC}"
  exit 0
fi

# Install chromium if not present
if ! npx playwright install --dry-run chromium 2>/dev/null | grep -q "chromium.*already installed" 2>/dev/null; then
  echo "-- Installing Chromium browser --"
  npx playwright install chromium
fi

# ── 2) Check or start FastAPI server ─────────────────────────────────────────
SERVER_STARTED=0

if curl -s "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
  echo "-- FastAPI server already running on port $API_PORT --"
else
  echo "-- Starting FastAPI server on port $API_PORT --"
  if [[ -f "$VENV_DIR/bin/activate" ]]; then
    source "$VENV_DIR/bin/activate"
  fi
  cd "$SCRIPT_DIR"
  python3 -m uvicorn api:app --port $API_PORT --host 127.0.0.1 &
  echo $! > "$API_PID_FILE"
  SERVER_STARTED=1
  # Wait for server to be ready
  echo "-- Waiting for server to be ready --"
  for i in $(seq 1 30); do
    if curl -s "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
      echo "-- Server ready after ${i}s --"
      break
    fi
    sleep 1
  done
  if ! curl -s "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
    echo -e "${RED}ERROR: Server did not start within 30s${NC}"
    exit 1
  fi
fi

# ── 3) Run Playwright tests ───────────────────────────────────────────────────
cd "$UI_DIR"
PLAYWRIGHT_ARGS="--config=playwright.config.ts"
if [[ "$HEADED" == "--headed" ]]; then
  PLAYWRIGHT_ARGS="$PLAYWRIGHT_ARGS --headed"
fi

set +e
npx playwright test $PLAYWRIGHT_ARGS
TEST_EXIT=$?
set -e

# ── 4) Stop server if we started it ──────────────────────────────────────────
if [[ $SERVER_STARTED -eq 1 && -f "$API_PID_FILE" ]]; then
  echo "-- Stopping FastAPI server --"
  kill "$(cat "$API_PID_FILE")" 2>/dev/null || true
  rm -f "$API_PID_FILE"
fi

# ── 5) Summary ───────────────────────────────────────────────────────────────
echo ""
if [[ $TEST_EXIT -eq 0 ]]; then
  echo -e "${GREEN}✅ All UI smoke tests passed${NC}"
else
  echo -e "${RED}❌ UI smoke tests failed — see ui/playwright-report/ for details${NC}"
  echo "   Open report: cd root/src/ui && npx playwright show-report"
fi

exit $TEST_EXIT
