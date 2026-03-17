# filename: snapshot.py
# --- Begin of file ---

import json
import os
from typing import Any, Dict, List, Optional


def _safe_write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def _build_portfolio_analysis(
    input_paths: Optional[Dict[str, str]],
    starting: Dict[str, float],
    ending_balances: Optional[List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """
    Compute portfolio allocation analysis and return as dict for snapshot.
    Silently returns None if allocation file is missing or analysis fails.
    """
    try:
        from portfolio_analysis import compute_portfolio_analysis

        alloc_path = (input_paths or {}).get("alloc", "")
        if not alloc_path or not os.path.isfile(alloc_path):
            return None

        with open(alloc_path, encoding="utf-8") as f:
            alloc_cfg = json.load(f)

        # Load assets.json for ETF look-through (Layer 5)
        assets_data: Optional[Dict] = None
        try:
            assets_path = (input_paths or {}).get("assets", "")
            if assets_path and os.path.isfile(assets_path):
                with open(assets_path, encoding="utf-8") as f:
                    assets_data = json.load(f).get("assets", {})
        except Exception:
            pass   # look-through optional — degrades gracefully

        # Build ending balance dict in current USD from ending_balances list
        ending_cur: Optional[Dict[str, float]] = None
        if ending_balances:
            ending_cur = {}
            for entry in ending_balances:
                acct = entry.get("account", "")
                # prefer median current, fall back to mean current
                bal = (entry.get("current_median")
                       or entry.get("current_mean")
                       or entry.get("ending_balance_current_mean")
                       or 0.0)
                if acct and bal:
                    ending_cur[acct] = float(bal)

        analysis = compute_portfolio_analysis(
            alloc_cfg=alloc_cfg,
            starting_balances=starting,
            ending_balances_cur=ending_cur if ending_cur else None,
            assets_cfg=assets_data,
        )
        return analysis.to_dict()

    except Exception as e:
        print(f"[WARN] portfolio_analysis skipped: {e}")
        return None


def save_raw_snapshot_accounts(
    out_dir: str,
    res: Dict[str, Any],
    run_info: Optional[Dict[str, Any]] = None,
    input_paths: Optional[Dict[str, str]] = None,
    tax_cfg: Optional[Dict[str, Any]] = None,
    person_cfg: Optional[Dict[str, Any]] = None,
    infl_yearly: Optional[List[float]] = None,
    shocks_events: Optional[List[Dict[str, Any]]] = None,
    shocks_mode: Optional[str] = None,
) -> None:
    """
    Save a rich snapshot the UI Results and CLI can both use.
    Copies arrays and summary fields from the simulator result `res`.

    Parameters
    ----------
    out_dir : str
        Output directory for this run (profiles/<profile>/reports/run_YYYYMMDD_HHMMSS).
    res : dict
        Result object returned from simulator.run_accounts. May contain:
          - paths, spy, dollars, base_year
          - years or portfolio.years
          - portfolio: future/current arrays
          - withdrawals
          - summary
          - returns, returns_acct, returns_acct_levels
          - accounts, starting
    run_info : dict, optional
        Canonical run parameters; overrides `res` for run_info if provided.
    input_paths : dict, optional
        Paths to config files used by the run.
    Other args are kept for compatibility/debugging; UI does not depend on them.
    """

    # 1) Run info: prefer explicit run_info, otherwise derive from res
    if run_info is not None:
        ri = dict(run_info)
    else:
        ri = {
            "paths": int(res.get("paths", 0)),
            "steps_per_year": int(res.get("spy", 0)),
            "dollars": str(res.get("dollars", "")),
            "base_year": int(res.get("base_year", 0) or 0),
        }
        # Copy optional fields if present
        for key in ("state", "filing", "shocks_mode", "flags"):
            if key in res:
                ri[key] = res[key]

    # 2) Years: prefer res["years"], else portfolio.years, else 1..30
    if isinstance(res.get("years"), list) and res["years"]:
        years = [int(y) for y in res["years"]]
    else:
        port = res.get("portfolio") or {}
        if isinstance(port.get("years"), list) and port["years"]:
            years = [int(y) for y in port["years"]]
        else:
            years = list(range(1, 31))  # fallback only; api.py always sets res['years']

    # 3) Build snapshot object from res
    snapshot: Dict[str, Any] = {}

    # Top-level run info
    snapshot["run_info"] = ri

    # Years
    snapshot["years"] = years
    snapshot["n_years"] = len(years)

    # Portfolio totals
    snapshot["portfolio"] = res.get("portfolio", {})

    # Summary, meta, returns
    snapshot["summary"] = res.get("summary", {})
    snapshot["meta"] = res.get("meta", {})
    snapshot["returns"] = res.get("returns", {})
    snapshot["returns_acct"] = res.get("returns_acct", {})
    snapshot["returns_acct_levels"] = res.get("returns_acct_levels", {})

    # Withdrawals, taxes & conversions
    snapshot["withdrawals"] = res.get("withdrawals", {})
    snapshot["taxes"] = res.get("taxes", {})
    snapshot["conversions"] = res.get("conversions", {})

    # Starting balances & account-level data
    snapshot["starting"] = res.get("starting", {})
    snapshot["accounts"] = res.get("accounts", {})

    # Ending balances per account (median + mean) — persisted so past runs load correctly
    if "ending_balances" in res:
        snapshot["ending_balances"] = res["ending_balances"]

    # Input paths (useful for debugging / UI links)
    if input_paths is not None:
        snapshot["input_paths"] = dict(input_paths)

    # Tax config (optional)
    if tax_cfg is not None:
        snapshot["tax_cfg"] = dict(tax_cfg)

    # --- Attach person so UI can show Age / RMD logic ---
    # Prefer explicit person_cfg (from profile JSON); if absent, fall back to res["person"] if present.
    if person_cfg is not None:
        snapshot["person"] = dict(person_cfg)
    elif "person" in res and isinstance(res["person"], dict):
        snapshot["person"] = dict(res["person"])
    else:
        snapshot["person"] = {}

    # --- Portfolio allocation analysis ---
    # Computed from allocation_yearly.json weighted by ending balances.
    # Silently skipped if allocation file unavailable (older runs, CLI use).
    _pa = _build_portfolio_analysis(
        input_paths=input_paths,
        starting=dict(res.get("starting", {})),
        ending_balances=res.get("ending_balances"),
    )
    if _pa is not None:
        snapshot["portfolio_analysis"] = _pa

    # 4) Write snapshot JSON
    out_path = os.path.join(out_dir, "raw_snapshot_accounts.json")
    _safe_write_json(out_path, snapshot)


# --- End of file ---

