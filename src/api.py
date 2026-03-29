# filename: api.py
# --- Begin of file ---

import os
import logging
import json
import shutil
from typing import Any, Dict, List
from datetime import datetime
import numpy as np

YEARS = 30

from fastapi import FastAPI, Body, HTTPException, Path
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# refresh_assets import disabled — auto-refresh is off; asset model managed by asset_calibration.py pipeline
# from refresh_assets import refresh_assets_if_stale
from loaders import (
    load_tax_unified,
    load_sched,
    load_inflation_yearly,
    load_shocks,
    load_system_shocks,
    load_allocation_yearly_accounts,
    validate_alloc_accounts,
    load_person,
    load_income,
    load_economic_policy,
)
from simulator_new import run_accounts_new

from income_core import build_income_streams


from simulation_core import simulate_balances
from snapshot import save_raw_snapshot_accounts
from reporting import report_and_plot_accounts, compute_account_ending_balances

# Paths
APP_ROOT = os.path.abspath(os.path.dirname(__file__))
UI_DIST = os.path.join(APP_ROOT, "ui", "dist")
ASSETS_DIR = os.path.join(UI_DIST, "assets")
COMMON_ASSETS_JSON = os.path.join(APP_ROOT, "config", "assets.json")
COMMON_RMD_JSON    = os.path.join(APP_ROOT, "config", "rmd.json")

# Profile versioning
VERSIONABLE_FILES  = {
    "person.json",
    "withdrawal_schedule.json",
    "allocation_yearly.json",
    "income.json",
    "inflation_yearly.json",
    "shocks_yearly.json",
    "economic.json",
}
MAX_VERSIONS       = 50  # auto-prune oldest beyond this

PROFILES_ROOT = os.path.join(APP_ROOT, "profiles")
DEFAULT_PROFILE = "default"

# Files that live at APP_ROOT, not per-profile
ECONOMIC_GLOBAL_PATH = os.path.join(APP_ROOT, "economicglobal.json")
TAX_GLOBAL_PATH      = os.path.join(APP_ROOT, "config", "taxes_states_mfj_single.json")
BENCHMARKS_GLOBAL_PATH = os.path.join(APP_ROOT, "benchmarks.json")
SYSTEM_SHOCKS_PATH   = os.path.join(APP_ROOT, "system_shocks.json")
SYSTEM_SHOCK_PRESETS = {"average", "below_average", "bad", "worst"}

# Names that must NOT appear in the Configure tab (global/hidden files)
_GLOBAL_ONLY_NAMES = {
    "economicglobal.json",
    "taxes_states_mfj_single.json",
    "benchmarks.json",
    "assets.json",
}

# ── Source file manifest — computed at import time ───────────────────────────
import hashlib as _hashlib

def _load_manifest_lock() -> Dict[str, str]:
    """
    Load manifest.lock and return the hashes dict.
    manifest.lock is Claude's voucher — lists every file Claude provided
    with the hash Claude computed when shipping it.
    The server tracks exactly these files — no hardcoding needed.
    Adding a file to manifest.lock automatically adds it to the startup check.
    """
    _mpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.lock")
    try:
        with open(_mpath, "r", encoding="utf-8") as _f:
            _data = json.load(_f)
        return _data.get("hashes", {})
    except Exception as _e:
        print(f"[manifest] WARNING: could not load manifest.lock: {_e}")
        return {}

# Files to track = exactly what manifest.lock["hashes"] says Claude provided.
# No hardcoding — manifest.lock is the single source of truth.
_MANIFEST_LOCK_HASHES: Dict[str, str] = _load_manifest_lock()
MANIFEST_FILES = list(_MANIFEST_LOCK_HASHES.keys())

def _file_sha256(path: str) -> str:
    """Return hex SHA256 of a file, or 'missing' if not found."""
    try:
        h = _hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]  # first 16 chars — enough for change detection
    except FileNotFoundError:
        return "missing"
    except Exception as e:
        return f"error:{e}"

def _build_manifest() -> Dict[str, Any]:
    """Build a manifest of all tracked source files."""
    import datetime as _dt
    files = {}
    for name in MANIFEST_FILES:
        path = os.path.join(APP_ROOT, name)
        files[name] = {
            "sha256_short": _file_sha256(path),
            "exists":       os.path.isfile(path),
            "size_bytes":   os.path.getsize(path) if os.path.isfile(path) else 0,
            "mtime":        _dt.datetime.fromtimestamp(
                                os.path.getmtime(path)
                            ).isoformat(timespec="seconds") if os.path.isfile(path) else None,
        }
    return {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "app_root":     APP_ROOT,
        "files":        files,
    }

# Compute manifest once at startup
_STARTUP_MANIFEST: Dict[str, Any] = {}


app = FastAPI(title="eNDinomics API", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    """On server start: build file manifest and snapshot all user profiles."""
    global _STARTUP_MANIFEST
    _STARTUP_MANIFEST = _build_manifest()

    # Log manifest summary
    print("[startup] Source file manifest:")
    for name, info in _STARTUP_MANIFEST["files"].items():
        status = info["sha256_short"] if info["exists"] else "⚠ MISSING"
        print(f"  {name:<30} {status}")

    # Auto-snapshot all non-default profiles
    profiles_dir = os.path.join(APP_ROOT, "profiles")
    if os.path.isdir(profiles_dir):
        for profile in os.listdir(profiles_dir):
            if profile.startswith(("default", "__", ".")):
                continue
            pdir = os.path.join(profiles_dir, profile)
            if not os.path.isdir(pdir):
                continue
            try:
                # Only snapshot if last version is >1 hour old — prevents test/dev
                # restarts from spamming version history
                history = _load_version_manifest(profile)
                should_snap = True
                if history:
                    import datetime as _dt2
                    last_ts = history[-1].get("ts", "")
                    try:
                        last_dt = _dt2.datetime.fromisoformat(last_ts)
                        age_mins = (_dt2.datetime.now() - last_dt).total_seconds() / 60
                        if age_mins < 60:
                            print(f"[startup] Skipping snapshot for '{profile}' — last version {age_mins:.0f}m ago")
                            should_snap = False
                    except Exception:
                        pass
                if should_snap:
                    v = _snapshot_profile_version(
                        profile,
                        note="server startup — auto-checkpoint",
                        source="auto"
                    )
                    print(f"[startup] Versioned profile '{profile}' → v{v}")
            except Exception as e:
                print(f"[startup] Could not version profile '{profile}': {e}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve built UI assets
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR, html=False), name="assets")


@app.get("/manifest")
def get_manifest() -> Dict[str, Any]:
    """
    Return the server's source file manifest (SHA256 hashes, sizes, mtimes).
    Used by test_flags.py --checkupdates to verify deployed files match local files.
    """
    if not _STARTUP_MANIFEST:
        return _build_manifest()
    return _STARTUP_MANIFEST


@app.get("/health")
def health() -> Dict[str, Any]:
    """
    Returns server health + market data freshness.
    UI shows a warning banner if market data is stale.
    """
    result: Dict[str, Any] = {"status": "ok"}
    try:
        _cache_dir = os.path.join(os.path.dirname(__file__), "..", "market_data", "cache", "store")
        _cache_dir = os.path.abspath(_cache_dir)
        from market_data.cache.cache import MarketDataCache
        _cache = MarketDataCache(_cache_dir)
        _status = _cache.status()

        stale  = [r for r in _status if not r["fresh"]]
        fresh  = [r for r in _status if r["fresh"]]

        # Most recent fetch timestamp across all entries
        import time as _time
        last_refresh = None
        if _status:
            newest_age = min(r["age_days"] for r in _status)
            last_refresh_ts = _time.time() - newest_age * 86400
            import datetime as _dt
            last_refresh = _dt.datetime.fromtimestamp(last_refresh_ts).strftime("%Y-%m-%d %H:%M")

        result["market_data"] = {
            "last_refresh":  last_refresh,
            "fresh_entries": len(fresh),
            "stale_entries": len(stale),
            "stale_keys":    [r["key"] for r in stale],
            "is_stale":      len(stale) > 0,
            "refresh_cmd":   "./refresh_model.sh",
        }
    except Exception as _e:
        result["market_data"] = {
            "last_refresh":  None,
            "is_stale":      True,
            "error":         str(_e),
            "refresh_cmd":   "./refresh_model.sh",
        }
    return result


