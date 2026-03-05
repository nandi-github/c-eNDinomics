# filename: sim_core_taxes_paths_test.py

import numpy as np
from loaders import load_tax_unified
from taxes_core import compute_annual_taxes_paths


def main() -> None:
    state = "California"
    filing = "MFJ"

    tax_cfg = load_tax_unified(
        "profiles/default/taxes_states_mfj_single.json",
        state,
        filing,
    )

    # Example: 3 paths of incomes in CURRENT USD for one year
    ordinary_income_cur_paths = np.array([200_000.0, 150_000.0, 250_000.0])
    qual_div_cur_paths = np.array([20_000.0, 10_000.0, 30_000.0])
    cap_gains_cur_paths = np.array([50_000.0, 0.0, 80_000.0])
    ytd_income_nom_paths = ordinary_income_cur_paths  # simple test: ytd = ordinary

    taxes_fed_cur_paths, taxes_state_cur_paths, taxes_niit_cur_paths, taxes_excise_cur_paths = compute_annual_taxes_paths(
        ordinary_income_cur_paths,
        qual_div_cur_paths,
        cap_gains_cur_paths,
        tax_cfg,
        ytd_income_nom_paths,
    )

    print("ordinary_income_cur_paths:", ordinary_income_cur_paths)
    print("qual_div_cur_paths:       ", qual_div_cur_paths)
    print("cap_gains_cur_paths:      ", cap_gains_cur_paths)
    print()
    print("taxes_fed_cur_paths:      ", taxes_fed_cur_paths)
    print("taxes_state_cur_paths:    ", taxes_state_cur_paths)
    print("taxes_niit_cur_paths:     ", taxes_niit_cur_paths)
    print("taxes_excise_cur_paths:   ", taxes_excise_cur_paths)


if __name__ == "__main__":
    main()

