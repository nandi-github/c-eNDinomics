# filename: simulator_new.py

import logging
from typing import Dict, Any, Optional
import numpy as np

from simulation_core import simulate_balances
from rebalancing_core import apply_rebalancing, build_econ_policy_yearly
from withdrawals_core import apply_withdrawals_nominal_per_account
from taxes_core import compute_annual_taxes_paths

from rmd_core import build_rmd_factors, compute_rmd_schedule_nominal
from roth_conversion_core import (
    apply_simple_conversions,
    apply_bracket_fill_conversions,
    parse_roth_conversion_policy,
    compute_conversion_window_years,
)

logger = logging.getLogger(__name__)


# NOTE: YEARS = 30 removed — all call sites pass n_years explicitly.
# The simulation horizon is driven by target_age - current_age (api.py).


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
    min_prior: float = 1_000.0,
) -> np.ndarray:
    """
    Compute per-path year-over-year returns as FRACTIONS:
    r[:, y] = series[:, y] / series[:, y-1] - 1

    If prior_col (shape: paths,) is provided it is used as the year-0
    starting value so that r[:, 0] = series[:, 0] / prior_col - 1.
    Otherwise r[:, 0] = NaN (no prior data).

    When the prior-year balance is below min_prior (default $1,000 nominal)
    the ratio is meaningless (tiny denominator → exploding %). Those cells
    are set to NaN so they can be excluded from mean/median via np.nanmean.
    The UI renders NaN cells as "—" rather than a garbage percentage.
    """
    s = np.asarray(series_2d, dtype=float)
    if s.ndim != 2:
        s = s.reshape(s.shape[0], -1)
    P, Y = s.shape
    r = np.full_like(s, np.nan)
    if Y < 2:
        return r
    prev = s[:, :-1]
    valid = prev >= min_prior                        # (P, Y-1) bool mask
    safe_prev = np.where(valid, prev, 1.0)           # avoid division by zero
    ratio = s[:, 1:] / safe_prev - 1.0
    r[:, 1:] = np.where(valid, ratio, np.nan)
    if prior_col is not None:
        pc = np.asarray(prior_col, dtype=float)
        valid0 = pc >= min_prior
        safe_pc = np.where(valid0, pc, 1.0)
        r[:, 0] = np.where(valid0, s[:, 0] / safe_pc - 1.0, np.nan)
    return r