@app.get("/")
def serve_index():
    index_path = os.path.join(UI_DIST, "index.html")
    if not os.path.isfile(index_path):
        raise HTTPException(status_code=404, detail=f"UI index not found: {index_path}")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/help.html")
def serve_help():
    path = os.path.join(UI_DIST, "help.html")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="help.html not found")
    return FileResponse(path, media_type="text/html")


@app.get("/favicon.ico")
def serve_favicon():
    path = os.path.join(UI_DIST, "favicon.ico")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="favicon.ico not found")
    return FileResponse(path, media_type="image/x-icon")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, obj: Dict[str, Any]) -> None:
    """Write JSON via temp file + os.replace to avoid SMB permission errors on existing files."""
    _ensure_dir(os.path.dirname(path))
    import tempfile as _tf2
    dir_ = os.path.dirname(path) or "."
    with _tf2.NamedTemporaryFile(mode="w", encoding="utf-8",
                                  dir=dir_, delete=False, suffix=".tmp") as tmp:
        json.dump(obj, tmp, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, path)


def _copy_file(src: str, dst: str) -> None:
    _ensure_dir(os.path.dirname(dst))
    shutil.copy(src, dst)  # copy without metadata to avoid SMB permission issues


def _write_run_meta(run_dir: str, profile: str, run_id: str, run_info: Dict[str, Any]) -> None:
    # Read the current config version so the run is linked to the config it ran on
    history = _load_version_manifest(profile)
    if history:
        latest = history[-1]
        config_version    = latest["v"]
        config_version_ts = latest["ts"]
        config_version_note = latest.get("note", "")
    else:
        config_version      = None
        config_version_ts   = None
        config_version_note = ""

    meta = {
        "profile":            profile,
        "run_id":             run_id,
        "run_info":           dict(run_info or {}),
        "config_version":     config_version,
        "config_version_ts":  config_version_ts,
        "config_version_note": config_version_note,
    }
    path = os.path.join(run_dir, "run_meta.json")
    _write_json(path, meta)



def _versions_dir(profile: str) -> str:
    return os.path.join(_profile_dir(profile), ".versions")

def _version_manifest_path(profile: str) -> str:
    return os.path.join(_versions_dir(profile), "profile_history.json")

def _load_version_manifest(profile: str) -> List[Dict[str, Any]]:
    path = _version_manifest_path(profile)
    if not os.path.isfile(path):
        return []
    try:
        with open(path) as f:
            return json.load(f) or []
    except Exception:
        return []

def _save_version_manifest(profile: str, history: List[Dict[str, Any]]) -> None:
    vdir = _versions_dir(profile)
    _ensure_dir(vdir)
    with open(_version_manifest_path(profile), "w") as f:
        json.dump(history, f, indent=2)

def _snapshot_profile_version(profile: str, note: str = "", source: str = "auto") -> int:
    """
    Snapshot the current versionable files into .versions/vN/.
    Returns the new version number.
    Auto-prunes versions beyond MAX_VERSIONS.
    """
    history    = _load_version_manifest(profile)
    next_v     = (history[-1]["v"] + 1) if history else 1
    vdir       = _versions_dir(profile)
    snap_dir   = os.path.join(vdir, f"v{next_v}")
    _ensure_dir(snap_dir)

    files_saved = []
    for fname in VERSIONABLE_FILES:
        src_path = _profile_json_path(profile, fname)
        if os.path.isfile(src_path):
            import shutil
            try:
                with open(src_path, "r", encoding="utf-8") as _fi:
                    _fc = _fi.read()
                snap_dst = os.path.join(snap_dir, fname)
                import tempfile as _tf4
                with _tf4.NamedTemporaryFile(mode="w", encoding="utf-8",
                                              dir=snap_dir, delete=False, suffix=".tmp") as _tmp:
                    _tmp.write(_fc)
                    _tmp_path = _tmp.name
                os.replace(_tmp_path, snap_dst)
            except Exception as _se:
                print(f"[snapshot] Could not snapshot {fname}: {_se}")
            files_saved.append(fname)

    history.append({
        "v":             next_v,
        "ts":            __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "note":          note or "manual save",
        "source":        source,
        "files_changed": files_saved,
    })

    # Auto-prune oldest beyond MAX_VERSIONS
    if len(history) > MAX_VERSIONS:
        old_entries = history[:-MAX_VERSIONS]
        history     = history[-MAX_VERSIONS:]
        for entry in old_entries:
            import shutil
            old_dir = os.path.join(vdir, f"v{entry['v']}")
            if os.path.isdir(old_dir):
                shutil.rmtree(old_dir, ignore_errors=True)

    _save_version_manifest(profile, history)
    return next_v


def _default_json_names() -> List[str]:
    # Only per-profile files; global files (taxes, benchmarks, economicglobal) live at APP_ROOT
    return [
        "allocation_yearly.json",
        "withdrawal_schedule.json",
        "shocks_yearly.json",
        "inflation_yearly.json",
        "person.json",
        "income.json",
        "economic.json",
        # rmd.json is a shared common file at src/config/rmd.json — not per-profile
    ]


def _profile_dir(profile: str) -> str:
    return os.path.join(PROFILES_ROOT, profile)


def _profile_reports_dir(profile: str) -> str:
    return os.path.join(_profile_dir(profile), "reports")


def _profile_json_path(profile: str, name: str) -> str:
    return os.path.join(_profile_dir(profile), name)


def _default_scaffold(name: str) -> Dict[str, Any]:
    if name == "allocation_yearly.json":
        return {"accounts": [], "starting": {}, "deposits": [], "global_allocation": {}, "overrides": []}
    if name == "withdrawal_schedule.json":
        return {"floor_k": 0, "schedule": []}
    if name == "inflation_yearly.json":
        return {"inflation": []}
    if name == "shocks_yearly.json":
        return {"mode": "augment", "events": []}
    if name == "taxes_states_mfj_single.json":
        # Global file - should not be scaffolded per-profile; return empty sentinel
        return {"federal": {}, "states": {}}
    if name == "person.json":
        return {
            "current_age": 65,
            "birth_year": 0,
            "assumed_death_age": 90,
            "filing_status": "MFJ",
            "spouse": {
                "name": "",
                "birth_year": 0,
                "sole_beneficiary_for_ira": false
            },
            "beneficiaries": {
                "primary": [],
                "contingent": []
            },
            "rmd_policy": {
                "extra_handling": "reinvest_in_brokerage"
            },
            "roth_conversion_policy": {
                "enabled": False,
                "window_years": ["now-75"],
                "keepit_below_max_marginal_fed_rate": "fill the bracket",
                "avoid_niit": True,
                "rmd_assist": "convert",
                "tax_payment_source": "BROKERAGE",
                "irmaa_guard": {"enabled": False}
            }
        }
    if name == "income.json":
        return {
            "w2": [],
            "rental": [],
            "interest": [],
            "ordinary_other": [],
            "qualified_div": [],
            "cap_gains": [],
        }
    if name == "rmd.json":
        return {"factors": []}
    if name == "economic.json":
        return {"defaults": {}, "overrides": []}
    if name == "benchmarks.json":
        return {"benchmarks": []}
    return {}


def _ensure_default_profile() -> None:
    _ensure_dir(PROFILES_ROOT)
    default_dir = _profile_dir(DEFAULT_PROFILE)
    _ensure_dir(default_dir)
    for name in _default_json_names():
        p = _profile_json_path(DEFAULT_PROFILE, name)
        if not os.path.isfile(p):
            _write_json(p, _default_scaffold(name))
    _ensure_dir(_profile_reports_dir(DEFAULT_PROFILE))


_ensure_default_profile()

# Profiles endpoints
@app.get("/profiles")
def list_profiles():
    _ensure_dir(PROFILES_ROOT)
    names = []
    for d in os.listdir(PROFILES_ROOT):
        p = os.path.join(PROFILES_ROOT, d)
        if os.path.isdir(p):
            names.append(d)
    names.sort()
    return {"profiles": names}


