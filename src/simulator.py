# filename: simulator.py

from typing import Dict, List, Optional, Any, Tuple
import os
import logging
import numpy as np
from withdrawals_core import apply_withdrawals_nominal_per_account
from taxes_core import compute_annual_taxes_paths



from engines import (
    build_shock_matrix_from_json,
    GUARDRAILS,
    compute_dividend_taxes_components,
    compute_gains_taxes_components,
    TaxLots,
)
from engines_assets import draw_asset_log_returns, shock_yearly_log_adjustments
from assets_loader import load_assets_model
from rmd import load_rmd_table, uniform_factor

LOG_DEBUG = os.environ.get("SIM_DEBUG", "0") == "1"
logging.basicConfig(
    level=logging.DEBUG if LOG_DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

YEARS = 30
INFL_BASELINE_ANNUAL = 0.035


def _to_year_vector(x, cast=float) -> np.ndarray:
    a = np.asarray(x)
    if a.ndim == 0:
        return np.full(YEARS, cast(a))
    if a.ndim > 1:
        a = a.reshape(-1)
    if a.size == YEARS:
        return a.astype(cast)
    if a.size == 0:
        return np.zeros(YEARS, dtype=type(cast(0.0)))
    out = np.empty(YEARS, dtype=type(cast(0.0)))
    k = min(a.size, YEARS)
    out[:k] = a[:k].astype(cast)
    out[k:] = cast(a[k - 1])
    return out


def _build_deflator(infl_yearly: Optional[np.ndarray]) -> np.ndarray:
    years_vec = np.arange(1, YEARS + 1, dtype=int)
    if infl_yearly is None or np.asarray(infl_yearly).size == 0:
        return (1.0 + INFL_BASELINE_ANNUAL) ** years_vec
    arr = np.asarray(infl_yearly, dtype=float).reshape(-1)
    if arr.size < YEARS:
        arr = np.concatenate(
            [
                arr,
                np.full(
                    YEARS - arr.size,
                    arr[-1] if arr.size > 0 else INFL_BASELINE_ANNUAL,
                ),
            ]
        )
    elif arr.size > YEARS:
        arr = arr[:YEARS]
    return np.cumprod(1.0 + arr)


def _default_withdraw_sequence(acct_names: List[str]) -> List[str]:
    order = []

    def is_brokerage(n: str) -> bool:
        nu = n.upper()
        return ("BROKERAGE" in nu) or ("TAXABLE" in nu)

    def is_trad(n: str) -> bool:
        nu = n.upper()
        return (("TRAD" in nu) or ("TRADITIONAL" in nu)) and ("ROTH" not in nu)

    def is_roth(n: str) -> bool:
        nu = n.upper()
        return "ROTH" in nu

    brokerages = [n for n in acct_names if is_brokerage(n)]
    trads = [n for n in acct_names if is_trad(n)]
    roths = [n for n in acct_names if is_roth(n)]
    others = [n for n in acct_names if n not in brokerages + trads + roths]

    order.extend(brokerages)
    order.extend(trads)
    order.extend(roths)
    order.extend(others)
    seen = set()
    out = []
    for n in order:
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _policy_sequences_from_econ(
    acct_names: List[str], economic_policy: Optional[Dict[str, Any]]
) -> Tuple[List[str], List[str], float]:
    order_good = _default_withdraw_sequence(acct_names)
    order_bad = list(order_good)
    thresh = 0.20
    if isinstance(economic_policy, dict):
        defaults = economic_policy.get("defaults", {}) or {}
        try:
            t = float(defaults.get("bad_market_drawdown_threshold", thresh))
            if 0.0 <= t <= 1.0:
                thresh = t
        except Exception:
            pass
        og = economic_policy.get("order_good_market", []) or []
        ob = economic_policy.get("order_bad_market", []) or []

        def _clean(xs: List[str]) -> List[str]:
            seen = set()
            out = []
            for n in xs:
                n2 = str(n).strip()
                if not n2 or n2 not in acct_names:
                    continue
                if n2 not in seen:
                    out.append(n2)
                    seen.add(n2)
            for a in acct_names:
                if a not in seen:
                    out.append(a)
                    seen.add(a)
            return out

        if og:
            order_good = _clean(og if isinstance(og, list) else [])
        if ob:
            order_bad = _clean(ob if isinstance(ob, list) else [])
    return order_good, order_bad, float(thresh)


def _apply_withdrawals_nominal_per_account(
    acct_eoy_nom: Dict[str, np.ndarray],
    y: int,
    amount_nom_paths: np.ndarray,
    sequence: List[str],
) -> Tuple[
    np.ndarray,
    np.ndarray,
    Dict[str, np.ndarray],
    Dict[str, np.ndarray],
    Dict[str, np.ndarray],
]:
    paths = next(iter(acct_eoy_nom.values())).shape[0]
    remaining = np.where(np.isfinite(amount_nom_paths), amount_nom_paths, 0.0).copy()
    realized_total = np.zeros(paths, dtype=float)
    realized_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros(paths, dtype=float) for acct in acct_eoy_nom.keys()
    }
    shortfall_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros(paths, dtype=float) for acct in acct_eoy_nom.keys()
    }
    sold_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros(paths, dtype=float) for acct in acct_eoy_nom.keys()
    }
    for acct in sequence:
        if acct not in acct_eoy_nom:
            continue
        bal = np.where(
            np.isfinite(acct_eoy_nom[acct][:, y]), acct_eoy_nom[acct][:, y], 0.0
        )
        take = np.minimum(bal, remaining)
        acct_eoy_nom[acct][:, y] = bal - take
        realized_per_acct[acct] += take
        sold_per_acct[acct] += take
        realized_total += take
        remaining -= take
        if np.all(remaining <= 1e-12):
            break
    shortfall_total = np.maximum(remaining, 0.0)
    return (
        realized_total,
        shortfall_total,
        realized_per_acct,
        shortfall_per_acct,
        sold_per_acct,
    )


