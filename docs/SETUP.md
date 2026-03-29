# eNDinomics — Developer Setup Guide

Complete environment setup for a new developer. Covers Python (conda), Node.js, and Playwright.

---

## Prerequisites

- **macOS** (primary dev environment — SMB share path assumes Mac)
- **Conda** (Anaconda or Miniconda) — https://docs.conda.io/en/latest/miniconda.html
- **Node.js 18+** — https://nodejs.org (or via `brew install node`)
- **Git** — https://git-scm.com

---

## 1. Clone the Repo

```bash
git clone https://github.com/nandi-github/c-eNDinomics.git
cd c-eNDinomics
```

If working from the SMB share (primary dev machine):
```bash
cd "/Volumes/My Shared Files/workspace/research/c-eNDinomics"
```

---

## 2. Python Environment (conda)

### Create and activate the environment

```bash
conda create -n endinomics python=3.11 -y
conda activate endinomics
```

### Install all Python dependencies

```bash
pip install -r requirements.txt
```

**Full requirements.txt** (copy this to replace the minimal one in the repo):

```
# Core scientific stack
numpy==2.4.2
matplotlib==3.10.8
pillow==12.1.0

# matplotlib dependencies (pinned for stability)
contourpy==1.3.3
cycler==0.12.1
fonttools==4.61.1
kiwisolver==1.4.9
packaging==26.0
pyparsing==3.3.2
python-dateutil==2.9.0.post0
six==1.17.0

# Web framework (API server)
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.9

# Market data
yfinance==0.2.38
pandas==2.2.2

# HTTP requests (for ETF data providers)
requests==2.32.3
```

### Verify Python installation

```bash
conda activate endinomics
python -c "import numpy, matplotlib, fastapi, uvicorn, yfinance, pandas; print('All Python deps OK')"
```

---

## 3. Node.js / npm / npx Setup

### 3a. Install Node.js (choose one method)

**Option A — Homebrew (recommended on macOS):**
```bash
brew install node
```

**Option B — nvm (Node Version Manager — best for managing multiple versions):**
```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
# Restart terminal, then:
nvm install 20
nvm use 20
nvm alias default 20
```

**Option C — Direct download:**
Go to https://nodejs.org → download LTS (20.x or 22.x)

> **npm and npx are included with Node.js** — no separate install needed.
> `npm` = package manager, `npx` = run packages without installing globally.

### 3b. Verify Node.js installation

```bash
node --version    # should be 18+ (20 or 22 LTS recommended)
npm --version     # should be 9+
npx --version     # same as npm version — comes bundled
```

### 3c. Install UI dependencies

```bash
cd src/ui
npm install
```

This reads `package.json` and installs:
- React 18, react-dom
- Vite 6 (build tool + dev server)
- TypeScript 5
- @playwright/test (UI smoke test runner)
- @vitejs/plugin-react-swc (fast React compilation)

### 3d. Install Playwright browser (one-time per machine)

```bash
cd src/ui
npx playwright install chromium
```

Downloads Chromium (~170MB). Only needed once. If you skip this, Playwright tests fail with "browser not found".

```bash
# Verify Playwright is ready
npx playwright --version
npx playwright show-report   # should open browser (or show "no report" message)
```

### 3e. Install docx (for Grand Plan document generation — optional)

```bash
npm install -g docx
```

Only needed if regenerating `eNDinomics_GrandPlan_v*.docx`.

---

## 4. Full Environment Verification

Run these in order to confirm everything works end-to-end:

```bash
# 1. Activate conda environment
conda activate endinomics

# 2. Start the server (builds UI + starts API on :8000)
cd src
./vcleanbld_ui
# Should print "== Build complete ==" then start uvicorn
# Leave this running in one terminal

# 3. In a new terminal — verify API is up
curl http://localhost:8000/health

# 4. Run Python test suite (skip Playwright for first check)
cd src
python3 -B test_flags.py --comprehensive-test --skip-playwright
# Expected: 502/503 (G19 requires Playwright — check next step)

# 5. Run Playwright UI tests
cd src/ui
npx playwright test
# Expected: 23/23 passing

# 6. Run full suite together
cd src
python3 -B test_flags.py --comprehensive-test
# Expected: 503/503 + 23/23

# 7. Verify file integrity
python3 -B test_flags.py --checkupdates
# Expected: all ✅ match
```

---

## 5. SMB Share Notes (primary dev machine only)

The working directory is on an SMB share (`/Volumes/My Shared Files/`). This causes a specific issue with Python file writes:

```python
# ❌ WRONG — PermissionError on existing files via SMB
with open(path, "w") as f:
    f.write(content)

# ✅ CORRECT — always use temp+replace
import tempfile, os
with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(path),
                                  delete=False, suffix=".tmp") as tmp:
    tmp.write(content)
os.replace(tmp.name, path)
```