@app.post("/profiles/create")
def create_profile(payload: Dict[str, Any] = Body(...)):
    name = str(payload.get("name", "")).strip()
    source = str(payload.get("source", "")).strip()

    if not name:
        raise HTTPException(status_code=400, detail="Profile name required.")
    if name == DEFAULT_PROFILE:
        raise HTTPException(status_code=400, detail="Cannot create or overwrite the default profile.")
    dest_dir = _profile_dir(name)
    if os.path.exists(dest_dir):
        raise HTTPException(status_code=400, detail="Profile already exists.")
    _ensure_dir(dest_dir)

    clone_version = payload.get("clone_version")  # specific version number to clone from

    if source == "clean":
        for n in _default_json_names():
            _write_json(_profile_json_path(name, n), _default_scaffold(n))
    else:
        src_profile = source if source and source != "default" else DEFAULT_PROFILE
        src_dir = _profile_dir(src_profile)
        if not os.path.isdir(src_dir):
            raise HTTPException(status_code=404, detail=f"Source profile '{src_profile}' not found.")

        # Determine source directory — versioned snapshot or current
        if clone_version is not None:
            version_dir = os.path.join(_versions_dir(src_profile), f"v{clone_version}")
            if not os.path.isdir(version_dir):
                raise HTTPException(status_code=404, detail=f"Version v{clone_version} not found in '{src_profile}'.")
            file_src_dir = version_dir
        else:
            file_src_dir = src_dir

        for n in _default_json_names():
            src_path = os.path.join(file_src_dir, n)
            # Fallback to current profile file if not in versioned snapshot
            if not os.path.isfile(src_path):
                src_path = _profile_json_path(src_profile, n)
            dst_path = _profile_json_path(name, n)
            if os.path.isfile(src_path):
                try:
                    with open(src_path, "r", encoding="utf-8") as _fi:
                        _fc = _fi.read()
                    with open(dst_path, "w", encoding="utf-8") as _fo:
                        _fo.write(_fc)
                except Exception:
                    _copy_file(src_path, dst_path)  # fallback
            else:
                _write_json(dst_path, _default_scaffold(n))

    _ensure_dir(_profile_reports_dir(name))
    return {"ok": True, "profile": name}


@app.post("/profiles/delete")
def delete_profile(payload: Dict[str, Any] = Body(...)):
    profile = str(payload.get("profile", "")).strip()
    if not profile:
        raise HTTPException(status_code=400, detail="profile is required.")
    if profile == DEFAULT_PROFILE:
        raise HTTPException(status_code=403, detail="Cannot delete the default profile.")
    pdir = _profile_dir(profile)
    if not os.path.isdir(pdir):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found.")
    try:
        shutil.rmtree(pdir)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _strip_meta_keys(d: dict) -> dict:
    """Return a copy of d with 'readme' and '_comment*' keys removed."""
    return {k: v for k, v in d.items() if k != "readme" and not k.startswith("_comment")}


def _extract_meta_keys(d: dict) -> dict:
    """Return only 'readme' and '_comment*' keys from d."""
    return {k: v for k, v in d.items() if k == "readme" or k.startswith("_comment")}


