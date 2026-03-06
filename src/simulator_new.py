# filename: simulator_new.py

from typing import Dict, Any, Optional
import numpy as np

from simulation_core import simulate_balances
from withdrawals_core import apply_withdrawals_nominal_per_account
from taxes_core import compute_annual_taxes_paths

from rmd_core import build_rmd_factors, compute_rmd_schedule_nominal
from roth_conversion_core import apply_simple_conversions


YEARS = 30


#def pct_change_paths(series_2d: np.ndarray) -> np.ndarray:
#    """
#    Compute per-path year-over-year returns in PERCENT:
#    r[:, y] = (series[:, y] / series[:, y-1] - 1) * 100
#    r[:, 0] = 0.
#    """
#    s = np.asarray(series_2d, dtype=float)
#    if s.ndim != 2:
#        s = s.reshape(s.shape[0], -1)
#    P, Y = s.shape
#    r = np.zeros_like(s)
#    if Y < 2:
#        return r
##    prev = np.maximum(s[:, :-1], 1e-12)
#    r[:, 1:] = (s[:, 1:] / prev - 1.0) * 100.0
#    return r

def pct_change_paths(
    series_2d: np.ndarray,
    prior_col: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Compute per-path year-over-year returns as FRACTIONS:
    r[:, y] = series[:, y] / series[:, y-1] - 1

    If prior_col (shape: paths,) is provided it is used as the year-0
    starting value so that r[:, 0] = series[:, 0] / prior_col - 1.
    Otherwise r[:, 0] = 0 (no prior data).
    """
    s = np.asarray(series_2d, dtype=float)
    if s.ndim != 2:
        s = s.reshape(s.shape[0], -1)
    P, Y = s.shape
    r = np.zeros_like(s)
    if Y < 2:
        return r
    prev = np.maximum(s[:, :-1], 1e-12)
    r[:, 1:] = (s[:, 1:] / prev - 1.0)
    if prior_col is not None:
        r[:, 0] = s[:, 0] / np.maximum(prior_col, 1e-12) - 1.0
    return r

def run_accounts_new(
    paths: int,
    spy: int,
    infl_yearly: Optional[np.ndarray],
    alloc_accounts: Dict[str, Any],
    assets_path: Optional[str] = None,
    sched: Optional[np.ndarray] = None,
    apply_withdrawals: bool = False,
    withdraw_sequence: Optional[list] = None,
    tax_cfg: Optional[Dict[str, Any]] = None,
    ordinary_income_cur_paths: Optional[np.ndarray] = None,
    qual_div_cur_paths: Optional[np.ndarray] = None,
    cap_gains_cur_paths: Optional[np.ndarray] = None,
    ytd_income_nom_paths: Optional[np.ndarray] = None,
    person_cfg: Optional[Dict[str, Any]] = None,
    rmd_table_path: Optional[str] = None,
    conversion_per_year_nom: Optional[float] = None,  # NEW
    rmds_enabled: bool = True,
) -> Dict[str, Any]:


    """
    Minimal simulator: Monte Carlo + inflation only.
    No shocks (we pass empty events), no withdrawals, no taxes,
    no RMDs, no conversions.

    Returns a res dict with the same high-level shape as the app expects:
      - portfolio
      - summary
      - meta
      - returns
      - returns_acct
      - returns_acct_levels
      - starting
      - accounts
    but withdrawals/taxes/etc. are omitted in this minimal version.
    """
    np.random.seed(42)
    paths = int(paths)
    spy = int(spy)

    # Core Monte Carlo
    acct_eoy_nom, total_nom_paths, total_real_paths = simulate_balances(
        paths=paths,
        years=YEARS,
        spy=spy,
        alloc_accounts=alloc_accounts,
        assets_path=assets_path,
        shocks_events=[],         # no shocks
        shocks_mode="augment",    # mode unused when events=[]
        infl_yearly=infl_yearly,
    )

    # Snapshot core-only totals and account means before RMD/withdrawals/reinvest (for debug)
    core_total_nom_before = np.zeros((paths, YEARS), dtype=float)
    core_acct_mean_before = {}
    for acct, bal in acct_eoy_nom.items():
        core_acct_mean_before[acct] = bal.mean(axis=0).copy()

    for y in range(YEARS):
        total_nom_y = None
        for acct, bal in acct_eoy_nom.items():
            v = np.where(np.isfinite(bal[:, y]), bal[:, y], 0.0)
            total_nom_y = v if total_nom_y is None else (total_nom_y + v)
        core_total_nom_before[:, y] = total_nom_y

    # Starting balances — needed for year-1 YoY and per-account stats
    starting = dict(alloc_accounts.get("starting", {}) or {})
    starting_total = float(sum(starting.values()))
    starting_total_nom = np.full(paths, starting_total, dtype=float)

    # Preserve core (pre-withdrawal) paths for investment YoY
    total_nom_paths_core = total_nom_paths.copy()
    total_real_paths_core = total_real_paths.copy()

    # Per-account pre-cashflow snapshot (before RMDs, withdrawals, reinvestments).
    # Used in STEP 6 to compute pure-investment YoY that is unaffected by cashflows.
    acct_eoy_nom_core = {acct: bal.copy() for acct, bal in acct_eoy_nom.items()}

    # Investment-only YoY from pure core path (before withdrawals/RMDs/etc.)
    # deflator not yet built here — compute year-1 inflation factor inline
    _infl_arr = np.asarray(infl_yearly, dtype=float).reshape(-1) if (
        infl_yearly is not None and np.asarray(infl_yearly).size > 0
    ) else np.zeros(YEARS, dtype=float)
    _deflator_y1 = float(1.0 + _infl_arr[0]) if len(_infl_arr) > 0 else 1.0

    inv_nom_yoy_paths_core = pct_change_paths(total_nom_paths_core,
                                               prior_col=starting_total_nom)

    # Build full deflator inline for real conversion of core paths
    _deflator_core = np.cumprod(1.0 + _infl_arr[:YEARS]) if len(_infl_arr) >= YEARS                      else np.ones(YEARS, dtype=float)
    _total_real_paths_core = total_nom_paths_core / np.maximum(_deflator_core, 1e-12)
    # Real prior = starting_total in nominal terms (base year has no deflation yet)
    # real_bal[0] = nom[0]/deflator[0], prior = starting_total
    # => real YoY[1] = (nom[0]/deflator[0]) / starting_total - 1
    #                = nominal_return / deflator[0] - 1  (correct real return)
    _starting_real_col = np.full(paths, starting_total, dtype=float)

    inv_real_yoy_paths_core = pct_change_paths(_total_real_paths_core,
                                                prior_col=_starting_real_col)

    # Shift YoY one year earlier: Year 1 row = 1→2, ..., last row = 0
    inv_nom_yoy_paths_core_shifted = np.zeros_like(inv_nom_yoy_paths_core)
    inv_real_yoy_paths_core_shifted = np.zeros_like(inv_real_yoy_paths_core)
    inv_nom_yoy_paths_core_shifted[:, :] = inv_nom_yoy_paths_core[:, :]
    inv_real_yoy_paths_core_shifted[:, :] = inv_real_yoy_paths_core[:, :]

    inv_nom_yoy_mean_pct_core = (
        inv_nom_yoy_paths_core_shifted.mean(axis=0) * 100.0
    ).tolist()
    inv_real_yoy_mean_pct_core = (
        inv_real_yoy_paths_core_shifted.mean(axis=0) * 100.0
    ).tolist()

    # Classify accounts: brokerage, trad, roth (same pattern as legacy)
    acct_names = list(acct_eoy_nom.keys())

    # Starting portfolio total — needed for year-1 YoY (prior_col)
    # Computed here early so it's available for both core and post-cashflow YoY


    def _is_brokerage(name: str) -> bool:
        nu = name.upper()
        return ("BROKERAGE" in nu) or ("TAXABLE" in nu)

    def _is_trad(name: str) -> bool:
        nu = name.upper()
        return (("TRAD" in nu) or ("TRAD-IRA" in nu) or ("TRADITIONAL" in nu)) and ("ROTH" not in nu)

    def _is_roth(name: str) -> bool:
        nu = name.upper()
        return "ROTH" in nu

    trad_accounts = [a for a in acct_names if _is_trad(a)]
    brokerage_accounts = [a for a in acct_names if _is_brokerage(a)]
    roth_accounts = [a for a in acct_names if _is_roth(a)]


    # --- RMDs: compute factors and per-account RMD schedule (nominal) ---
    rmd_factors = None
    rmd_total_nom_paths = None
    rmd_nom_per_acct = None
    rmd_future_mean = np.zeros(YEARS, dtype=float)
    rmd_current_mean = np.zeros(YEARS, dtype=float)
    
    rmd_extra_current = np.zeros(YEARS, dtype=float)

    #if trad_accounts and rmd_table_path is not None and person_cfg is not None:
    if (
        rmds_enabled
        and trad_accounts
        and rmd_table_path is not None
        and person_cfg is not None
    ):
 
        owner_current_age = float(person_cfg.get("current_age", 60.0))
        rmd_factors = build_rmd_factors(
            rmd_table_path=rmd_table_path,
            owner_current_age=owner_current_age,
            years=YEARS,
        )
    
        rmd_total_nom_paths, rmd_nom_per_acct = compute_rmd_schedule_nominal(
            trad_ira_balances_nom={a: acct_eoy_nom[a] for a in trad_accounts},
            rmd_factors=rmd_factors,
        )
    
        # Subtract RMDs from TRAD balances
        for y in range(YEARS):
            for a in trad_accounts:
                bal = np.where(np.isfinite(acct_eoy_nom[a][:, y]), acct_eoy_nom[a][:, y], 0.0)
                take = np.where(np.isfinite(rmd_nom_per_acct[a][:, y]), rmd_nom_per_acct[a][:, y], 0.0)
                acct_eoy_nom[a][:, y] = bal - take
    
        # Summaries: mean RMD per year in future & current USD
        if rmd_total_nom_paths is not None:
            rmd_future_mean = rmd_total_nom_paths.mean(axis=0)
            if infl_yearly is not None and np.asarray(infl_yearly).size > 0:
                arr_rmd = np.asarray(infl_yearly, dtype=float).reshape(-1)
                if arr_rmd.size < YEARS:
                    arr_rmd = np.concatenate(
                        [arr_rmd, np.full(YEARS - arr_rmd.size, arr_rmd[-1] if arr_rmd.size > 0 else 0.0)]
                    )
                elif arr_rmd.size > YEARS:
                    arr_rmd = arr_rmd[:YEARS]
                deflator_rmd = np.cumprod(1.0 + arr_rmd)
            else:
                deflator_rmd = np.ones(YEARS, dtype=float)
            rmd_current_mean = rmd_future_mean / np.maximum(deflator_rmd, 1e-12)
    
            # Add per-path RMD in current USD into ordinary income (optional)
            if ordinary_income_cur_paths is not None:
                for y in range(YEARS):
                    rmd_cur_paths_y = rmd_total_nom_paths[:, y] / max(deflator_rmd[y], 1e-12)
                    ordinary_income_cur_paths[:, y] += rmd_cur_paths_y


    # --- Simple Roth conversions (lab only) ---
    conversion_nom_paths = None

    # Example: convert a fixed nominal amount per year across TRAD accounts
    # only if we have both TRAD and ROTH accounts and a conversion amount.
    if trad_accounts and roth_accounts and conversion_per_year_nom is not None:
        # Build TRAD/ROTH balance dicts for conversions
        trad_balances_nom = {a: acct_eoy_nom[a] for a in trad_accounts}
        roth_balances_nom = {a: acct_eoy_nom[a] for a in roth_accounts}

        updated_trad, updated_roth, conversion_nom_paths = apply_simple_conversions(
            trad_ira_balances_nom=trad_balances_nom,
            roth_ira_balances_nom=roth_balances_nom,
            conversion_per_year_nom=float(conversion_per_year_nom),
            window_start_y=0,   # for lab: convert in all years
            window_end_y=YEARS,
        )

        # Write updated balances back into acct_eoy_nom
        for a in trad_accounts:
            acct_eoy_nom[a] = updated_trad[a]
        for a in roth_accounts:
            acct_eoy_nom[a] = updated_roth[a]

        # Add conversion income (current USD) into ordinary income for taxes
        if (
            ordinary_income_cur_paths is not None
            and infl_yearly is not None
            and conversion_nom_paths is not None
        ):
            # Deflator for conversion nominal → current
            deflator_conv = np.ones(YEARS, dtype=float)
            arr_conv = np.asarray(infl_yearly, dtype=float).reshape(-1)
            if arr_conv.size < YEARS:
                arr_conv = np.concatenate(
                    [arr_conv, np.full(YEARS - arr_conv.size, arr_conv[-1] if arr_conv.size > 0 else 0.0)]
                )
            elif arr_conv.size > YEARS:
                arr_conv = arr_conv[:YEARS]
            deflator_conv = np.cumprod(1.0 + arr_conv)

            for y in range(YEARS):
                conv_cur_y = conversion_nom_paths[:, y] / max(deflator_conv[y], 1e-12)
                ordinary_income_cur_paths[:, y] += conv_cur_y


    # (no legacy withdrawals block here anymore)

    # --- Taxes over all years (current USD, per-path) — modular path only ---
    taxes_fed_cur_paths = np.zeros((paths, YEARS), dtype=float)
    taxes_state_cur_paths = np.zeros((paths, YEARS), dtype=float)
    taxes_niit_cur_paths = np.zeros((paths, YEARS), dtype=float)
    taxes_excise_cur_paths = np.zeros((paths, YEARS), dtype=float)
    
    if (
        tax_cfg is not None
        and ordinary_income_cur_paths is not None
        and qual_div_cur_paths is not None
        and cap_gains_cur_paths is not None
        and ytd_income_nom_paths is not None
    ):
        for y in range(YEARS):
            (
                taxes_fed_cur_paths[:, y],
                taxes_state_cur_paths[:, y],
                taxes_niit_cur_paths[:, y],
                taxes_excise_cur_paths[:, y],
            ) = compute_annual_taxes_paths(
                ordinary_income_cur_paths[:, y],
                qual_div_cur_paths[:, y],
                cap_gains_cur_paths[:, y],
                tax_cfg,
                ytd_income_nom_paths[:, y],
            )


    # =========================================================================
    # STEP 1: Build deflator once — used by withdrawals, reinvestment, and stats
    # =========================================================================
    deflator = np.ones(YEARS, dtype=float)
    if infl_yearly is not None and np.asarray(infl_yearly).size > 0:
        _arr = np.asarray(infl_yearly, dtype=float).reshape(-1)
        if _arr.size < YEARS:
            _arr = np.concatenate(
                [_arr, np.full(YEARS - _arr.size, _arr[-1] if _arr.size > 0 else 0.0)]
            )
        elif _arr.size > YEARS:
            _arr = _arr[:YEARS]
        deflator = np.cumprod(1.0 + _arr)

    # =========================================================================
    # STEP 2: Withdrawals dict — init all zeros; populated below if enabled
    # =========================================================================
    zeros = np.zeros(YEARS, dtype=float)
    withdrawals = {
        "planned_current":              zeros.tolist(),
        "realized_current_mean":        zeros.tolist(),
        "realized_future_mean":         zeros.tolist(),
        "shortfall_current_mean":       zeros.tolist(),
        "realized_current_per_acct_mean":  {},
        "shortfall_current_per_acct_mean": {},
        "sequence_good_market":         [],
        "sequence_bad_market":          [],
        "bad_market_drawdown_threshold": 0.0,
        "taxes_fed_current_mean":       zeros.tolist(),
        "taxes_state_current_mean":     zeros.tolist(),
        "taxes_niit_current_mean":      zeros.tolist(),
        "taxes_excise_current_mean":    zeros.tolist(),
        "tax_shortfall_current_mean":   zeros.tolist(),
        "realized_gains_current_mean":  zeros.tolist(),
        "rmd_current_mean":             zeros.tolist(),
        "rmd_future_mean":              zeros.tolist(),
        "total_withdraw_current_mean":  zeros.tolist(),
        "total_withdraw_future_mean":   zeros.tolist(),
    }

    planned_cur = np.zeros(YEARS, dtype=float)

    # =========================================================================
    # STEP 3: Apply discretionary withdrawals (amount above RMD) if enabled
    #
    # RMD was already deducted from TRAD accounts in the RMD block above.
    # Here we only pull the portion of the spending plan that exceeds the RMD.
    #
    #   plan > RMD  →  pull (plan - RMD) from brokerage/IRA accounts
    #   plan <= RMD →  RMD already covers the plan; nothing extra to pull
    # =========================================================================
    # Ensure all account arrays are writable C-contiguous copies before any
    # slice assignment.  simulate_balances (or upstream reassignments) may
    # return read-only or Fortran-order views; in-place assignment silently
    # fails on read-only arrays.
    acct_eoy_nom = {
        acct: np.array(bal, dtype=float, order='C', copy=True)
        for acct, bal in acct_eoy_nom.items()
    }

    if apply_withdrawals and sched is not None:
        sched_vec = np.asarray(sched, dtype=float).reshape(-1)
        if sched_vec.size < YEARS:
            sched_vec = np.concatenate(
                [sched_vec, np.full(YEARS - sched_vec.size, sched_vec[-1])]
            )
        elif sched_vec.size > YEARS:
            sched_vec = sched_vec[:YEARS]

        planned_cur = sched_vec.copy()

        # Mean-basis: how much does the plan exceed the mean RMD each year?
        extra_cur = np.maximum(planned_cur - rmd_current_mean, 0.0)

        realized_cur   = np.zeros(YEARS, dtype=float)
        shortfall_cur  = np.zeros(YEARS, dtype=float)
        withdrawals["realized_current_per_acct_mean"]  = {}
        withdrawals["shortfall_current_per_acct_mean"] = {}

        # withdraw_sequence may be a flat list (same every year) or a list-of-lists (per year).
        # Normalise to per-year so the simulator always uses seq_y for year y.
        _fallback_seq = list(acct_eoy_nom.keys())
        if withdraw_sequence is None:
            _seq_per_year = [_fallback_seq] * YEARS
        elif withdraw_sequence and isinstance(withdraw_sequence[0], list):
            # Already per-year list-of-lists
            _seq_per_year = withdraw_sequence
        else:
            # Flat list — use same sequence every year
            _seq_per_year = [withdraw_sequence] * YEARS

        for y in range(YEARS):
            extra_nom = extra_cur[y] * deflator[y]
            amount_nom_paths = np.full(paths, extra_nom, dtype=float)
            seq = _seq_per_year[y] if y < len(_seq_per_year) else _fallback_seq

            if y == 0:
                print(f"[WDEBUG y=0] extra_cur[0]={extra_cur[0]:.2f} deflator[0]={deflator[0]:.4f} extra_nom={extra_nom:.2f}")
                print(f"[WDEBUG y=0] seq[:3]={seq[:3]}")
                for _a in list(acct_eoy_nom.keys())[:3]:
                    _arr = acct_eoy_nom[_a]
                    print(f"[WDEBUG y=0] acct={_a} flags={_arr.flags['WRITEABLE']} mean_y0={_arr[:, 0].mean():.2f}")

            (
                realized_total_nom,
                shortfall_total_nom,
                realized_per_acct_nom,
                shortfall_per_acct_nom,
                sold_per_acct_nom,
            ) = apply_withdrawals_nominal_per_account(
                acct_eoy_nom, y, amount_nom_paths, seq,
            )

            if y == 0:
                for _a in list(sold_per_acct_nom.keys())[:4]:
                    print(f"[WDEBUG y=0] sold_per_acct[{_a}] sum={sold_per_acct_nom[_a].sum():.2f}")

            # Explicitly deduct sold amounts from each account's balance for year y.
            # withdrawals_core no longer mutates the arrays itself; we own that here
            # to guarantee the deduction persists into STEP 5 / STEP 6 statistics.
            for acct, sold_arr in sold_per_acct_nom.items():
                if acct in acct_eoy_nom and np.any(sold_arr > 0):
                    acct_eoy_nom[acct][:, y] = np.maximum(
                        acct_eoy_nom[acct][:, y] - sold_arr, 0.0
                    )

            if y == 0:
                for _a in list(acct_eoy_nom.keys())[:3]:
                    print(f"[WDEBUG post-deduct y=0] acct={_a} mean_y0={acct_eoy_nom[_a][:, 0].mean():.2f}")

            scale = max(deflator[y], 1e-12)
            realized_cur[y]  = (realized_total_nom / scale).mean()
            shortfall_cur[y] = (shortfall_total_nom / scale).mean()

            for acct in acct_eoy_nom.keys():
                rn = realized_per_acct_nom.get(acct)
                sn = shortfall_per_acct_nom.get(acct)
                if rn is not None:
                    withdrawals["realized_current_per_acct_mean"].setdefault(acct, [0.0] * YEARS)
                    withdrawals["realized_current_per_acct_mean"][acct][y] = (rn / scale).mean()
                if sn is not None:
                    withdrawals["shortfall_current_per_acct_mean"].setdefault(acct, [0.0] * YEARS)
                    withdrawals["shortfall_current_per_acct_mean"][acct][y] = (sn / scale).mean()

        # realized_current_mean = total cash the person actually receives:
        #   min(plan, RMD)  — RMD portion covering up to the plan
        #   + realized_cur  — extra discretionary pulled from accounts (plan > RMD years)
        rmd_covering_plan  = np.minimum(planned_cur, rmd_current_mean)
        total_realized_cur = rmd_covering_plan + realized_cur

        withdrawals["planned_current"]        = planned_cur.tolist()
        withdrawals["realized_current_mean"]  = total_realized_cur.tolist()
        withdrawals["shortfall_current_mean"] = shortfall_cur.tolist()
        withdrawals["realized_future_mean"]   = (total_realized_cur * deflator).tolist()

    # rmd_extra_current: mean surplus RMD beyond plan (candidate for reinvest).
    # Computed here (not inside apply_withdrawals block) so it's always valid —
    # when ignore_withdrawals=True, planned_cur=zeros and surplus = full RMD.
    rmd_extra_current = np.maximum(rmd_current_mean - planned_cur, 0.0)

    # =========================================================================
    # STEP 4: Reinvest surplus RMD into primary brokerage (if policy says so)
    #
    # Test 3 (ignore_withdrawals=True,  ignore_rmds=False):
    #   planned_cur = zeros → surplus = full per-path RMD → all goes to brokerage
    #
    # Test 4 (ignore_withdrawals=False, ignore_rmds=False):
    #   surplus = max(per-path RMD - mean plan, 0) → excess goes to brokerage
    #
    # acct_eoy_nom is mutated in-place here.
    # total_nom_paths recompute (STEP 5) MUST happen AFTER this block.
    # =========================================================================
    extra_handling = "cash_out"
    if person_cfg is not None:
        extra_handling = person_cfg.get("rmd_policy", {}).get("extra_handling", "cash_out")

    # Track per-account reinvestment (paths x YEARS) for pure-investment YoY
    reinvest_nom_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, YEARS), dtype=float) for acct in acct_eoy_nom.keys()
    }

    if (
        extra_handling == "reinvest_in_brokerage"
        and rmd_total_nom_paths is not None
        and brokerage_accounts
    ):
        primary_brokerage = brokerage_accounts[0]
        acct_b = acct_eoy_nom[primary_brokerage]

        for y in range(YEARS):
            # Spending plan in nominal dollars (scalar, mean-basis)
            plan_nom_y = planned_cur[y] * deflator[y]
            # Per-path nominal RMD
            rmd_nom_y = rmd_total_nom_paths[:, y]
            # Per-path surplus above the plan
            extra_rmd_nom_y = np.maximum(rmd_nom_y - plan_nom_y, 0.0)
            acct_b[:, y] = acct_b[:, y] + extra_rmd_nom_y
            reinvest_nom_per_acct[primary_brokerage][:, y] = extra_rmd_nom_y

    # If cash_out policy: nothing was reinvested — zero out the reinvested arrays.
    # Also patch realized: surplus RMD is received as cash (not reinvested),
    # so realized = max(plan, RMD), and diff = RMD - plan when RMD > plan.
    if extra_handling != "reinvest_in_brokerage":
        if extra_handling == "cash_out" and apply_withdrawals and sched is not None:
            total_realized_cur = total_realized_cur + rmd_extra_current
            withdrawals["realized_current_mean"] = total_realized_cur.tolist()
            withdrawals["realized_future_mean"]  = (total_realized_cur * deflator).tolist()
        rmd_extra_current = np.zeros(YEARS, dtype=float)

    # =========================================================================
    # STEP 5: Recompute total portfolio paths — AFTER all cashflows
    #   (RMD deductions, withdrawal pulls, reinvestment additions all done above)
    # =========================================================================
    total_nom_paths = np.zeros((paths, YEARS), dtype=float)
    for y in range(YEARS):
        total_nom_y = None
        for acct, bal in acct_eoy_nom.items():
            v = np.where(np.isfinite(bal[:, y]), bal[:, y], 0.0)
            total_nom_y = v if total_nom_y is None else (total_nom_y + v)
        total_nom_paths[:, y] = total_nom_y

    total_real_paths = total_nom_paths / np.maximum(deflator, 1e-12)

    # =========================================================================
    # STEP 6: Per-account levels and YoY stats (post-cashflow account balances)
    # 'starting' needed here for per-account year-1 YoY prior_col    # =========================================================================
    if apply_withdrawals and sched is not None:
        for _a in list(acct_eoy_nom.keys())[:3]:
            print(f"[WDEBUG STEP6] acct={_a} mean_y0={acct_eoy_nom[_a][:, 0].mean():.2f}")
    inv_nom_yoy_mean_pct_acct:   Dict[str, Any] = {}
    inv_real_yoy_mean_pct_acct:  Dict[str, Any] = {}
    inv_nom_levels_mean_acct:    Dict[str, Any] = {}
    inv_real_levels_mean_acct:   Dict[str, Any] = {}
    inv_nom_levels_med_acct:     Dict[str, Any] = {}
    inv_real_levels_med_acct:    Dict[str, Any] = {}
    inv_nom_levels_p10_acct:     Dict[str, Any] = {}
    inv_nom_levels_p90_acct:     Dict[str, Any] = {}
    inv_real_levels_p10_acct:    Dict[str, Any] = {}
    inv_real_levels_p90_acct:    Dict[str, Any] = {}

    for acct in list(acct_eoy_nom.keys()):
        lvl_nom  = acct_eoy_nom[acct]
        lvl_real = lvl_nom / deflator

        # Pure-investment YoY: use pre-cashflow snapshot (captured right after
        # simulate_balances, before RMDs / withdrawals / reinvestments).
        # Subtracting reinvest_nom from the post-withdrawal balance was wrong —
        # it left the withdrawal drag baked into the ratio denominator.
        lvl_nom_inv  = acct_eoy_nom_core.get(acct, lvl_nom)
        lvl_real_inv = lvl_nom_inv / deflator
        # Keep reinvest_nom available for the reinvestment summary below
        reinvest_nom = reinvest_nom_per_acct.get(acct, np.zeros((paths, YEARS), dtype=float))

        acct_start = float(starting.get(acct, 0.0))
        acct_start_nom = np.full(paths, acct_start, dtype=float)

        # Pure investment YoY: strip reinvestment inflows before ratio
        yoy_nom_inv  = pct_change_paths(lvl_nom_inv,  prior_col=acct_start_nom)
        yoy_real_inv = pct_change_paths(lvl_real_inv,
                                        prior_col=acct_start_nom)

        # Aggregate YoY: includes all cashflows (withdrawals, deposits, reinvestments)
        yoy_nom_agg  = pct_change_paths(lvl_nom,  prior_col=acct_start_nom)
        yoy_real_agg = pct_change_paths(lvl_real,
                                        prior_col=acct_start_nom)

        # r[:,y] = bal[y]/bal[y-1]-1, r[:,0] uses actual starting balance
        inv_nom_yoy_mean_pct_acct[acct]               = (yoy_nom_inv.mean(axis=0)   * 100.0).tolist()
        inv_real_yoy_mean_pct_acct[acct]              = (yoy_real_inv.mean(axis=0)  * 100.0).tolist()
        inv_nom_yoy_mean_pct_acct[acct + "__inv_med"] = (np.median(yoy_nom_inv, axis=0) * 100.0).tolist()
        inv_nom_yoy_mean_pct_acct[acct + "__agg_nom"] = (yoy_nom_agg.mean(axis=0)   * 100.0).tolist()
        inv_nom_yoy_mean_pct_acct[acct + "__agg_real"]= (yoy_real_agg.mean(axis=0)  * 100.0).tolist()
        inv_nom_yoy_mean_pct_acct[acct + "__agg_nom_med"] = (np.median(yoy_nom_agg, axis=0) * 100.0).tolist()

        # Reinvestment summary per account (current and future USD, mean)
        reinvest_cur_mean = (reinvest_nom / np.maximum(deflator, 1e-12)).mean(axis=0)
        reinvest_fut_mean = reinvest_nom.mean(axis=0)
        inv_nom_levels_mean_acct[acct + "__reinvest_cur"] = reinvest_cur_mean.tolist()
        inv_nom_levels_mean_acct[acct + "__reinvest_fut"] = reinvest_fut_mean.tolist()

        inv_nom_levels_mean_acct[acct]  = lvl_nom.mean(axis=0).tolist()
        inv_real_levels_mean_acct[acct] = lvl_real.mean(axis=0).tolist()
        inv_nom_levels_med_acct[acct]   = np.median(lvl_nom, axis=0).tolist()
        inv_real_levels_med_acct[acct]  = np.median(lvl_real, axis=0).tolist()
        inv_nom_levels_p10_acct[acct]   = np.percentile(lvl_nom, 10, axis=0).tolist()
        inv_nom_levels_p90_acct[acct]   = np.percentile(lvl_nom, 90, axis=0).tolist()
        inv_real_levels_p10_acct[acct]  = np.percentile(lvl_real, 10, axis=0).tolist()
        inv_real_levels_p90_acct[acct]  = np.percentile(lvl_real, 90, axis=0).tolist()

    # =========================================================================
    # STEP 7: Portfolio aggregates, YoY, CAGR, drawdown
    # =========================================================================
    fut_mean = total_nom_paths.mean(axis=0)
    fut_med  = np.median(total_nom_paths, axis=0)
    fut_p10  = np.percentile(total_nom_paths, 10, axis=0)
    fut_p90  = np.percentile(total_nom_paths, 90, axis=0)

    cur_mean = total_real_paths.mean(axis=0)
    cur_med  = np.median(total_real_paths, axis=0)
    cur_p10  = np.percentile(total_real_paths, 10, axis=0)
    cur_p90  = np.percentile(total_real_paths, 90, axis=0)

    inv_nom_yoy  = pct_change_paths(total_nom_paths,  prior_col=starting_total_nom)
    inv_real_yoy = pct_change_paths(total_real_paths,
                                    prior_col=starting_total_nom)

    # r[:,y] = bal[y]/bal[y-1]-1, r[:,0] uses actual starting balance
    nom_withdraw_yoy_mean_pct  = (inv_nom_yoy.mean(axis=0)  * 100.0).tolist()
    real_withdraw_yoy_mean_pct = (inv_real_yoy.mean(axis=0) * 100.0).tolist()

    start_nom  = np.maximum(total_nom_paths[:,  0], 1e-12)
    end_nom    = np.maximum(total_nom_paths[:, -1], 1e-12)
    start_real = np.maximum(total_real_paths[:,  0], 1e-12)
    end_real   = np.maximum(total_real_paths[:, -1], 1e-12)

    cagr_nom_paths  = (end_nom  / start_nom)  ** (1.0 / YEARS) - 1.0
    cagr_real_paths = (end_real / start_real) ** (1.0 / YEARS) - 1.0

    cagr_nom_mean   = float(cagr_nom_paths.mean())
    cagr_nom_median = float(np.median(cagr_nom_paths))
    cagr_nom_p10    = float(np.percentile(cagr_nom_paths, 10))
    cagr_nom_p90    = float(np.percentile(cagr_nom_paths, 90))

    cagr_real_mean   = float(cagr_real_paths.mean())
    cagr_real_median = float(np.median(cagr_real_paths))
    cagr_real_p10    = float(np.percentile(cagr_real_paths, 10))
    cagr_real_p90    = float(np.percentile(cagr_real_paths, 90))

    max_to_date = np.maximum.accumulate(total_nom_paths, axis=1)
    dd_end = (1.0 - (total_nom_paths / np.clip(max_to_date, 1e-12, None))[:, -1]) * 100.0
    drawdown_p50 = float(np.percentile(dd_end, 50))
    drawdown_p90 = float(np.percentile(dd_end, 90))

    success_rate_pct       = 100.0
    success_rate_by_year   = [100.0] * YEARS
    shortfall_years_mean   = 0.0

    # --- Attach RMD summaries and total-withdrawal totals to withdrawals dict ---
    withdrawals["rmd_current_mean"] = rmd_current_mean.tolist()
    withdrawals["rmd_future_mean"]  = rmd_future_mean.tolist()

    # Total withdrawal per year = max(plan, RMD) on a mean basis
    total_cur = np.maximum(planned_cur, rmd_current_mean)
    total_fut = total_cur * deflator   # deflator already built in STEP 1

    withdrawals["total_withdraw_current_mean"] = total_cur.tolist()
    withdrawals["total_withdraw_future_mean"]  = total_fut.tolist()
    withdrawals["rmd_extra_current"]           = rmd_extra_current.tolist()
    withdrawals["rmd_extra_future"]            = (rmd_extra_current * deflator).tolist()


    # Assemble res
    res: Dict[str, Any] = {}
    res["paths"] = int(paths)
    res["spy"] = int(spy)

    res["portfolio"] = {
        "years": list(range(1, YEARS + 1)),
        "future_mean": fut_mean.tolist(),
        "future_median": fut_med.tolist(),
        "future_p10_mean": fut_p10.tolist(),
        "future_p90_mean": fut_p90.tolist(),
        "current_mean": cur_mean.tolist(),
        "current_median": cur_med.tolist(),
        "current_p10_mean": cur_p10.tolist(),
        "current_p90_mean": cur_p90.tolist(),
    }

    # Scale CAGRs to percent before storing
    cagr_nom_mean   *= 100.0;  cagr_nom_median *= 100.0
    cagr_nom_p10    *= 100.0;  cagr_nom_p90    *= 100.0
    cagr_real_mean  *= 100.0;  cagr_real_median *= 100.0
    cagr_real_p10   *= 100.0;  cagr_real_p90   *= 100.0

    res["summary"] = {
        "success_rate":               success_rate_pct,
        "success_rate_by_year":       success_rate_by_year,
        "shortfall_years_mean":       shortfall_years_mean,
        "drawdown_p50":               drawdown_p50,
        "drawdown_p90":               drawdown_p90,
        "taxes_fed_total_current":    0.0,
        "taxes_state_total_current":  0.0,
        "taxes_niit_total_current":   0.0,
        "taxes_excise_total_current": 0.0,
        "tax_shortfall_total_current": 0.0,
        "rmd_total_current":          0.0,
        "cagr_nominal_mean":          cagr_nom_mean,
        "cagr_nominal_median":        cagr_nom_median,
        "cagr_nominal_p10":           cagr_nom_p10,
        "cagr_nominal_p90":           cagr_nom_p90,
        "cagr_real_mean":             cagr_real_mean,
        "cagr_real_median":           cagr_real_median,
        "cagr_real_p10":              cagr_real_p10,
        "cagr_real_p90":              cagr_real_p90,
    }


#    res["meta"] = {
#        "success": success_rate_pct,
#        "paths": int(paths),
#        "years": YEARS,
#    }

    res["meta"] = {
        "success": success_rate_pct,
        "paths": int(paths),
        "years": YEARS,
    }

    if person_cfg is not None:
        res["person"] = dict(person_cfg)


    res["returns"] = {
        "nom_withdraw_yoy_mean_pct": nom_withdraw_yoy_mean_pct,
        "real_withdraw_yoy_mean_pct": real_withdraw_yoy_mean_pct,

        # Investment-only YoY from core path
        "inv_nom_yoy_mean_pct": inv_nom_yoy_mean_pct_core,
        "inv_real_yoy_mean_pct": inv_real_yoy_mean_pct_core,

        # (plus your median/p10/p90 arrays if you’ve added them)
        #"inv_nom_yoy_median_pct": inv_nom_yoy_median_pct,
        #"inv_real_yoy_median_pct": inv_real_yoy_median_pct,
        #"inv_nom_yoy_p10_pct": inv_nom_yoy_p10_pct,
        #"inv_nom_yoy_p90_pct": inv_nom_yoy_p90_pct,
        #"inv_real_yoy_p10_pct": inv_real_yoy_p10_pct,
        #"inv_real_yoy_p90_pct": inv_real_yoy_p90_pct,
    }

    res["returns_acct"] = {
        "inv_nom_yoy_mean_pct_acct": inv_nom_yoy_mean_pct_acct,
        "inv_real_yoy_mean_pct_acct": inv_real_yoy_mean_pct_acct,
    }
    
    res["returns_acct_levels"] = {
        "inv_nom_levels_mean_acct": inv_nom_levels_mean_acct,
        "inv_real_levels_mean_acct": inv_real_levels_mean_acct,
        "inv_nom_levels_med_acct": inv_nom_levels_med_acct,
        "inv_nom_levels_p10_acct": inv_nom_levels_p10_acct,
        "inv_nom_levels_p90_acct": inv_nom_levels_p90_acct,
        "inv_real_levels_med_acct": inv_real_levels_med_acct,
        "inv_real_levels_p10_acct": inv_real_levels_p10_acct,
        "inv_real_levels_p90_acct": inv_real_levels_p90_acct,
    }


   # Withdrawals block for modular path (core-only: all zeros for now)
    res["withdrawals"] = withdrawals

    res["taxes"] = {
        "fed_year0_cur_paths_mean": float(taxes_fed_cur_paths.mean()) if taxes_fed_cur_paths is not None else 0.0,
        "state_year0_cur_paths_mean": float(taxes_state_cur_paths.mean()) if taxes_state_cur_paths is not None else 0.0,
        "niit_year0_cur_paths_mean": float(taxes_niit_cur_paths.mean()) if taxes_niit_cur_paths is not None else 0.0,
        "excise_year0_cur_paths_mean": float(taxes_excise_cur_paths.mean()) if taxes_excise_cur_paths is not None else 0.0,
    }

    # Starting balances and account types (for UI)

    accounts: List[Dict[str, str]] = []
    for name in starting.keys():
        u = name.upper()
        acct_type = ""
        if "BROKERAGE" in u or "TAXABLE" in u:
            acct_type = "taxable"
        elif ("TRAD" in u or "TRADITIONAL" in u) and "ROTH" not in u:
            acct_type = "traditional_ira"
        elif "ROTH" in u:
            acct_type = "roth_ira"
        accounts.append({"name": name, "type": acct_type})

    res["starting"] = starting
    res["accounts"] = accounts

    # DEBUG: inspect modular res for Test profile
    print("[DEBUG new-sim] summary keys:", list(res.get("summary", {}).keys()))
    print("[DEBUG new-sim] summary YoY scalars:",
          res["summary"].get("nominal_yoy_withdrawals_pct"),
          res["summary"].get("real_yoy_withdrawals_pct"),
          res["summary"].get("nominal_yoy_investment_pct"),
          res["summary"].get("real_yoy_investment_pct"))

    w = res.get("withdrawals", {})
    print("[DEBUG new-sim] withdrawals keys:", list(w.keys()))
    print("[DEBUG new-sim] withdrawals planned_current sample:",
          w.get("planned_current", [])[:5])
    print("[DEBUG new-sim] withdrawals realized_current_mean sample:",
          w.get("realized_current_mean", [])[:5])

    return res
