# filename: api.py
# --- Begin of file ---

import os
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
from simulator import run_accounts
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

PROFILES_ROOT = os.path.join(APP_ROOT, "profiles")
DEFAULT_PROFILE = "default"

# Files that live at APP_ROOT, not per-profile
ECONOMIC_GLOBAL_PATH = os.path.join(APP_ROOT, "economicglobal.json")
TAX_GLOBAL_PATH      = os.path.join(APP_ROOT, "taxes_states_mfj_single.json")
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

app = FastAPI(title="eNDinomics API", version="1.0.0")


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


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}


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
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def _copy_file(src: str, dst: str) -> None:
    _ensure_dir(os.path.dirname(dst))
    shutil.copy2(src, dst)


def _write_run_meta(run_dir: str, profile: str, run_id: str, run_info: Dict[str, Any]) -> None:
    meta = {
        "profile": profile,
        "run_id": run_id,
        "run_info": dict(run_info or {}),
    }
    path = os.path.join(run_dir, "run_meta.json")
    _write_json(path, meta)


def _default_json_names() -> List[str]:
    # Only per-profile files; global files (taxes, benchmarks, economicglobal) live at APP_ROOT
    return [
        "allocation_yearly.json",
        "withdrawal_schedule.json",
        "shocks_yearly.json",
        "inflation_yearly.json",
        "person.json",
        "income.json",
        "rmd.json",
        "economic.json",
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

    if source == "clean":
        for n in _default_json_names():
            _write_json(_profile_json_path(name, n), _default_scaffold(n))
    else:
        src_profile = source if source and source != "default" else DEFAULT_PROFILE
        src_dir = _profile_dir(src_profile)
        if not os.path.isdir(src_dir):
            raise HTTPException(status_code=404, detail=f"Source profile '{src_profile}' not found.")
        for n in _default_json_names():
            src_path = _profile_json_path(src_profile, n)
            dst_path = _profile_json_path(name, n)
            if os.path.isfile(src_path):
                _copy_file(src_path, dst_path)
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
    if not os.path.isfile(path):
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

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Reports endpoints
@app.get("/reports/{profile}")
def list_reports_profile(profile: str):
    rdir = _profile_reports_dir(profile)
    if not os.path.isdir(rdir):
        return {"runs": []}
    runs = sorted(
        [d for d in os.listdir(rdir) if d.startswith("run_") and os.path.isdir(os.path.join(rdir, d))],
        reverse=False,
    )
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
    rmd_path = payload.get("rmd") or P("rmd.json")
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

    # 6) Load configs
    tax_cfg = load_tax_unified(tax_path, state=state, filing=filing)
    sched_arr, sched_base = load_sched(withdraw_path_effective)
    # Derive scalar floor_k for legacy run_accounts path
    floor_k = float(sched_base.min()) if sched_base is not None and sched_base.size > 0 else 0.0

    # DEBUG: see what schedule we really loaded
    print("[DEBUG api] withdraw_path_effective:", withdraw_path_effective)
    print("[DEBUG api] sched_arr[0:10]:", sched_arr[:10])
    print("[DEBUG api] sched_base[0:10]:", sched_base[:10])
    print("[DEBUG api] floor_k (legacy scalar):", floor_k)


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

    person_cfg = load_person(person_path)
    print("[DEBUG api] person_cfg.rmd_policy:", person_cfg.get("rmd_policy") if person_cfg else None)

    income_cfg = load_income(income_path)
    econ_policy = load_economic_policy(economic_path_effective, global_path=economic_global_path)

    # 7) Run simulation
    ignore_withdrawals_flag = bool(ignore_withdrawals)
    ignore_rmds_flag = bool(ignore_rmds)
    ignore_conversions_flag = bool(ignore_conversions)
    shocks_mode_raw = (shocks_mode or "").lower()

    rmds_enabled = not ignore_rmds_flag
    
    # DEBUG: see what the server thinks the flags are
    print(
        "[DEBUG api] standard_test inputs:",
        "shocks_mode_raw:",
        (shocks_mode or "").lower(),
        "shocks_mode_raw_req:",
        (shocks_mode_req or "").lower(),
        #####################
        "ignore_withdrawals:",
        ignore_withdrawals,
        "ignore_rmds:",
        ignore_rmds,
        "ignore_conversions:",
        ignore_conversions,
    )

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

    print(
        "[DEBUG api] modular routing:",
        "profile:", profile,
        "shocks_req:", shocks_mode_req_raw,
        "ignore_withdrawals:", ignore_withdrawals_flag,
        "ignore_rmds:", ignore_rmds_flag,
        "ignore_conversions:", ignore_conversions_flag,
        "modular_core_only_test:", modular_core_only_test,
        "modular_core_withdrawals_test:", modular_core_withdrawals_test,
        "modular_rmd_only_test:", modular_rmd_only_test,
        "modular_withdrawals_rmd_test:", modular_withdrawals_rmd_test,
        "modular_withdrawals_rmd_conv_test:", modular_withdrawals_rmd_conv_test,
        "modular_test:", modular_test,
    )



    if modular_test:
        print("[DEBUG api] Using modular run_accounts_new for Test profile")
        # RMDs are enabled in the modular engine when Ignore RMDs is False
        rmds_enabled = not ignore_rmds_flag

        # Build income streams from Test profile income_cfg
        income_cfg = load_income(f"profiles/{profile}/income.json")
        (
            w2_cur,
            rental_cur,
            interest_cur,
            ordinary_other_cur,
            qual_div_cur,
            cap_gains_cur,
        ) = build_income_streams(income_cfg, years=YEARS)

        ordinary_income_cur_paths = np.zeros((paths, YEARS), dtype=float)
        qual_div_cur_paths = np.zeros((paths, YEARS), dtype=float)
        cap_gains_cur_paths = np.zeros((paths, YEARS), dtype=float)
        ytd_income_nom_paths = np.zeros((paths, YEARS), dtype=float)

        for y in range(YEARS):
            ordinary_year = (
                w2_cur[y]
                + rental_cur[y]
                + interest_cur[y]
                + ordinary_other_cur[y]
            )
            qual_div_year = qual_div_cur[y]
            cap_gains_year = cap_gains_cur[y]

            ordinary_income_cur_paths[:, y] = ordinary_year
            qual_div_cur_paths[:, y] = qual_div_year
            cap_gains_cur_paths[:, y] = cap_gains_year
            # ytd_income_nom_paths can stay zeros for now

        # Decide sched/apply_withdrawals based on which modular case we’re in
        #sched_for_modular = None
        #apply_withdrawals_flag = False
        #if modular_core_withdrawals_test:
        #    sched_for_modular = sched_arr   # use the real schedule
        #    apply_withdrawals_flag = True


        # Decide sched/apply_withdrawals based on which modular case we’re in
        sched_for_modular = None
        sched_base_for_modular = None   # safe default
        apply_withdrawals_flag = False

        # Core-only: no withdrawals, no RMDs → sched=None, apply_withdrawals=False
        if modular_core_only_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False

        # Withdrawals-only: discretionary schedule ON, RMDs ignored
        elif modular_core_withdrawals_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True

        # RMD-only: RMDs ON, no discretionary withdrawals
        elif modular_rmd_only_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False

        # Withdrawals + RMDs: both ON
        elif modular_withdrawals_rmd_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True

        # ── Conversion-enabled variants ──────────────────────────────────────
        # Conversions are handled inside simulator_new.py.
        # These branches mirror the above but with ignore_conversions_flag=False.

        # Core + Conversions only
        elif modular_core_conv_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False

        # Withdrawals + Conversions (no RMDs)
        elif modular_withdrawals_conv_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True

        # RMDs + Conversions (no discretionary withdrawals)
        elif modular_rmd_conv_test:
            sched_for_modular = None
            sched_base_for_modular = None
            apply_withdrawals_flag = False

        # Withdrawals + RMDs + Conversions: all ON
        elif modular_withdrawals_rmd_conv_test:
            sched_for_modular = sched_arr
            sched_base_for_modular = sched_base
            apply_withdrawals_flag = True

        # Build per-year age-gated withdrawal sequence from economic policy
        acct_names    = list(alloc_accounts.get("per_year_portfolios", {}).keys())
        starting_age  = int(person_cfg.get("current_age", 70)) if person_cfg else 70
        tira_age_gate = float(econ_policy.get("tira_age_gate", 59.5))

        # Pick the correct bad-market sequence based on conversion policy
        # NOTE: key is roth_conversion_policy (not conversion_policy)
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

        # Build good/bad sequences per year — simulator picks based on market condition
        seq_good_per_year = []
        seq_bad_per_year  = []
        for y in range(YEARS):
            age_y      = starting_age + y
            allow_trad = age_y >= tira_age_gate
            allow_roth = age_y >= tira_age_gate
            seq_good_per_year.append(_expand(order_good, acct_names, allow_trad, allow_roth))
            seq_bad_per_year.append( _expand(order_bad,  acct_names, allow_trad, allow_roth))

        # TODO: simulator_new.py needs per-path bad-market flag support to use seq_bad_per_year.
        # When implemented, pass {"good": seq_good_per_year, "bad": seq_bad_per_year} and
        # the simulator will pick the sequence per year per path based on drawdown detection.
        # For now, good-market sequence is used for all years.
        withdraw_seq_per_year = seq_good_per_year

        print("[DEBUG api] conversion_enabled:", conversion_enabled)
        print("[DEBUG api] seq_good year 0:", seq_good_per_year[0])
        print("[DEBUG api] seq_bad  year 0:", seq_bad_per_year[0])
        print("[DEBUG api] seq_good year 14:", seq_good_per_year[14] if len(seq_good_per_year) > 14 else "N/A")
        print("[DEBUG api] seq_bad  year 14:", seq_bad_per_year[14]  if len(seq_bad_per_year)  > 14 else "N/A")

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
            tax_cfg=tax_cfg,
            ordinary_income_cur_paths=ordinary_income_cur_paths,
            qual_div_cur_paths=qual_div_cur_paths,
            cap_gains_cur_paths=cap_gains_cur_paths,
            ytd_income_nom_paths=ytd_income_nom_paths,
            person_cfg=person_cfg,
            rmd_table_path=rmd_path,
            conversion_per_year_nom=None,  # simulator_new resolves from person_cfg roth_conversion_policy
            rmds_enabled=rmds_enabled,
            shocks_events=shocks_events,
            shocks_mode=str(internal_shocks_mode),
            econ_policy=econ_policy,
            rebalancing_enabled=True,
        )
    else:
        res = run_accounts(
            paths=int(paths),
            spy=int(steps_per_year),
            tax_cfg=tax_cfg,
            sched=sched_arr,
            floor_k=float(floor_k),
            shocks_events=shocks_events,
            shocks_mode=str(internal_shocks_mode),
            infl_yearly=infl_yearly,
            alloc_accounts=alloc_accounts,
            person_cfg=person_cfg,
            income_cfg=income_cfg,
            dollars=str(dollars or "current"),
            rmd_table_path=rmd_path,
            base_year=int(base_year),
            rebalance_drift_threshold=float(rebalance_threshold),
            rebalance_brokerage_enabled=bool(rebalance_brokerage_enabled),
            rebalance_brokerage_capgain_limit_k=float(rebalance_brokerage_capgain_limit_k),
            economic_policy=econ_policy,
            assets_path=assets_path,
        )

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
        # Show exactly what the user chose; "none" if they picked that
        "shocks_mode": raw_shocks_mode ,
        "flags": {
            "ignore_withdrawals": bool(ignore_withdrawals),
            "ignore_rmds": bool(ignore_rmds),
            "ignore_conversions": bool(ignore_conversions),
        },
    }

    # 9) Snapshot + run_meta
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
        # Non-fatal for UI
        pass

    # 11) Compute ending balances per account for UI
    accounts_levels = res.get("returns_acct_levels", {}) or {}
    inv_nom_levels_mean_acct = accounts_levels.get("inv_nom_levels_mean_acct", {}) or {}
    inv_real_levels_mean_acct = accounts_levels.get("inv_real_levels_mean_acct", {}) or {}

    try:
        ending_balances = compute_account_ending_balances(
            inv_nom_levels_mean_acct=inv_nom_levels_mean_acct,
            inv_real_levels_mean_acct=inv_real_levels_mean_acct,
        )
    except Exception:
        ending_balances = []

    # Final response to UI
    return {
        "ok": True,
        "profile": profile,
        "run": run_id,
        "ending_balances": ending_balances,
    }

# --- End of file ---

