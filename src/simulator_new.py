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


# ── Simulation Mode Transformer ───────────────────────────────────────────────
def _compute_waterfall_deposits(
    surplus_by_year: np.ndarray,         # (n_years,) net surplus in current USD
    waterfall_order: list,               # e.g. ["401k_limit","roth_direct","brokerage"]
    account_types:   dict,               # acct_name → type string
    w2_by_year:      np.ndarray,         # (n_years,) gross W2 in current USD
    current_age:     float,
    n_years:         int,
    filing:          str = "MFJ",
) -> dict:
    """
    Route per-year surplus income through a priority waterfall into deposit buckets.

    Waterfall steps (in order, each fills to its IRS limit before passing remainder):
      401k_match         — employer match only (modelled as 0 — user deposits captured elsewhere)
      401k_limit         — employee pre-tax 401K up to IRS limit ($23,000 2024, $30,500 age 50+)
      roth_direct        — direct Roth IRA (MAGI phase-out enforced; $7K/$8K limit)
      backdoor_roth      — traditional IRA then immediate conversion (bypasses MAGI limit)
      mega_backdoor_roth — after-tax 401K in-plan rollover (residual 401K space up to $69K total)
      brokerage          — remainder to first brokerage account
      spend              — remainder is consumed (no deposit)

    Returns dict: acct_name → np.ndarray of additional deposits by year (current USD).
    Only returns accounts that appear in account_types.
    """
    # IRS limits (2024 figures)
    K401_BASE    = 23_000.0
    K401_CATCHUP =  7_500.0  # age 50+ additional
    K401_TOTAL   = 69_000.0  # total including employer + after-tax
    IRA_BASE     =  7_000.0
    IRA_CATCHUP  =  1_000.0  # age 50+

    # Roth phase-out by filing
    _roth_phase = {
        "MFJ":    (236_000.0, 246_000.0),
        "Single": (150_000.0, 165_000.0),
        "HOH":    (150_000.0, 165_000.0),
        "MFS":    (0.0,       10_000.0),
    }
    ph_floor, ph_ceil = _roth_phase.get(filing, _roth_phase["MFJ"])

    # Identify accounts by type
    trad401k_accts   = [a for a, t in account_types.items() if t in ("traditional_401k", "401k")]
    roth_accts       = [a for a, t in account_types.items() if t == "roth_ira"]
    trad_ira_accts   = [a for a, t in account_types.items() if t == "traditional_ira"]
    brokerage_accts  = [a for a, t in account_types.items()
                        if t in ("taxable", "brokerage") or "BROKERAGE" in a.upper()]
    after_tax_401k   = [a for a, t in account_types.items() if t == "after_tax_401k"]

    # Build output: acct_name → deposit array
    deposits_out: dict = {}

    for yr in range(n_years):
        remaining = float(surplus_by_year[yr])
        if remaining <= 0.0:
            continue

        age_yr   = current_age + yr + 1
        w2_yr    = float(w2_by_year[yr]) if yr < len(w2_by_year) else 0.0
        catch50  = age_yr >= 50

        k401_emp_limit = K401_BASE + (K401_CATCHUP if catch50 else 0.0)
        ira_limit      = IRA_BASE  + (IRA_CATCHUP  if catch50 else 0.0)

        # Roth phase-out factor
        if ph_ceil <= ph_floor:
            roth_f = 0.0 if w2_yr > ph_floor else 1.0
        elif w2_yr >= ph_ceil:
            roth_f = 0.0
        elif w2_yr <= ph_floor:
            roth_f = 1.0
        else:
            roth_f = 1.0 - (w2_yr - ph_floor) / (ph_ceil - ph_floor)

        for step in waterfall_order:
            if remaining <= 0.0:
                break

            if step == "401k_match":
                # employer match — modelled as zero incremental cost to user
                pass

            elif step == "401k_limit":
                if trad401k_accts and w2_yr > 0:
                    fill = min(remaining, k401_emp_limit)
                    acct = trad401k_accts[0]
                    deposits_out.setdefault(acct, np.zeros(n_years, dtype=float))
                    deposits_out[acct][yr] += fill
                    remaining -= fill

            elif step == "roth_direct":
                if roth_accts and w2_yr > 0 and roth_f > 0:
                    fill = min(remaining, ira_limit * roth_f)
                    acct = roth_accts[0]
                    deposits_out.setdefault(acct, np.zeros(n_years, dtype=float))
                    deposits_out[acct][yr] += fill
                    remaining -= fill

            elif step == "backdoor_roth":
                # TRAD IRA → immediate Roth conversion: deposit to TRAD IRA
                # (conversion will be handled by roth_conversion_core separately;
                #  here we model the deposit side only)
                if trad_ira_accts and w2_yr > 0:
                    fill = min(remaining, ira_limit)
                    acct = trad_ira_accts[0]
                    deposits_out.setdefault(acct, np.zeros(n_years, dtype=float))
                    deposits_out[acct][yr] += fill
                    remaining -= fill

            elif step == "mega_backdoor_roth":
                # After-tax 401K → in-plan Roth rollover
                # Space = K401_TOTAL - employee_contributions - employer_match (simplified: residual)
                if (after_tax_401k or roth_accts) and w2_yr > 0:
                    mega_space = max(0.0, K401_TOTAL - k401_emp_limit)
                    fill = min(remaining, mega_space)
                    # Deposit to after_tax_401k if exists, else Roth IRA directly
                    target = after_tax_401k[0] if after_tax_401k else (roth_accts[0] if roth_accts else None)
                    if target:
                        deposits_out.setdefault(target, np.zeros(n_years, dtype=float))
                        deposits_out[target][yr] += fill
                        remaining -= fill

            elif step == "brokerage":
                if brokerage_accts:
                    acct = brokerage_accts[0]
                    deposits_out.setdefault(acct, np.zeros(n_years, dtype=float))
                    deposits_out[acct][yr] += remaining
                    remaining = 0.0

            elif step == "spend":
                # Surplus is consumed — no deposit
                remaining = 0.0

    return deposits_out


def infer_lifecycle_phases(
    w2_by_year:       list,          # gross W2 per year, current USD
    sched_by_year:    list,          # withdrawal target per year, current USD
    current_age:      float,
    n_years:          int,
    rmd_start_age:    int   = 75,
    retirement_age_override: Optional[float] = None,  # optional manual override
) -> list:
    """
    Derive lifecycle phase per simulation year from actual income and spending data.
    Returns a list of n_years phase strings:
      'accumulation'  — W2 > withdrawal target (surplus, no portfolio draw needed)
      'transition'    — W2 > 0 but W2 <= target (partial coverage, may still draw)
      'distribution'  — W2 == 0, portfolio draws required
      'rmd'           — age >= rmd_start_age (RMDs mandatory, may overlap distribution)

    retirement_age_override: if provided, forces distribution phase at this age
    regardless of income — used when the user explicitly sets retirement_age and
    income.json hasn't been updated to match.
    """
    phases = []
    for y in range(n_years):
        age_y = current_age + y + 1
        w2_y  = float(w2_by_year[y]) if y < len(w2_by_year) else 0.0
        tgt_y = float(sched_by_year[y]) if y < len(sched_by_year) else 0.0

        # RMD era overrides everything else (may co-exist with distribution)
        if age_y >= rmd_start_age:
            phases.append("rmd")
            continue

        # Manual retirement age override: force distribution from that age
        if retirement_age_override is not None and age_y >= retirement_age_override:
            phases.append("distribution")
            continue

        if w2_y > tgt_y * 1.05:          # W2 meaningfully exceeds target
            phases.append("accumulation")
        elif w2_y > 50:                   # W2 non-zero but <= target
            phases.append("transition")
        else:                             # W2 zero or negligible
            phases.append("distribution")

    return phases


def compute_mode_weights_for_year(
    phase:           str,
    simulation_mode: str,
    years_to_phase_end: float = 0.0,    # years until next phase transition
) -> tuple:
    """
    Return (investment_weight, retirement_weight) for a single year given its phase.
    In automatic mode, weights are phase-driven rather than retirement-age-countdown.
    """
    mode = str(simulation_mode or "automatic").lower().strip()
    if mode == "investment":  return 1.0, 0.0
    if mode == "retirement":  return 0.0, 1.0
    if mode == "balanced":    return 0.5, 0.5

    # Automatic — phase-driven weights
    if phase == "accumulation":
        return 0.85, 0.15     # strong growth bias, small survival check
    elif phase == "transition":
        return 0.50, 0.50     # balanced — approaching distribution
    elif phase == "distribution":
        return 0.20, 0.80     # income protection dominant
    else:  # rmd
        return 0.10, 0.90     # survival-first in RMD era

    return 0.0, 1.0