def run_accounts(
    paths: int,
    spy: int,
    tax_cfg: Dict[str, Any],
    sched: np.ndarray,
    floor_k: float,
    shocks_events: Optional[List[dict]],
    shocks_mode: str,
    infl_yearly: Optional[np.ndarray],
    alloc_accounts: Dict[str, Any],
    person_cfg: Dict[str, Any],
    income_cfg: Dict[str, Any],
    dollars: str = "current",
    rmd_table_path: Optional[str] = None,
    base_year: Optional[int] = None,
    rebalance_drift_threshold: float = 0.10,
    rebalance_brokerage_enabled: bool = True,
    rebalance_brokerage_capgain_limit_k: float = 0.0,
    economic_policy: Optional[Dict[str, Any]] = None,
    assets_path: Optional[str] = None,
    gains_ratio_brokerage: float = 0.30,
) -> Dict[str, Any]:
    np.random.seed(42)
    paths = int(paths)
    spy = int(spy)
    steps = YEARS * spy

    sched = _to_year_vector(sched, cast=float)

    deflator = _build_deflator(infl_yearly)

    per_year_pf = alloc_accounts.get("per_year_portfolios", {}) or {}
    acct_names = list(per_year_pf.keys())
    starting_cfg = alloc_accounts.get("starting", {}) or {}
    deposits_yearly = alloc_accounts.get("deposits_yearly", {}) or {}

    # Correct account classification helpers
    def _is_brokerage(name: str) -> bool:
        nu = name.upper()
        return ("BROKERAGE" in nu) or ("TAXABLE" in nu)

    def _is_trad(name: str) -> bool:
        nu = name.upper()
        return (("TRAD" in nu) or ("TRADITIONAL" in nu)) and ("ROTH" not in nu)

    def _is_roth(name: str) -> bool:
        nu = name.upper()
        return "ROTH" in nu

    trad_accounts = [a for a in acct_names if _is_trad(a)]
    brokerage_accounts = [a for a in acct_names if _is_brokerage(a)]
    roth_accounts = [a for a in acct_names if _is_roth(a)]

    if LOG_DEBUG:
        logger.debug(
            f"Accounts classified → brokerage: {brokerage_accounts}, "
            f"trad: {trad_accounts}, roth: {roth_accounts}"
        )

    # Income vectors (nominal, deterministic per path)
    w2 = np.asarray(income_cfg.get("w2", np.zeros(YEARS)), dtype=float)
    rental = np.asarray(income_cfg.get("rental", np.zeros(YEARS)), dtype=float)
    interest = np.asarray(income_cfg.get("interest", np.zeros(YEARS)), dtype=float)
    ordinary_other = np.asarray(
        income_cfg.get("ordinary_other", np.zeros(YEARS)), dtype=float
    )
    qualified_div_income = np.asarray(
        income_cfg.get("qualified_div", np.zeros(YEARS)), dtype=float
    )
    cap_gains_income = np.asarray(
        income_cfg.get("cap_gains", np.zeros(YEARS)), dtype=float
    )

    def ytd_income_for_year(i: int) -> float:
        return float(
            w2[i]
            + rental[i]
            + interest[i]
            + ordinary_other[i]
            + qualified_div_income[i]
            + cap_gains_income[i]
        )

    # Asset model
    assets_model = load_assets_model(assets_path)
    assets_cfg = assets_model.get("assets", {})
    asset_order = assets_model.get("order", [])
    corr = assets_model.get("corr")

    # Shocks
    shock_mats = build_shock_matrix_from_json(
        shocks_events or [], YEARS, spy, paths, mode=shocks_mode or "augment"
    )
    shock_logs = shock_yearly_log_adjustments(
        shock_mats, years=YEARS, spy=spy, paths=paths
    )

    # Per-asset yearly log returns
    asset_log_R, asset_order = draw_asset_log_returns(
        paths, YEARS, asset_order, assets_cfg, corr, seed=42
    )

    # Balances and trackers
    acct_eoy_nom: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, YEARS), dtype=float) for acct in acct_names
    }
    withdrawals_realized_cur_paths = np.zeros((paths, YEARS), dtype=float)
    withdrawals_shortfall_cur_paths = np.zeros((paths, YEARS), dtype=float)
    withdrawals_realized_cur_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, YEARS), dtype=float) for acct in acct_names
    }
    withdrawals_shortfall_cur_per_acct: Dict[str, np.ndarray] = {
        acct: np.zeros((paths, YEARS), dtype=float) for acct in acct_names
    }

    taxes_fed_cur_paths = np.zeros((paths, YEARS), dtype=float)
    taxes_state_cur_paths = np.zeros((paths, YEARS), dtype=float)
    taxes_niit_cur_paths = np.zeros((paths, YEARS), dtype=float)
    taxes_excise_cur_paths = np.zeros((paths, YEARS), dtype=float)
    realized_gains_cur_paths = np.zeros((paths, YEARS), dtype=float)
    tax_shortfall_cur_paths = np.zeros((paths, YEARS), dtype=float)

    rmd_cur_paths = np.zeros((paths, YEARS), dtype=float)
    rmd_fed_tax_cur_paths = np.zeros((paths, YEARS), dtype=float)
    rmd_state_tax_cur_paths = np.zeros((paths, YEARS), dtype=float)
    rmd_niit_tax_cur_paths = np.zeros((paths, YEARS), dtype=float)
    rmd_shortfall_cur_paths = np.zeros((paths, YEARS), dtype=float)

    order_good, order_bad, dd_thresh = _policy_sequences_from_econ(
        acct_names, economic_policy
    )

    def _pf_defs(acct: str, year_idx: int) -> Dict[str, Dict[str, Any]]:
        rows = per_year_pf.get(acct, [])
        if not rows:
            return {}
        i = min(max(int(year_idx), 0), len(rows) - 1)
        item = rows[i] or {}
        return item.get("portfolios") or {}

    total_nom_paths_accum = np.zeros((paths, YEARS), dtype=float)

    rmd_table = {}
    if rmd_table_path and os.path.isfile(rmd_table_path):
        try:
            rmd_table = load_rmd_table(rmd_table_path)
        except Exception:
            rmd_table = {}

    owner_current_age = float(person_cfg.get("current_age", 0.0))

    # TaxLots and price proxies for brokerage
    taxlots: Dict[str, List[TaxLots]] = {}
    price_series: Dict[str, np.ndarray] = {}
    for a in brokerage_accounts:
        taxlots[a] = [TaxLots() for _ in range(paths)]
        price_series[a] = np.ones((paths, YEARS), dtype=float)
        start_bal = float(starting_cfg.get(a, 0.0))
        if start_bal > 1e-12:
            for p in range(paths):
                taxlots[a][p].add(units=start_bal, basis_per_unit=1.0)
            price_series[a][:, 0] = 1.0

    acct_class_w_last: Dict[str, Dict[str, float]] = {}
    for y in range(YEARS):
        # 1) Grow balances and add deposits
        for acct in acct_names:
            pf = _pf_defs(acct, y)

            class_w = {
                "US_STOCKS": 0.0,
                "INTL_STOCKS": 0.0,
                "LONG_TREAS": 0.0,
                "INT_TREAS": 0.0,
                "TIPS": 0.0,
                "GOLD": 0.0,
                "COMMOD": 0.0,
                "OTHER": 0.0,
            }
            asset_w: Dict[str, float] = {}

            for pf_name, pf_def in (pf or {}).items():
                w_pf = float(pf_def.get("weight", 0.0))

                # Class-level weights
                for cls, w in (pf_def.get("classes", {}) or {}).items():
                    class_w[cls] = class_w.get(cls, 0.0) + w_pf * float(w)

                # Holdings within classes (tickers)
                hp = pf_def.get("holdings_pct", {}) or {}
                for cls, items in hp.items():
                    if not isinstance(items, list):
                        continue
                    for it in items:
                        ticker = str(it.get("ticker", "")).strip()
                        pct = float(it.get("pct", 0.0))
                        if ticker and pct > 0.0 and ticker in assets_cfg:
                            asset_w[ticker] = asset_w.get(ticker, 0.0) + w_pf * (
                                pct / 100.0
                            )

            w_sum = max(sum(class_w.values()), 1e-12)
            for k in list(class_w.keys()):
                class_w[k] = class_w[k] / w_sum
            acct_class_w_last[acct] = dict(class_w)

            # Compute per-year multiplier paths
            if asset_order and asset_log_R.shape[2] > 0:
                mult_paths = np.ones(paths, dtype=float)
                for i, ticker in enumerate(asset_order):
                    w = float(asset_w.get(ticker, 0.0))
                    if w <= 1e-12:
                        continue
                    cls = assets_cfg[ticker]["class"]
                    er = float(assets_cfg[ticker].get("expense_ratio", 0.0))
                    s_log = shock_logs.get(
                        cls, np.zeros((paths, YEARS), dtype=float)
                    )[:, y]
                    r_log = asset_log_R[:, y, i]
                    mult_paths *= (np.exp(r_log + s_log) * max(0.0, 1.0 - er)) ** w
                year_mult = mult_paths
            else:
                def _year_mult(cls: str) -> np.ndarray:
                    arr = shock_mats.get(cls)
                    if arr is None or arr.shape != (paths, steps):
                        return np.ones(paths, dtype=float)
                    t0 = y * spy
                    t1 = t0 + spy
                    return arr[:, t0:t1].prod(axis=1)

                eq_mult = 0.5 * _year_mult("US_STOCKS") + 0.5 * _year_mult(
                    "INTL_STOCKS"
                )
                bd_mult = (
                    _year_mult("LONG_TREAS")
                    + _year_mult("INT_TREAS")
                    + _year_mult("TIPS")
                ) / 3.0
                gd_mult = _year_mult("GOLD")
                cm_mult = _year_mult("COMMOD")

                w_equity = class_w.get("US_STOCKS", 0.0) + class_w.get(
                    "INTL_STOCKS", 0.0
                )
                w_bonds = (
                    class_w.get("LONG_TREAS", 0.0)
                    + class_w.get("INT_TREAS", 0.0)
                    + class_w.get("TIPS", 0.0)
                )
                w_gold = class_w.get("GOLD", 0.0)
                w_commod = class_w.get("COMMOD", 0.0)
                w_sum2 = max(w_equity + w_bonds + w_gold + w_commod, 1e-12)
                w_equity /= w_sum2
                w_bonds /= w_sum2
                w_gold /= w_sum2
                w_commod /= w_sum2

                year_mult = (
                    w_equity * eq_mult
                    + w_bonds * bd_mult
                    + w_gold * gd_mult
                    + w_commod * cm_mult
                )

            # Compound balances and add deposits
            if y == 0:
                start_bal = float(starting_cfg.get(acct, 0.0))
                acct_eoy_nom[acct][:, y] = np.full(paths, start_bal, dtype=float) * year_mult
            else:
                prev = acct_eoy_nom[acct][:, y - 1]
                acct_eoy_nom[acct][:, y] = prev * year_mult

            dep_vec = np.asarray(
                deposits_yearly.get(acct, np.zeros(YEARS)), dtype=float
            ).reshape(-1)
            acct_eoy_nom[acct][:, y] += (
                np.where(np.isfinite(dep_vec[y]), dep_vec[y], 0.0) * deflator[y]
            )

        # Brokerage price proxy and FIFO buys
        for a in brokerage_accounts:
            prev_bal = acct_eoy_nom[a][:, y - 1] if y > 0 else np.ones(
                paths, dtype=float
            )
            curr_bal = acct_eoy_nom[a][:, y]
            prev_bal_safe = np.where(prev_bal > 1e-12, prev_bal, 1.0)
            curr_bal_safe = np.where(np.isfinite(curr_bal), curr_bal, 0.0)
            ratio_raw = curr_bal_safe / prev_bal_safe
            ratio = np.clip(ratio_raw, 0.25, 4.0)
            price_series[a][:, y] = (
                price_series[a][:, y - 1] * ratio if y > 0 else price_series[a][:, y]
            )

            delta = curr_bal_safe - (
                acct_eoy_nom[a][:, y - 1]
                if y > 0
                else np.full(
                    paths, float(starting_cfg.get(a, 0.0)), dtype=float
                )
            )
            price_y = price_series[a][:, y]
            for p in range(paths):
                if (
                    delta[p] > 1e-12
                    and price_y[p] > 1e-12
                    and np.isfinite(price_y[p])
                ):
                    units = delta[p] / price_y[p]
                    if units > 1e-12:
                        taxlots[a][p].add(units, price_y[p])

        # 2) RMD from prior TRAD balances
        if trad_accounts and rmd_table:
            prior_trad_nom = np.zeros(paths, dtype=float)
            if y > 0:
                for a in trad_accounts:
                    prior_trad_nom += np.where(
                        np.isfinite(acct_eoy_nom[a][:, y - 1]),
                        acct_eoy_nom[a][:, y - 1],
                        0.0,
                    )
            else:
                for a in trad_accounts:
                    prior_trad_nom += np.full(
                        paths, float(starting_cfg.get(a, 0.0)), dtype=float
                    )

            owner_age_y = owner_current_age + y
            try:
                factor = float(uniform_factor(int(owner_age_y), rmd_table))
            except Exception:
                factor = 0.0

            rmd_nom_paths = np.zeros(paths, dtype=float)
            if factor > 1e-12:
                rmd_nom_paths = prior_trad_nom / factor

            remaining_rmd = rmd_nom_paths.copy()
            if np.any(remaining_rmd > 1e-12):
                total_prior = prior_trad_nom.copy()
                for a in trad_accounts:
                    if y > 0:
                        bal_prior = np.where(
                            np.isfinite(acct_eoy_nom[a][:, y - 1]),
                            acct_eoy_nom[a][:, y - 1],
                            0.0,
                        )
                    else:
                        bal_prior = np.full(
                            paths, float(starting_cfg.get(a, 0.0)), dtype=float
                        )
                    share = np.where(
                        total_prior > 1e-12, bal_prior / total_prior, 0.0
                    )
                    bal_now = np.where(
                        np.isfinite(acct_eoy_nom[a][:, y]),
                        acct_eoy_nom[a][:, y],
                        0.0,
                    )
                    take = np.minimum(bal_now, remaining_rmd * share)
                    acct_eoy_nom[a][:, y] = bal_now - take
                    remaining_rmd -= take

                rmd_shortfall_cur_paths[:, y] = remaining_rmd / max(
                    deflator[y], 1e-12
                )

            rmd_cur_paths[:, y] = (rmd_nom_paths - remaining_rmd) / max(
                deflator[y], 1e-12
            )

        # 3) Market state for sequencing
        total_nom_paths_y = None
        for acct in acct_names:
            v = np.where(
                np.isfinite(acct_eoy_nom[acct][:, y]), acct_eoy_nom[acct][:, y], 0.0
            )
            total_nom_paths_y = v if total_nom_paths_y is None else (
                total_nom_paths_y + v
            )
        total_nom_paths_accum[:, y] = total_nom_paths_y

        max_to_date = np.maximum.accumulate(total_nom_paths_accum, axis=1)[:, y]
        dd = np.where(
            max_to_date > 1e-12, 1.0 - (total_nom_paths_y / max_to_date), 0.0
        )
        dd_med = float(np.median(dd))
        sequence = order_bad if (dd_med >= dd_thresh) else order_good

        # 4) Discretionary withdrawals
        planned_cur = float(sched[y])
        planned_nom_paths = np.full(paths, planned_cur * deflator[y], dtype=float)