def run_accounts_new(
    paths: int,
    spy: int,
    infl_yearly: Optional[np.ndarray],
    alloc_accounts: Dict[str, Any],
    assets_path: Optional[str] = None,
    sched: Optional[np.ndarray] = None,
    sched_base: Optional[np.ndarray] = None,   # per-year minimum (floor) withdrawal
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
    conversions_enabled: bool = True,
    ignore_taxes: bool = False,     # When True: skip all tax computation, zero all tax arrays
    shocks_events: Optional[list] = None,
    shocks_mode: str = "augment",
    econ_policy: Optional[Dict[str, Any]] = None,
    rebalancing_enabled: bool = True,
    # -----------------------------------------------------------------------
    # Runtime override params — supplied by api.py when the Run panel has
    # user-selected values that differ from person.json. These take precedence
    # over person_cfg values for THIS run only. Echoed in res["meta"]["run_params"]
    # so every result is fully self-describing.
    # -----------------------------------------------------------------------
    override_state: Optional[str] = None,
    override_filing_status: Optional[str] = None,
    override_rmd_table: Optional[str] = None,
    n_years: Optional[int] = None,
) -> Dict[str, Any]:


    """
    Monte Carlo simulator with shocks, withdrawals, RMDs, and reinvestment.
    No taxes,
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
    n_years = int(n_years) if n_years is not None else 30

    # -----------------------------------------------------------------------
    # Resolve effective run parameters: runtime overrides win over person_cfg.
    # These are the values actually used for this run — recorded in meta.
    # -----------------------------------------------------------------------
    _pcfg = person_cfg or {}
    _eff_state          = override_state          or _pcfg.get("state", "California")
    _eff_filing_status  = override_filing_status  or _pcfg.get("filing_status", "MFJ")
    _eff_rmd_table      = override_rmd_table      or _pcfg.get("rmd_table", "uniform_lifetime")
    _overrides_applied  = {
        k: v for k, v in {
            "state":          override_state,
            "filing_status":  override_filing_status,
            "rmd_table":      override_rmd_table,
        }.items() if v is not None
    }

    # Core Monte Carlo
    acct_eoy_nom, total_nom_paths, total_real_paths, acct_class_eoy_nom = simulate_balances(
        paths=paths,
        years=n_years,
        spy=spy,
        alloc_accounts=alloc_accounts,
        assets_path=assets_path,
        shocks_events=shocks_events or [],
        shocks_mode=shocks_mode,
        infl_yearly=infl_yearly,
    )

    # ── Rebalancing ────────────────────────────────────────────────────────────
    rebal_gains_brokerage = np.zeros((paths, n_years), dtype=float)
    if rebalancing_enabled:
        econ_policy_yearly = build_econ_policy_yearly(
            econ_policy or {}, n_years
        )
        rebal_gains_brokerage, _, _ = apply_rebalancing(
            acct_eoy_nom       = acct_eoy_nom,
            acct_class_eoy_nom = acct_class_eoy_nom,
            alloc_accounts     = alloc_accounts,
            econ_policy_yearly = econ_policy_yearly,
            paths              = paths,
            years              = n_years,
        )
        if cap_gains_cur_paths is not None:
            cap_gains_cur_paths = cap_gains_cur_paths + rebal_gains_brokerage
        else:
            cap_gains_cur_paths = rebal_gains_brokerage.copy()
        logger.debug(
            "[sim] rebalancing enabled — mean annual brokerage gains: %s",
            np.mean(rebal_gains_brokerage, axis=0).round(0).tolist(),
        )

    # Snapshot core-only totals and account means before RMD/withdrawals/reinvest (for debug)
    core_total_nom_before = np.zeros((paths, n_years), dtype=float)
    core_acct_mean_before = {}
    for acct, bal in acct_eoy_nom.items():
        core_acct_mean_before[acct] = bal.mean(axis=0).copy()

    for y in range(n_years):
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
    ) else np.zeros(n_years, dtype=float)
    _deflator_y1 = float(1.0 + _infl_arr[0]) if len(_infl_arr) > 0 else 1.0

    inv_nom_yoy_paths_core = pct_change_paths(total_nom_paths_core,
                                               prior_col=starting_total_nom)

    # Build full deflator inline for real conversion of core paths
    _deflator_core = np.cumprod(1.0 + _infl_arr[:n_years]) if len(_infl_arr) >= n_years                      else np.ones(n_years, dtype=float)
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
        np.nanmean(inv_nom_yoy_paths_core_shifted, axis=0) * 100.0
    ).tolist()
    inv_real_yoy_mean_pct_core = (
        np.nanmean(inv_real_yoy_paths_core_shifted, axis=0) * 100.0
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
    rmd_future_mean = np.zeros(n_years, dtype=float)
    rmd_current_mean = np.zeros(n_years, dtype=float)
    
    rmd_extra_current = np.zeros(n_years, dtype=float)

    #if trad_accounts and rmd_table_path is not None and person_cfg is not None:
    if (
        rmds_enabled
        and trad_accounts
        and rmd_table_path is not None
        and person_cfg is not None
    ):
 
        owner_current_age = float(person_cfg.get("current_age", 60.0))
        # birth_year determines SECURE 2.0 RMD bracket only — independent of current_age
        owner_birth_year = int(person_cfg.get("birth_year", 0) or 0) or None
        rmd_factors = build_rmd_factors(
            rmd_table_path=rmd_table_path,
            owner_current_age=owner_current_age,
            years=n_years,
            owner_birth_year=owner_birth_year,
        )
    
        rmd_total_nom_paths, rmd_nom_per_acct = compute_rmd_schedule_nominal(
            trad_ira_balances_nom={a: acct_eoy_nom[a] for a in trad_accounts},
            rmd_factors=rmd_factors,
        )
    
        # Subtract RMDs from TRAD balances
        for y in range(n_years):
            for a in trad_accounts:
                bal = np.where(np.isfinite(acct_eoy_nom[a][:, y]), acct_eoy_nom[a][:, y], 0.0)
                take = np.where(np.isfinite(rmd_nom_per_acct[a][:, y]), rmd_nom_per_acct[a][:, y], 0.0)
                acct_eoy_nom[a][:, y] = bal - take
    
        # Summaries: mean RMD per year in future & current USD
        if rmd_total_nom_paths is not None:
            rmd_future_mean = rmd_total_nom_paths.mean(axis=0)
            if infl_yearly is not None and np.asarray(infl_yearly).size > 0:
                arr_rmd = np.asarray(infl_yearly, dtype=float).reshape(-1)
                if arr_rmd.size < n_years:
                    arr_rmd = np.concatenate(
                        [arr_rmd, np.full(n_years - arr_rmd.size, arr_rmd[-1] if arr_rmd.size > 0 else 0.0)]
                    )
                elif arr_rmd.size > n_years:
                    arr_rmd = arr_rmd[:n_years]
                deflator_rmd = np.cumprod(1.0 + arr_rmd)
            else:
                deflator_rmd = np.ones(n_years, dtype=float)
            rmd_current_mean = rmd_future_mean / np.maximum(deflator_rmd, 1e-12)
    
            # Add per-path RMD in current USD into ordinary income (optional)
            if ordinary_income_cur_paths is not None:
                for y in range(n_years):
                    rmd_cur_paths_y = rmd_total_nom_paths[:, y] / max(deflator_rmd[y], 1e-12)
                    ordinary_income_cur_paths[:, y] += rmd_cur_paths_y


    # --- Roth conversions — policy-driven ---
    conversion_nom_paths = None
    conversion_tax_cost_cur_paths = np.zeros((paths, n_years), dtype=float)
    conv_out_per_trad: Dict[str, np.ndarray] = {}
    conv_in_per_roth:  Dict[str, np.ndarray] = {}
    conv_tax_per_brok: Dict[str, np.ndarray] = {}

    _roth_policy  = parse_roth_conversion_policy(person_cfg or {})
    _conv_enabled = _roth_policy["enabled"]

    # Resolve conversion amount: explicit override > policy conversion_amount_k
    _raw_policy = _roth_policy.get("raw", {}) or {}
    if conversion_per_year_nom is None and _conv_enabled:
        _amount_k = float(_raw_policy.get("conversion_amount_k", 0.0))
        conversion_per_year_nom = _amount_k * 1_000.0 if _amount_k > 0.0 else None

    # Determine if bracket-fill mode is requested
    _keepit_str = str(_raw_policy.get("keepit_below_max_marginal_fed_rate", "")).strip().lower()
    _bracket_fill_mode = (
        _conv_enabled
        and tax_cfg is not None
        and ordinary_income_cur_paths is not None
        and ("fill" in _keepit_str or _keepit_str.replace("%", "").replace(".", "").isdigit())
    )

    # Resolve window from policy
    _current_age    = float((person_cfg or {}).get("current_age", 65))
    _window_end_age = _roth_policy.get("window_end_age")
    if _window_end_age is not None:
        _window_start_y, _window_end_y = compute_conversion_window_years(
            current_age=_current_age,
            window_end_age=_window_end_age,
            years=n_years,
        )
    else:
        _window_start_y, _window_end_y = 0, n_years

    # Build deflator for conversion block (STEP 1 builds it again later; this is intentional)
    _deflator_conv = np.ones(n_years, dtype=float)
    if infl_yearly is not None and np.asarray(infl_yearly).size > 0:
        _arr_conv = np.asarray(infl_yearly, dtype=float).reshape(-1)
        if _arr_conv.size < n_years:
            _arr_conv = np.concatenate(
                [_arr_conv, np.full(n_years - _arr_conv.size, _arr_conv[-1] if _arr_conv.size > 0 else 0.0)]
            )
        elif _arr_conv.size > n_years:
            _arr_conv = _arr_conv[:n_years]
        _deflator_conv = np.cumprod(1.0 + _arr_conv)

    if trad_accounts and roth_accounts and _conv_enabled and conversions_enabled:

        if _bracket_fill_mode:
            # ── Bracket-fill: compute conversion amount per-path per-year
            # based on how much income headroom exists before next bracket.
            # ordinary_income_cur_paths already includes RMDs at this point.
            # apply_bracket_fill_conversions also:
            #   - adds conversion to ordinary_income_cur_paths
            #   - computes tax cost
            #   - debits tax from brokerage
            brokerage_balances_nom = {a: acct_eoy_nom[a] for a in brokerage_accounts}
            _ytd = ytd_income_nom_paths if ytd_income_nom_paths is not None else np.zeros((paths, n_years), dtype=float)

            _conv_result = apply_bracket_fill_conversions(
                    trad_ira_balances_nom      = {a: acct_eoy_nom[a] for a in trad_accounts},
                    roth_ira_balances_nom      = {a: acct_eoy_nom[a] for a in roth_accounts},
                    brokerage_balances_nom     = brokerage_balances_nom,
                    ordinary_income_cur_paths  = ordinary_income_cur_paths,
                    ytd_income_nom_paths       = _ytd,
                    tax_cfg                    = tax_cfg,
                    roth_policy                = _roth_policy,
                    deflator                   = _deflator_conv,
                    window_start_y             = _window_start_y,
                    window_end_y               = _window_end_y,
            )
            # roth_conversion_core returns 8 values:
            # updated_trad, updated_roth, updated_brok,
            # conversion_nom_paths, tax_cost_cur_paths,
            # conv_out_per_trad, conv_in_per_roth, conv_tax_per_brok
            (updated_trad, updated_roth, updated_brok,
             conversion_nom_paths, conversion_tax_cost_cur_paths,
             conv_out_per_trad, conv_in_per_roth, conv_tax_per_brok) = _conv_result
            for a in trad_accounts:
                acct_eoy_nom[a] = updated_trad[a]
            for a in roth_accounts:
                acct_eoy_nom[a] = updated_roth[a]
            for a in brokerage_accounts:
                acct_eoy_nom[a] = updated_brok[a]

            _mean_conv = float(conversion_nom_paths.mean())
            _mean_tax  = float(conversion_tax_cost_cur_paths.mean())
            logger.info(
                "[sim] Roth bracket-fill conversions | window y%d-y%d | age %.0f→%.0f"
                " | mean_conv_nom=$%.0f | mean_tax_cur=$%.0f",
                _window_start_y, _window_end_y,
                _current_age, _current_age + _window_end_y,
                _mean_conv, _mean_tax,
            )
            logger.info(
                "[DIAG] conversion_nom_paths per-year mean (all 30 yrs): %s",
                np.round(conversion_nom_paths.mean(axis=0), 0).tolist(),
            )
            logger.info(
                "[DIAG] TRAD accts year 1-5 mean post-conv: %s",
                {a: np.round(acct_eoy_nom[a][:, :5].mean(axis=0), 0).tolist()
                 for a in trad_accounts},
            )
            logger.info(
                "[DIAG] ROTH accts year 1-5 mean post-conv: %s",
                {a: np.round(acct_eoy_nom[a][:, :5].mean(axis=0), 0).tolist()
                 for a in roth_accounts},
            )

        elif conversion_per_year_nom is not None:
            # ── Fixed-amount fallback (conversion_amount_k in person.json)
            trad_balances_nom = {a: acct_eoy_nom[a] for a in trad_accounts}
            roth_balances_nom = {a: acct_eoy_nom[a] for a in roth_accounts}

            updated_trad, updated_roth, conversion_nom_paths = apply_simple_conversions(
                trad_ira_balances_nom  = trad_balances_nom,
                roth_ira_balances_nom  = roth_balances_nom,
                conversion_per_year_nom = float(conversion_per_year_nom),
                window_start_y         = _window_start_y,
                window_end_y           = _window_end_y,
            )
            for a in trad_accounts:
                acct_eoy_nom[a] = updated_trad[a]
            for a in roth_accounts:
                acct_eoy_nom[a] = updated_roth[a]

            # Note: ordinary_income_cur_paths already updated inside apply_bracket_fill_conversions

            logger.info(
                "[sim] Roth fixed conversions | amount=$%.0f/yr | window y%d-y%d | age %.0f→%.0f",
                float(conversion_per_year_nom),
                _window_start_y, _window_end_y,
                _current_age, _current_age + _window_end_y,
            )
        else:
            logger.info(
                "[sim] Roth conversions ENABLED but no amount configured"
                " — set conversion_amount_k or keepit_below_max_marginal_fed_rate"
            )

    # (no legacy withdrawals block here anymore)

    # --- Taxes over all years (current USD, per-path) — modular path only ---
    taxes_fed_cur_paths = np.zeros((paths, n_years), dtype=float)
    taxes_state_cur_paths = np.zeros((paths, n_years), dtype=float)
    taxes_niit_cur_paths = np.zeros((paths, n_years), dtype=float)
    taxes_excise_cur_paths = np.zeros((paths, n_years), dtype=float)

    if (
        not ignore_taxes
        and tax_cfg is not None
        and ordinary_income_cur_paths is not None
        and qual_div_cur_paths is not None
        and cap_gains_cur_paths is not None
        and ytd_income_nom_paths is not None
    ):
        for y in range(n_years):
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
    deflator = np.ones(n_years, dtype=float)
    if infl_yearly is not None and np.asarray(infl_yearly).size > 0:
        _arr = np.asarray(infl_yearly, dtype=float).reshape(-1)
        if _arr.size < n_years:
            _arr = np.concatenate(
                [_arr, np.full(n_years - _arr.size, _arr[-1] if _arr.size > 0 else 0.0)]
            )
        elif _arr.size > n_years:
            _arr = _arr[:n_years]
        deflator = np.cumprod(1.0 + _arr)

    # =========================================================================
    # STEP 2: Withdrawals dict — init all zeros; populated below if enabled
    # =========================================================================
    zeros = np.zeros(n_years, dtype=float)
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
        "taxes_fed_current_mean":          taxes_fed_cur_paths.mean(axis=0).tolist(),
        "taxes_state_current_mean":        taxes_state_cur_paths.mean(axis=0).tolist(),
        "taxes_niit_current_mean":         taxes_niit_cur_paths.mean(axis=0).tolist(),
        "taxes_excise_current_mean":       taxes_excise_cur_paths.mean(axis=0).tolist(),

        "tax_shortfall_current_mean":   zeros.tolist(),
        "realized_gains_current_mean":  zeros.tolist(),
        "rmd_current_mean":             zeros.tolist(),
        "rmd_future_mean":              zeros.tolist(),
        "total_withdraw_current_mean":  zeros.tolist(),
        "total_withdraw_future_mean":   zeros.tolist(),
        "net_spendable_current_mean":   zeros.tolist(),
    }

    planned_cur = np.zeros(n_years, dtype=float)

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

    # Per-account withdrawal outflow tracker (paths × n_years).
    # Accumulated inside the STEP 3 loop; available in STEP 6 for per-account stats.
    withdrawal_out_nom_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, n_years), dtype=float) for acct in acct_eoy_nom.keys()
    }

    # Per-path shortfall tracker — populated inside withdrawal loop.
    # Always defined here so success rate computation is unconditional.
    _shortfall_any_path = np.zeros((paths, n_years), dtype=bool)

    if apply_withdrawals and sched is not None:
        sched_vec = np.asarray(sched, dtype=float).reshape(-1)
        if sched_vec.size < n_years:
            sched_vec = np.concatenate(
                [sched_vec, np.full(n_years - sched_vec.size, sched_vec[-1])]
            )
        elif sched_vec.size > n_years:
            sched_vec = sched_vec[:n_years]

        planned_cur = sched_vec.copy()

        # Mean-basis: how much does the plan exceed the mean RMD each year?
        extra_cur = np.maximum(planned_cur - rmd_current_mean, 0.0)

        realized_cur   = np.zeros(n_years, dtype=float)
        shortfall_cur  = np.zeros(n_years, dtype=float)
        # Full per-path realized/shortfall — needed for median-path reporting
        realized_nom_paths   = np.zeros((paths, n_years), dtype=float)
        shortfall_nom_paths  = np.zeros((paths, n_years), dtype=float)
        # Per-path shortfall tracker: True if path had any shortfall in that year
        _shortfall_any_path = np.zeros((paths, n_years), dtype=bool)
        withdrawals["realized_current_per_acct_mean"]  = {}
        withdrawals["shortfall_current_per_acct_mean"] = {}

        # withdraw_sequence may be a flat list (same every year) or a list-of-lists (per year).
        # Normalise to per-year so the simulator always uses seq_y for year y.
        _fallback_seq = list(acct_eoy_nom.keys())
        if withdraw_sequence is None:
            _seq_per_year = [_fallback_seq] * n_years
        elif withdraw_sequence and isinstance(withdraw_sequence[0], list):
            # Already per-year list-of-lists
            _seq_per_year = withdraw_sequence
        else:
            # Flat list — use same sequence every year
            _seq_per_year = [withdraw_sequence] * n_years

        # ---------------------------------------------------------------
        # IRS age gate: before 59.5, TRAD IRA and ROTH withdrawals incur
        # a 10% early-withdrawal penalty.  Hard-enforce brokerage-only
        # regardless of what the withdrawal_sequence config says.
        # After 59.5 the configured sequence is used as-is.
        # ---------------------------------------------------------------
        owner_age_y0 = float(person_cfg.get("current_age", 60.0)) if person_cfg else 60.0
        brokerage_only_seq = [a for a in _fallback_seq if _is_brokerage(a)]
        if not brokerage_only_seq:
            brokerage_only_seq = [a for a in acct_eoy_nom.keys() if _is_brokerage(a)]

        _seq_per_year = [
            brokerage_only_seq if (owner_age_y0 + y) < 59.5 else
            (_seq_per_year[y] if y < len(_seq_per_year) else _fallback_seq)
            for y in range(n_years)
        ]

        # Base (floor) withdrawal schedule — pad/trim to n_years
        if sched_base is not None:
            _sb = np.asarray(sched_base, dtype=float)
            if _sb.size < n_years:
                _sb = np.concatenate([_sb, np.full(n_years - _sb.size, _sb[-1] if _sb.size else 0.0)])
            elif _sb.size > n_years:
                _sb = _sb[:n_years]
            _sched_base = _sb
        else:
            _sched_base = np.zeros(n_years, dtype=float)

        for y in range(n_years):
            extra_nom = extra_cur[y] * deflator[y]
            amount_nom_paths = np.full(paths, extra_nom, dtype=float)
            seq = _seq_per_year[y] if y < len(_seq_per_year) else _fallback_seq

            if y == 0:
                logger.debug("[WDEBUG y=0] extra_cur[0]=%.2f deflator[0]=%.4f extra_nom=%.2f",
                             extra_cur[0], deflator[0], extra_nom)
                logger.debug("[WDEBUG y=0] seq[:3]=%s", seq[:3])
                for _a in list(acct_eoy_nom.keys())[:3]:
                    _arr = acct_eoy_nom[_a]
                    logger.debug("[WDEBUG y=0] acct=%s flags=%s mean_y0=%.2f",
                                 _a, _arr.flags['WRITEABLE'], _arr[:, 0].mean())

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
                    logger.debug("[WDEBUG y=0] sold_per_acct[%s] sum=%.2f",
                                 _a, sold_per_acct_nom[_a].sum())

            # Explicitly deduct sold amounts from each account's balance for year y.
            # withdrawals_core no longer mutates the arrays itself; we own that here
            # to guarantee the deduction persists into STEP 5 / STEP 6 statistics.
            for acct, sold_arr in sold_per_acct_nom.items():
                if acct in acct_eoy_nom and np.any(sold_arr > 0):
                    acct_eoy_nom[acct][:, y] = np.maximum(
                        acct_eoy_nom[acct][:, y] - sold_arr, 0.0
                    )
                # Accumulate withdrawal outflow for STEP 6 per-account reporting
                if acct in withdrawal_out_nom_per_acct:
                    withdrawal_out_nom_per_acct[acct][:, y] = sold_arr

            if y == 0:
                for _a in list(acct_eoy_nom.keys())[:3]:
                    logger.debug("[WDEBUG post-deduct y=0] acct=%s mean_y0=%.2f",
                                 _a, acct_eoy_nom[_a][:, 0].mean())

            scale = max(deflator[y], 1e-12)
            realized_cur[y]  = (realized_total_nom / scale).mean()
            shortfall_cur[y] = (shortfall_total_nom / scale).mean()
            # Track which paths had shortfall this year (for success rate)
            _shortfall_any_path[:, y] = shortfall_total_nom > 1e-6
            # Accumulate per-path realized/shortfall for median-path reporting
            realized_nom_paths[:, y]  = realized_total_nom
            shortfall_nom_paths[:, y] = shortfall_total_nom

            for acct in acct_eoy_nom.keys():
                rn = realized_per_acct_nom.get(acct)
                sn = shortfall_per_acct_nom.get(acct)
                if rn is not None:
                    withdrawals["realized_current_per_acct_mean"].setdefault(acct, [0.0] * n_years)
                    withdrawals["realized_current_per_acct_mean"][acct][y] = (rn / scale).mean()
                if sn is not None:
                    withdrawals["shortfall_current_per_acct_mean"].setdefault(acct, [0.0] * n_years)
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
        # Base (floor) schedule — useful for tax engine and UI to show desired vs minimum
        _base_cur = _sched_base if '_sched_base' in dir() else np.zeros(n_years, dtype=float)
        withdrawals["base_current"]           = _base_cur.tolist()
        withdrawals["base_future_mean"]       = (_base_cur * deflator).tolist()

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

    # Track per-account reinvestment (paths x n_years) for pure-investment YoY
    reinvest_nom_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, n_years), dtype=float) for acct in acct_eoy_nom.keys()
    }

    if (
        extra_handling == "reinvest_in_brokerage"
        and rmd_total_nom_paths is not None
        and brokerage_accounts
    ):
        for y in range(n_years):
            # Spending plan in nominal dollars (scalar, mean-basis)
            plan_nom_y = planned_cur[y] * deflator[y]
            # Per-path surplus RMD above the plan
            rmd_nom_y = rmd_total_nom_paths[:, y]
            extra_rmd_nom_y = np.maximum(rmd_nom_y - plan_nom_y, 0.0)

            # Proportional split across brokerage accounts by their current balance.
            # Each brokerage receives: surplus * (its balance / total brokerage balance).
            brok_bals = np.stack(
                [np.maximum(acct_eoy_nom[b][:, y], 0.0) for b in brokerage_accounts],
                axis=1
            )  # shape (paths, n_brok)
            total_brok = brok_bals.sum(axis=1, keepdims=True)  # (paths, 1)
            # Equal split when all balances are zero (edge case)
            n_brok = len(brokerage_accounts)
            fracs = np.where(
                total_brok > 1e-12,
                brok_bals / np.maximum(total_brok, 1e-12),
                np.full_like(brok_bals, 1.0 / n_brok)
            )  # (paths, n_brok)

            for i, b in enumerate(brokerage_accounts):
                share = extra_rmd_nom_y * fracs[:, i]          # (paths,)
                acct_eoy_nom[b][:, y] = acct_eoy_nom[b][:, y] + share
                reinvest_nom_per_acct[b][:, y] = share

    # If cash_out policy: nothing was reinvested — zero out the reinvested arrays.
    # Also patch realized: surplus RMD is received as cash (not reinvested),
    # so realized = max(plan, RMD), and diff = RMD - plan when RMD > plan.
    if extra_handling != "reinvest_in_brokerage":
        if extra_handling == "cash_out" and apply_withdrawals and sched is not None:
            total_realized_cur = total_realized_cur + rmd_extra_current
            withdrawals["realized_current_mean"] = total_realized_cur.tolist()
            withdrawals["realized_future_mean"]  = (total_realized_cur * deflator).tolist()
        rmd_extra_current = np.zeros(n_years, dtype=float)

    # =========================================================================
    # STEP 4b: Debit ordinary income taxes from brokerage accounts
    #
    # taxes_fed/state/niit/excise_cur_paths are in current $. Convert to nominal
    # and debit proportionally across brokerage accounts by balance each year.
    # Conversion taxes are already handled inside apply_bracket_fill_conversions
    # (conv_tax_per_brok) — subtract that to avoid double-debiting.
    # =========================================================================
    if brokerage_accounts and tax_cfg is not None:
        for y in range(n_years):
            scale = max(float(deflator[y]), 1e-12)
            # Total ordinary tax this year (nominal $), net of conversion tax already debited
            conv_tax_nom_y = np.zeros(paths, dtype=float)
            for b in brokerage_accounts:
                conv_tax_nom_y += conv_tax_per_brok.get(b, np.zeros((paths, n_years)))[: ,y]
            total_tax_nom_y = (
                taxes_fed_cur_paths[:, y]
                + taxes_state_cur_paths[:, y]
                + taxes_niit_cur_paths[:, y]
                + taxes_excise_cur_paths[:, y]
            ) * scale - conv_tax_nom_y
            total_tax_nom_y = np.maximum(total_tax_nom_y, 0.0)

            # Proportional split by brokerage balance
            brok_bals = np.stack(
                [np.maximum(acct_eoy_nom[b][:, y], 0.0) for b in brokerage_accounts], axis=1
            )
            total_brok = brok_bals.sum(axis=1, keepdims=True)
            n_brok = len(brokerage_accounts)
            fracs = np.where(
                total_brok > 1e-12,
                brok_bals / np.maximum(total_brok, 1e-12),
                np.full_like(brok_bals, 1.0 / n_brok)
            )
            for i, b in enumerate(brokerage_accounts):
                share = total_tax_nom_y * fracs[:, i]
                acct_eoy_nom[b][:, y] = np.maximum(acct_eoy_nom[b][:, y] - share, 0.0)

    # =========================================================================
    # STEP 5: Recompute total portfolio paths — AFTER all cashflows
    #   (RMD deductions, withdrawal pulls, reinvestment additions all done above)
    # =========================================================================
    total_nom_paths = np.zeros((paths, n_years), dtype=float)
    for y in range(n_years):
        total_nom_y = None
        for acct, bal in acct_eoy_nom.items():
            v = np.where(np.isfinite(bal[:, y]), bal[:, y], 0.0)
            total_nom_y = v if total_nom_y is None else (total_nom_y + v)
        total_nom_paths[:, y] = total_nom_y

    total_real_paths = total_nom_paths / np.maximum(deflator, 1e-12)

    # =========================================================================
    # STEP 5b: Identify median path — the path whose final-year portfolio
    # is closest to the cross-sectional median. Used to report withdrawals,
    # taxes, RMD, and conversions as a fully consistent single-path scenario
    # rather than independent per-year means.
    # =========================================================================
    _final_balances   = total_nom_paths[:, -1]
    _median_balance   = float(np.median(_final_balances))
    _median_path_idx  = int(np.argmin(np.abs(_final_balances - _median_balance)))

    def _med_path(arr2d: np.ndarray) -> np.ndarray:
        """Extract the median path row from a (paths, n_years) array."""
        return arr2d[_median_path_idx, :]

    # Store median-path tax arrays — merged into res["taxes"] at assembly time below
    # Total ordinary income = everything taxed (W2 + RMD + conversions + cap gains + dividends)
    # This is the correct denominator for effective tax rate
    _ord_income_med = None
    if ordinary_income_cur_paths is not None:
        _ord_income_med = _med_path(ordinary_income_cur_paths).tolist()

    _taxes_median_path = {
        "taxes_fed_current_median_path":       _med_path(taxes_fed_cur_paths).tolist(),
        "taxes_state_current_median_path":     _med_path(taxes_state_cur_paths).tolist(),
        "taxes_niit_current_median_path":      _med_path(taxes_niit_cur_paths).tolist(),
        "taxes_excise_current_median_path":    _med_path(taxes_excise_cur_paths).tolist(),
        "total_ordinary_income_median_path":   _ord_income_med or [0.0] * n_years,
    }
    # Merge into withdrawals so snapshot.withdrawals has these fields.
    # App.tsx reads all per-year arrays from W = snapshot.withdrawals.
    # Without this, the effective rate denominator falls back to (twE+cvE)
    # which is far too small → rate > 100% → guard shows dash.
    withdrawals.update(_taxes_median_path)

    # =========================================================================
    # STEP 6: Per-account levels and YoY stats (post-cashflow account balances)
    # 'starting' needed here for per-account year-1 YoY prior_col    # =========================================================================
    if apply_withdrawals and sched is not None:
        for _a in list(acct_eoy_nom.keys())[:3]:
            logger.debug("[WDEBUG STEP6] acct=%s mean_y0=%.2f",
                         _a, acct_eoy_nom[_a][:, 0].mean())
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

    # -----------------------------------------------------------------------
    # Pre-compute: how much of each year's plan each TRAD account's RMD covers.
    # Uses proportional attribution: each account's share = its RMD / total RMD.
    # Both accounts independently owe RMDs regardless of each other, so the
    # plan spending funded by RMDs is attributed proportionally.
    # Withdrawal Out = proportional plan share + any extra discretionary sold.
    # Reinvested    = RMD Out - Withdrawal Out (surplus above plan, per account).
    # -----------------------------------------------------------------------
    rmd_covers_plan_per_acct: Dict[str, np.ndarray] = {}
    if rmd_nom_per_acct is not None and rmd_total_nom_paths is not None:
        for y in range(n_years):
            plan_nom_y  = planned_cur[y] * deflator[y]            # scalar
            rmd_total_y = rmd_total_nom_paths[:, y]               # per-path total RMD
            rmd_covers_total_y = np.minimum(rmd_total_y, plan_nom_y)  # per-path plan covered

            for a, rmd_arr in rmd_nom_per_acct.items():
                acct_rmd_y = rmd_arr[:, y]
                # Fraction of total RMD from this account (per path)
                frac_y = np.where(rmd_total_y > 1e-12,
                                  acct_rmd_y / np.maximum(rmd_total_y, 1e-12),
                                  0.0)
                if a not in rmd_covers_plan_per_acct:
                    rmd_covers_plan_per_acct[a] = np.zeros((paths, n_years), dtype=float)
                rmd_covers_plan_per_acct[a][:, y] = frac_y * rmd_covers_total_y

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
        reinvest_nom = reinvest_nom_per_acct.get(acct, np.zeros((paths, n_years), dtype=float))

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

        # r[:,y] = bal[y]/bal[y-1]-1, r[:,0] uses actual starting balance.
        # Use nanmean/nanmedian so NaN cells (prior balance < $1k) are excluded
        # rather than polluting the mean with division-by-near-zero garbage.
        def _pct_tolist(arr2d):
            """nanmean over paths, scale to %, replace NaN with None for JSON.
            nanmean/nanmedian emit 'mean of empty slice' via Python warnings
            (not numpy errstate) when all paths are NaN for a column — expected
            for depleted accounts. Suppress with warnings.catch_warnings."""
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore", RuntimeWarning)
                m = np.nanmean(arr2d, axis=0) * 100.0
            return [None if np.isnan(v) else float(v) for v in m]

        def _pct_med_tolist(arr2d):
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore", RuntimeWarning)
                m = np.nanmedian(arr2d, axis=0) * 100.0
            return [None if np.isnan(v) else float(v) for v in m]

        inv_nom_yoy_mean_pct_acct[acct]               = _pct_tolist(yoy_nom_inv)
        inv_real_yoy_mean_pct_acct[acct]              = _pct_tolist(yoy_real_inv)
        inv_nom_yoy_mean_pct_acct[acct + "__inv_med"] = _pct_med_tolist(yoy_nom_inv)
        inv_nom_yoy_mean_pct_acct[acct + "__agg_nom"] = _pct_tolist(yoy_nom_agg)
        inv_nom_yoy_mean_pct_acct[acct + "__agg_real"]= _pct_tolist(yoy_real_agg)
        inv_nom_yoy_mean_pct_acct[acct + "__agg_nom_med"] = _pct_med_tolist(yoy_nom_agg)

        # Reinvestment summary per account (current and future USD, mean)
        reinvest_cur_mean = (reinvest_nom / np.maximum(deflator, 1e-12)).mean(axis=0)
        reinvest_fut_mean = reinvest_nom.mean(axis=0)
        inv_nom_levels_mean_acct[acct + "__reinvest_cur"] = reinvest_cur_mean.tolist()
        inv_nom_levels_mean_acct[acct + "__reinvest_fut"] = reinvest_fut_mean.tolist()

        # RMD outflow per account (non-zero for TRAD IRAs only)
        rmd_out_nom = (rmd_nom_per_acct or {}).get(acct, np.zeros((paths, n_years), dtype=float))
        rmd_out_cur_mean = (rmd_out_nom / np.maximum(deflator, 1e-12)).mean(axis=0)
        rmd_out_fut_mean = rmd_out_nom.mean(axis=0)
        inv_nom_levels_mean_acct[acct + "__rmd_out_cur"] = rmd_out_cur_mean.tolist()
        inv_nom_levels_mean_acct[acct + "__rmd_out_fut"] = rmd_out_fut_mean.tolist()

        # Withdrawal outflow per account:
        #   = discretionary sold (plan > RMD years)
        #   + portion of RMD that funded the plan (RMD >= plan years)
        #
        # When RMD > plan: the full planned spend is embedded in the RMD deduction.
        #   Attribute it proportionally across TRAD accounts by their RMD share.
        # When plan > RMD: RMD covers plan up to its amount, discretionary sold covers the rest.
        #
        # Reinvested (surplus) = RMD Out - rmd_covers_plan = max(RMD - plan, 0) * frac
        discretionary_nom = withdrawal_out_nom_per_acct.get(acct, np.zeros((paths, n_years), dtype=float))

        if _is_trad(acct) and rmd_nom_per_acct is not None:
            # Use waterfall pre-computed coverage (sequential, not proportional)
            rmd_covers_plan_nom = rmd_covers_plan_per_acct.get(
                acct, np.zeros((paths, n_years), dtype=float)
            )
            # Total withdrawal = RMD-covered plan portion + any extra discretionary sold
            withdrawal_out_nom   = rmd_covers_plan_nom + discretionary_nom
            # Reinvested surplus = RMD beyond what covered the plan
            reinvest_surplus_nom = np.maximum(rmd_out_nom - rmd_covers_plan_nom, 0.0)
        else:
            withdrawal_out_nom   = discretionary_nom
            reinvest_surplus_nom = np.zeros((paths, n_years), dtype=float)

        withdrawal_out_cur_mean = (withdrawal_out_nom / np.maximum(deflator, 1e-12)).mean(axis=0)
        withdrawal_out_fut_mean = withdrawal_out_nom.mean(axis=0)
        inv_nom_levels_mean_acct[acct + "__withdrawal_out_cur"] = withdrawal_out_cur_mean.tolist()
        inv_nom_levels_mean_acct[acct + "__withdrawal_out_fut"] = withdrawal_out_fut_mean.tolist()

        # For TRAD accounts: reinvest_nom is now the RMD surplus (overrides the zero default).
        # For brokerage: reinvest_nom remains as the inflow received from TRAD surplus.
        if _is_trad(acct):
            reinvest_nom = reinvest_surplus_nom

        # Conversion flows per account (from roth_conversion_core per-account tracking)
        _zeros_pa = np.zeros((paths, n_years), dtype=float)
        if _is_trad(acct):
            conv_out_nom = conv_out_per_trad.get(acct, _zeros_pa)
            inv_nom_levels_mean_acct[acct + "__conversion_out_cur"] = \
                (conv_out_nom / np.maximum(deflator, 1e-12)).mean(axis=0).tolist()
            inv_nom_levels_mean_acct[acct + "__conversion_out_fut"] = \
                conv_out_nom.mean(axis=0).tolist()
        elif _is_roth(acct):
            conv_in_nom = conv_in_per_roth.get(acct, _zeros_pa)
            inv_nom_levels_mean_acct[acct + "__conversion_in_cur"] = \
                (conv_in_nom / np.maximum(deflator, 1e-12)).mean(axis=0).tolist()
            inv_nom_levels_mean_acct[acct + "__conversion_in_fut"] = \
                conv_in_nom.mean(axis=0).tolist()
        elif _is_brokerage(acct):
            conv_tax_nom = conv_tax_per_brok.get(acct, _zeros_pa)
            inv_nom_levels_mean_acct[acct + "__conv_tax_out_cur"] = \
                (conv_tax_nom / np.maximum(deflator, 1e-12)).mean(axis=0).tolist()
            inv_nom_levels_mean_acct[acct + "__conv_tax_out_fut"] = \
                conv_tax_nom.mean(axis=0).tolist()

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

    cagr_nom_paths  = (end_nom  / start_nom)  ** (1.0 / n_years) - 1.0
    cagr_real_paths = (end_real / start_real) ** (1.0 / n_years) - 1.0

    cagr_nom_mean   = float(cagr_nom_paths.mean())
    cagr_nom_median = float(np.median(cagr_nom_paths))
    cagr_nom_p10    = float(np.percentile(cagr_nom_paths, 10))
    cagr_nom_p90    = float(np.percentile(cagr_nom_paths, 90))

    cagr_real_mean   = float(cagr_real_paths.mean())
    cagr_real_median = float(np.median(cagr_real_paths))
    cagr_real_p10    = float(np.percentile(cagr_real_paths, 10))
    cagr_real_p90    = float(np.percentile(cagr_real_paths, 90))

    # Drawdown: worst peak-to-trough over the FULL simulation period per path.
    # max_to_date[path, y] = running portfolio peak up to year y.
    # dd_each[path, y] = fractional drawdown from peak at that year.
    # dd_max_per_path = worst single drawdown any path experienced at any year.
    # P50/P90 across paths: median and bad-case worst-drawdown experience.
    max_to_date    = np.maximum.accumulate(total_nom_paths, axis=1)
    dd_each        = (1.0 - total_nom_paths / np.clip(max_to_date, 1e-12, None)) * 100.0
    dd_max_per_path = dd_each.max(axis=1)   # worst drawdown this path ever saw
    drawdown_p50   = float(np.percentile(dd_max_per_path, 50))
    drawdown_p90   = float(np.percentile(dd_max_per_path, 90))

    # Per-year drawdown percentiles — cross-section across all paths at each year.
    # dd_each[:, y] = drawdown each path is experiencing at year y (from its own running peak).
    # P50 = median path drawdown that year; P90 = bad-case drawdown that year.
    # These power the drawdown-over-time chart in the UI.
    drawdown_by_year_p50 = [float(np.percentile(dd_each[:, y], 50)) for y in range(n_years)]
    drawdown_by_year_p90 = [float(np.percentile(dd_each[:, y], 90)) for y in range(n_years)]

    # Success rate: % of paths that FULLY delivered the planned withdrawal every year.
    # A path "fails" in any year where realized < planned (shortfall > 0).
    # Uses _shortfall_any_path accumulated during STEP 3 (only set when withdrawals enabled).
    # When withdrawals are disabled, all paths succeed by definition.
    # _shortfall_any_path always defined above (zeros when withdrawals disabled)
    _path_ever_short = _shortfall_any_path.any(axis=1)
    _first_short_yr  = np.where(
        _path_ever_short,
        np.argmax(_shortfall_any_path, axis=1),
        n_years,
    )

    success_rate_pct = float(100.0 * (~_path_ever_short).mean())
    # Per-year: % of paths with no shortfall up to and including year y
    success_rate_by_year = [
        float(100.0 * (_first_short_yr > y).mean()) for y in range(n_years)
    ]
    # Mean shortfall duration (only among paths that failed)
    _fail_dur = n_years - _first_short_yr[_path_ever_short]
    shortfall_years_mean = float(_fail_dur.mean()) if _fail_dur.size > 0 else 0.0

    # --- Attach RMD summaries and total-withdrawal totals to withdrawals dict ---
    withdrawals["rmd_current_mean"] = rmd_current_mean.tolist()
    withdrawals["rmd_future_mean"]  = rmd_future_mean.tolist()

    # Total withdrawal per year = max(plan, RMD) on a mean basis
    total_cur = np.maximum(planned_cur, rmd_current_mean)
    total_fut = total_cur * deflator   # deflator already built in STEP 1

    withdrawals["total_withdraw_current_mean"] = total_cur.tolist()
    withdrawals["total_withdraw_future_mean"]  = total_fut.tolist()

    # ── Median-path withdrawal arrays ─────────────────────────────────────
    # All values from the single path whose final portfolio is closest to the
    # cross-sectional median — fully consistent scenario (no per-year mixing).
    if apply_withdrawals and sched is not None and 'realized_nom_paths' in locals():
        _rz_med = _med_path(realized_nom_paths)
        _sf_med = _med_path(shortfall_nom_paths)
        _rz_med_cur = _rz_med / np.maximum(deflator, 1e-12)
        _rmd_med_cur = (_med_path(rmd_total_nom_paths) / np.maximum(deflator, 1e-12)
                        if rmd_total_nom_paths is not None else np.zeros(n_years))
        withdrawals["realized_current_median_path"]  = _rz_med_cur.tolist()
        withdrawals["realized_future_median_path"]   = (_rz_med_cur * deflator).tolist()
        withdrawals["shortfall_current_median_path"] = (_sf_med / np.maximum(deflator, 1e-12)).tolist()
        withdrawals["rmd_current_median_path"]       = _rmd_med_cur.tolist()
        withdrawals["rmd_future_median_path"]        = (_rmd_med_cur * deflator).tolist()
        _total_med = np.maximum(_rz_med_cur, _rmd_med_cur)
        withdrawals["total_withdraw_current_median_path"] = _total_med.tolist()
        withdrawals["total_withdraw_future_median_path"]  = (_total_med * deflator).tolist()
    else:
        # No withdrawals enabled — deterministic zeros on median path too
        withdrawals["realized_current_median_path"]       = [0.0] * n_years
        withdrawals["shortfall_current_median_path"]      = [0.0] * n_years
        withdrawals["rmd_current_median_path"]            = rmd_current_mean.tolist()
        withdrawals["total_withdraw_current_median_path"] = total_cur.tolist()
        withdrawals["total_withdraw_future_median_path"]  = total_fut.tolist()
    withdrawals["rmd_extra_current"]           = rmd_extra_current.tolist()
    withdrawals["rmd_extra_future"]            = (rmd_extra_current * deflator).tolist()

    # Net spendable = realized withdrawal - all ordinary taxes (current USD, mean)
    _total_taxes_cur = (
        taxes_fed_cur_paths.mean(axis=0)
        + taxes_state_cur_paths.mean(axis=0)
        + taxes_niit_cur_paths.mean(axis=0)
        + taxes_excise_cur_paths.mean(axis=0)
    )
    _realized_cur_arr = np.asarray(withdrawals["realized_current_mean"], dtype=float)
    withdrawals["net_spendable_current_mean"] = np.maximum(
        _realized_cur_arr - _total_taxes_cur, 0.0
    ).tolist()


    # Assemble res
    res: Dict[str, Any] = {}
    res["paths"] = int(paths)
    res["spy"] = int(spy)

    res["portfolio"] = {
        "years": list(range(1, n_years + 1)),
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
        "drawdown_by_year_p50":       drawdown_by_year_p50,
        "drawdown_by_year_p90":       drawdown_by_year_p90,
        "taxes_fed_total_current":    float(taxes_fed_cur_paths.sum(axis=1).mean()),
        "taxes_state_total_current":  float(taxes_state_cur_paths.sum(axis=1).mean()),
        "taxes_niit_total_current":   float(taxes_niit_cur_paths.sum(axis=1).mean()),
        "taxes_excise_total_current": float(taxes_excise_cur_paths.sum(axis=1).mean()),
        "tax_shortfall_total_current": 0.0,
        "rmd_total_current":          float(rmd_current_mean.sum()) if rmd_current_mean is not None else 0.0,
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
#        "years": n_years,
#    }

    res["meta"] = {
        "success":      success_rate_pct,
        "paths":        int(paths),
        "years":        n_years,
        # --- Run parameters: what actually drove this simulation ---
        # Always present so results are fully self-describing.
        # UI should display these alongside results so user knows
        # exactly which settings produced this output.
        "run_params": {
            "state":            _eff_state,
            "filing_status":    _eff_filing_status,
            "rmd_table":        _eff_rmd_table,
            "current_age":      _pcfg.get("current_age"),
            "birth_year":       _pcfg.get("birth_year"),
            "assumed_death_age":_pcfg.get("assumed_death_age"),
            "roth_conversion_enabled": (_pcfg.get("roth_conversion_policy") or {}).get("enabled", False),
            "rmd_extra_handling": (_pcfg.get("rmd_policy") or {}).get("extra_handling", "cash_out"),
        },
        # Flags any values that were overridden at runtime vs person.json.
        # Empty dict {} means all values came directly from person.json.
        "runtime_overrides": _overrides_applied,
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
        "fed_year0_cur_paths_mean":   float(taxes_fed_cur_paths[:, 0].mean())   if taxes_fed_cur_paths   is not None else 0.0,
        "state_year0_cur_paths_mean": float(taxes_state_cur_paths[:, 0].mean()) if taxes_state_cur_paths is not None else 0.0,
        "niit_year0_cur_paths_mean":  float(taxes_niit_cur_paths[:, 0].mean())  if taxes_niit_cur_paths  is not None else 0.0,
        "excise_year0_cur_paths_mean":float(taxes_excise_cur_paths[:, 0].mean())if taxes_excise_cur_paths is not None else 0.0,
        # Per-year mean arrays (current USD) for UI display
        "fed_cur_mean_by_year":    taxes_fed_cur_paths.mean(axis=0).tolist(),
        "state_cur_mean_by_year":  taxes_state_cur_paths.mean(axis=0).tolist(),
        "niit_cur_mean_by_year":   taxes_niit_cur_paths.mean(axis=0).tolist(),
        "excise_cur_mean_by_year": taxes_excise_cur_paths.mean(axis=0).tolist(),
        # 30yr totals
        "fed_total_cur_mean":    float(taxes_fed_cur_paths.sum(axis=1).mean()),
        "state_total_cur_mean":  float(taxes_state_cur_paths.sum(axis=1).mean()),
        "niit_total_cur_mean":   float(taxes_niit_cur_paths.sum(axis=1).mean()),
        "excise_total_cur_mean": float(taxes_excise_cur_paths.sum(axis=1).mean()),
        **_taxes_median_path,
    }

    # Roth conversion summary
    _conv_nom = conversion_nom_paths if conversion_nom_paths is not None else np.zeros((paths, n_years), dtype=float)
    _conv_cur = _conv_nom / np.maximum(_deflator_conv, 1e-12)
    _conv_tax = conversion_tax_cost_cur_paths  # already current USD
    res["conversions"] = {
        # Per-year mean (future USD nominal)
        "conversion_nom_mean_by_year":  _conv_nom.mean(axis=0).tolist(),
        # Per-year mean (current USD deflated)
        "conversion_cur_mean_by_year":          _conv_cur.mean(axis=0).tolist(),
        "conversion_cur_median_path_by_year":   _med_path(_conv_cur).tolist(),
        "conversion_tax_cur_median_path_by_year":_med_path(_conv_tax).tolist(),
        # Per-year tax cost (current USD)
        "conversion_tax_cur_mean_by_year": _conv_tax.mean(axis=0).tolist(),
        # Net benefit = conversion - tax (current USD, per year)
        "conversion_net_cur_mean_by_year": (_conv_cur - _conv_tax).mean(axis=0).tolist(),
        # 30yr totals
        "total_converted_nom_mean":  float(_conv_nom.sum(axis=1).mean()),
        "total_converted_cur_mean":  float(_conv_cur.sum(axis=1).mean()),
        "total_tax_cost_cur_mean":   float(_conv_tax.sum(axis=1).mean()),
        "conversion_enabled": bool(_conv_enabled),
        "bracket_fill_mode":  bool(_bracket_fill_mode),
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

    logger.debug("[DEBUG new-sim] summary keys: %s", list(res.get("summary", {}).keys()))
    logger.debug("[DEBUG new-sim] summary YoY scalars: %s %s %s %s",
                 res["summary"].get("nominal_yoy_withdrawals_pct"),
                 res["summary"].get("real_yoy_withdrawals_pct"),
                 res["summary"].get("nominal_yoy_investment_pct"),
                 res["summary"].get("real_yoy_investment_pct"))

    w = res.get("withdrawals", {})
    logger.debug("[DEBUG new-sim] withdrawals keys: %s", list(w.keys()))
    logger.debug("[DEBUG new-sim] withdrawals planned_current sample: %s",
                 w.get("planned_current", [])[:5])
    logger.debug("[DEBUG new-sim] withdrawals realized_current_mean sample: %s",
                 w.get("realized_current_mean", [])[:5])

    return res