def compute_mode_weights(current_age: float, retirement_age: float, simulation_mode: str):
    """Legacy single-weight function — kept for backward compatibility with tests.
    New code uses compute_mode_weights_for_year() with infer_lifecycle_phases()."""
    mode = str(simulation_mode or "automatic").lower().strip()
    if mode == "investment":  return 1.0, 0.0
    if mode == "retirement":  return 0.0, 1.0
    if mode == "balanced":    return 0.5, 0.5
    years_to_retirement = max(0.0, float(retirement_age) - float(current_age))
    if years_to_retirement >= 15:   investment_w = 0.85
    elif years_to_retirement >= 10: investment_w = 0.65
    elif years_to_retirement >= 5:  investment_w = 0.40
    elif years_to_retirement >= 0:  investment_w = 0.20
    else:                           investment_w = 0.0
    return investment_w, 1.0 - investment_w


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
    withdraw_sequence_bad: Optional[list] = None,   # bad-market sequence (previously built but unused)
    econ_scaling_params: Optional[Dict[str, Any]] = None,  # from economicglobal.json — now wired
    tax_cfg: Optional[Dict[str, Any]] = None,
    ordinary_income_cur_paths: Optional[np.ndarray] = None,
    qual_div_cur_paths: Optional[np.ndarray] = None,
    cap_gains_cur_paths: Optional[np.ndarray] = None,
    ytd_income_nom_paths: Optional[np.ndarray] = None,
    w2_income_cur_paths: Optional[np.ndarray] = None,        # W2 wages — for Additional Medicare Tax (0.9%)
    income_sources_cur_paths: Optional[np.ndarray] = None,  # Income.json sources only (pre-RMD/conversion) — for withdrawal offset
    excess_income_policy: Optional[Dict[str, Any]] = None,  # From economic.json — how to route surplus income
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

    _simulation_mode  = str(_pcfg.get("simulation_mode", "automatic")).lower()
    _current_age_now  = float(_pcfg.get("current_age", 60))

    # ── Phase inference — derive lifecycle phase from actual income + spending ──
    # Use w2_income_cur_paths (W2 wages only) for accurate phase classification.
    # Falls back to total ordinary income if W2-only array not provided.
    _w2_mean_by_year = np.zeros(n_years, dtype=float)
    if w2_income_cur_paths is not None:
        _w2_arr = np.asarray(w2_income_cur_paths, dtype=float)
        if _w2_arr.ndim == 2 and _w2_arr.shape[1] >= n_years:
            _w2_mean_by_year = _w2_arr[:, :n_years].mean(axis=0)
        elif _w2_arr.ndim == 1 and len(_w2_arr) >= n_years:
            _w2_mean_by_year = _w2_arr[:n_years]
    elif income_sources_cur_paths is not None:
        _ic_arr = np.asarray(income_sources_cur_paths, dtype=float)
        if _ic_arr.ndim == 2 and _ic_arr.shape[1] >= n_years:
            _w2_mean_by_year = _ic_arr[:, :n_years].mean(axis=0)

    _tgt_for_phase = [float(sched[y]) if sched is not None and y < len(sched) else 0.0
                      for y in range(n_years)]

    _rmd_start_age = int(_pcfg.get("rmd_start_age", 75))
    # Only use retirement_age as a phase override when it's explicitly set above current_age.
    # load_person() defaults retirement_age=current_age when the key is absent — that
    # sentinel value must not trigger the override (it would force distribution from yr1).
    _ret_age_raw = float(_pcfg.get("retirement_age", _current_age_now + n_years + 1))
    _ret_override = (
        _ret_age_raw
        if _ret_age_raw > _current_age_now and _ret_age_raw < _current_age_now + n_years
        else None
    )

    _phase_by_year = infer_lifecycle_phases(
        w2_by_year=_w2_mean_by_year.tolist(),
        sched_by_year=_tgt_for_phase,
        current_age=_current_age_now,
        n_years=n_years,
        rmd_start_age=_rmd_start_age,
        retirement_age_override=_ret_override,
    )

    # Per-year mode weights from inferred phases
    _weights_by_year = [
        compute_mode_weights_for_year(_phase_by_year[y], _simulation_mode)
        for y in range(n_years)
    ]
    # Summary weights: mean across all years (legacy score/label logic)
    _investment_w = float(sum(w[0] for w in _weights_by_year) / max(n_years, 1))
    _retirement_w = float(sum(w[1] for w in _weights_by_year) / max(n_years, 1))

    # ── Pre-compute income surplus and inject into deposits_yearly ─────────────
    # Surplus = net income after approx tax minus withdrawal target.
    # Must happen BEFORE simulate_balances so the deposit compounds correctly
    # through the year-by-year growth simulation. Doing it after (in-loop) means
    # the deposit only affects a single year's balance — it doesn't compound.
    #
    # Note: alloc_accounts is a caller-owned dict — deep-copy deposits_yearly
    # to avoid mutating the caller's data.
    if (income_sources_cur_paths is not None
            and excess_income_policy is not None
            and apply_withdrawals
            and sched is not None):
        _eip_pre = excess_income_policy or {}
        _surplus_tax_rate_pre = float(_eip_pre.get("income_offset_tax_rate", 0.30))
        _surplus_policy_pre   = str(_eip_pre.get("surplus_policy", "reinvest_in_brokerage"))
        if _surplus_policy_pre in ("reinvest_in_brokerage", "waterfall"):
            _sched_pre = np.asarray(sched, dtype=float)
            if _sched_pre.size < n_years:
                _sched_pre = np.concatenate([_sched_pre,
                    np.full(n_years - _sched_pre.size, _sched_pre[-1] if _sched_pre.size else 0.0)])
            _gross_mean_pre = income_sources_cur_paths[:, :n_years].mean(axis=0)
            _net_pre        = _gross_mean_pre * (1.0 - _surplus_tax_rate_pre)
            _surplus_pre    = np.maximum(_net_pre - _sched_pre[:n_years], 0.0)  # current USD

            if np.any(_surplus_pre > 0):
                # Deep-copy deposits_yearly so we don't mutate caller's alloc_accounts
                import copy as _copy
                alloc_accounts = dict(alloc_accounts)
                alloc_accounts["deposits_yearly"] = {
                    k: v.copy() if hasattr(v, "copy") else np.array(v, dtype=float)
                    for k, v in (alloc_accounts.get("deposits_yearly") or {}).items()
                }

                if _surplus_policy_pre == "waterfall":
                    # Priority waterfall — routes surplus through IRS-limited buckets in order
                    _waterfall_order = _eip_pre.get("waterfall_order",
                        ["401k_limit", "roth_direct", "backdoor_roth", "brokerage"])
                    _w2_for_wf = np.zeros(n_years, dtype=float)
                    if w2_income_cur_paths is not None:
                        _w2a = np.asarray(w2_income_cur_paths, dtype=float)
                        _w2_for_wf = _w2a.mean(axis=0)[:n_years] if _w2a.ndim == 2 else _w2a[:n_years]
                    _acct_types = alloc_accounts.get("account_types", {})
                    _wf_deps = _compute_waterfall_deposits(
                        surplus_by_year=_surplus_pre,
                        waterfall_order=_waterfall_order,
                        account_types=_acct_types,
                        w2_by_year=_w2_for_wf,
                        current_age=_current_age_now,
                        n_years=n_years,
                        filing=str((_pcfg or {}).get("filing_status", "MFJ")),
                    )
                    for _wa, _wd_arr in _wf_deps.items():
                        _dep_wf = alloc_accounts["deposits_yearly"].get(
                            _wa, np.zeros(n_years, dtype=float))
                        for _y in range(min(n_years, len(_wd_arr), len(_dep_wf))):
                            if _wd_arr[_y] > 0.0:
                                _dep_wf[_y] += _wd_arr[_y]
                        alloc_accounts["deposits_yearly"][_wa] = _dep_wf
                else:
                    # reinvest_in_brokerage — all surplus → first brokerage account
                    _brok_names = [a for a in (alloc_accounts.get("per_year_portfolios") or {}).keys()
                                   if "BROKERAGE" in a.upper() or "TAXABLE" in a.upper()]
                    if _brok_names:
                        _brok0 = _brok_names[0]
                        _dep = alloc_accounts["deposits_yearly"].get(
                            _brok0, np.zeros(n_years, dtype=float))
                        for _y in range(min(n_years, len(_surplus_pre), len(_dep))):
                            if _surplus_pre[_y] > 0.0:
                                _dep[_y] = _dep[_y] + _surplus_pre[_y]
                        alloc_accounts["deposits_yearly"][_brok0] = _dep

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

    # ── Extract per-year growth multipliers from Monte Carlo output ────────────
    # mult[a][:, y] = 1 + portfolio_return_y for account a in year y.
    # Percentage returns are independent of balance size for proportional
    # allocation models (the % return is the same whether $1M or $2M in the account).
    # These multipliers are applied year-by-year to the post-cashflow running balance
    # in the master cashflow loop below, which correctly propagates each year's
    # RMD / withdrawal / tax debit into the starting balance for the next year.
    _starting_bals = alloc_accounts.get("starting", {}) or {}
    _growth_mult: Dict[str, np.ndarray] = {}
    for _a, _bal_mc in acct_eoy_nom.items():
        _s0 = float(_starting_bals.get(_a, 0.0))
        _m = np.ones_like(_bal_mc)
        if _s0 > 1e-6:
            _raw0 = _bal_mc[:, 0] / _s0
            _m[:, 0] = np.where(np.isfinite(_raw0), _raw0, 1.0)
        else:
            _m[:, 0] = 1.0
        for _y in range(1, n_years):
            _prev = np.maximum(np.where(np.isfinite(_bal_mc[:, _y - 1]), _bal_mc[:, _y - 1], 0.0), 1e-12)
            _raw_y = _bal_mc[:, _y] / _prev
            _m[:, _y] = np.where(np.isfinite(_raw_y), _raw_y, 1.0)
        _growth_mult[_a] = _m
    logger.debug("[sim] growth_mult extracted for %d accounts over %d years", len(_growth_mult), n_years)

    # Investment-only YoY from pure core path (before withdrawals/RMDs/etc.)
    # deflator not yet built here — compute year-1 inflation factor inline
    _infl_arr = np.asarray(infl_yearly, dtype=float).reshape(-1) if (
        infl_yearly is not None and np.asarray(infl_yearly).size > 0
    ) else np.zeros(n_years, dtype=float)
    _deflator_y1 = float(1.0 + _infl_arr[0]) if len(_infl_arr) > 0 else 1.0

    inv_nom_yoy_paths_core = pct_change_paths(total_nom_paths_core,
                                               prior_col=starting_total_nom)

    # Build full deflator inline for real conversion of core paths.
    # MUST pad _infl_arr to n_years (same pattern as main deflator at STEP 1)
    # to avoid falling back to all-ones (= no deflation = nominal == real bug).
    if len(_infl_arr) < n_years:
        _infl_arr_padded = np.concatenate([
            _infl_arr,
            np.full(n_years - len(_infl_arr), _infl_arr[-1] if len(_infl_arr) > 0 else 0.0)
        ])
    elif len(_infl_arr) > n_years:
        _infl_arr_padded = _infl_arr[:n_years]
    else:
        _infl_arr_padded = _infl_arr
    _deflator_core = np.cumprod(1.0 + _infl_arr_padded)
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


    # ── RMD initialization — factors only; amounts computed year-by-year in cashflow loop ──
    # IRS rule: RMD = prior-year-end balance ÷ factor[age].
    # In the year-by-year loop, the "prior-year-end balance" is the actual
    # post-cashflow running balance — not the raw Monte Carlo growth balance.
    rmd_total_nom_paths = np.zeros((paths, n_years), dtype=float)
    rmd_nom_per_acct: Dict[str, np.ndarray] = {}
    rmd_future_mean  = np.zeros(n_years, dtype=float)
    rmd_current_mean = np.zeros(n_years, dtype=float)
    rmd_extra_current = np.zeros(n_years, dtype=float)
    rmd_factors = None

    if (
        rmds_enabled
        and trad_accounts
        and rmd_table_path is not None
        and person_cfg is not None
    ):
        owner_current_age = float(person_cfg.get("current_age", 60.0))
        owner_birth_year  = int(person_cfg.get("birth_year", 0) or 0) or None
        rmd_factors = build_rmd_factors(
            rmd_table_path=rmd_table_path,
            owner_current_age=owner_current_age,
            years=n_years,
            owner_birth_year=owner_birth_year,
        )
        rmd_nom_per_acct = {a: np.zeros((paths, n_years), dtype=float) for a in trad_accounts}
        logger.debug("[sim] RMD factors built; start_age computed from birth_year=%s", owner_birth_year)


    # --- Roth conversions — policy-driven ---
    # Policy and window parsed here. Actual conversion amounts computed year-by-year
    # in the master cashflow loop below, using the correct post-RMD running balance.
    conversion_nom_paths = np.zeros((paths, n_years), dtype=float)
    conversion_tax_cost_cur_paths = np.zeros((paths, n_years), dtype=float)
    conv_out_per_trad: Dict[str, np.ndarray] = {a: np.zeros((paths, n_years), dtype=float) for a in trad_accounts}
    conv_in_per_roth:  Dict[str, np.ndarray] = {a: np.zeros((paths, n_years), dtype=float) for a in roth_accounts}
    conv_tax_per_brok: Dict[str, np.ndarray] = {a: np.zeros((paths, n_years), dtype=float) for a in brokerage_accounts}

    _roth_policy  = parse_roth_conversion_policy(person_cfg or {})
    _conv_enabled = _roth_policy["enabled"]

    _raw_policy = _roth_policy.get("raw", {}) or {}
    if conversion_per_year_nom is None and _conv_enabled:
        _amount_k = float(_raw_policy.get("conversion_amount_k", 0.0))
        conversion_per_year_nom = _amount_k * 1_000.0 if _amount_k > 0.0 else None

    _keepit_str = str(_raw_policy.get("keepit_below_max_marginal_fed_rate", "")).strip().lower()
    _bracket_fill_mode = (
        _conv_enabled
        and tax_cfg is not None
        and ordinary_income_cur_paths is not None
        and ("fill" in _keepit_str or _keepit_str.replace("%", "").replace(".", "").isdigit())
    )

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

    # ── Proactive conversion gate — evaluated ONCE before any year runs ────────
    # Roth conversion is a tax-optimization desire, not a survival necessity.
    # If the plan shows foreseeable liquidity stress, defer conversion entirely
    # until that stress period has passed. The gate uses only known-today data:
    #   - current brokerage balance (from starting)
    #   - confirmed net income (income.json, no growth)
    #   - planned spending (withdrawal_schedule)
    #   - IRS age gate (59.5)
    # No MC returns, no inflation projections — forward information is excluded.
    #
    # Liquidity stress is defined as:
    #   sum(planned_cur[y] - net_income[y] - 0) > brokerage_balance
    # for any year y before age 59.5 (when IRA access opens).
    # i.e. "will the brokerage run dry before 59.5 at current spending?"
    #
    # If yes: defer _window_start_y to the first year where age >= 59.5.
    # The conversion can then start once liquidity pressure is resolved.
    _conv_defer_until_y = _window_start_y  # default: no deferral
    if _conv_enabled and _current_age < 59.5:
        _age_595_y = max(0, int(np.ceil(59.5 - _current_age)))  # first year at/past 59.5
        _brok_start = sum(
            float(alloc_accounts.get("starting", {}).get(b, 0.0))
            for b in brokerage_accounts
        )
        _net_inc_arr = np.zeros(n_years, dtype=float)
        if income_sources_cur_paths is not None and income_sources_cur_paths.shape[1] >= n_years:
            _gross_mean = income_sources_cur_paths[:, :n_years].mean(axis=0)
            _net_inc_arr = _gross_mean * (1.0 - float(
                (excess_income_policy or {}).get("income_offset_tax_rate", 0.30)
            ))
        _planned_arr = np.asarray(sched, dtype=float) if sched is not None else np.zeros(n_years)
        if _planned_arr.size < n_years:
            _planned_arr = np.concatenate([_planned_arr, np.full(n_years - _planned_arr.size, _planned_arr[-1] if _planned_arr.size else 0.0)])

        # Cumulative net draw on brokerage for each year before 59.5
        _brok_running = float(_brok_start)
        _liquidity_stressed = False
        for _gy in range(min(_age_595_y, n_years)):
            _draw_y = max(float(_planned_arr[_gy]) - float(_net_inc_arr[_gy]), 0.0)
            _brok_running -= _draw_y
            if _brok_running < 0:
                _liquidity_stressed = True
                break

        if _liquidity_stressed:
            # Defer conversion window start to first year at/past 59.5
            # (when IRA access opens and liquidity pressure resolves)
            _conv_defer_until_y = max(_window_start_y, _age_595_y)
            _window_start_y = _conv_defer_until_y
            logger.info(
                "[sim] Proactive conversion gate: brokerage projected to deplete before age 59.5 "
                "(starting=$%.0f, net_draw/yr≈$%.0f). Deferring conversions from yr%d → yr%d (age 59.5).",
                _brok_start,
                float(np.maximum(_planned_arr[:_age_595_y] - _net_inc_arr[:_age_595_y], 0).mean()),
                _window_start_y - (_age_595_y - _window_start_y),
                _conv_defer_until_y,
            )

    # ── Pre-simulation withdrawal sustainability check ────────────────────────
    # Before ANY Monte Carlo runs, check if the plan is arithmetically viable.
    # Uses ONLY:
    #   - starting portfolio (all accounts, known today)
    #   - confirmed net income from income.json (no growth assumed)
    #   - planned withdrawal schedule
    # Deliberately excludes: market returns, inflation, shocks — all forward info.
    #
    # Two thresholds:
    #   CRITICAL: total_planned > total_resources        → plan mathematically impossible
    #   WARNING:  total_planned > total_resources × 0.85 → plan requires every dollar + growth
    #
    # These flags flow into the withdrawals dict and are read by the insights engine
    # BEFORE the MC results are available — so the UI can flag immediately.
    _plan_viability: dict = {}
    if sched is not None and starting_total > 0:
        # Build confirmed resources (no growth, no inflation)
        _net_inc_arr2 = np.zeros(n_years, dtype=float)
        _income_offset_rate2 = float((excess_income_policy or {}).get("income_offset_tax_rate", 0.30))
        if income_sources_cur_paths is not None and income_sources_cur_paths.shape[1] >= n_years:
            _gross2 = income_sources_cur_paths[:, :n_years].mean(axis=0)
            _net_inc_arr2 = _gross2 * (1.0 - _income_offset_rate2)

        _planned_arr2 = np.asarray(sched, dtype=float)
        if _planned_arr2.size < n_years:
            _planned_arr2 = np.concatenate([_planned_arr2,
                np.full(n_years - _planned_arr2.size,
                        _planned_arr2[-1] if _planned_arr2.size else 0.0)])

        _total_confirmed_resources = float(starting_total) + float(_net_inc_arr2.sum())
        _total_planned_spend       = float(_planned_arr2[:n_years].sum())
        _net_draw_total            = max(_total_planned_spend - float(_net_inc_arr2.sum()), 0.0)
        _coverage_ratio            = _total_confirmed_resources / max(_total_planned_spend, 1.0)

        # Per-year arithmetic sustainability: simulate balance with ZERO market return
        # (worst-case: money doesn't grow at all, plain subtraction)
        _bal_noreturn = float(starting_total)
        _first_failure_y = None
        _failure_gap_total = 0.0
        for _gy2 in range(n_years):
            _draw_y2 = max(float(_planned_arr2[_gy2]) - float(_net_inc_arr2[_gy2]), 0.0)
            _bal_noreturn -= _draw_y2
            if _bal_noreturn < 0 and _first_failure_y is None:
                _first_failure_y = _gy2
            if _bal_noreturn < 0:
                _failure_gap_total += abs(_bal_noreturn)
                _bal_noreturn = 0.0  # can't go below zero

        _start_age_pv = float((person_cfg or {}).get("current_age", 55))
        _plan_viability = {
            "total_confirmed_resources": round(_total_confirmed_resources, 0),
            "total_planned_spend":        round(_total_planned_spend, 0),
            "total_net_portfolio_draw":   round(_net_draw_total, 0),
            "coverage_ratio":             round(_coverage_ratio, 3),
            "arithmetic_failure_year":    (_first_failure_y + 1) if _first_failure_y is not None else None,
            "arithmetic_failure_age":     (int(_start_age_pv + _first_failure_y + 1)
                                          if _first_failure_y is not None else None),
            "arithmetic_failure_gap_total": round(_failure_gap_total, 0),
            "viability_level": (
                "CRITICAL" if _coverage_ratio < 1.0 else
                "WARNING"  if _coverage_ratio < 1.15 else
                "OK"
            ),
        }
        logger.info(
            "[sim] Plan viability (no-return arithmetic): coverage=%.2fx  "
            "resources=$%.0f  planned=$%.0f  first_failure_yr=%s  level=%s",
            _coverage_ratio, _total_confirmed_resources, _total_planned_spend,
            _first_failure_y + 1 if _first_failure_y is not None else "none",
            _plan_viability["viability_level"],
        )

    # --- Tax arrays — populated year-by-year in the master cashflow loop below ---
    taxes_fed_cur_paths    = np.zeros((paths, n_years), dtype=float)
    taxes_state_cur_paths  = np.zeros((paths, n_years), dtype=float)
    taxes_niit_cur_paths   = np.zeros((paths, n_years), dtype=float)
    taxes_excise_cur_paths = np.zeros((paths, n_years), dtype=float)
    # _taxable_income_snapshot taken after the master loop (ordinary_income_cur_paths
    # accumulates RMDs + conversions year-by-year, so snapshot after loop is correct).
    _taxable_income_snapshot = None


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
        # Plan viability arithmetic (computed before any MC, no predictions)
        "plan_viability":               _plan_viability,
    }

    planned_cur = np.zeros(n_years, dtype=float)

    # =========================================================================
    # PRE-STEP 3: Bad market detection setup
    # Extract scaling params from econ_scaling_params (wired from economicglobal.json)
    # =========================================================================
    _esp = econ_scaling_params or {}
    _shock_scaling_enabled   = bool(_esp.get("shock_scaling_enabled",   True))
    _drawdown_threshold      = float(_esp.get("drawdown_threshold",     0.15))
    _min_scaling_factor      = float(_esp.get("min_scaling_factor",     0.65))
    _scale_curve             = str(_esp.get("scale_curve",             "linear"))
    _scale_poly_alpha        = float(_esp.get("scale_poly_alpha",       1.2))
    _scale_exp_lambda        = float(_esp.get("scale_exp_lambda",       0.8))
    _makeup_enabled          = bool(_esp.get("makeup_enabled",          True))
    _makeup_ratio            = float(_esp.get("makeup_ratio",           0.3))
    _makeup_cap_per_year     = float(_esp.get("makeup_cap_per_year",    0.1))
    _p10_signal_enabled      = bool(_esp.get("p10_signal_enabled",      True))
    _p10_threshold           = float(_esp.get("p10_return_threshold_pct", -15.0)) / 100.0

    # Cross-sectional P10 return per year — computed from pre-cashflow core paths.
    # One scalar per year shared across all paths: if P10 < threshold, that year
    # is classified as a bad-market year for ALL paths (leading indicator).
    import warnings as _bm_w
    with _bm_w.catch_warnings():
        _bm_w.simplefilter("ignore", RuntimeWarning)
        _p10_return_by_year = np.nanpercentile(
            inv_nom_yoy_paths_core_shifted, 10, axis=0
        ) if _p10_signal_enabled else np.zeros(n_years, dtype=float)

    # Running portfolio peak per path — for drawdown detection per path per year.
    # Uses pre-cashflow core paths so peak is not inflated by RMD reinvestment.
    _running_peak_core = np.maximum.accumulate(total_nom_paths_core, axis=1)

    # Per-path bad market flag (paths × n_years) — True = bad market for this path this year
    _bad_market_paths = np.zeros((paths, n_years), dtype=bool)
    for _y in range(n_years):
        _drawdown_y = 1.0 - total_nom_paths_core[:, _y] / np.maximum(
            _running_peak_core[:, _y], 1e-12
        )
        _p10_bad_y = (_p10_return_by_year[_y] < _p10_threshold)
        _bad_market_paths[:, _y] = (_drawdown_y > _drawdown_threshold) | _p10_bad_y

    # Pad/normalise bad-market sequence (same structure as _seq_per_year)
    _fallback_bad_seq = None  # resolved inside the withdrawal block below

    # Cumulative deficit tracker for makeup payments (paths × scalar running total)
    _cumulative_deficit_nom = np.zeros(paths, dtype=float)

    # =========================================================================
    # MASTER CASHFLOW LOOP — Year-by-year simulation
    #
    # For each year y, in correct order:
    #   1. Apply MC portfolio growth to running balance
    #   2. Compute and deduct RMD from TRAD accounts (based on actual balance)
    #   3. Apply Roth conversions (bracket-fill or fixed, if enabled)
    #   4. Compute taxes from actual income (W2 + SS + RMD + conversion + divs/CG)
    #   5. Apply discretionary withdrawal from portfolio accounts
    #   6. Debit taxes from brokerage (net of conversion tax already debited)
    #   7. Reinvest surplus RMD to brokerage (if policy = reinvest_in_brokerage)
    #   8. Store post-cashflow balance as acct_eoy_nom[:, y]
    #
    # The running balance propagates correctly: year Y's cashflows are reflected
    # in the starting balance for year Y+1's growth computation.
    # =========================================================================

    # ── Running balances — start at actual starting values ──────────────────
    _running_bal: Dict[str, np.ndarray] = {
        a: np.full(paths, float(_starting_bals.get(a, 0.0)), dtype=float)
        for a in acct_eoy_nom
    }

    # ── Reinvestment tracker ─────────────────────────────────────────────────
    reinvest_nom_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, n_years), dtype=float) for acct in acct_eoy_nom.keys()
    }

    # ── Withdrawal output arrays ─────────────────────────────────────────────
    withdrawal_out_nom_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, n_years), dtype=float) for acct in acct_eoy_nom.keys()
    }
    _shortfall_any_path    = np.zeros((paths, n_years), dtype=bool)
    realized_nom_paths     = np.zeros((paths, n_years), dtype=float)
    shortfall_nom_paths    = np.zeros((paths, n_years), dtype=float)
    realized_cur           = np.zeros(n_years, dtype=float)
    shortfall_cur          = np.zeros(n_years, dtype=float)
    _cumulative_deficit_nom = np.zeros(paths, dtype=float)
    planned_cur            = np.zeros(n_years, dtype=float)

    withdrawals["realized_current_per_acct_mean"]  = {}
    withdrawals["shortfall_current_per_acct_mean"] = {}

    # ── RMD surplus policy ───────────────────────────────────────────────────
    extra_handling = "cash_out"
    if person_cfg is not None:
        extra_handling = person_cfg.get("rmd_policy", {}).get("extra_handling", "cash_out")

    # ── Withdrawal setup (schedule, income offset, sequence) ─────────────────
    if apply_withdrawals and sched is not None:
        sched_vec = np.asarray(sched, dtype=float).reshape(-1)
        if sched_vec.size < n_years:
            sched_vec = np.concatenate([sched_vec, np.full(n_years - sched_vec.size, sched_vec[-1])])
        elif sched_vec.size > n_years:
            sched_vec = sched_vec[:n_years]

        planned_cur = sched_vec.copy()

        _eip = excess_income_policy or {}
        _income_offset_tax_rate = float(_eip.get("income_offset_tax_rate", 0.30))
        _surplus_policy = str(_eip.get("surplus_policy", "reinvest_in_brokerage")).strip()

        _net_income_offset = np.zeros(n_years, dtype=float)
        _surplus_income_cur = np.zeros(n_years, dtype=float)
        if income_sources_cur_paths is not None and income_sources_cur_paths.shape[1] >= n_years:
            _gross_income_mean = income_sources_cur_paths[:, :n_years].mean(axis=0)
            _net_income_offset = _gross_income_mean * (1.0 - _income_offset_tax_rate)
            _surplus_income_cur = np.maximum(_net_income_offset - planned_cur, 0.0)

        if sched_base is not None:
            _sb = np.asarray(sched_base, dtype=float)
            if _sb.size < n_years:
                _sb = np.concatenate([_sb, np.full(n_years - _sb.size, _sb[-1] if _sb.size else 0.0)])
            elif _sb.size > n_years:
                _sb = _sb[:n_years]
            _sched_base = _sb
        else:
            _sched_base = np.zeros(n_years, dtype=float)

        # Withdrawal sequence
        _fallback_seq = list(acct_eoy_nom.keys())
        if withdraw_sequence is None:
            _seq_per_year = [_fallback_seq] * n_years
        elif withdraw_sequence and isinstance(withdraw_sequence[0], list):
            _seq_per_year = withdraw_sequence
        else:
            _seq_per_year = [withdraw_sequence] * n_years

        owner_age_y0 = float(person_cfg.get("current_age", 60.0)) if person_cfg else 60.0
        brokerage_only_seq = [a for a in _fallback_seq if _is_brokerage(a)]
        if not brokerage_only_seq:
            brokerage_only_seq = [a for a in acct_eoy_nom.keys() if _is_brokerage(a)]
        _seq_per_year = [
            brokerage_only_seq if (owner_age_y0 + y) < 59.5 else
            (_seq_per_year[y] if y < len(_seq_per_year) else _fallback_seq)
            for y in range(n_years)
        ]
        _fallback_bad_seq = list(acct_eoy_nom.keys())
        if withdraw_sequence_bad is None:
            _seq_bad_per_year = _seq_per_year
        elif withdraw_sequence_bad and isinstance(withdraw_sequence_bad[0], list):
            _seq_bad_per_year = withdraw_sequence_bad
        else:
            _seq_bad_per_year = [withdraw_sequence_bad] * n_years
        _seq_bad_per_year = [
            brokerage_only_seq if (owner_age_y0 + y) < 59.5 else
            (_seq_bad_per_year[y] if y < len(_seq_bad_per_year) else _fallback_bad_seq)
            for y in range(n_years)
        ]
    else:
        _sched_base = np.zeros(n_years, dtype=float)
        _net_income_offset = np.zeros(n_years, dtype=float)
        _fallback_seq = list(acct_eoy_nom.keys())
        _seq_per_year = [_fallback_seq] * n_years
        _seq_bad_per_year = [_fallback_seq] * n_years
        _fallback_bad_seq = _fallback_seq

    # ── n_brok for tax/reinvest debit split ─────────────────────────────────
    n_brok = max(len(brokerage_accounts), 1)

    # =========================================================================
    # YEAR-BY-YEAR LOOP
    # =========================================================================
    for y in range(n_years):
        # ── 1. Apply MC growth for year y ──────────────────────────────────
        for a in list(_running_bal.keys()):
            _gm = _growth_mult[a][:, y] if a in _growth_mult else np.ones(paths)
            _running_bal[a] = np.maximum(_running_bal[a] * _gm, 0.0)

        # ── 2. Compute and deduct RMD from TRAD accounts ───────────────────
        _rmd_total_y = np.zeros(paths, dtype=float)
        if rmd_factors is not None and y < len(rmd_factors) and rmd_factors[y] > 0.0:
            _f = float(rmd_factors[y])
            for a in trad_accounts:
                _ba = _running_bal[a]
                # RMD = balance ÷ factor, capped at actual balance (can't RMD more than you have)
                _rmd_a = np.minimum(_ba / _f, _ba)
                rmd_nom_per_acct[a][:, y] = _rmd_a
                _rmd_total_y += _rmd_a
                _running_bal[a] = np.maximum(_ba - _rmd_a, 0.0)
            rmd_total_nom_paths[:, y] = _rmd_total_y
            # Add RMD to ordinary income (taxable income for this year)
            if ordinary_income_cur_paths is not None:
                ordinary_income_cur_paths[:, y] += _rmd_total_y / max(deflator[y], 1e-12)

        # ── 3. Roth conversions for year y ─────────────────────────────────
        # Proactive liquidity gate (above) already deferred _window_start_y past
        # age 59.5 if the plan shows brokerage depletion risk. The only in-loop
        # guard needed is a hard stop when brokerage is actually empty (can't pay
        # the conversion tax bill) — not a policy decision, just arithmetic.
        _brok_bal_y = sum(np.maximum(_running_bal.get(b, np.zeros(paths)), 0.0)
                          for b in brokerage_accounts)
        _brok_mean_y = float(_brok_bal_y.mean()) if hasattr(_brok_bal_y, 'mean') else float(_brok_bal_y)
        _conv_blocked = _brok_mean_y < 5_000.0

        if _conv_enabled and conversions_enabled and trad_accounts and roth_accounts and _window_start_y <= y < _window_end_y and not _conv_blocked:
            # Pass single-year (paths × 1) slices to conversion functions
            _trad_y = {a: _running_bal[a].reshape(-1, 1) for a in trad_accounts}
            _roth_y = {a: _running_bal[a].reshape(-1, 1) for a in roth_accounts}
            _brok_y = {a: _running_bal[a].reshape(-1, 1) for a in brokerage_accounts}
            _inc_y  = (ordinary_income_cur_paths[:, y:y+1].copy()
                       if ordinary_income_cur_paths is not None else np.zeros((paths, 1)))
            _ytd_y  = (ytd_income_nom_paths[:, y:y+1]
                       if ytd_income_nom_paths is not None else np.zeros((paths, 1)))
            _defl_y = _deflator_conv[y:y+1]

            if _bracket_fill_mode:
                try:
                    _cr = apply_bracket_fill_conversions(
                        trad_ira_balances_nom     = _trad_y,
                        roth_ira_balances_nom     = _roth_y,
                        brokerage_balances_nom    = _brok_y,
                        ordinary_income_cur_paths = _inc_y,
                        ytd_income_nom_paths      = _ytd_y,
                        tax_cfg                   = tax_cfg,
                        roth_policy               = _roth_policy,
                        deflator                  = _defl_y,
                        window_start_y            = 0,
                        window_end_y              = 1,
                    )
                    (u_trad, u_roth, u_brok, _conv_p_y, _conv_tax_y,
                     _cout_y, _cin_y, _ctax_y) = _cr
                    for a in trad_accounts:
                        _running_bal[a]       = u_trad[a][:, 0]
                        conv_out_per_trad[a][:, y] = _cout_y.get(a, np.zeros((paths, 1)))[:, 0]
                    for a in roth_accounts:
                        _running_bal[a]       = u_roth[a][:, 0]
                        conv_in_per_roth[a][:, y]  = _cin_y.get(a, np.zeros((paths, 1)))[:, 0]
                    for a in brokerage_accounts:
                        _running_bal[a]       = u_brok[a][:, 0]
                        conv_tax_per_brok[a][:, y] = _ctax_y.get(a, np.zeros((paths, 1)))[:, 0]
                    conversion_nom_paths[:, y] = _conv_p_y[:, 0]
                    conversion_tax_cost_cur_paths[:, y] = _conv_tax_y[:, 0] if hasattr(_conv_tax_y, '__len__') else 0.0
                    if ordinary_income_cur_paths is not None:
                        ordinary_income_cur_paths[:, y] = _inc_y[:, 0]
                except Exception as _conv_err:
                    logger.warning("[sim yr%d] bracket-fill conversion failed: %s", y, _conv_err)

            elif conversion_per_year_nom is not None:
                try:
                    u_trad2, u_roth2, _conv_p2 = apply_simple_conversions(
                        trad_ira_balances_nom    = _trad_y,
                        roth_ira_balances_nom    = _roth_y,
                        conversion_per_year_nom  = float(conversion_per_year_nom),
                        window_start_y           = 0,
                        window_end_y             = 1,
                    )
                    for a in trad_accounts:
                        _running_bal[a] = u_trad2[a][:, 0]
                    for a in roth_accounts:
                        _running_bal[a] = u_roth2[a][:, 0]
                    _conv_nom_y = _conv_p2[:, 0]
                    conversion_nom_paths[:, y] = _conv_nom_y
                    if ordinary_income_cur_paths is not None:
                        ordinary_income_cur_paths[:, y] += _conv_nom_y / max(deflator[y], 1e-12)
                except Exception as _conv_err2:
                    logger.warning("[sim yr%d] fixed conversion failed: %s", y, _conv_err2)

        # ── 4. Compute taxes for year y ─────────────────────────────────────
        if not ignore_taxes and tax_cfg is not None and ordinary_income_cur_paths is not None:
            _income_y = ordinary_income_cur_paths[:, y]
            _qdiv_y   = qual_div_cur_paths[:, y]  if qual_div_cur_paths  is not None else np.zeros(paths)
            _cg_y     = cap_gains_cur_paths[:, y] if cap_gains_cur_paths is not None else np.zeros(paths)
            _ytd2_y   = ytd_income_nom_paths[:, y] if ytd_income_nom_paths is not None else np.zeros(paths)
            _w2_y     = w2_income_cur_paths[:, y]  if w2_income_cur_paths  is not None else None
            (
                _fed_brackets_y,
                taxes_state_cur_paths[:, y],
                taxes_niit_cur_paths[:, y],
                taxes_excise_cur_paths[:, y],
                _medicare_y,
            ) = compute_annual_taxes_paths(
                _income_y, _qdiv_y, _cg_y, tax_cfg, _ytd2_y, _w2_y,
            )
            taxes_fed_cur_paths[:, y] = _fed_brackets_y + _medicare_y

        # ── 5. Discretionary withdrawal ─────────────────────────────────────
        if apply_withdrawals and sched is not None:
            bad_flag_y = _bad_market_paths[:, y]
            frac_bad   = float(bad_flag_y.mean())
            seq = (_seq_bad_per_year[y] if y < len(_seq_bad_per_year) else _fallback_seq) if frac_bad > 0.5 \
                  else (_seq_per_year[y]  if y < len(_seq_per_year)     else _fallback_seq)

            # Compute extra_cur[y] using actual RMD for this year
            _rmd_mean_cur_y = float(_rmd_total_y.mean()) / max(deflator[y], 1e-12)
            _income_adj_y   = max(float(planned_cur[y]) - float(_net_income_offset[y]), 0.0)
            _extra_cur_y    = max(_income_adj_y - _rmd_mean_cur_y, 0.0)
            extra_nom_base  = _extra_cur_y * deflator[y]

            # Bad-market scaling
            _dd_y = 1.0 - total_nom_paths_core[:, y] / np.maximum(_running_peak_core[:, y], 1e-12)
            if _shock_scaling_enabled:
                if _scale_curve == "linear":
                    _scale_y = np.where(bad_flag_y, np.clip(
                        1.0 - (_dd_y - _drawdown_threshold) / max(_drawdown_threshold, 1e-6)
                        * (1.0 - _min_scaling_factor), _min_scaling_factor, 1.0), 1.0)
                elif _scale_curve == "poly":
                    _norm_dd = np.clip((_dd_y - _drawdown_threshold) / max(_drawdown_threshold, 1e-6), 0.0, 1.0)
                    _scale_y = np.where(bad_flag_y, np.clip(
                        1.0 - (1.0 - _min_scaling_factor) * (_norm_dd ** _scale_poly_alpha),
                        _min_scaling_factor, 1.0), 1.0)
                else:
                    _norm_dd = np.clip((_dd_y - _drawdown_threshold) / max(_drawdown_threshold, 1e-6), 0.0, 1.0)
                    _scale_y = np.where(bad_flag_y, np.clip(
                        1.0 - (1.0 - _min_scaling_factor) * (1.0 - np.exp(-_scale_exp_lambda * _norm_dd)),
                        _min_scaling_factor, 1.0), 1.0)
            else:
                _scale_y = np.ones(paths, dtype=float)

            # Makeup payment
            _makeup_y = np.zeros(paths, dtype=float)
            if _makeup_enabled:
                _good_paths = ~bad_flag_y
                _makeup_candidate = np.minimum(
                    _cumulative_deficit_nom * _makeup_ratio,
                    extra_nom_base * _makeup_cap_per_year
                )
                _makeup_y = np.where(_good_paths, _makeup_candidate, 0.0)

            _floor_nom_y = float(_sched_base[y]) * deflator[y]
            amount_nom_paths = np.maximum(_floor_nom_y, _scale_y * extra_nom_base + _makeup_y)

            # ── Survival-probability-weighted depletion cap ────────────────────
            # Sustainable withdrawal = what the portfolio + confirmed income can
            # pay for each remaining year WITHOUT any market return assumptions.
            # Only uses: (a) actual current balance in drawable accounts,
            #            (b) confirmed net income from income.json (no forward projections),
            #            (c) per-path and cross-path survival signals.
            # Deliberately excludes: inflation projections, MC return assumptions,
            # shock scenarios — all of which are forward information.
            _years_remaining = max(n_years - y, 1)

            # Drawable portfolio balance (accounts in current withdrawal sequence)
            _drawable_bal = np.zeros(paths, dtype=float)
            for _seq_a in seq:
                if _seq_a in _running_bal:
                    _drawable_bal += np.maximum(_running_bal[_seq_a], 0.0)

            # Confirmed income PV: net income for remaining years
            _income_pv_y = np.zeros(paths, dtype=float)
            if income_sources_cur_paths is not None and y < income_sources_cur_paths.shape[1]:
                _remaining_income_cur = income_sources_cur_paths[:, y:n_years]
                _net_income_remaining = _remaining_income_cur.mean(axis=0) * (1.0 - _income_offset_tax_rate)
                _income_pv_y = np.full(paths, float(_net_income_remaining.sum()))

            # Total resources = portfolio + confirmed income (no growth assumption)
            _total_resources = _drawable_bal + _income_pv_y

            # (a) Per-path stress flag
            _path_stressed = (
                _shortfall_any_path[:, :y].any(axis=1)
                if y > 0 else np.zeros(paths, dtype=bool)
            )
            # (b) Cross-path survival rate
            _surv_rate_y = (
                1.0 - float(_shortfall_any_path[:, :y].any(axis=1).mean())
                if y > 0 else 1.0
            )
            _global_tighten = max(0.0, 1.0 - _surv_rate_y) * 0.12

            # Sustainable = total_resources × buffer ÷ remaining_years
            # net of income already credited to this year by the withdrawal engine
            _income_offset_nom_y = float(_net_income_offset[y]) * deflator[y] if y < len(_net_income_offset) else 0.0
            _buffer_factor = np.where(
                _path_stressed,
                max(0.50, 0.65 - _global_tighten),
                max(0.60, 0.85 - _global_tighten),
            )
            _sustainable_nom = np.maximum(
                (_total_resources * _buffer_factor) / _years_remaining - _income_offset_nom_y,
                0.0
            )

            # ── CRITICAL: only clamp when portfolio is genuinely stressed ──────
            # Gate: per-path stressed flag AND systemic stress AND portfolio not over-funded.
            # Additional bypass: if drawable balance > 5x planned withdrawal for this year,
            # the portfolio is clearly healthy enough — skip cap entirely for this path.
            _amount_nom_y = amount_nom_paths[0] if hasattr(amount_nom_paths, '__len__') else float(amount_nom_paths)
            _portfolio_abundant = _drawable_bal > (_amount_nom_y * deflator[y] * 5.0)
            _systemic_stress = (1.0 - _surv_rate_y) > 0.10
            _cap_active = _path_stressed & _systemic_stress & (_sustainable_nom < amount_nom_paths) & ~_portfolio_abundant
            amount_nom_paths = np.where(
                _cap_active,
                np.maximum(_sustainable_nom, _floor_nom_y),
                amount_nom_paths
            )

            # Set acct_eoy_nom[:, y] from running balance so withdrawal function can draw from it
            for a in _running_bal:
                acct_eoy_nom[a][:, y] = np.maximum(_running_bal[a], 0.0)

            (
                realized_total_nom,
                shortfall_total_nom,
                realized_per_acct_nom,
                shortfall_per_acct_nom,
                sold_per_acct_nom,
            ) = apply_withdrawals_nominal_per_account(acct_eoy_nom, y, amount_nom_paths, seq)

            for acct, sold_arr in sold_per_acct_nom.items():
                if acct in acct_eoy_nom and np.any(sold_arr > 0):
                    acct_eoy_nom[acct][:, y] = np.maximum(acct_eoy_nom[acct][:, y] - sold_arr, 0.0)
                if acct in withdrawal_out_nom_per_acct:
                    withdrawal_out_nom_per_acct[acct][:, y] = sold_per_acct_nom.get(acct, np.zeros(paths))

            # Read post-withdrawal balances back into running_bal
            for a in _running_bal:
                _running_bal[a] = acct_eoy_nom[a][:, y]

            scale = max(deflator[y], 1e-12)
            realized_cur[y]   = (realized_total_nom / scale).mean()
            shortfall_cur[y]  = (shortfall_total_nom / scale).mean()
            _shortfall_any_path[:, y] = shortfall_total_nom > 1e-6
            realized_nom_paths[:, y]  = realized_total_nom
            shortfall_nom_paths[:, y] = shortfall_total_nom

            _deficit_y = np.maximum(amount_nom_paths - realized_total_nom, 0.0)
            _cumulative_deficit_nom = np.maximum(_cumulative_deficit_nom + _deficit_y - _makeup_y, 0.0)

            for acct in acct_eoy_nom.keys():
                rn = realized_per_acct_nom.get(acct)
                sn = shortfall_per_acct_nom.get(acct)
                if rn is not None:
                    withdrawals["realized_current_per_acct_mean"].setdefault(acct, [0.0] * n_years)
                    withdrawals["realized_current_per_acct_mean"][acct][y] = (rn / scale).mean()
                if sn is not None:
                    withdrawals["shortfall_current_per_acct_mean"].setdefault(acct, [0.0] * n_years)
                    withdrawals["shortfall_current_per_acct_mean"][acct][y] = (sn / scale).mean()
        else:
            # No withdrawal mode — running_bal → acct_eoy_nom for this year
            for a in _running_bal:
                acct_eoy_nom[a][:, y] = np.maximum(_running_bal[a], 0.0)
            realized_total_nom = np.zeros(paths, dtype=float)
            amount_nom_paths   = np.zeros(paths, dtype=float)
            _makeup_y          = np.zeros(paths, dtype=float)
            scale              = max(deflator[y], 1e-12)

        # ── 6. Debit taxes from brokerage ──────────────────────────────────
        if brokerage_accounts and tax_cfg is not None:
            _scl = max(deflator[y], 1e-12)
            # Conversion taxes already debited inside apply_bracket_fill_conversions — subtract
            _conv_already = np.zeros(paths, dtype=float)
            for b in brokerage_accounts:
                _conv_already += conv_tax_per_brok[b][:, y]
            _total_tax_nom = np.maximum(
                (taxes_fed_cur_paths[:, y] + taxes_state_cur_paths[:, y]
                 + taxes_niit_cur_paths[:, y] + taxes_excise_cur_paths[:, y])
                * _scl - _conv_already,
                0.0
            )
            _brok_total = np.zeros(paths, dtype=float)
            for b in brokerage_accounts:
                _brok_total += np.maximum(_running_bal[b], 0.0)
            for b in brokerage_accounts:
                _frac = np.where(
                    _brok_total > 1e-12,
                    np.maximum(_running_bal[b], 0.0) / np.maximum(_brok_total, 1e-12),
                    1.0 / n_brok
                )
                _share = _total_tax_nom * _frac
                _running_bal[b] = np.maximum(_running_bal[b] - _share, 0.0)
                acct_eoy_nom[b][:, y] = _running_bal[b]

        # ── 7. Reinvest surplus RMD to brokerage ───────────────────────────
        if extra_handling == "reinvest_in_brokerage" and brokerage_accounts and np.any(_rmd_total_y > 0):
            _plan_nom_y   = float(planned_cur[y]) * deflator[y] if y < len(planned_cur) else 0.0
            _surplus_rmd  = np.maximum(_rmd_total_y - _plan_nom_y, 0.0)
            if np.any(_surplus_rmd > 0):
                _brok_tot2 = np.zeros(paths, dtype=float)
                for b in brokerage_accounts:
                    _brok_tot2 += np.maximum(_running_bal[b], 0.0)
                for b in brokerage_accounts:
                    _frac2 = np.where(
                        _brok_tot2 > 1e-12,
                        np.maximum(_running_bal[b], 0.0) / np.maximum(_brok_tot2, 1e-12),
                        1.0 / n_brok
                    )
                    _share2 = _surplus_rmd * _frac2
                    _running_bal[b]     = _running_bal[b] + _share2
                    acct_eoy_nom[b][:, y] = _running_bal[b]
                    reinvest_nom_per_acct[b][:, y] = _share2

        # ── Final: store post-cashflow balance for year y ───────────────────
        for a in _running_bal:
            acct_eoy_nom[a][:, y] = np.maximum(_running_bal[a], 0.0)

    # ── Post-loop: write tax arrays into withdrawals dict ─────────────────────
    # The withdrawals dict was initialized BEFORE the year loop with all-zero
    # tax arrays. Now that the loop has populated taxes_*_cur_paths, overwrite.
    withdrawals["taxes_fed_current_mean"]    = taxes_fed_cur_paths.mean(axis=0).tolist()
    withdrawals["taxes_state_current_mean"]  = taxes_state_cur_paths.mean(axis=0).tolist()
    withdrawals["taxes_niit_current_mean"]   = taxes_niit_cur_paths.mean(axis=0).tolist()
    withdrawals["taxes_excise_current_mean"] = taxes_excise_cur_paths.mean(axis=0).tolist()

    # ── Post-loop: compute RMD summary stats ─────────────────────────────────
    rmd_future_mean  = rmd_total_nom_paths.mean(axis=0)
    rmd_current_mean = rmd_future_mean / np.maximum(deflator, 1e-12)

    # Snapshot ordinary_income_cur_paths now that all years are finalized
    _taxable_income_snapshot = (
        ordinary_income_cur_paths.copy() if ordinary_income_cur_paths is not None else None
    )

    # Realized totals (RMD covering plan + discretionary)
    rmd_covering_plan  = np.minimum(planned_cur, rmd_current_mean)
    total_realized_cur = rmd_covering_plan + realized_cur

    # rmd_extra_current: mean surplus RMD beyond plan
    rmd_extra_current = np.maximum(rmd_current_mean - planned_cur, 0.0)
    if extra_handling != "reinvest_in_brokerage":
        if extra_handling == "cash_out" and apply_withdrawals and sched is not None:
            total_realized_cur = total_realized_cur + rmd_extra_current
        rmd_extra_current = np.zeros(n_years, dtype=float)

    if apply_withdrawals and sched is not None:
        _base_cur = _sched_base if '_sched_base' in dir() else np.zeros(n_years, dtype=float)
        _bad_market_frac_by_year = _bad_market_paths.mean(axis=0).tolist()
        withdrawals["planned_current"]              = planned_cur.tolist()
        withdrawals["realized_current_mean"]        = total_realized_cur.tolist()
        withdrawals["shortfall_current_mean"]       = shortfall_cur.tolist()
        withdrawals["realized_future_mean"]         = (total_realized_cur * deflator).tolist()
        withdrawals["base_current"]                 = _base_cur.tolist()
        withdrawals["base_future_mean"]             = (_base_cur * deflator).tolist()
        withdrawals["bad_market_frac_by_year"]      = _bad_market_frac_by_year
        withdrawals["bad_market_drawdown_threshold"]= _drawdown_threshold
        withdrawals["shock_scaling_enabled"]        = _shock_scaling_enabled
        withdrawals["min_scaling_factor"]           = _min_scaling_factor
        withdrawals["upside_scaling_enabled"]       = bool(_esp.get("upside_scaling_enabled", False))

        # Safe withdrawal rate (P10 = 90% survival, P25 = 75% survival, P50 = median)
        # ALSO computes a conservative floor based only on current balances + confirmed income
        # with NO market return assumptions — pure "what do I have today" calculation.
        try:
            if starting_total > 0 and total_real_paths is not None:
                _start_real = float(starting_total)
                _mean_planned = float(planned_cur.mean()) if len(planned_cur) > 0 else 0.0
                _lo_hi = max(_mean_planned * 3.0, _start_real * 0.15)

                def _pN_survives(wd_cur: float, pctile: int) -> bool:
                    """Binary-search helper: can the Nth-percentile path sustain wd_cur?"""
                    _pN_core_real = np.percentile(
                        total_nom_paths_core / np.maximum(deflator, 1e-12), pctile, axis=0
                    )
                    bal = _start_real
                    for _y in range(n_years):
                        gf = (float(_pN_core_real[_y]) /
                              max(float(_pN_core_real[_y - 1]) if _y > 0 else _start_real, 1.0))
                        bal = bal * gf - wd_cur
                        if bal < 0:
                            return False
                    return True

                for _pctile, _key in [(10, "safe_withdrawal_rate_p10_pct"),
                                       (25, "safe_withdrawal_rate_p25_pct"),
                                       (50, "safe_withdrawal_rate_p50_pct")]:
                    _lo, _hi = 0.0, _lo_hi
                    for _ in range(30):
                        _mid = (_lo + _hi) / 2.0
                        if _pN_survives(_mid, _pctile):
                            _lo = _mid
                        else:
                            _hi = _mid
                    withdrawals[_key] = round((_lo / _start_real) * 100.0, 2) if _start_real > 0 else 0.0

                # ── Conservative floor: balance + income only, zero market assumptions ──
                # This is what the person CAN spend with certainty today, using:
                #   - actual starting portfolio (no growth projection)
                #   - confirmed net income from income.json (W2, rental, SS already in payment)
                #   - no inflation, no MC returns, no shocks
                # Formula: (starting_balance × 0.85 + total_net_income_pv) / n_years
                # The 0.85 factor preserves a 15% buffer for unexpected withdrawals.
                _total_net_income_cur = float(
                    np.sum(_net_income_offset) if hasattr(_net_income_offset, '__len__') else 0.0
                )
                _conservative_floor_cur = (
                    (_start_real * 0.85 + _total_net_income_cur) / max(n_years, 1)
                )
                withdrawals["conservative_floor_current"] = round(_conservative_floor_cur, 0)
                withdrawals["conservative_floor_pct"] = round(
                    _conservative_floor_cur / _start_real * 100.0, 2
                ) if _start_real > 0 else 0.0

                # Per-year survival rate: fraction of paths that met their target each year
                _surv_by_year = (1.0 - _shortfall_any_path.mean(axis=0)).tolist()
                withdrawals["survival_rate_by_year"] = [round(v * 100, 1) for v in _surv_by_year]
            else:
                withdrawals["safe_withdrawal_rate_p10_pct"] = 0.0
                withdrawals["safe_withdrawal_rate_p25_pct"] = 0.0
                withdrawals["safe_withdrawal_rate_p50_pct"] = 0.0
                withdrawals["survival_rate_by_year"] = [100.0] * n_years
        except Exception:
            withdrawals["safe_withdrawal_rate_p10_pct"] = 0.0
            withdrawals["safe_withdrawal_rate_p25_pct"] = 0.0
            withdrawals["safe_withdrawal_rate_p50_pct"] = 0.0
            withdrawals["survival_rate_by_year"] = [100.0] * n_years

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
    # This is the correct denominator for effective tax rate.
    # NOTE: ordinary_income_cur_paths has RMDs and conversions added to it inside the
    # simulation loop (lines ~368-441), so by this point it contains the full picture.
    # Use the tax-computation snapshot as the authoritative income basis.
    # This is what the tax engine actually taxed — consistent with the tax output.
    _ord_income_med = None
    if _taxable_income_snapshot is not None:
        _ord_income_med = _med_path(_taxable_income_snapshot).tolist()
    elif ordinary_income_cur_paths is not None:
        _ord_income_med = _med_path(ordinary_income_cur_paths).tolist()

    # Compute effective tax rate in the backend so both App.tsx and API consumers
    # get the same number without duplicating logic on the client side.
    # Denominator: taxable income = ordinary income MINUS standard deduction
    # (same base the tax engine uses — gross income overstates the denominator).
    # Standard deduction is inflation-adjusted per the tax config; we use a
    # conservative fixed value that matches roth_optimizer.py constants.
    _filing = str((_pcfg or {}).get("filing_status", "MFJ")).upper()
    _std_ded = 31_500.0 if _filing == "MFJ" else 15_750.0  # matches roth_optimizer.py

    _taxes_fed_med   = _med_path(taxes_fed_cur_paths)
    _taxes_state_med = _med_path(taxes_state_cur_paths)
    _taxes_niit_med  = _med_path(taxes_niit_cur_paths)
    _taxes_excise_med= _med_path(taxes_excise_cur_paths)
    _total_taxes_med = _taxes_fed_med + _taxes_state_med + _taxes_niit_med + _taxes_excise_med

    _eff_rate_med = [0.0] * n_years
    for _y in range(n_years):
        _gross = float(_ord_income_med[_y]) if _ord_income_med and _ord_income_med[_y] > 0 else 0.0
        # Subtract standard deduction to get taxable income (same base as tax engine)
        _taxable = max(0.0, _gross - _std_ded)
        if _taxable <= 0:
            # Fallback: planned withdrawal + conversion minus std deduction
            _wd = float(planned_cur[_y]) if planned_cur is not None and _y < len(planned_cur) else 0.0
            _cv = 0.0
            if conversion_nom_paths is not None:
                _cv = float(_med_path(conversion_nom_paths)[_y]) if hasattr(conversion_nom_paths, 'shape') else 0.0
            _taxable = max(0.0, _wd + _cv - _std_ded)
        _tax = float(_total_taxes_med[_y])
        if _taxable > 0 and _tax >= 0:
            _rate = _tax / _taxable
            _eff_rate_med[_y] = round(min(_rate, 1.0), 4)  # cap at 100%, 4dp

    _taxes_median_path = {
        "taxes_fed_current_median_path":       _taxes_fed_med.tolist(),
        "taxes_state_current_median_path":     _taxes_state_med.tolist(),
        "taxes_niit_current_median_path":      _taxes_niit_med.tolist(),
        "taxes_excise_current_median_path":    _taxes_excise_med.tolist(),
        "total_ordinary_income_median_path":   _ord_income_med or [0.0] * n_years,
        # Pre-computed effective rate — use this in App.tsx and API consumers
        # instead of recomputing client-side. Avoids denominator bugs.
        "effective_tax_rate_median_path":      _eff_rate_med,
    }
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

    # Median YoY — the typical (50th percentile) path each year
    import warnings as _w2m
    with _w2m.catch_warnings():
        _w2m.simplefilter("ignore", RuntimeWarning)
        nom_withdraw_yoy_med_pct  = (np.nanmedian(inv_nom_yoy,  axis=0) * 100.0).tolist()
        real_withdraw_yoy_med_pct = (np.nanmedian(inv_real_yoy, axis=0) * 100.0).tolist()
        inv_nom_yoy_med_pct_core  = (np.nanmedian(inv_nom_yoy_paths_core_shifted, axis=0) * 100.0).tolist()
        inv_real_yoy_med_pct_core = (np.nanmedian(inv_real_yoy_paths_core_shifted, axis=0) * 100.0).tolist()

    # P10/P90 of annual returns — shows the realistic downside/upside range
    # P10: 1-in-10 bad year return — will show negative years during shocks/bad markets
    # P90: 1-in-10 good year return — shows realistic upside per year
    import warnings as _w2
    with _w2.catch_warnings():
        _w2.simplefilter("ignore", RuntimeWarning)
        nom_withdraw_yoy_p10_pct  = (np.nanpercentile(inv_nom_yoy,  10, axis=0) * 100.0).tolist()
        nom_withdraw_yoy_p90_pct  = (np.nanpercentile(inv_nom_yoy,  90, axis=0) * 100.0).tolist()
        inv_nom_yoy_p10_pct_core  = (np.nanpercentile(inv_nom_yoy_paths_core_shifted, 10, axis=0) * 100.0).tolist()
        inv_nom_yoy_p90_pct_core  = (np.nanpercentile(inv_nom_yoy_paths_core_shifted, 90, axis=0) * 100.0).tolist()
        inv_real_yoy_p10_pct_core = (np.nanpercentile(inv_real_yoy_paths_core_shifted, 10, axis=0) * 100.0).tolist()

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
    drawdown_by_year_p50 = [float(np.percentile(dd_each[:, y], 50)) for y in range(n_years)]
    drawdown_by_year_p90 = [float(np.percentile(dd_each[:, y], 90)) for y in range(n_years)]

    # Success rate: mode-dependent shortfall threshold.
    # retirement_w high  → full plan is the bar (strict)
    # investment_w high  → floor (sched_base) is the bar (lenient — plan overruns ok)
    # balanced/automatic → blend: use full plan when retirement_w >= 0.5, floor otherwise
    #
    # The GBM math is identical across modes. Only the success measurement changes.
    if apply_withdrawals and sched is not None and '_sched_base' in locals() and _investment_w >= 0.5:
        # Investment-first / Balanced-investment: shortfall measured against floor, not full plan
        # Rebuild _shortfall_any_path against _sched_base instead of planned amount
        _floor_nom_paths = np.outer(np.ones(paths), _sched_base * deflator)  # (paths x years)
        if 'realized_nom_paths' in locals():
            _shortfall_any_path_mode = realized_nom_paths < (_floor_nom_paths - 1.0)
        else:
            _shortfall_any_path_mode = _shortfall_any_path
    else:
        # Retirement-first / Automatic-retirement: shortfall vs full plan (strict)
        _shortfall_any_path_mode = _shortfall_any_path

    _path_ever_short = _shortfall_any_path_mode.any(axis=1)
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

    # Floor-only success rate (always computed regardless of mode — useful for UI comparison)
    # Total money delivered = non-RMD withdrawal + RMD (both paths x years, nominal)
    # _sched_base is in current USD → multiply by deflator to get nominal floor
    if apply_withdrawals and sched is not None and '_sched_base' in locals() and 'realized_nom_paths' in locals():
        _total_delivered_nom = realized_nom_paths.copy()
        if rmd_total_nom_paths is not None:
            _total_delivered_nom = _total_delivered_nom + rmd_total_nom_paths
        _floor_nom = np.outer(np.ones(paths), _sched_base * deflator)
        _floor_short = (_total_delivered_nom < (_floor_nom - 1.0)).any(axis=1)
        floor_success_rate_pct = float(100.0 * (~_floor_short).mean())
    else:
        floor_success_rate_pct = success_rate_pct

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

    # ── Pure Asset Return ─────────────────────────────────────────────────────
    # CAGR from pre-cashflow core paths (no RMDs, withdrawals, or reinvestment).
    # pure_return <= cagr_nominal because RMD reinvestment inflates final balance.
    _core_start_nom  = np.maximum(total_nom_paths_core[:, 0], 1e-12)
    _core_end_nom    = np.maximum(total_nom_paths_core[:, -1], 1e-12)
    _core_start_real = _core_start_nom / float(np.maximum(_deflator_core[0], 1e-12))
    _core_end_real   = _core_end_nom   / float(np.maximum(_deflator_core[-1], 1e-12))
    _pure_nom_paths  = ((_core_end_nom  / _core_start_nom)  ** (1.0 / n_years) - 1.0) * 100.0
    _pure_real_paths = ((_core_end_real / _core_start_real) ** (1.0 / n_years) - 1.0) * 100.0
    pure_asset_return_nom_pct  = float(_pure_nom_paths.mean())
    pure_asset_return_real_pct = float(_pure_real_paths.mean())

    res["summary"] = {
        "success_rate":               success_rate_pct,
        "success_rate_label":         "Floor survival rate" if _investment_w >= 0.5 else "Full-plan survival rate",
        "floor_success_rate":         floor_success_rate_pct,
        "success_rate_by_year":       success_rate_by_year,
        "shortfall_years_mean":       shortfall_years_mean,
        "drawdown_p50":               drawdown_p50,
        "drawdown_p90":               drawdown_p90,
        "drawdown_by_year_p50":       drawdown_by_year_p50,
        "drawdown_by_year_p90":       drawdown_by_year_p90,
        "simulation_mode":            _simulation_mode,
        "investment_weight":          _investment_w,
        "retirement_weight":          _retirement_w,
        "primary_metric":             "cagr" if _investment_w >= 0.5 else "survival",
        "composite_score":            round(
            _investment_w  * min(100.0, max(0.0, cagr_real_mean / 6.0 * 100.0)) +
            _retirement_w  * success_rate_pct, 1),
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
        # Pure asset return: CAGR from pre-cashflow core paths (no RMDs/withdrawals/reinvest)
        "pure_asset_return_nom_pct":  pure_asset_return_nom_pct,
        "pure_asset_return_real_pct": pure_asset_return_real_pct,
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
            "simulation_mode":    _simulation_mode,
            "investment_weight":  _investment_w,
            "retirement_weight":  _retirement_w,
            # Phase inference output — per-year lifecycle phase derived from income + spending
            "phase_by_year":      _phase_by_year,
            "weights_by_year":    [[round(w[0],3), round(w[1],3)] for w in _weights_by_year],
            "retirement_age_override_used": _ret_override is not None,
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
        "nom_withdraw_yoy_med_pct":  nom_withdraw_yoy_med_pct,
        "real_withdraw_yoy_med_pct": real_withdraw_yoy_med_pct,

        # P10/P90 of annual portfolio returns — realistic downside/upside per year
        "nom_withdraw_yoy_p10_pct":  nom_withdraw_yoy_p10_pct,
        "nom_withdraw_yoy_p90_pct":  nom_withdraw_yoy_p90_pct,

        # Investment-only YoY from core path (mean + median)
        "inv_nom_yoy_mean_pct": inv_nom_yoy_mean_pct_core,
        "inv_real_yoy_mean_pct": inv_real_yoy_mean_pct_core,
        "inv_nom_yoy_med_pct":  inv_nom_yoy_med_pct_core,
        "inv_real_yoy_med_pct": inv_real_yoy_med_pct_core,

        # Investment-only P10/P90 — pure asset return downside/upside
        "inv_nom_yoy_p10_pct":  inv_nom_yoy_p10_pct_core,
        "inv_nom_yoy_p90_pct":  inv_nom_yoy_p90_pct_core,
        "inv_real_yoy_p10_pct": inv_real_yoy_p10_pct_core,
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
        "conversion_deferred_to_year": int(_conv_defer_until_y) if _conv_defer_until_y > 0 else None,
        "conversion_deferred_reason": (
            "Liquidity gate: brokerage projected to deplete before age 59.5. "
            "Conversions deferred until IRA access opens to preserve spending capacity."
            if _conv_defer_until_y > _window_start_y - (_conv_defer_until_y - _window_start_y)
            else None
        ),
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
