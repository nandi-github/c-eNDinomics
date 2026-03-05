# filename: sim_core_taxes_test.py

from loaders import load_tax_unified
from taxes_core import compute_annual_taxes


def main() -> None:
    state = "California"
    filing = "MFJ"

    tax_cfg = load_tax_unified(
        "profiles/default/taxes_states_mfj_single.json",
        state,
        filing,
    )

    ordinary_income_cur = 200_000.0
    qual_div_cur = 20_000.0
    cap_gains_cur = 50_000.0
    ytd_income_nom = 200_000.0  # or whatever you use in the simulator

    taxes_fed_cur, taxes_state_cur, taxes_niit_cur, taxes_excise_cur = compute_annual_taxes(
        ordinary_income_cur,
        qual_div_cur,
        cap_gains_cur,
        tax_cfg,
        ytd_income_nom,
    )

    print("New taxes_core outputs (current USD):")
    print("  taxes_fed_cur:   ", taxes_fed_cur)
    print("  taxes_state_cur: ", taxes_state_cur)
    print("  taxes_niit_cur:  ", taxes_niit_cur)
    print("  taxes_excise_cur:", taxes_excise_cur)


if __name__ == "__main__":
    main()