#        (
#            realized_nom_paths,
#            shortfall_nom_paths,
#            realized_per_acct_nom,
#            shortfall_per_acct_nom,
#            sold_per_acct_nom,
#        ) = _apply_withdrawals_nominal_per_account(
#            acct_eoy_nom, y, planned_nom_paths, sequence
#        )

        (
            realized_nom_paths,
            shortfall_nom_paths,
            realized_per_acct_nom,
            shortfall_per_acct_nom,
            sold_per_acct_nom,
        ) = apply_withdrawals_nominal_per_account(
            acct_eoy_nom, y, planned_nom_paths, sequence
        )

        # FIFO sells for brokerage realized gains
        for a in brokerage_accounts:
            price_y = price_series[a][:, y]
            bal_vec = np.where(
                np.isfinite(acct_eoy_nom[a][:, y]), acct_eoy_nom[a][:, y], 0.0
            )
            sell_vec = realized_per_acct_nom.get(a, np.zeros(paths))
            for p in range(paths):
                pay = sell_vec[p]
                if (
                    pay > 1e-12
                    and price_y[p] > 1e-12
                    and np.isfinite(price_y[p])
                ):
                    units_to_sell = pay / price_y[p]
                    units_sold, total_basis_units = taxlots[a][p].sell(
                        units_to_sell
                    )
                    realized_cost_nom = total_basis_units
                    realized_gain = max(0.0, pay - realized_cost_nom)
                    realized_gains_cur_paths[p, y] += realized_gain / max(
                        deflator[y], 1e-12
                    )
                    acct_eoy_nom[a][p, y] = bal_vec[p] - pay

        withdrawals_realized_cur_paths[:, y] = realized_nom_paths / max(
            deflator[y], 1e-12
        )
        withdrawals_shortfall_cur_paths[:, y] = shortfall_nom_paths / max(
            deflator[y], 1e-12
        )
        for acct in acct_names:
            withdrawals_realized_cur_per_acct[acct][:, y] = (
                realized_per_acct_nom.get(acct, np.zeros(paths))
                / max(deflator[y], 1e-12)
            )
            withdrawals_shortfall_cur_per_acct[acct][:, y] = (
                shortfall_per_acct_nom.get(acct, np.zeros(paths))
                / max(deflator[y], 1e-12)
            )

        # 5) Taxes — distributions and realized gains
        ord_div_nom = np.zeros(paths, dtype=float)
        qual_div_nom = np.zeros(paths, dtype=float)
        for acct in acct_names:
            pf = _pf_defs(acct, y)
            yield_annual = 0.0
            qual_ratio = 0.0
            total_asset_weight = 0.0
            for pf_name, pf_def in (pf or {}).items():
                w_pf = float(pf_def.get("weight", 0.0))
                hp = pf_def.get("holdings_pct", {}) or {}
                for cls, items in hp.items():
                    if not isinstance(items, list):
                        continue
                    for it in items:
                        ticker = str(it.get("ticker", "")).strip()
                        pct = float(it.get("pct", 0.0)) / 100.0
                        if ticker in assets_cfg and pct > 0.0:
                            aw = w_pf * pct
                            total_asset_weight += aw
                            yield_annual += aw * float(
                                assets_cfg[ticker]
                                .get("dist", {})
                                .get("yield_annual", 0.0)
                            )
                            qual_ratio += aw * float(
                                assets_cfg[ticker]
                                .get("dist", {})
                                .get("qualified_ratio", 0.0)
                            )
            if total_asset_weight > 1e-12:
                yield_annual /= total_asset_weight
                qual_ratio /= total_asset_weight
            acct_bal_nom = np.where(
                np.isfinite(acct_eoy_nom[acct][:, y]), acct_eoy_nom[acct][:, y], 0.0
            )
            dist_nom = acct_bal_nom * max(yield_annual, 0.0)
            qual_part = dist_nom * max(min(qual_ratio, 1.0), 0.0)
            ord_part = dist_nom - qual_part
            ord_div_nom += ord_part
            qual_div_nom += qual_part

        fed_ord_br = tax_cfg.get("FED_ORD", [])
        fed_qual_br = tax_cfg.get("FED_QUAL", [])
        state_ord_br = tax_cfg.get("STATE_ORD", [])
        niit_rate = float(tax_cfg.get("NIIT_RATE", 0.0))
        niit_thresh_nom = float(tax_cfg.get("NIIT_THRESH", 0.0))

        fed_tax_nom = np.zeros(paths, dtype=float)
        state_tax_nom = np.zeros(paths, dtype=float)
        niit_nom = np.zeros(paths, dtype=float)
        excise_nom = np.zeros(paths, dtype=float)

        for p in range(paths):
            comp = compute_dividend_taxes_components(
                ordinary_div_nom=float(ord_div_nom[p]),
                qualified_div_nom=float(qual_div_nom[p]),
                fed_ord_brackets=fed_ord_br,
                fed_qual_brackets=fed_qual_br,
                state_type=str(tax_cfg.get("STATE_TYPE", "none")),
                state_ord_brackets=state_ord_br,
                niit_rate=niit_rate,
                niit_threshold_nom=niit_thresh_nom,
                ytd_income_nom=ytd_income_for_year(y),
            )
            fed_tax_nom[p] = comp["fed_ord"] + comp["fed_qual"]
            state_tax_nom[p] = comp["state"]
            niit_nom[p] = comp["niit"]
            excise_nom[p] = comp.get("excise", 0.0)

        realized_gains_nom = (
            np.where(
                np.isfinite(realized_gains_cur_paths[:, y]),
                realized_gains_cur_paths[:, y],
                0.0,
            )
            * max(deflator[y], 1e-12)
        )

        excise_rate_nom = float(
            ((tax_cfg.get("STATE_CG_EXCISE", {}) or {}).get("rate", 0.0))
        )
        fed_gain_nom = np.zeros(paths, dtype=float)
        state_gain_nom = np.zeros(paths, dtype=float)
        niit_gain_nom = np.zeros(paths, dtype=float)
        excise_gain_nom = np.zeros(paths, dtype=float)

        for p in range(paths):
            compg = compute_gains_taxes_components(
                realized_gains_nom=float(realized_gains_nom[p]),
                fed_qual_brackets=fed_qual_br,
                state_ord_brackets=state_ord_br,
                niit_rate=niit_rate,
                niit_threshold_nom=niit_thresh_nom,
                ytd_income_nom=ytd_income_for_year(y),
                excise_rate_nom=excise_rate_nom,
            )
            fed_gain_nom[p] = compg["fed_qual"]
            state_gain_nom[p] = compg["state"]
            niit_gain_nom[p] = compg["niit"]
            excise_gain_nom[p] = compg["excise"]

        total_tax_nom = (
            fed_tax_nom
            + state_tax_nom
            + niit_nom
            + excise_nom
            + (fed_gain_nom + state_gain_nom + niit_gain_nom + excise_gain_nom)
        )

        taxes_fed_cur_paths[:, y] = (fed_tax_nom + fed_gain_nom) / max(
            deflator[y], 1e-12
        )
        taxes_state_cur_paths[:, y] = (state_tax_nom + state_gain_nom) / max(
            deflator[y], 1e-12
        )
        taxes_niit_cur_paths[:, y] = (niit_nom + niit_gain_nom) / max(
            deflator[y], 1e-12
        )
        taxes_excise_cur_paths[:, y] = (excise_nom + excise_gain_nom) / max(
            deflator[y], 1e-12
        )

        # Deduct taxes from brokerage via FIFO sells
        if brokerage_accounts:
            bro_sum = np.zeros(paths, dtype=float)
            for a in brokerage_accounts:
                bro_sum += np.where(
                    np.isfinite(acct_eoy_nom[a][:, y]), acct_eoy_nom[a][:, y], 0.0
                )
            bro_sum_safe = np.where(bro_sum > 1e-12, bro_sum, 1.0)
            remaining_tax = total_tax_nom.copy()
            for a in brokerage_accounts:
                bal_vec = np.where(
                    np.isfinite(acct_eoy_nom[a][:, y]), acct_eoy_nom[a][:, y], 0.0
                )
                share = bal_vec / bro_sum_safe
                pay_vec = np.minimum(remaining_tax * share, bal_vec)
                price_y = price_series[a][:, y]
                for p in range(paths):
                    pay = pay_vec[p]
                    if (
                        pay > 1e-12
                        and price_y[p] > 1e-12
                        and np.isfinite(price_y[p])
                    ):
                        units_to_sell = pay / price_y[p]
                        units_sold, total_basis_units = taxlots[a][p].sell(
                            units_to_sell
                        )
                        realized_cost_nom = total_basis_units
                        realized_gain = max(0.0, pay - realized_cost_nom)
                        realized_gains_cur_paths[p, y] += realized_gain / max(
                            deflator[y], 1e-12
                        )
                        acct_eoy_nom[a][p, y] = bal_vec[p] - pay
                remaining_tax -= pay_vec
            tax_shortfall_cur_paths[:, y] += remaining_tax / max(
                deflator[y], 1e-12
            )
        else:
            tax_shortfall_cur_paths[:, y] += total_tax_nom / max(
                deflator[y], 1e-12
            )

        # 6) Rebalancing at year-end
        def target_class_weights(acct: str, y_idx: int) -> Dict[str, float]:
            pf = _pf_defs(acct, y_idx)
            target = {
                "US_STOCKS": 0.0,
                "INTL_STOCKS": 0.0,
                "LONG_TREAS": 0.0,
                "INT_TREAS": 0.0,
                "TIPS": 0.0,
                "GOLD": 0.0,
                "COMMOD": 0.0,
                "OTHER": 0.0,
            }
            total_pf = 0.0
            for name, p in (pf or {}).items():
                w = float(p.get("weight", 0.0))
                total_pf += w
                for cls, cw in (p.get("classes", {}) or {}).items():
                    target[cls] = target.get(cls, 0.0) + w * float(cw)
            if total_pf > 1e-12:
                for k in list(target.keys()):
                    target[k] = target[k] / total_pf
            return target

        fed_ord_br = tax_cfg.get("FED_ORD", [])
        fed_qual_br = tax_cfg.get("FED_QUAL", [])
        state_ord_br = tax_cfg.get("STATE_ORD", [])
        niit_rate = float(tax_cfg.get("NIIT_RATE", 0.0))
        niit_thresh_nom = float(tax_cfg.get("NIIT_THRESH", 0.0))
        excise_rate_nom = float(
            ((tax_cfg.get("STATE_CG_EXCISE", {}) or {}).get("rate", 0.0))
        )

        for acct in acct_names:
            tgt = target_class_weights(acct, y)
            actual = acct_class_w_last.get(acct, tgt)
            max_drift = max(
                abs(actual.get(k, 0.0) - tgt.get(k, 0.0)) for k in tgt.keys()
            )
            if max_drift < rebalance_drift_threshold:
                continue

            if acct in trad_accounts:
                # Costless rebalance approximation (no per-class buckets tracked here)
                pass
            elif acct in brokerage_accounts and rebalance_brokerage_enabled:
                cap_nom = rebalance_brokerage_capgain_limit_k * 1000.0
                if cap_nom <= 1e-12:
                    continue
                price_y = price_series[acct][:, y]
                bal_vec = np.where(
                    np.isfinite(acct_eoy_nom[acct][:, y]),
                    acct_eoy_nom[acct][:, y],
                    0.0,
                )
                pay_vec = np.minimum(np.full(paths, cap_nom, dtype=float), bal_vec)
                for p in range(paths):
                    pay = pay_vec[p]
                    if (
                        pay > 1e-12
                        and price_y[p] > 1e-12
                        and np.isfinite(price_y[p])
                    ):
                        units_to_sell = pay / price_y[p]
                        units_sold, total_basis_units = taxlots[acct][p].sell(
                            units_to_sell
                        )
                        realized_cost_nom = total_basis_units
                        realized_gain = max(0.0, pay - realized_cost_nom)
                        acct_eoy_nom[acct][p, y] = bal_vec[p] - pay

                        # Immediate taxes on rebalancing gains
                        compg = compute_gains_taxes_components(
                            realized_gains_nom=realized_gain,
                            fed_qual_brackets=fed_qual_br,
                            state_ord_brackets=state_ord_br,
                            niit_rate=niit_rate,
                            niit_threshold_nom=niit_thresh_nom,
                            ytd_income_nom=ytd_income_for_year(y),
                            excise_rate_nom=excise_rate_nom,
                        )
                        tax_now = (
                            compg["fed_qual"]
                            + compg["state"]
                            + compg["niit"]
                            + compg["excise"]
                        )
                        pay_tax = min(tax_now, acct_eoy_nom[acct][p, y])
                        acct_eoy_nom[acct][p, y] -= pay_tax

                        realized_gains_cur_paths[p, y] += realized_gain / max(
                            deflator[y], 1e-12
                        )
                        taxes_fed_cur_paths[p, y] += compg["fed_qual"] / max(
                            deflator[y], 1e-12
                        )
                        taxes_state_cur_paths[p, y] += compg["state"] / max(
                            deflator[y], 1e-12
                        )
                        taxes_niit_cur_paths[p, y] += compg["niit"] / max(
                            deflator[y], 1e-12
                        )
                        taxes_excise_cur_paths[p, y] += compg["excise"] / max(
                            deflator[y], 1e-12
                        )
                        tax_shortfall_cur_paths[p, y] += max(
                            0.0, tax_now - pay_tax
                        ) / max(deflator[y], 1e-12)

        # 7) Totals after RMD, withdrawals, taxes, rebalancing
        total_nom_paths = None
        for acct in acct_names:
            paths_nom = np.where(
                np.isfinite(acct_eoy_nom[acct]), acct_eoy_nom[acct], 0.0
            )
            total_nom_paths = (
                paths_nom if total_nom_paths is None else (total_nom_paths + paths_nom)
            )
        total_cur_paths = total_nom_paths / deflator

        def pct_change_paths(series_2d: np.ndarray) -> np.ndarray:
            s = np.asarray(series_2d, dtype=float)
            P, Y = s.shape
            r = np.zeros_like(s)
            prev = np.maximum(s[:, :-1], 1e-12)
            r[:, 1:] = (s[:, 1:] / prev - 1.0) * 100.0
            return r

        yoy_nom_paths = pct_change_paths(total_nom_paths)
        yoy_real_paths = pct_change_paths(total_nom_paths / deflator)
        fut_mean = total_nom_paths.mean(axis=0)
        fut_med = np.median(total_nom_paths, axis=0)
        fut_p10 = np.percentile(total_nom_paths, 10, axis=0)
        fut_p90 = np.percentile(total_nom_paths, 90, axis=0)
        cur_mean = total_cur_paths.mean(axis=0)
        cur_med = np.median(total_cur_paths, axis=0)
        cur_p10 = np.percentile(total_cur_paths, 10, axis=0)
        cur_p90 = np.percentile(total_cur_paths, 90, axis=0)

        # Per-account levels and YoY
        inv_nom_yoy_mean_pct_acct: Dict[str, List[float]] = {}
        inv_real_yoy_mean_pct_acct: Dict[str, List[float]] = {}
        inv_nom_levels_mean_acct: Dict[str, List[float]] = {}
        inv_nom_levels_med_acct: Dict[str, List[float]] = {}
        inv_nom_levels_p10_acct: Dict[str, List[float]] = {}
        inv_nom_levels_p90_acct: Dict[str, List[float]] = {}
        inv_real_levels_mean_acct: Dict[str, List[float]] = {}
        inv_real_levels_med_acct: Dict[str, List[float]] = {}
        inv_real_levels_p10_acct: Dict[str, List[float]] = {}
        inv_real_levels_p90_acct: Dict[str, List[float]] = {}

        for acct in acct_names:
            acct_nom = np.where(np.isfinite(acct_eoy_nom[acct]), acct_eoy_nom[acct], 0.0)
            acct_real = acct_nom / deflator

            inv_nom_levels_mean_acct[acct] = acct_nom.mean(axis=0).tolist()
            inv_nom_levels_med_acct[acct] = np.median(acct_nom, axis=0).tolist()
            inv_nom_levels_p10_acct[acct] = np.percentile(acct_nom, 10, axis=0).tolist()
            inv_nom_levels_p90_acct[acct] = np.percentile(acct_nom, 90, axis=0).tolist()

            inv_real_levels_mean_acct[acct] = acct_real.mean(axis=0).tolist()
            inv_real_levels_med_acct[acct] = np.median(acct_real, axis=0).tolist()
            inv_real_levels_p10_acct[acct] = np.percentile(acct_real, 10, axis=0).tolist()
            inv_real_levels_p90_acct[acct] = np.percentile(acct_real, 90, axis=0).tolist()

            yoy_nom_acct = pct_change_paths(acct_nom)
            yoy_real_acct = pct_change_paths(acct_real)
            inv_nom_yoy_mean_pct_acct[acct] = yoy_nom_acct.mean(axis=0).tolist()
            inv_real_yoy_mean_pct_acct[acct] = yoy_real_acct.mean(axis=0).tolist()

        # Success metrics (based on discretionary withdrawals only)
        met_year_disc = (withdrawals_shortfall_cur_paths <= 1e-6)
        met_year = met_year_disc
        met_all_years = np.all(met_year, axis=1)
        success_rate_pct = float(np.mean(met_all_years) * 100.0)
        success_rate_by_year = (np.mean(met_year, axis=0) * 100.0).tolist()
        shortfall_years_mean = float(np.mean(np.sum(~met_year, axis=1)))

        if LOG_DEBUG:
            logger.debug(
                "Success metrics → success_rate_pct=%.3f, "
                "shortfall_years_mean=%.3f, "
                "sample success_rate_by_year[0:5]=%s",
                success_rate_pct,
                shortfall_years_mean,
                success_rate_by_year[:5],
            )
            logger.debug(
                "Taxes summary → fed=%.2f, state=%.2f, niit=%.2f, excise=%.2f, "
                "tax_shortfall=%.2f, rmd_total=%.2f",
                float(taxes_fed_cur_paths.sum()),
                float(taxes_state_cur_paths.sum()),
                float(taxes_niit_cur_paths.sum()),
                float(taxes_excise_cur_paths.sum()),
                float(tax_shortfall_cur_paths.sum()),
                float(rmd_cur_paths.sum()),
            )

        # Assemble result
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
        res["withdrawals"] = {
            "planned_current": sched.tolist(),
            "realized_current_mean": withdrawals_realized_cur_paths.mean(axis=0).tolist(),
            "realized_future_mean": (
                withdrawals_realized_cur_paths.mean(axis=0) * deflator
            ).tolist(),
            "shortfall_current_mean": withdrawals_shortfall_cur_paths.mean(axis=0).tolist(),
            "realized_current_per_acct_mean": {
                acct: withdrawals_realized_cur_per_acct[acct].mean(axis=0).tolist()
                for acct in acct_names
            },
            "shortfall_current_per_acct_mean": {
                acct: withdrawals_shortfall_cur_per_acct[acct].mean(axis=0).tolist()
                for acct in acct_names
            },
            "sequence_good_market": order_good,
            "sequence_bad_market": order_bad,
            "bad_market_drawdown_threshold": dd_thresh,
            "taxes_fed_current_mean": taxes_fed_cur_paths.mean(axis=0).tolist(),
            "taxes_state_current_mean": taxes_state_cur_paths.mean(axis=0).tolist(),
            "taxes_niit_current_mean": taxes_niit_cur_paths.mean(axis=0).tolist(),
            "taxes_excise_current_mean": taxes_excise_cur_paths.mean(axis=0).tolist(),
            "tax_shortfall_current_mean": tax_shortfall_cur_paths.mean(axis=0).tolist(),
            "realized_gains_current_mean": realized_gains_cur_paths.mean(axis=0).tolist(),
            "rmd_current_mean": rmd_cur_paths.mean(axis=0).tolist(),
        }

        res["summary"] = {
            "success_rate": success_rate_pct,
            "success_rate_by_year": success_rate_by_year,
            "shortfall_years_mean": shortfall_years_mean,
            "drawdown_p50": float(
                np.percentile(
                    (1.0 - (total_nom_paths / np.maximum.accumulate(total_nom_paths, axis=1))[:, -1])
                    * 100.0,
                    50,
                )
            ),
            "drawdown_p90": float(
                np.percentile(
                    (1.0 - (total_nom_paths / np.maximum.accumulate(total_nom_paths, axis=1))[:, -1])
                    * 100.0,
                    90,
                )
            ),
            "taxes_fed_total_current": float(taxes_fed_cur_paths.sum()),
            "taxes_state_total_current": float(taxes_state_cur_paths.sum()),
            "taxes_niit_total_current": float(taxes_niit_cur_paths.sum()),
            "taxes_excise_total_current": float(taxes_excise_cur_paths.sum()),
            "tax_shortfall_total_current": float(tax_shortfall_cur_paths.sum()),
            "rmd_total_current": float(rmd_cur_paths.sum()),
        }

        # meta: expose success explicitly for reporting/UI
        res["meta"] = {
            "success": success_rate_pct,
            "paths": int(paths),
            "years": YEARS,
        }

        res["returns"] = {
            "nom_withdraw_yoy_mean_pct": yoy_nom_paths.mean(axis=0).tolist(),
            "real_withdraw_yoy_mean_pct": yoy_real_paths.mean(axis=0).tolist(),
            "inv_nom_yoy_mean_pct": yoy_nom_paths.mean(axis=0).tolist(),
            "inv_real_yoy_mean_pct": yoy_real_paths.mean(axis=0).tolist(),
        }
        res["returns_acct"] = {
            "inv_nom_yoy_mean_pct_acct": inv_nom_yoy_mean_pct_acct,
            "inv_real_yoy_mean_pct_acct": inv_real_yoy_mean_pct_acct,
        }
        res["returns_acct_levels"] = {
            "inv_nom_levels_mean_acct": inv_nom_levels_mean_acct,
            "inv_nom_levels_med_acct": inv_nom_levels_med_acct,
            "inv_nom_levels_p10_acct": inv_nom_levels_p10_acct,
            "inv_nom_levels_p90_acct": inv_nom_levels_p90_acct,
            "inv_real_levels_mean_acct": inv_real_levels_mean_acct,
            "inv_real_levels_med_acct": inv_real_levels_med_acct,
            "inv_real_levels_p10_acct": inv_real_levels_p10_acct,
            "inv_real_levels_p90_acct": inv_real_levels_p90_acct,
        }

        if LOG_DEBUG and acct_names:
            a0 = acct_names[0]
            logger.debug(
                "Account %s $Future mean first 5: %s",
                a0,
                res["returns_acct_levels"]["inv_nom_levels_mean_acct"][a0][:5],
            )
            logger.debug(
                "Account %s Nominal YoY mean first 5: %s",
                a0,
                res["returns_acct"]["inv_nom_yoy_mean_pct_acct"][a0][:5],
            )

        # Inject starting balances and accounts list for snapshot/UI
        starting = dict(starting_cfg or {})
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

    return res
# --- End of Part 3/3 / End of file ---