@app.get("/profile-config/{profile}/{name}")
def get_profile_config(
    profile: str = Path(..., description="Profile name"),
    name: str = Path(..., description="Config file name, e.g. allocation_yearly.json"),
):
    path = _profile_json_path(profile, name)
    # Fallback: system config files (cape_config.json, assets.json, etc.)
    # live in src/config/ not in profiles/. Check there before returning 404.
    if not os.path.isfile(path):
        config_path = os.path.join(APP_ROOT, "config", name)
        if os.path.isfile(config_path):
            path = config_path
        else:
            raise HTTPException(status_code=404, detail=f"{name} not found in profile '{profile}'.")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        readme = data.get("readme")
        editable = _strip_meta_keys(data)
        return {
            "profile": profile,
            "name": name,
            "content": json.dumps(editable, indent=2),
            "readme": readme,  # None if not present
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/template/{name}")
def download_template(name: str = Path(..., description="Config filename e.g. person.json")):
    """Return a default profile config file as a downloadable attachment."""
    # Sanitize — only allow known config filenames
    allowed = {
        "person.json", "withdrawal_schedule.json", "allocation_yearly.json",
        "income.json", "inflation_yearly.json", "shocks_yearly.json",
        "economic.json",
        "cape_config.json",
    }
    if name not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown template file: {name}")
    path = _profile_json_path("default", name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{name} not found in default profile")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/profile-config")
def save_profile_json(payload: Dict[str, Any] = Body(...)):
    profile = str(payload.get("profile", "")).strip()
    name = str(payload.get("name", "")).strip()
    content = payload.get("content")

    if not profile or not name or content is None:
        raise HTTPException(status_code=400, detail="Missing profile, name or content.")
    if profile == DEFAULT_PROFILE:
        raise HTTPException(status_code=403, detail="Default profile is non-editable.")

    if not name.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are supported.")

    try:
        incoming = json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    path = _profile_json_path(profile, name)

    # Re-merge readme and _comment keys from the file on disk — never lose them on save
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            meta = _extract_meta_keys(existing)
        except Exception:
            meta = {}
    else:
        meta = {}

    # Strip any meta keys the editor may have accidentally included, then re-apply from disk
    merged = _strip_meta_keys(incoming)
    merged.update(meta)

    # Snapshot current state before overwriting (versioning)
    note = str(payload.get("version_note", "")).strip() or f"saved {name}"
    if name in VERSIONABLE_FILES:
        try:
            _source = str(payload.get("version_source", "auto"))
            _snapshot_profile_version(profile, note=note, source=_source)
        except Exception as _ve:
            logger.warning("Version snapshot failed (non-fatal): %s", _ve)

    try:
        import tempfile as _tf3
        dir_ = os.path.dirname(path) or "."
        with _tf3.NamedTemporaryFile(mode="w", encoding="utf-8",
                                      dir=dir_, delete=False, suffix=".tmp") as tmp:
            json.dump(merged, tmp, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, path)
        return {"ok": True, "note": note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Profile versioning endpoints ──────────────────────────────────────────

@app.get("/profile/{profile}/versions")
def list_profile_versions(profile: str):
    """List all saved versions for a profile."""
    if not os.path.isdir(_profile_dir(profile)):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    history = _load_version_manifest(profile)
    return {"profile": profile, "versions": history}


@app.get("/profile/{profile}/versions/{v}/{name}")
def get_version_file(profile: str, v: int, name: str):
    """Return content of a specific file from a version snapshot for preview."""
    if not os.path.isdir(_profile_dir(profile)):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    if not name.lower().endswith(".json") or "/" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    snap_path = os.path.join(_versions_dir(profile), f"v{v}", name)
    if not os.path.isfile(snap_path):
        raise HTTPException(status_code=404, detail=f"v{v}/{name} not found")
    try:
        with open(snap_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        editable = _strip_meta_keys(data)
        return {"profile": profile, "v": v, "name": name, "content": json.dumps(editable, indent=2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/profile/{profile}/restore/{v}")
def restore_profile_version(profile: str, v: int):
    """
    Restore profile to version v.
    First saves current state as a new version (auto-save before restore),
    then copies vN files back to profile root.
    """
    if not os.path.isdir(_profile_dir(profile)):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    if profile == DEFAULT_PROFILE:
        raise HTTPException(status_code=403, detail="Cannot restore default profile")

    vdir     = _versions_dir(profile)
    snap_dir = os.path.join(vdir, f"v{v}")
    if not os.path.isdir(snap_dir):
        raise HTTPException(status_code=404, detail=f"Version v{v} not found")

    # Save current state first so restore is always reversible
    history = _load_version_manifest(profile)
    saved_v = _snapshot_profile_version(profile, note=f"auto-save before restore to v{v}")

    # Copy vN files back to profile root
    import shutil
    files_restored = []
    for fname in VERSIONABLE_FILES:
        src_path = os.path.join(snap_dir, fname)
        if os.path.isfile(src_path):
            dst_path = _profile_json_path(profile, fname)
            try:
                # Read source content
                with open(src_path, "r", encoding="utf-8") as f_in:
                    content = f_in.read()
                # Write via temp file then replace — avoids SMB open-existing-file permission errors
                import tempfile as _tf
                dst_dir = os.path.dirname(dst_path)
                with _tf.NamedTemporaryFile(mode="w", encoding="utf-8",
                                            dir=dst_dir, delete=False, suffix=".tmp") as f_tmp:
                    f_tmp.write(content)
                    tmp_path = f_tmp.name
                os.replace(tmp_path, dst_path)
                files_restored.append(fname)
            except Exception as _re:
                print(f"[restore] Could not restore {fname}: {_re}")

    return {
        "ok":             True,
        "restored_to":    v,
        "auto_saved_as":  saved_v,
        "files_restored": files_restored,
    }


# Reports endpoints
@app.post("/roth-optimize")
def run_roth_optimizer_standalone(payload: Dict[str, Any] = Body(...)):
    """
    Standalone Roth optimizer endpoint — runs without a full Monte Carlo simulation.
    If run_id is provided, loads projected IRA balances from that snapshot.
    Otherwise uses person.json alone (falls back to compound growth estimate).
    """
    profile  = str(payload.get("profile", "") or DEFAULT_PROFILE).strip()
    run_id   = payload.get("run_id")
    state    = str(payload.get("state", "California"))
    filing   = str(payload.get("filing", "MFJ"))

    person_path = os.path.join(PROFILES_ROOT, profile, "person.json")
    if not os.path.isfile(person_path):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")

    try:
        from roth_optimizer import optimize_roth_conversion_full
        person_cfg = load_person(person_path)

        # Override state/filing from request
        person_cfg["state"]          = state
        person_cfg["filing_status"]  = filing

        # Load projected portfolio from snapshot if run_id provided
        sim_portfolio: Dict[str, Any] = {}
        sim_summary:   Dict[str, Any] = {}
        if run_id:
            snap_path = os.path.join(PROFILES_ROOT, profile, "reports", run_id,
                                     "raw_snapshot_accounts.json")
            if os.path.isfile(snap_path):
                with open(snap_path) as f:
                    snap = json.load(f)
                sim_portfolio = snap.get("portfolio", {})
                sim_summary   = snap.get("summary", {})

        result = optimize_roth_conversion_full(
            person_cfg=person_cfg,
            simulation_summary=sim_summary,
            simulation_portfolio=sim_portfolio,
            withdrawals={},
        )
        return {"ok": True, "roth_optimizer": result}
    except Exception as e:
        logger.exception("roth-optimize failed")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/profile/{profile}/snapshot")
def snapshot_profile(profile: str, payload: Dict[str, Any] = Body(...)):
    """Create a version snapshot without modifying any files — used by Save Version button."""
    if not os.path.isdir(_profile_dir(profile)):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    if profile == DEFAULT_PROFILE:
        raise HTTPException(status_code=403, detail="Cannot version default profile")
    note   = str(payload.get("note", "")).strip() or "manual checkpoint"
    source = str(payload.get("source", "user"))
    try:
        v = _snapshot_profile_version(profile, note=note, source=source)
        return {"ok": True, "v": v, "note": note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/profile/{profile}/versions/{v}/{filename}")
def get_version_file(profile: str, v: int, filename: str):
    """Return the content of a specific file from a saved version snapshot."""
    if not os.path.isdir(_profile_dir(profile)):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    allowed = VERSIONABLE_FILES
    if filename not in allowed:
        raise HTTPException(status_code=400, detail=f"File '{filename}' not versionable")
    snap_dir  = os.path.join(_versions_dir(profile), f"v{v}")
    file_path = os.path.join(snap_dir, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"v{v}/{filename} not found")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        editable = _strip_meta_keys(data)
        return {"v": v, "filename": filename, "content": json.dumps(editable, indent=2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.delete("/profile/{profile}/versions/{v}")
def delete_profile_version(profile: str, v: int):
    """Delete a single version snapshot from history."""
    if not os.path.isdir(_profile_dir(profile)):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    if profile == DEFAULT_PROFILE:
        raise HTTPException(status_code=403, detail="Cannot modify default profile")
    history = _load_version_manifest(profile)
    entry = next((e for e in history if e["v"] == v), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Version v{v} not found")
    # Remove snapshot directory
    snap_dir = os.path.join(_versions_dir(profile), f"v{v}")
    if os.path.isdir(snap_dir):
        import shutil
        shutil.rmtree(snap_dir, ignore_errors=True)
    # Remove from manifest
    history = [e for e in history if e["v"] != v]
    _save_version_manifest(profile, history)
    return {"ok": True, "deleted_v": v}


@app.delete("/profile/{profile}/versions")
def clear_profile_versions(profile: str, keep: int = 0):
    """
    Admin: delete version history for a profile.
    keep=0 deletes everything; keep=N keeps the N most recent versions.
    """
    if not os.path.isdir(_profile_dir(profile)):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    vdir = _versions_dir(profile)
    if not os.path.isdir(vdir):
        return {"ok": True, "deleted": 0, "kept": 0}
    history = _load_version_manifest(profile)
    if keep <= 0:
        # Delete everything
        import shutil
        shutil.rmtree(vdir, ignore_errors=True)
        return {"ok": True, "deleted": len(history), "kept": 0}
    else:
        # Keep last N, delete the rest
        to_keep   = history[-keep:]
        to_delete = history[:-keep]
        for entry in to_delete:
            import shutil
            old_dir = os.path.join(vdir, f"v{entry['v']}")
            if os.path.isdir(old_dir):
                shutil.rmtree(old_dir, ignore_errors=True)
        _save_version_manifest(profile, to_keep)
        return {"ok": True, "deleted": len(to_delete), "kept": len(to_keep)}


@app.get("/reports/{profile}")
def list_reports_profile(profile: str):
    rdir = _profile_reports_dir(profile)
    if not os.path.isdir(rdir):
        return {"runs": []}
    run_ids = sorted(
        [d for d in os.listdir(rdir) if d.startswith("run_") and os.path.isdir(os.path.join(rdir, d))],
        reverse=False,
    )
    # Enrich each run with config_version from its run_meta.json
    runs = []
    for rid in run_ids:
        meta_path = os.path.join(rdir, rid, "run_meta.json")
        config_version = None
        config_version_ts = None
        config_version_note = ""
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                config_version      = meta.get("config_version")
                config_version_ts   = meta.get("config_version_ts")
                config_version_note = meta.get("config_version_note", "")
            except Exception:
                pass
        runs.append({
            "run_id":              rid,
            "config_version":      config_version,
            "config_version_ts":   config_version_ts,
            "config_version_note": config_version_note,
        })
    return {"runs": runs}


@app.get("/reports")
def list_reports_default():
    return list_reports_profile(DEFAULT_PROFILE)


@app.delete("/reports/{profile}")
def clear_reports_profile(profile: str):
    rdir = _profile_reports_dir(profile)
    if not os.path.isdir(rdir):
        _ensure_dir(rdir)
        return {"ok": True, "runs": []}
    for d in os.listdir(rdir):
        p = os.path.join(rdir, d)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except Exception:
            pass
    return {"ok": True, "runs": []}


@app.post("/reports/clear")
def clear_reports_post(payload: Dict[str, Any] = Body(...)):
    profile = str(payload.get("profile", "")).strip()
    if not profile:
        raise HTTPException(status_code=400, detail="profile is required.")
    rdir = _profile_reports_dir(profile)
    if not os.path.isdir(rdir):
        _ensure_dir(rdir)
        return {"ok": True, "runs": []}
    for d in os.listdir(rdir):
        p = os.path.join(rdir, d)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except Exception:
            pass
    return {"ok": True, "runs": []}


@app.post("/profiles/clear-reports")
def clear_reports_profile_legacy(payload: Dict[str, Any] = Body(...)):
    profile = str(payload.get("profile", "")).strip()
    if not profile:
        raise HTTPException(status_code=400, detail="profile is required.")
    rdir = _profile_reports_dir(profile)
    if not os.path.isdir(rdir):
        _ensure_dir(rdir)
        return {"ok": True, "runs": []}
    for d in os.listdir(rdir):
        p = os.path.join(rdir, d)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except Exception:
            pass
    return {"ok": True, "runs": []}


# Artifact serving
@app.get("/artifact/{profile}/{run_id}/{name}")
def get_artifact(profile: str, run_id: str, name: str):
    run_dir = os.path.join(_profile_reports_dir(profile), run_id)
    path = os.path.join(run_dir, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{name} not found for {profile}/{run_id}")
    return FileResponse(path)


# /run endpoint
@app.post("/run")
def run_simulation(payload: Dict[str, Any] = Body(...)):
    # 1) Canonical request parameters
    profile = str(payload.get("profile", "")).strip() or DEFAULT_PROFILE

    def P(name: str) -> str:
        return _profile_json_path(profile, name)

    tax_path = payload.get("tax") or TAX_GLOBAL_PATH
    withdraw_path = payload.get("withdraw") or P("withdrawal_schedule.json")
    infl_path = payload.get("inflation") or P("inflation_yearly.json")
    shocks_path = payload.get("shocks") or P("shocks_yearly.json")
    alloc_path = payload.get("alloc_yearly") or P("allocation_yearly.json")
    person_path = payload.get("person") or P("person.json")
    income_path = payload.get("income") or P("income.json")
    # rmd.json: per-profile overrides common; fall back to src/config/rmd.json
    _profile_rmd = P("rmd.json")
    rmd_path = payload.get("rmd") or (
        _profile_rmd if os.path.isfile(_profile_rmd) else COMMON_RMD_JSON
    )
    economic_path        = payload.get("economic") or P("economic.json")
    economic_global_path = ECONOMIC_GLOBAL_PATH if os.path.isfile(ECONOMIC_GLOBAL_PATH) else None
    # Always resolve assets.json from APP_ROOT (global file, never per-profile)
    assets_path = payload.get("assets") or COMMON_ASSETS_JSON

    paths = int(payload.get("paths", 500))
    steps_per_year = int(payload.get("steps_per_year", payload.get("spy", 2)))
    dollars = str(payload.get("dollars", "current"))
    base_year = int(payload.get("base_year", 2026))
    state = str(payload.get("state", "California"))
    filing = str(payload.get("filing", "MFJ"))
    shocks_mode_req = payload.get("shocks_mode")

    ignore_withdrawals = bool(payload.get("ignore_withdrawals", False))
    ignore_rmds = bool(payload.get("ignore_rmds", False))
    ignore_conversions = bool(payload.get("ignore_conversions", False))
    ignore_taxes = bool(payload.get("ignore_taxes", False))
    simulation_mode = str(payload.get("simulation_mode", "automatic")).lower().strip()

    rebalance_threshold = float(payload.get("rebalance_threshold", 0.10))
    rebalance_brokerage_enabled = bool(payload.get("rebalance_brokerage_enabled", False))
    rebalance_brokerage_capgain_limit_k = float(payload.get("rebalance_brokerage_capgain_limit_k", 0.0))

    # 2) Run directory
    reports_dir = _profile_reports_dir(profile)
    _ensure_dir(reports_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{ts}"
    run_dir = os.path.join(reports_dir, run_id)
    _ensure_dir(run_dir)

    # 3) Shocks override
    if shocks_path:
        shocks_json: Dict[str, Any] = {}
        if os.path.isfile(shocks_path):
            with open(shocks_path, "r", encoding="utf-8") as f:
                shocks_json = json.load(f) or {}
        mode_base = shocks_json.get("mode", "augment")

        # Only override file mode when user explicitly picks augment or override.
        # "none" is handled later via ignore_shocks.
        if shocks_mode_req in ("augment", "override"):
            shocks_json["mode"] = shocks_mode_req

        shocks_mode = shocks_json.get("mode", mode_base)
        shocks_override_path = os.path.join(run_dir, "shocks_override.json")
        with open(shocks_override_path, "w", encoding="utf-8") as f:
            json.dump(shocks_json, f, indent=2)
        shocks_path_effective = shocks_override_path
    else:
        shocks_path_effective = shocks_path
        shocks_mode = shocks_mode_req or "augment"




    # 4) Withdrawals override if ignoring
    withdraw_path_effective = withdraw_path
    if ignore_withdrawals and withdraw_path:
        base_w: Dict[str, Any] = {}
        if os.path.isfile(withdraw_path):
            with open(withdraw_path, "r", encoding="utf-8") as f:
                base_w = json.load(f) or {}
        base_w["schedule"] = []
        withdraw_override_path = os.path.join(run_dir, "withdraw_override.json")
        with open(withdraw_override_path, "w", encoding="utf-8") as f:
            json.dump(base_w, f, indent=2)
        withdraw_path_effective = withdraw_override_path

    # 5) Economic override marker if ignoring RMDs or conversions
    economic_path_effective = economic_path
    if (ignore_rmds or ignore_conversions) and economic_path:
        # Merge global + profile BEFORE writing the override file so withdrawal_sequence is preserved
        global_e: Dict[str, Any] = {}
        if economic_global_path and os.path.isfile(economic_global_path):
            with open(economic_global_path, "r", encoding="utf-8") as f:
                global_e = json.load(f) or {}
        profile_e: Dict[str, Any] = {}
        if os.path.isfile(economic_path):
            with open(economic_path, "r", encoding="utf-8") as f:
                profile_e = json.load(f) or {}
        # Deep merge: global base, profile on top
        def _merge(base, over):
            r = dict(base)
            for k, v in over.items():
                if k in r and isinstance(r[k], dict) and isinstance(v, dict):
                    r[k] = _merge(r[k], v)
                else:
                    r[k] = v
            return r
        base_e = _merge(global_e, profile_e)
        economic_override_path = os.path.join(run_dir, "economic_override.json")
        with open(economic_override_path, "w", encoding="utf-8") as f:
            json.dump(base_e, f, indent=2)
        economic_path_effective = economic_override_path

    # 6) Load configs — load person first so current_age is available for schedule parsing
    tax_cfg    = load_tax_unified(tax_path, state=state, filing=filing)
    person_cfg = load_person(person_path)

    # Extract current_age for age-based withdrawal schedule conversion
    _sched_current_age = float(person_cfg.get("current_age") or 0.0) if person_cfg else 0.0
    _sched_target_age  = float(person_cfg.get("target_age") or
                               person_cfg.get("assumed_death_age") or 95.0) if person_cfg else 95.0
    _sched_n_years = max(10, min(60, int(_sched_target_age - _sched_current_age)))
    sched_arr, sched_base = load_sched(
        withdraw_path_effective,
        current_age=_sched_current_age,
        max_years=_sched_n_years,
    )
    # Derive scalar floor_k for legacy run_accounts path
    floor_k = float(sched_base.min()) if sched_base is not None and sched_base.size > 0 else 0.0

    # DEBUG: see what schedule we really loaded
    # debug removed
    # debug removed
    # debug removed
    # debug removed:", floor_k)


    infl_yearly = load_inflation_yearly(infl_path, years_count=30)

    # shocks_mode comes from the UI ("augment" / "override" / "none")
    # shocks_mode_req tells you whether the user explicitly chose it
    # shocks_mode comes from the request JSON; shocks_mode_req tells you if user set it explicitly

    # shocks_mode_req is the raw request field from the UI ("augment"/"override"/"none"/None)
    raw_shocks_mode = (shocks_mode_req or "").strip().lower()
    ignore_shocks = raw_shocks_mode == "none"

    
    if ignore_shocks:
        # User requested no shocks: pass no events to the engine
        shocks_events = []
        internal_shocks_mode = "augment"  # internal label; with no events, this does nothing
    elif raw_shocks_mode in SYSTEM_SHOCK_PRESETS:
        # System preset: load from system_shocks.json, ignore user shocks file
        shocks_events, _, _ = load_system_shocks(SYSTEM_SHOCKS_PATH, raw_shocks_mode)
        internal_shocks_mode = "override"  # system presets always use override
    else:
        shocks_events, shocks_mode_file, _ = (
            load_shocks(shocks_path_effective)
            if shocks_path_effective
            else ([], raw_shocks_mode, [])
        )
        # UI choice always wins over JSON file mode
        internal_shocks_mode = raw_shocks_mode or shocks_mode_file or "augment"

    alloc_accounts = load_allocation_yearly_accounts(alloc_path)
    validate_alloc_accounts(alloc_accounts)

    # NOTE: assets.json auto-refresh is DISABLED.
    # assets.json is now a versioned model artifact managed by the asset-model pipeline.
    # To update: run asset_calibration.py manually or deploy a new model version.
    # Do NOT re-enable this block until asset_calibration.py is production-ready.
    #
    # try:
    #     refresh_assets_if_stale(
    #         assets_path=COMMON_ASSETS_JSON,
    #         profiles_root=PROFILES_ROOT,
    #     )
    # except Exception as _e:
    #     print(f"[run] assets refresh skipped: {_e}")

    # person_cfg already loaded above (moved before load_sched for current_age)
    # debug removed if person_cfg else None)

    # Dynamic simulation years: target_age - current_age (default target=95, min 10, max 60)
    _current_age = int((person_cfg or {}).get("current_age", 55))
    _target_age  = int((person_cfg or {}).get("target_age",  95))
    _n_years     = max(10, min(60, _target_age - _current_age))
    # debug removed")

    income_cfg = load_income(income_path, current_age=float(_current_age), max_years=int(_n_years))
    econ_policy = load_economic_policy(economic_path_effective, global_path=economic_global_path)

    # 7) Run simulation
    ignore_withdrawals_flag = bool(ignore_withdrawals)
    ignore_rmds_flag = bool(ignore_rmds)
    ignore_conversions_flag = bool(ignore_conversions)
    shocks_mode_raw = (shocks_mode or "").lower()

    rmds_enabled = not ignore_rmds_flag
    
    # DEBUG: see what the server thinks the flags are

    shocks_mode_req_raw = (shocks_mode_req or "").lower()

    # Route all runs through run_accounts_new — it is now the primary simulator.
    # Shocks support will be added to run_accounts_new next; for now shocks_events
    # are passed but the simulator ignores non-empty events (no-op, safe to run).
    modular_core_only_test = (
        ignore_withdrawals_flag
        and ignore_rmds_flag
        and ignore_conversions_flag
    )

    modular_core_withdrawals_test = (
        not ignore_withdrawals_flag
        and ignore_rmds_flag
        and ignore_conversions_flag
    )

    # RMDs only: no discretionary withdrawals, RMDs ON, conversions OFF
    modular_rmd_only_test = (
        ignore_withdrawals_flag
        and not ignore_rmds_flag
        and ignore_conversions_flag
    )

    # Withdrawals + RMDs: both enabled, conversions OFF
    modular_withdrawals_rmd_test = (
        not ignore_withdrawals_flag
        and not ignore_rmds_flag
        and ignore_conversions_flag
    )

    # Withdrawals + RMDs + Conversions: all enabled
    # Conversions are handled inside simulator_new.py — routing flag just needs
    # to ensure apply_withdrawals_flag=True and sched is passed correctly.
    modular_withdrawals_rmd_conv_test = (
        not ignore_withdrawals_flag
        and not ignore_rmds_flag
        and not ignore_conversions_flag
    )

    # Withdrawals-only + Conversions ON
    modular_withdrawals_conv_test = (
        not ignore_withdrawals_flag
        and ignore_rmds_flag
        and not ignore_conversions_flag
    )

    # RMD-only + Conversions ON
    modular_rmd_conv_test = (
        ignore_withdrawals_flag
        and not ignore_rmds_flag
        and not ignore_conversions_flag
    )

    # Core-only + Conversions ON (no withdrawals, no RMDs, but conversions fire)
    modular_core_conv_test = (
        ignore_withdrawals_flag
        and ignore_rmds_flag
        and not ignore_conversions_flag
    )

    # Always True — run_accounts_new handles all cases
    modular_test = True

    # debug removed



    if modular_test:
        # debug removed
        rmds_enabled = not ignore_rmds_flag

        income_cfg = load_income(f"profiles/{profile}/income.json",
                         current_age=float((person_cfg or {}).get("current_age", 55)),
                         max_years=max(10, min(60, int((person_cfg or {}).get("target_age", 95)) - int((person_cfg or {}).get("current_age", 55)))))

        # ── Social Security injection from person.json ────────────────────────
        # If person.json has a 'social_security' block, compute SS income per year
        # and inject into income_cfg, overriding any manual ordinary_other entries.
        # This ensures correct start age, benefit amount, and 85% inclusion rule.
        _ss_cfg = (person_cfg or {}).get("social_security") or {}
        if _ss_cfg and not _ss_cfg.get("exclude_from_plan", False):
            _ca   = float(_current_age)
            _ta   = float((person_cfg or {}).get("target_age", 95))
            _ny   = int(_ta - _ca)
            _filing = str((person_cfg or {}).get("filing_status", "MFJ")).upper()

            # Self SS
            _self_monthly  = float(_ss_cfg.get("self_benefit_monthly", 0) or 0)
            _self_start    = int(_ss_cfg.get("self_start_age", 67) or 67)
            # Spouse SS
            _spouse_monthly = float(_ss_cfg.get("spouse_benefit_monthly", 0) or 0)
            _spouse_start   = int(_ss_cfg.get("spouse_start_age", 67) or 67)

            # Early/delayed adjustment: FRA=67 for born 1960+, 66 for born 1943-1954
            # Reduction: 5/9% per month early (first 36mo), 5/12% beyond
            # Credit: 8%/yr delayed past FRA up to age 70
            _birth_year = int((person_cfg or {}).get("birth_year", 1960) or 1960)
            _fra = 67 if _birth_year >= 1960 else (66 if _birth_year >= 1943 else 65)

            def _ss_adjustment(start_age, fra):
                months_diff = (start_age - fra) * 12
                if months_diff >= 0:
                    # Delayed: +8%/yr credit
                    return 1.0 + min(months_diff, 36) * 0.08 / 12
                else:
                    # Early: -5/9% per month first 36mo, -5/12% beyond
                    early_mo = abs(months_diff)
                    first36  = min(early_mo, 36)
                    beyond36 = max(0, early_mo - 36)
                    return 1.0 - (first36 * 5/9/100) - (beyond36 * 5/12/100)

            _self_adj   = _ss_adjustment(_self_start, _fra)
            _spouse_fra = 67 if int((_ss_cfg.get("spouse_birth_year") or
                          (person_cfg or {}).get("spouse", {}).get("birth_year", 1960)) or 1960) >= 1960 else 66
            _spouse_adj = _ss_adjustment(_spouse_start, _spouse_fra)

            _self_annual   = _self_monthly  * 12 * _self_adj
            _spouse_annual = _spouse_monthly * 12 * _spouse_adj

            # Build per-year SS array
            _ss_by_year = []
            for _y in range(_ny):
                _age = _ca + _y + 1
                _ss_gross = 0.0
                if _age >= _self_start:
                    _ss_gross += _self_annual
                if _age >= _spouse_start:
                    _ss_gross += _spouse_annual

                # 85% inclusion rule (simplified — full computation requires provisional income)
                # Provisional income = AGI + 50% SS; for most retirees with IRA income, 85% applies
                # We default to 85% and note in README that this is conservative
                _ss_taxable = _ss_gross * 0.85

                _ss_by_year.append(_ss_taxable)

            # Inject into income_cfg as ordinary_other (overrides manual entry if SS block present)
            if "ordinary_other" in income_cfg and hasattr(income_cfg["ordinary_other"], "__len__"):
                # Replace with computed SS values
                _arr = np.asarray(income_cfg["ordinary_other"], dtype=float)
                if len(_arr) < _ny:
                    _arr = np.concatenate([_arr, np.zeros(_ny - len(_arr))])
                # Override years where SS is active
                for _y, _ss in enumerate(_ss_by_year):
                    if _y < len(_arr):
                        _arr[_y] = _ss
                income_cfg["ordinary_other"] = _arr.tolist()
            else:
                income_cfg["ordinary_other"] = _ss_by_year

        elif _ss_cfg.get("exclude_from_plan", False):
            # Zero out SS entirely — portfolio-only sufficiency test
            if "ordinary_other" in income_cfg:
                _arr = np.asarray(income_cfg.get("ordinary_other", [0.0] * _n_years), dtype=float)
                income_cfg["ordinary_other"] = np.zeros_like(_arr).tolist()
        # ── End SS injection ──────────────────────────────────────────────────
        (
            w2_cur,
            rental_cur,
            interest_cur,
            ordinary_other_cur,
            qual_div_cur,
            cap_gains_cur,
        ) = build_income_streams(income_cfg, years=_n_years)

        # ── Apply dollar_type="future" deflation ─────────────────────────────
        # loaders.py computed per-year _is_future flags (1.0 = future/nominal).
        # future $ amounts are already nominal — divide by cumulative deflator
        # to convert to current USD so the simulator sees consistent real values.
        # current $ (default) amounts are already in real terms — no change needed.
        if infl_yearly is not None and len(infl_yearly) > 0:
            _infl_arr = np.asarray(infl_yearly, dtype=float)
            if len(_infl_arr) < _n_years:
                _infl_arr = np.concatenate([_infl_arr, np.full(_n_years - len(_infl_arr), _infl_arr[-1] if len(_infl_arr) > 0 else 0.03)])
            _deflator = np.cumprod(1.0 + _infl_arr[:_n_years])
        else:
            _deflator = np.ones(_n_years, dtype=float)

        for _inc_arr, _key in [
            (w2_cur,            "w2"),
            (rental_cur,        "rental"),
            (interest_cur,      "interest"),
            (ordinary_other_cur,"ordinary_other"),
            (qual_div_cur,      "qualified_div"),
            (cap_gains_cur,     "cap_gains"),
        ]:
            _is_fut = np.asarray(income_cfg.get(f"{_key}_is_future", np.zeros(_n_years)), dtype=float)
            if len(_is_fut) < _n_years:
                _is_fut = np.concatenate([_is_fut, np.zeros(_n_years - len(_is_fut))])
            for _y in range(_n_years):
                if _is_fut[_y] > 0.5:
                    # Convert nominal future amount to current USD
                    _inc_arr[_y] = _inc_arr[_y] / max(_deflator[_y], 1e-12)
        # ── End dollar_type deflation ─────────────────────────────────────────

        ordinary_income_cur_paths = np.zeros((paths, _n_years), dtype=float)
        qual_div_cur_paths = np.zeros((paths, _n_years), dtype=float)
        cap_gains_cur_paths = np.zeros((paths, _n_years), dtype=float)
        ytd_income_nom_paths = np.zeros((paths, _n_years), dtype=float)

        for y in range(_n_years):
            ordinary_income_cur_paths[:, y] = (
                w2_cur[y] + rental_cur[y] + interest_cur[y] + ordinary_other_cur[y]
            )
            qual_div_cur_paths[:, y] = qual_div_cur[y]
            cap_gains_cur_paths[:, y] = cap_gains_cur[y]

        sched_for_modular = None
        sched_base_for_modular = None
        apply_withdrawals_flag = False

        if modular_core_only_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_core_withdrawals_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True
        elif modular_rmd_only_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_withdrawals_rmd_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True
        elif modular_core_conv_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_withdrawals_conv_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True
        elif modular_rmd_conv_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False
        elif modular_withdrawals_rmd_conv_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True

        acct_names    = list(alloc_accounts.get("per_year_portfolios", {}).keys())
        starting_age  = int(person_cfg.get("current_age", 70)) if person_cfg else 70
        tira_age_gate = float(econ_policy.get("tira_age_gate", 59.5))

        conversion_enabled = bool(
            (person_cfg or {}).get("roth_conversion_policy", {}).get("enabled", False)
        )
        order_good = econ_policy.get("order_good_market", [])
        order_bad  = (
            econ_policy.get("order_bad_market_with_conversion", [])
            if conversion_enabled
            else econ_policy.get("order_bad_market", [])
        )

        def _is_brokerage(n): u = n.upper(); return "BROKERAGE" in u or "TAXABLE" in u
        def _is_trad(n):      u = n.upper(); return ("TRAD" in u or "TRADITIONAL" in u) and "ROTH" not in u
        def _is_roth(n):      return "ROTH" in n.upper()

        def _expand(tmpl, accts, allow_trad, allow_roth):
            seen, result = set(), []
            for token in tmpl:
                t = token.upper()
                if "BROKERAGE" in t or "TAXABLE" in t:
                    for a in accts:
                        if _is_brokerage(a) and a not in seen:
                            result.append(a); seen.add(a)
                elif ("TRAD" in t) and allow_trad:
                    for a in accts:
                        if _is_trad(a) and a not in seen:
                            result.append(a); seen.add(a)
                elif "ROTH" in t and allow_roth:
                    for a in accts:
                        if _is_roth(a) and a not in seen:
                            result.append(a); seen.add(a)
            return result if result else [a for a in accts if _is_brokerage(a)]

        seq_good_per_year = []
        seq_bad_per_year  = []
        for y in range(YEARS):
            age_y      = starting_age + y
            allow_trad = age_y >= tira_age_gate
            allow_roth = age_y >= tira_age_gate
            seq_good_per_year.append(_expand(order_good, acct_names, allow_trad, allow_roth))
            seq_bad_per_year.append( _expand(order_bad,  acct_names, allow_trad, allow_roth))

        withdraw_seq_per_year      = seq_good_per_year
        withdraw_seq_bad_per_year  = seq_bad_per_year

        # Extract bad market + withdrawal scaling params from econ_policy
        # These were previously config-only dead code — now wired to simulator.
        _wd_policy = econ_policy.get("withdrawals", {}) or {}
        _bm_policy = econ_policy.get("bad_market",  {}) or {}
        econ_scaling_params = {
            "shock_scaling_enabled":   bool(_wd_policy.get("shock_scaling_enabled",  True)),
            "drawdown_threshold":       float(_wd_policy.get("drawdown_threshold",    0.15)),
            "min_scaling_factor":       float(_wd_policy.get("min_scaling_factor",    0.65)),
            "scale_curve":              str(_wd_policy.get("scale_curve",            "linear")),
            "scale_poly_alpha":         float(_wd_policy.get("scale_poly_alpha",      1.2)),
            "scale_exp_lambda":         float(_wd_policy.get("scale_exp_lambda",      0.8)),
            "makeup_enabled":           bool(_wd_policy.get("makeup_enabled",         True)),
            "makeup_ratio":             float(_wd_policy.get("makeup_ratio",          0.3)),
            "makeup_cap_per_year":      float(_wd_policy.get("makeup_cap_per_year",   0.1)),
            "p10_signal_enabled":       bool(_bm_policy.get("p10_signal_enabled",     True)),
            "p10_return_threshold_pct": float(_bm_policy.get("p10_return_threshold_pct", -15.0)),
        }

        # Inject UI-selected simulation_mode into person_cfg
        person_cfg["simulation_mode"] = simulation_mode

        res = run_accounts_new(
            paths=paths,
            spy=steps_per_year,
            infl_yearly=infl_yearly,
            alloc_accounts=alloc_accounts,
            assets_path=assets_path,
            sched=sched_for_modular,
            sched_base=sched_base_for_modular,
            apply_withdrawals=apply_withdrawals_flag,
            withdraw_sequence=withdraw_seq_per_year,
            withdraw_sequence_bad=withdraw_seq_bad_per_year,
            econ_scaling_params=econ_scaling_params,
            tax_cfg=tax_cfg,
            ordinary_income_cur_paths=ordinary_income_cur_paths,
            qual_div_cur_paths=qual_div_cur_paths,
            cap_gains_cur_paths=cap_gains_cur_paths,
            ytd_income_nom_paths=ytd_income_nom_paths,
            w2_income_cur_paths=np.broadcast_to(w2_cur[np.newaxis, :], (paths, _n_years)).copy(),
            person_cfg=person_cfg,
            rmd_table_path=rmd_path,
            conversion_per_year_nom=None,
            rmds_enabled=rmds_enabled,
            conversions_enabled=not ignore_conversions_flag,
            shocks_events=shocks_events,
            shocks_mode=str(internal_shocks_mode),
            econ_policy=econ_policy,
            rebalancing_enabled=True,
            override_state         = payload.get("state"),
            override_filing_status = payload.get("filing"),
            override_rmd_table     = payload.get("rmd_table"),
            n_years                = _n_years,
        )

    # -- Tax diagnostic (server log -- remove once tax table confirmed working) --
    _wd_d = res.get("withdrawals", {})
    _cx_d = res.get("conversions", {})
    # debug removed for v in (_wd_d.get("taxes_fed_current_mean") or [0]*30)[20:25]])
    # debug removed for v in (_wd_d.get("taxes_state_current_mean") or [0]*30)[20:25]])
    # debug removed for v in (_cx_d.get("conversion_tax_cur_mean_by_year") or [0]*30)[0:5]])
    # debug removed), 2))
    # debug removed), 2))

    rmd_table = str(payload.get("rmd_table") or (person_cfg or {}).get("rmd_table", "uniform_lifetime"))

    # 8) Canonical input paths and run_info
    input_paths = {
        "tax": tax_path,
        "withdraw": withdraw_path_effective,
        "inflation": infl_path,
        "shocks": shocks_path_effective,
        "alloc": alloc_path,
        "person": person_path,
        "income": income_path,
        "economic": economic_path_effective,
        "rmd": rmd_path,
        "assets": assets_path or "",
    }

    run_info = {
        "paths": int(paths),
        "steps_per_year": int(steps_per_year),
        "dollars": str(dollars or "current"),
        "base_year": int(base_year),
        "state": state,
        "filing": filing,
        "rmd_table": rmd_table,
        "runtime_overrides": {k: v for k, v in {"state": payload.get("state"), "filing": payload.get("filing"), "rmd_table": payload.get("rmd_table")}.items() if v is not None},
        "shocks_mode": raw_shocks_mode,
        "flags": {
            "ignore_withdrawals": bool(ignore_withdrawals),
            "ignore_rmds": bool(ignore_rmds),
            "ignore_conversions": bool(ignore_conversions),
            "ignore_taxes": bool(ignore_taxes),
            "simulation_mode": simulation_mode,
        },
    }

    # 9a) Compute ending balances first so they get saved into the snapshot
    accounts_levels = res.get("returns_acct_levels", {}) or {}
    inv_nom_levels_mean_acct = accounts_levels.get("inv_nom_levels_mean_acct", {}) or {}
    inv_real_levels_mean_acct = accounts_levels.get("inv_real_levels_mean_acct", {}) or {}
    inv_nom_levels_med_acct  = accounts_levels.get("inv_nom_levels_med_acct",  {}) or {}
    inv_real_levels_med_acct = accounts_levels.get("inv_real_levels_med_acct", {}) or {}
    try:
        ending_balances_pre = compute_account_ending_balances(
            inv_nom_levels_mean_acct=inv_nom_levels_mean_acct,
            inv_real_levels_mean_acct=inv_real_levels_mean_acct,
            inv_nom_levels_med_acct=inv_nom_levels_med_acct,
            inv_real_levels_med_acct=inv_real_levels_med_acct,
        )
    except Exception:
        ending_balances_pre = []
    res["ending_balances"] = ending_balances_pre

    # 9a-income) Inject income.json year-1 estimates into person_cfg for optimizer
    try:
        _ic = income_cfg if isinstance(income_cfg, dict) else {}
        def _yr1(entries):
            for e in (entries or []):
                rng = str(e.get("years","")).strip()
                if rng.startswith("1-") or rng == "1":
                    return float(e.get("amount_nom", 0) or 0)
            return 0.0
        person_cfg["income_data"] = {
            "w2_yr1":       _yr1(_ic.get("w2", [])),
            "rental_yr1":   _yr1(_ic.get("rental", [])),
            "ordinary_yr1": _yr1(_ic.get("ordinary_other", [])),
        }
    except Exception:
        pass

    # 9a-roth) Run Roth optimizer inline — always runs so Results tab always has data.
    # The optimizer uses roth_policy.enabled internally to flag opportunities when disabled.
    try:
        from roth_optimizer import optimize_roth_conversion_full
        res["roth_optimizer"] = optimize_roth_conversion_full(
            person_cfg=person_cfg,
            simulation_summary=res.get("summary", {}),
            simulation_portfolio=res.get("portfolio", {}),
            withdrawals=res.get("withdrawals", {}),
        )
    except Exception as _roth_exc:
        logger.warning("Roth optimizer failed (non-fatal): %s", _roth_exc)
        res["roth_optimizer"] = {"error": str(_roth_exc)}

    # 9b) Snapshot + run_meta (now includes ending_balances)
    save_raw_snapshot_accounts(
        out_dir=run_dir,
        res=res,
        run_info=run_info,
        input_paths=input_paths,
        tax_cfg=tax_cfg,
        person_cfg=person_cfg,
        infl_yearly=infl_yearly,
        shocks_events=shocks_events,
        shocks_mode=str(shocks_mode or "augment"),
    )
    _write_run_meta(run_dir=run_dir, profile=profile, run_id=run_id, run_info=run_info)

    # Read back config_version that was just written
    try:
        with open(os.path.join(run_dir, "run_meta.json")) as _f:
            _meta = json.load(_f)
        _config_version = _meta.get("config_version")
    except Exception:
        _config_version = None

    # 10) Reporting artifacts (PNGs/CSVs)
    try:
        report_and_plot_accounts(
            res=res,
            args=type(
                "Args",
                (),
                {
                    "paths": paths,
                    "spy": steps_per_year,
                    "dollars": dollars,
                    "base_year": base_year,
                    "rebalance_threshold": rebalance_threshold,
                    "rebalance_brokerage_enabled": rebalance_brokerage_enabled,
                    "rebalance_brokerage_capgain_limit_k": rebalance_brokerage_capgain_limit_k,
                },
            )(),
            out_dir=run_dir,
            alloc_accounts=alloc_accounts,
            tax_cfg=tax_cfg,
            person_cfg=person_cfg,
            benchmarks_path=BENCHMARKS_GLOBAL_PATH
            if os.path.isfile(BENCHMARKS_GLOBAL_PATH)
            else None,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "profile": profile,
        "run": run_id,
        "config_version": _config_version,
        "ending_balances": ending_balances_pre,
    }


def _apply_ira_contribution_rules(
    alloc_accounts: Dict[str, Any],
    income_cfg: Dict[str, Any],
    current_age: int,
    n_years: int,
    filing: str = "MFJ",
) -> None:
    """
    Enforce IRS IRA contribution rules on deposits_yearly in-place.

    Rules applied per year:
      - Earned income requirement: if W2 == 0, zero all IRA deposits
      - Annual cap: $7,000 (age < 50) or $8,000 (age >= 50, catch-up)
      - Deposit also capped at earned income (can't contribute more than you earn)
      - Roth IRA: MAGI phase-out
          MFJ:    floor=$236,000  ceiling=$246,000
          Single: floor=$150,000  ceiling=$165,000
          MFS:    floor=$0        ceiling=$10,000
      - Traditional IRA: no MAGI phase-out (deductibility has limits but
        contribution is always allowed if earned income exists)
      - Taxable / brokerage accounts: untouched

    Modifies alloc_accounts["deposits_yearly"] numpy arrays in-place.
    """
    import numpy as np

    account_types: Dict[str, str] = alloc_accounts.get("account_types", {})
    deposits: Dict[str, Any]      = alloc_accounts.get("deposits_yearly", {})

    w2_arr      = income_cfg.get("w2",             np.zeros(n_years))
    rental_arr  = income_cfg.get("rental",         np.zeros(n_years))
    ord_arr     = income_cfg.get("ordinary_other",  np.zeros(n_years))

    # Roth phase-out thresholds by filing status
    _phase = {
        "MFJ":    (236_000.0, 246_000.0),
        "Single": (150_000.0, 165_000.0),
        "HOH":    (150_000.0, 165_000.0),
        "MFS":    (0.0,       10_000.0),
    }
    ph_floor, ph_ceil = _phase.get(filing, _phase["MFJ"])

    for yr in range(n_years):
        age_this_year = current_age + yr + 1
        w2    = float(w2_arr[yr])   if yr < len(w2_arr)     else 0.0
        # earned income = W2 (rental/ordinary_other are not earned income)
        earned = max(0.0, w2)

        # IRS annual cap (2024 figures, catch-up at 50+)
        ira_cap = 8_000.0 if age_this_year >= 50 else 7_000.0

        # Contribution limit = min(cap, earned income)
        max_contrib = min(ira_cap, earned)

        # MAGI for Roth phase-out = W2 + rental + ordinary_other (simplified)
        magi = w2 + float(rental_arr[yr] if yr < len(rental_arr) else 0.0) \
                  + float(ord_arr[yr]    if yr < len(ord_arr)     else 0.0)

        # Roth phase-out reduction factor (0.0 = fully phased out, 1.0 = full)
        if ph_ceil <= ph_floor:
            roth_factor = 0.0 if magi > ph_floor else 1.0
        elif magi >= ph_ceil:
            roth_factor = 0.0
        elif magi <= ph_floor:
            roth_factor = 1.0
        else:
            roth_factor = 1.0 - (magi - ph_floor) / (ph_ceil - ph_floor)

        for acct, acct_type in account_types.items():
            if acct not in deposits:
                continue
            arr = deposits[acct]
            if yr >= len(arr):
                continue

            if acct_type == "roth_ira":
                if earned == 0.0:
                    arr[yr] = 0.0
                else:
                    allowed = min(float(arr[yr]), max_contrib) * roth_factor
                    arr[yr] = allowed

            elif acct_type == "traditional_ira":
                if earned == 0.0:
                    arr[yr] = 0.0
                else:
                    arr[yr] = min(float(arr[yr]), max_contrib)

            # taxable / brokerage: untouched


# --- End of file ---
