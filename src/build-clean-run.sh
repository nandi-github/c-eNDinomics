# filename: build-clean.sh

#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$REPO_DIR/ui"
DIST_DIR="$UI_DIR/dist"
VENV_DIR="$REPO_DIR/venv"

echo "== eNDinomics Clean Build =="
echo "Repo: $REPO_DIR"

if command -v node >/dev/null 2>&1; then echo "Node: $(node -v)"; fi
if command -v npm  >/dev/null 2>&1; then echo "npm: $(npm -v)"; fi
if command -v python3 >/dev/null 2>&1; then echo "Python3: $(python3 --version)"; fi

echo "== UI: cleaning and building =="
if [[ ! -d "$UI_DIR" ]]; then echo "Error: UI directory not found: $UI_DIR"; exit 1; fi
pushd "$UI_DIR" >/dev/null
rm -rf "$DIST_DIR"
rm -rf node_modules package-lock.json || true
npm cache clean --force || true
echo "-- npm install --"
npm install || {
  echo "npm install failed; attempting Rollup quarantine fix and JS fallback"
  xattr -dr com.apple.quarantine node_modules/@rollup || true
  export ROLLUP_SKIP_NODE_BINARY=1
  npm install
}
echo "-- npm run build --"
npm run build || {
  echo "Build failed; retrying with JS Rollup fallback"
  export ROLLUP_SKIP_NODE_BINARY=1
  npm run build
}
if [[ ! -f "$DIST_DIR/index.html" ]]; then echo "Error: dist/index.html not found after build"; exit 1; fi
if [[ ! -f "$DIST_DIR/help.html" ]]; then echo "Warning: dist/help.html not found. Ensure help.html resides in ui/public/ if needed."; fi
popd >/dev/null
echo "== UI build complete: $DIST_DIR =="

echo "== Favicon =="
# Generate a favicon and copy to dist to avoid 404s on /favicon.ico
python3 "$REPO_DIR/make_favicon.py" || true
if [[ -f "$REPO_DIR/favicon.ico" ]]; then
  cp "$REPO_DIR/favicon.ico" "$DIST_DIR/favicon.ico" || true
fi

echo "== Python: virtual environment setup =="
if ! command -v python3 >/dev/null 2>&1; then echo "Error: python3 not found on PATH"; exit 1; fi
if [[ -d "$VENV_DIR" ]]; then
  echo "-- Using existing venv: $VENV_DIR --"
else
  echo "-- Creating venv: $VENV_DIR --"
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
REQ="$REPO_DIR/requirements.txt"
if [[ -f "$REQ" ]]; then
  echo "-- pip install -r requirements.txt --"
  python -m pip install -r "$REQ"
else
  echo "-- Installing core deps (no requirements.txt found) --"
  python -m pip install fastapi "uvicorn[standard]" numpy matplotlib
fi
deactivate
echo "== Python venv ready: $VENV_DIR =="

echo "== Marking scripts executable =="
if [[ -f "$REPO_DIR/run-retire" ]]; then chmod +x "$REPO_DIR/run-retire"; fi

echo "== Profiles and reports preserved (no deletion) =="
echo "== Cleaning Python caches =="
find "$REPO_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} + || true
find "$REPO_DIR" -name "*.pyc" -type f -delete || true

APP_ASSETS_JSON="$REPO_DIR/assets.json"
if [[ -f "$APP_ASSETS_JSON" ]]; then
  echo "== Found common assets.json at: $APP_ASSETS_JSON =="
else
  echo "Note: No assets.json found at app root."
fi

echo "== Build complete =="
echo "UI dist: $DIST_DIR"
echo "Python venv: $VENV_DIR"
echo "== Starting API (Uvicorn) =="
python -m uvicorn api:app --reload

# --- End of file ---

