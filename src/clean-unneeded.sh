# filename: clean-unneeded.sh

#!/usr/bin/env sh
set -eu

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== eNDinomics Cleanup =="

# Preserve core files and directories (one per line)
PRESERVE_PATHS="
$REPO_DIR/api.py
$REPO_DIR/cli.py
$REPO_DIR/loaders.py
$REPO_DIR/simulator.py
$REPO_DIR/snapshot.py
$REPO_DIR/reporting.py
$REPO_DIR/engines.py
$REPO_DIR/engines_assets.py
$REPO_DIR/assets_loader.py
$REPO_DIR/rmd.py
$REPO_DIR/assets.json
$REPO_DIR/taxes_states_mfj_single.json
$REPO_DIR/shocks_yearly.json
$REPO_DIR/inflation_yearly.json
$REPO_DIR/person.json
$REPO_DIR/income.json
$REPO_DIR/rmd.json
$REPO_DIR/economic.json
$REPO_DIR/allocation_yearly.json
$REPO_DIR/run-retire
$REPO_DIR/build-clean.sh
$REPO_DIR/build-clean-run.sh
$REPO_DIR/make_favicon.py
$REPO_DIR/ui
$REPO_DIR/profiles
$REPO_DIR/venv
"

# Temp file to accumulate delete candidates
DELETE_LIST_FILE="$(mktemp)"
# Ensure we clean up temp file on exit
trap 'rm -f "$DELETE_LIST_FILE"' EXIT

# Helper: check if path is preserved
is_preserved() {
  p="$1"
  echo "$PRESERVE_PATHS" | grep -Fqx "$p"
}

# Helper: add a path to delete list if it exists and isn't preserved
add_path() {
  p="$1"
  [ -z "$p" ] && return
  [ ! -e "$p" ] && return
  if is_preserved "$p"; then
    return
  fi
  # Avoid duplicates
  if ! grep -Fqx "$p" "$DELETE_LIST_FILE"; then
    printf "%s\n" "$p" >> "$DELETE_LIST_FILE"
  fi
}

# 1) Python caches and logs
find "$REPO_DIR" -type d -name '__pycache__' -print 2>/dev/null | while IFS= read -r line; do add_path "$line"; done
find "$REPO_DIR" -type f -name '*.pyc' -print 2>/dev/null | while IFS= read -r line; do add_path "$line"; done
find "$REPO_DIR" -type f -name '*.pyo' -print 2>/dev/null | while IFS= read -r line; do add_path "$line"; done
find "$REPO_DIR" -type f -name '*.log' -print 2>/dev/null | while IFS= read -r line; do add_path "$line"; done

# 2) UI build caches
add_path "$REPO_DIR/ui/node_modules"
add_path "$REPO_DIR/ui/package-lock.json"
for f in "$REPO_DIR"/ui/dist/assets/index-*.js; do [ -e "$f" ] && add_path "$f"; done
for f in "$REPO_DIR"/ui/dist/assets/index-*.js.map; do [ -e "$f" ] && add_path "$f"; done
for f in "$REPO_DIR"/ui/dist/assets/index-*.css; do [ -e "$f" ] && add_path "$f"; done

# 3) Optional: report artifacts (PNG/CSV) across profiles
find "$REPO_DIR/profiles" -type f \( \
  -name 'portfolio_*_summary.png' -o \
  -name 'totals_*.csv' -o \
  -name 'accounts_*_investment_yoy.csv' -o \
  -name 'taxes_*_components.png' -o \
  -name 'rmd_*_components.png' \
\) -print 2>/dev/null | while IFS= read -r line; do add_path "$line"; done

# 4) Optional: shocks overrides and console logs
find "$REPO_DIR/profiles" -type f -name 'shocks_override.json' -print 2>/dev/null | while IFS= read -r line; do add_path "$line"; done
find "$REPO_DIR/profiles" -type f -name 'console_output.log' -print 2>/dev/null | while IFS= read -r line; do add_path "$line"; done

# 5) Optional: legacy/reference/scaffold dirs (comment any you want to keep)
add_path "$REPO_DIR/legacy_reference_jsons"
add_path "$REPO_DIR/reference_jsons"
add_path "$REPO_DIR/saved_jsons"
add_path "$REPO_DIR/json-wo-withdraw-simpler"
add_path "$REPO_DIR/default_jsons"
add_path "$REPO_DIR/READMEs"

# Summarize
echo "These paths will be deleted:"
if [ -s "$DELETE_LIST_FILE" ]; then
  sed 's/^/  - /' "$DELETE_LIST_FILE"
else
  echo "  (none)"
fi

echo
printf "Proceed with deletion? (yes/no): "
read ans
case "$(echo "$ans" | tr '[:upper:]' '[:lower:]')" in
  yes)
    ;;
  *)
    echo "Aborted."
    exit 0
    ;;
esac

# Delete
if [ -s "$DELETE_LIST_FILE" ]; then
  while IFS= read -r p; do
    if [ -d "$p" ]; then
      rm -rf "$p"
    else
      rm -f "$p"
    fi
  done < "$DELETE_LIST_FILE"
fi

echo "Cleanup complete."