This pattern is already used throughout `api.py` — never bypass it.

---

## 6. Environment Quick Reference

```bash
# Activate environment (do this in every new terminal)
conda activate endinomics

# Start server
cd src && ./vcleanbld_ui

# Run tests
cd src && python3 -B test_flags.py --comprehensive-test

# Playwright only
cd src/ui && npx playwright test

# Playwright with visible browser (debug failing tests)
cd src/ui && npx playwright test --headed

# Playwright HTML report (screenshots + video of failures)
cd src/ui && npx playwright show-report

# UI hot-reload dev server (proxies API to :8000, no rebuild needed)
cd src/ui && npm run dev
# Then open http://localhost:5173 — changes to App.tsx reload instantly

# Check deployed files match local
cd src && python3 -B test_flags.py --checkupdates

# Update baseline after intentional number changes
cd src && python3 -B test_flags.py --comprehensive-test --update-baseline

# Deactivate environment
conda deactivate
```

---

## 7. What Each Piece Does

| Component | Version | Purpose |
|-----------|---------|---------|
| Python 3.11 | 3.11 | Runtime — all simulation, API, tests |
| numpy | 2.4.2 | Monte Carlo GBM simulation, matrix operations |
| matplotlib | 3.10.8 | Chart generation for run reports |
| fastapi | 0.115.0 | REST API server |
| uvicorn | 0.30.0 | ASGI server (runs FastAPI) |
| yfinance | 0.2.38 | Market data — prices, dividends (optional, for refresh) |
| pandas | 2.2.2 | Data manipulation in market data providers |
| requests | 2.32.3 | HTTP — ETF holdings fetcher, FRED API |
| Node.js | 18+ | UI build toolchain (Vite + TypeScript) |
| React | 18.3.1 | UI framework |
| Vite | 6.0.0 | UI bundler / dev server |
| TypeScript | 5.6.3 | Type-safe UI code |
| Playwright | 1.44.0 | Browser automation for UI smoke tests |
| Chromium | latest | Browser for Playwright tests |

**Optional (for market data refresh only):**
- `yfinance`, `pandas`, `requests` — only needed when running `refresh_model.sh`
- The simulator itself only needs numpy, matplotlib, fastapi, uvicorn

---

## 8. Conda Environment Export

Save the full environment for exact reproduction:

```bash
conda activate endinomics
conda env export > environment.yml
```

Recreate on a new machine:
```bash
conda env create -f environment.yml
conda activate endinomics
```

Or for a cross-platform export (no OS-specific build deps):
```bash
conda env export --from-history > environment_minimal.yml
```

---

## 9. Directory Structure

```
c-eNDinomics/
  src/
    api.py                    ← FastAPI server (start with ./vcleanbld_ui)
    simulator_new.py          ← Simulation orchestrator
    test_flags.py             ← Full test suite (python3 -B test_flags.py ...)
    vcleanbld_ui              ← Build + start server script
    requirements.txt          ← Python deps (pip install -r requirements.txt)
    config/
      assets.json             ← Asset model v1.3.0
      rmd.json                ← IRS RMD tables
      cape_config.json        ← CAPE calibration
      economicglobal.json     ← Global economic defaults
    profiles/
      Test/                   ← Test profile (used by all tests)
      default/                ← Default profile (template for new users)
    ui/
      package.json            ← npm deps (npm install)
      src/App.tsx             ← Full React UI
      tests/smoke.spec.ts     ← 23 Playwright tests
  DEVELOPER_GUIDE.md          ← Dev commands, conventions — READ FIRST
  API_REFERENCE.md            ← REST API docs (25 endpoints)
  SESSION_STATE_v4_0.md       ← Current build state
  NEXT_SESSION_v4_0.md        ← Roadmap and priorities
  eNDinomics_GrandPlan_v1_7.docx ← Full architecture document
```

---

## 10. Common Issues

**`PermissionError` on file writes:**
→ SMB share issue. Use temp+replace pattern (see Section 5).

**`ModuleNotFoundError: fastapi`:**
→ Conda environment not activated. Run `conda activate endinomics`.

**Playwright `TimeoutError`:**
→ Server not running. Start with `cd src && ./vcleanbld_ui` first.

**`npx playwright test` — browser not found:**
→ Run `cd src/ui && npx playwright install chromium` once.

**`npm run build` fails:**
→ Run `cd src/ui && npm install` first.

**Tests show unexpected failures after copying files from Claude:**
→ Run `python3 -B test_flags.py --checkupdates` — likely a file wasn't copied or server wasn't restarted.

*Version 1.0 | March 2026 | Keep in sync with requirements.txt and DEVELOPER_GUIDE.md*
