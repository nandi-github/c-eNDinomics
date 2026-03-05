# filename: build-clean.sh

#!/usr/bin/env bash
# Clean build for UI (Vite React) and CLI/Backend (FastAPI + Python) under the Profiles scheme.
# Run from the repository root:
#   chmod +x ./build-clean.sh
#   ./build-clean.sh
#
# This script:
# - Cleans and builds the UI (ui/dist), including help.html from ui/public
# - Creates/updates a Python virtual environment and installs dependencies
# - Verifies build artifacts exist (index.html/help.html)
# - Leaves profile directories intact (no deletion of profiles or their reports)
# - Prints tool versions for traceability

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$REPO_DIR/ui"
DIST_DIR="$UI_DIR/dist"
VENV_DIR="$REPO_DIR/venv"
REQ="$REPO_DIR/requirements.txt"
APP_ASSETS_JSON="$REPO_DIR/assets.json"

echo "== eNDinomics Clean Build =="
echo "Repo: $REPO_DIR"

# Tool versions (optional traceability)
if command -v node >/dev/null 2>&1; then
  echo "Node: $(node -v)"
fi
if command -v npm >/dev/null 2>&1; then
  echo "npm: $(npm -v)"
fi
if command -v python3 >/dev/null 2>&1; then
  echo "Python3: $(python3 --version)"
fi

# 1) UI build (Vite)
echo "== UI: cleaning and building =="
if [[ ! -d "$UI_DIR" ]]; then
  echo "Error: UI directory not found: $UI_DIR"
  exit 1
fi

pushd "$UI_DIR" >/dev/null

# Remove previous dist
rm -rf "$DIST_DIR"

# Install node dependencies (prefer clean install)
if command -v npm >/dev/null 2>&1; then
  echo "-- npm ci (or install) --"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
else
  echo "Error: npm not found on PATH"
  exit 1
fi

# Build for production
echo "-- npm run build --"
npm run build

# Verify index.html and help.html exist in dist
if [[ ! -f "$DIST_DIR/index.html" ]]; then
  echo "Error: dist/index.html not found after build"
  exit 1
fi
if [[ ! -f "$DIST_DIR/help.html" ]]; then
  echo "Warning: dist/help.html not found. Ensure help.html resides in ui/public/"
fi

popd >/dev/null
echo "== UI build complete: $DIST_DIR =="

# 2) Python virtual environment for CLI/Backend
echo "== Python: virtual environment setup =="
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Error: python3 not found on PATH"
  exit 1
fi

# Create venv if missing
if [[ -d "$VENV_DIR" ]]; then
  echo "-- Using existing venv: $VENV_DIR --"
else
  echo "-- Creating venv: $VENV_DIR --"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate venv
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies (prefer requirements.txt if present)
if [[ -f "$REQ" ]]; then
  echo "-- pip install -r requirements.txt --"
  python -m pip install -r "$REQ"
else
  echo "-- Installing core deps (no requirements.txt found) --"
  python -m pip install fastapi "uvicorn[standard]" numpy matplotlib
  # Add project-specific libs here if needed:
  # python -m pip install pandas scipy
fi

deactivate
echo "== Python venv ready: $VENV_DIR =="

# 3) Ensure scripts are executable
echo "== Marking scripts executable =="
if [[ -f "$REPO_DIR/run-retire" ]]; then
  chmod +x "$REPO_DIR/run-retire"
fi

# 4) Preserve profiles and reports (no clearing)
echo "== Profiles and reports preserved (no deletion) =="

# 5) Clean Python caches (optional)
echo "== Cleaning Python caches =="
find "$REPO_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$REPO_DIR" -name "*.pyc" -type f -delete

# 6) Info: common assets.json presence
if [[ -f "$APP_ASSETS_JSON" ]]; then
  echo "== Found common assets.json at: $APP_ASSETS_JSON =="
else
  echo "Note: No assets.json found at app root. Asset-level Monte Carlo will be disabled unless passed via --assets."
fi

echo "== Build complete =="
echo "UI dist: $DIST_DIR"
echo "Python venv: $VENV_DIR"

# --- End of file ---

