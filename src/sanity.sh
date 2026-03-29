#!/usr/bin/env bash
# sanity.sh — eNDinomics standard sanity check
# Usage: ./sanity.sh
#
# Runs: --checkupdates (file hash gate) + all 32 test groups + G19 Playwright
# Clears stale G18 snapshot baseline automatically before each run.
# Aborts if any deployed file is out of date (hash mismatch).

clear
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "Sanity Testing - comprehensive-test"
python3 -B test_flags.py --sanity

echo "Running playwright seperately"
cd ui
npx playwright test
cd .. 

echo "Sanity Testing complete"
