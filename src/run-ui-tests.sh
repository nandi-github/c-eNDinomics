#!/usr/bin/env bash
# run-ui-tests.sh — start API server, run Playwright UI tests, stop server
#
# Usage:
#   ./run-ui-tests.sh              # run all 14 Playwright tests
#   ./run-ui-tests.sh --install    # one-time Playwright + Chromium install, then run
#   ./run-ui-tests.sh --headed     # run with visible browser (debug mode)
#
# Exit code:
#   0  all tests passed
#   1  one or more tests failed
#   2  server failed to start

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$SCRIPT_DIR/ui"
SERVER_PORT=8000
SERVER_URL="http://localhost:$SERVER_PORT"
SERVER_PID=""
PLAYWRIGHT_ARGS=""
INSTALL=0

for arg in "$@"; do
    case "$arg" in
        --install) INSTALL=1 ;;
        --headed)  PLAYWRIGHT_ARGS="--headed" ;;
        --help)
            echo "Usage: $0 [--install] [--headed]"
            echo "  --install  Install Playwright + Chromium browser (run once)"
            echo "  --headed   Run with visible browser window (for debugging)"
            exit 0 ;;
    esac
done

if [[ $INSTALL -eq 1 ]]; then
    echo "== Installing Playwright and Chromium =="
    cd "$UI_DIR"
    npm install
    npx playwright install chromium
    echo "== Install complete =="
    echo ""
fi

if ! command -v npx &>/dev/null; then
    echo "ERROR: npx not found — install Node.js first"
    exit 2
fi
if [[ ! -f "$UI_DIR/playwright.config.ts" ]]; then
    echo "ERROR: playwright.config.ts not found at $UI_DIR"
    exit 2
fi
if [[ ! -d "$UI_DIR/node_modules/@playwright" ]]; then
    echo "ERROR: Playwright not installed — run: $0 --install"
    exit 2
fi

server_already_running=0
if curl -sf "$SERVER_URL/health" &>/dev/null; then
    echo "== API server already running on :$SERVER_PORT =="
    server_already_running=1
fi

if [[ $server_already_running -eq 0 ]]; then
    echo "== Starting API server on :$SERVER_PORT =="
    cd "$SCRIPT_DIR"
    python -m uvicorn api:app --port "$SERVER_PORT" --log-level warning &
    SERVER_PID=$!

    echo -n "   Waiting for server"
    for i in $(seq 1 30); do
        sleep 0.5
        if curl -sf "$SERVER_URL/health" &>/dev/null; then
            echo " ready (${i}×0.5s)"
            break
        fi
        echo -n "."
        if [[ $i -eq 30 ]]; then
            echo ""
            echo "ERROR: Server did not start within 15s"
            kill "$SERVER_PID" 2>/dev/null || true
            exit 2
        fi
    done
fi

cleanup() {
    if [[ -n "$SERVER_PID" ]] && [[ $server_already_running -eq 0 ]]; then
        echo ""
        echo "== Stopping API server (PID $SERVER_PID) =="
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo ""
echo "== Running Playwright UI tests =="
cd "$UI_DIR"

set +e
npx playwright test --config=playwright.config.ts $PLAYWRIGHT_ARGS
PLAYWRIGHT_EXIT=$?
set -e

echo ""
if [[ $PLAYWRIGHT_EXIT -eq 0 ]]; then
    echo "== ✅  All Playwright tests passed =="
else
    echo "== ❌  Playwright tests failed (exit $PLAYWRIGHT_EXIT) =="
    echo "   View report: cd $UI_DIR && npx playwright show-report"
fi

exit $PLAYWRIGHT_EXIT
