# filename: peek_engines_taxes.py

from loaders import load_tax_unified
from engines import compute_dividend_taxes_components, compute_gains_taxes_components


def main() -> None:
    state = "California"
    filing = "MFJ"

    tax_cfg = load_tax_unified(
        "profiles/default/taxes_states_mfj_single.json",
        state,
        filing,
    )

    fed_ord_br = tax_cfg.get("FED_ORD", [])
    fed_qual_br = tax_cfg.get("FED_QUAL", [])
    fed_std_ded = float(tax_cfg.get("FED_STD_DED", 0.0))

    state_ord_br = tax_cfg.get("STATE_ORD", [])
    state_std_ded = float(tax_cfg.get("STATE_STD_DED", 0.0))

    niit_rate = float(tax_cfg.get("NIIT_RATE", 0.0))
    niit_thresh_cur = float(tax_cfg.get("NIIT_THRESH", 0.0))

    excise_cfg = (tax_cfg.get("STATE_CG_EXCISE", {}) or {})
    excise_rate = float(excise_cfg.get("rate", 0.0))

    ordinary_income_cur = 200_000.0
    qual_div_cur = 20_000.0
    cap_gains_cur = 50_000.0

    div_res = compute_dividend_taxes_components(
        ordinary_income_cur,
        qual_div_cur,
        fed_ord_br,
        fed_qual_br,
        fed_std_ded,
        state_ord_br,
        state_std_ded,
        niit_rate,
        niit_thresh_cur,
    )

    gains_res = compute_gains_taxes_components(
        ordinary_income_cur,
        qual_div_cur,
        cap_gains_cur,
        fed_ord_br,
        fed_qual_br,
        fed_std_ded,
        state_ord_br,
        state_std_ded,
        niit_rate,
        niit_thresh_cur,
        excise_rate,
    )

    print("compute_dividend_taxes_components returns type:", type(div_res))
    print("compute_dividend_taxes_components returns value:", div_res)
    print()
    print("compute_gains_taxes_components returns type:", type(gains_res))
    print("compute_gains_taxes_components returns value:", gains_res)


if __name__ == "__main__":
    main()

