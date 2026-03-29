# eNDinomics Next Session Plan — v3.0
_Updated: session 23 complete (2026-03-20)_

## Session 23b — Immediate (next session)

### 1. Profile versioning (HIGH — unblocks Apply to config safety)
- api.py: wrap save_profile_json with version snapshot
  - Before every write: copy versionable files to .versions/vN/
  - profile_history.json manifest: [{v, ts, note, files_changed}]
  - Versionable: person.json, withdrawal_schedule.json, allocation_yearly.json, income.json
  - Auto-prune: keep last 20 versions
- api.py: GET /profile/{name}/versions — list history
- api.py: POST /profile/{name}/restore/{v} — restore (saves current as new version first)
- App.tsx: version history in Configure tab header
  - "Version: v4 — Today 11:02 AM" with [▼ History] toggle
  - Inline list: timestamp, note, [Apply] button
  - Apply: confirm dialog → save current as vN+1 → restore vN → reload

### 2. Playwright tests for Roth Insights (MEDIUM)
- Test 17: Roth Conversion Insights section
  - Present in Results tab after simulation
  - Collapsed by default
  - Expands on click, shows Current Situation + Recommendation
  - Apply button present with strategy name
- Test 18: Investment tab Option C
  - Tab accessible, section present

### 3. income.json realistic modeling (MEDIUM)
- Currently all zeros — affects Roth optimizer bracket positioning
- W2 income for ages 47-64 (working years)
- Social Security starting age 67-70 (ordinary_other)
- Rental income if applicable
- Update Test profile income.json with realistic values
- Update G4 income tests

## Session 24+ Backlog
- Pure investment return metric (strip RMD reinvestment from CAGR)
- Investment tab Phase 2 — signal_computation.py
- Shocks: custom named scenarios
- Export: PDF report generation
