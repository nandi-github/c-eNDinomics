# filename: sim_core_full_year_test.py

from loaders import (
    load_allocation_yearly_accounts,
    load_inflation_yearly,
    load_tax_unified,
    load_income,
    load_person,
)
from income_core import build_income_streams
from simulator_new import run_accounts_new
import numpy as np

YEARS = 30


def main() -> None:
    # Use Test profile for modular lab runs
    alloc = load_allocation_yearly_accounts("profiles/Test/allocation_yearly.json")
    infl = load_inflation_yearly("profiles/Test/inflation_yearly.json", years_count=YEARS)
    income_cfg = load_income("profiles/Test/income.json")
    person_cfg = load_person("profiles/Test/person.json")

    # Unified tax config for Test profile
    tax_cfg = load_tax_unified(
        "profiles/Test/taxes_states_mfj_single.json",
        "California",
        "MFJ",
    )

    # Build per-year income streams in CURRENT USD from income.json (Test)
    (
        w2_cur,
        rental_cur,
        interest_cur,
        ordinary_other_cur,
        qual_div_cur,
        cap_gains_cur,
    ) = build_income_streams(income_cfg, years=YEARS)

    paths = 200
    spy = 2

    # Build per-path, per-year incomes in CURRENT USD
    ordinary_income_cur_paths = np.zeros((paths, YEARS), dtype=float)
    qual_div_cur_paths = np.zeros((paths, YEARS), dtype=float)
    cap_gains_cur_paths = np.zeros((paths, YEARS), dtype=float)
    ytd_income_nom_paths = np.zeros((paths, YEARS), dtype=float)

    for y in range(YEARS):
        # Ordinary = wages + rental + interest + other (no RMDs/conversions yet)
        ordinary_year = (
            w2_cur[y] + rental_cur[y] + interest_cur[y] + ordinary_other_cur[y]
        )
        qual_div_year = qual_div_cur[y]
        cap_gains_year = cap_gains_cur[y]

        ordinary_income_cur_paths[:, y] = ordinary_year
        qual_div_cur_paths[:, y] = qual_div_year
        cap_gains_cur_paths[:, y] = cap_gains_year

        # Simple YTD approximation: this year's ordinary income only
        ytd_income_nom_paths[:, y] = ordinary_year

    # Call the new modular simulator path:
    # core + taxes (no withdrawals in this harness; RMDs only if you pass rmd_table_path)

    conversion_per_year_nom = 50_000.0  # lab: fixed 50k nominal per year

    res = run_accounts_new(
        paths=paths,
        spy=spy,
        infl_yearly=infl,
        alloc_accounts=alloc,
        assets_path="assets.json",
        sched=None,
        apply_withdrawals=False,
        withdraw_sequence=None,
        tax_cfg=tax_cfg,
        ordinary_income_cur_paths=ordinary_income_cur_paths,
        qual_div_cur_paths=qual_div_cur_paths,
        cap_gains_cur_paths=cap_gains_cur_paths,
        ytd_income_nom_paths=ytd_income_nom_paths,
        person_cfg=person_cfg,
        rmd_table_path="profiles/Test/rmd.json",
        conversion_per_year_nom=conversion_per_year_nom,
    )


    # Core portfolio stats from res["portfolio"]
    portfolio = res.get("portfolio", {})
    fut_mean = np.array(portfolio.get("future_mean", []), dtype=float)
    cur_mean = np.array(portfolio.get("current_mean", []), dtype=float)

    print("Core Future mean first 5:", fut_mean[:5])
    print("Core Future mean last 5:", fut_mean[-5:])
    print("Core Current mean first 5:", cur_mean[:5])
    print("Core Current mean last 5:", cur_mean[-5:])

    # Investment returns from res["returns"]
    returns = res.get("returns", {})
    inv_nom_yoy = np.array(returns.get("inv_nom_yoy_mean_pct", []), dtype=float)
    inv_real_yoy = np.array(returns.get("inv_real_yoy_mean_pct", []), dtype=float)

    print("Ordinary income year 1 mean (with RMD+conversions):",
          ordinary_income_cur_paths[:, 0].mean())

    print("Core nominal YoY first 5:", inv_nom_yoy[:5].tolist())
    print("Core real YoY first 5:   ", inv_real_yoy[:5].tolist())

    # If you’ve wired taxes into res["withdrawals"], you can also inspect tax means here.
    # For now, we just confirm the modular path runs end-to-end.


if __name__ == "__main__":
    main()

