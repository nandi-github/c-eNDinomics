#!/usr/bin/env bash
# =============================================================================
# refresh_model.sh — Full market data + asset model refresh pipeline
# =============================================================================
#
# Runs the complete pipeline in one command:
#   1. Fetch market data (holdings, prices, sectors) → cache
#   2. Calibrate asset model from cache → candidate/assets.json
#   3. Validate candidate (bounds, SPD, required tickers)
#   4. Prompt for confirmation → promote to src/config/assets.json
#
# Usage:
#   ./refresh_model.sh              # interactive (prompts before promote)
#   ./refresh_model.sh --yes        # auto-promote without prompt
#   ./refresh_model.sh --dry-run    # fetch + calibrate + validate, never promote
#   ./refresh_model.sh --no-fetch   # skip fetch, use existing cache
#   ./refresh_model.sh --validate-only  # validate existing candidate only
#
# Cron example (weekly Sunday 6 AM, auto-promote):
#   0 6 * * 0 cd /path/to/c-eNDinomics && ./refresh_model.sh --yes >> logs/refresh.log 2>&1
#
# =============================================================================

set -euo pipefail

# ── Resolve repo root regardless of where script is called from ──────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

# ── Parse arguments ──────────────────────────────────────────────────────────
AUTO_YES=false
DRY_RUN=false
NO_FETCH=false
VALIDATE_ONLY=false

for arg in "$@"; do
    case $arg in
        --yes)           AUTO_YES=true ;;
        --dry-run)       DRY_RUN=true ;;
        --no-fetch)      NO_FETCH=true ;;
        --validate-only) VALIDATE_ONLY=true ;;
        --help|-h)
            sed -n '2,25p' "$0"
            exit 0 ;;
        *)
            echo "Unknown argument: $arg  (use --help for usage)"
            exit 1 ;;
    esac
done

# ── Paths ────────────────────────────────────────────────────────────────────
ASSETS_JSON="$REPO_ROOT/src/config/assets.json"
CANDIDATE="$REPO_ROOT/asset-model/candidate/assets.json"
PROMO_LOG="$REPO_ROOT/asset-model/promotion_log.json"
CACHE_DIR="$REPO_ROOT/market_data/cache/store"
LOG_DIR="$REPO_ROOT/logs"

mkdir -p "$LOG_DIR"
mkdir -p "$REPO_ROOT/asset-model/candidate"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/refresh_${TIMESTAMP}.log"

# ── Logging ──────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
log_section() {
    echo "" | tee -a "$LOG_FILE"
    echo "════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
    echo "  $*" | tee -a "$LOG_FILE"
    echo "════════════════════════════════════════════════════" | tee -a "$LOG_FILE"
}

log_section "eNDinomics Model Refresh  |  $(date '+%Y-%m-%d %H:%M')"
log "Repo root : $REPO_ROOT"
log "Log file  : $LOG_FILE"
log "Options   : auto_yes=$AUTO_YES dry_run=$DRY_RUN no_fetch=$NO_FETCH validate_only=$VALIDATE_ONLY"

# ── Ensure assets.json is writable (SMB share sometimes sets read-only) ──────
if [[ -f "$ASSETS_JSON" ]]; then
    chmod 644 "$ASSETS_JSON" 2>/dev/null || true
fi

# ── STEP 1: Fetch market data ─────────────────────────────────────────────────
if [[ "$VALIDATE_ONLY" == "false" && "$NO_FETCH" == "false" ]]; then
    log_section "Step 1 — Market Data Fetch"

    FETCH_FLAGS=""
    if [[ "$DRY_RUN" == "true" ]]; then
        FETCH_FLAGS="--dry-run"
        log "DRY RUN: showing cache status only"
    fi

    cd "$REPO_ROOT"
    python3 -m market_data.scheduler.weekly_job \
        --assets "$ASSETS_JSON" \
        --cache-dir "$CACHE_DIR" \
        $FETCH_FLAGS \
        2>&1 | tee -a "$LOG_FILE"

    FETCH_EXIT=${PIPESTATUS[0]}
    if [[ $FETCH_EXIT -ne 0 ]]; then
        log "WARNING: market data fetch had failures (exit $FETCH_EXIT)"
        log "Continuing — stale cache will be used where fresh data unavailable"
    fi
else
    log "Step 1 SKIPPED (--no-fetch or --validate-only)"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    log_section "DRY RUN complete — no calibration or promotion"
    exit 0
fi

if [[ "$VALIDATE_ONLY" == "true" ]]; then
    log_section "Step 2 SKIPPED — validate-only mode"
else
    # ── STEP 2: Calibrate ────────────────────────────────────────────────────
    log_section "Step 2 — Asset Model Calibration"

    cd "$REPO_ROOT"
    python3 src/asset_calibration.py \
        --assets-in "$ASSETS_JSON" \
        --out "$CANDIDATE" \
        --cache-dir "$CACHE_DIR" \
        2>&1 | tee -a "$LOG_FILE"

    if [[ ! -f "$CANDIDATE" ]]; then
        log "ERROR: calibration did not produce a candidate model"
        exit 1
    fi
    log "Candidate written: $CANDIDATE"
fi

# ── STEP 3: Validate ─────────────────────────────────────────────────────────
log_section "Step 3 — Validation"

cd "$REPO_ROOT"
python3 src/promote_model.py \
    --candidate "$CANDIDATE" \
    --production "$ASSETS_JSON" \
    --log "$PROMO_LOG" \
    --validate-only \
    2>&1 | tee -a "$LOG_FILE"

VALIDATE_EXIT=${PIPESTATUS[0]}
if [[ $VALIDATE_EXIT -ne 0 ]]; then
    log ""
    log "ERROR: validation failed — promotion blocked"
    log "Fix errors above and re-run: ./refresh_model.sh --no-fetch"
    exit 1
fi

if [[ "$VALIDATE_ONLY" == "true" ]]; then
    log_section "VALIDATE ONLY complete — no promotion"
    exit 0
fi

# ── STEP 4: Promote ───────────────────────────────────────────────────────────
log_section "Step 4 — Promotion"

# Ensure writable before promote
chmod 644 "$ASSETS_JSON" 2>/dev/null || true

PROMOTE_FLAGS="--candidate $CANDIDATE --production $ASSETS_JSON --log $PROMO_LOG"
if [[ "$AUTO_YES" == "true" ]]; then
    PROMOTE_FLAGS="$PROMOTE_FLAGS --yes"
fi

cd "$REPO_ROOT"
python3 src/promote_model.py $PROMOTE_FLAGS 2>&1 | tee -a "$LOG_FILE"
PROMOTE_EXIT=${PIPESTATUS[0]}

if [[ $PROMOTE_EXIT -ne 0 ]]; then
    log "ERROR: promotion failed (exit $PROMOTE_EXIT)"
    exit 1
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log_section "Done"
log "New model : $(python3 -c "import json; d=json.load(open('$ASSETS_JSON')); print(d.get('model_version','?'))" 2>/dev/null || echo '?')"
log "Log       : $LOG_FILE"
log ""
log "Next steps:"
log "  1. Restart API server to pick up new assets.json"
log "  2. Run a simulation to verify results look sensible"
log "  3. Commit: git add src/config/assets.json asset-model/ && git commit -m 'chore: promote asset model vX.X.X'"
