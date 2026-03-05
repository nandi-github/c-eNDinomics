
import numpy as np

def _fmt_row(cols, widths, seps="  "):
    out = []
    for i, c in enumerate(cols):
        w = widths[i] if i < len(widths) else 12
        s = f"{c}"
        is_num_like = isinstance(c, (int, float)) or (isinstance(c, str) and (s.strip().startswith(("$", "-")) or any(ch.isdigit() for ch in s)))
        s = s if len(s) <= w else s[:w]
        out.append(s.rjust(w) if is_num_like else s.ljust(w))
    return seps.join(out)


def _print_table(header_cols, rows, col_widths=None, title=None):
    if title:
        print(f"\n{title}")
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(header_cols):
            max_len = len(str(h))
            for r in rows:
                if i < len(r):
                    max_len = max(max_len, len(str(r[i])))
            col_widths.append(max(10, min(26, max_len)))
    print(_fmt_row(header_cols, col_widths))
    print(_fmt_row(["-" * w for w in col_widths], col_widths))
    for r in rows:
        print(_fmt_row(r, col_widths))


def _calc_progressive_tax(amount_nom, ytd_nom, brackets):
    """
    Progressive tax across caps in NOMINAL units.
    amount_nom and ytd_nom are nominal. Brackets 'up_to' are nominal.
    """
    if amount_nom <= 1e-12:
        return 0.0
    tax = 0.0
    remaining = float(amount_nom)
    prev_cap = float(ytd_nom)
    for br in (brackets or []):
        cap = br.get("up_to")
        rate = float(br.get("rate", 0.0))
        if cap is None:
            tax += remaining * rate
            remaining = 0.0
            break
        room = max(0.0, float(cap) - prev_cap)
        take = min(remaining, room)
        tax += take * rate
        remaining -= take
        prev_cap = float(cap)
        if remaining <= 1e-12:
            break
    return float(tax)


def _policy_target_cap_for_year(tax_cfg, person_cfg, taxable_ytd_cur, year_defl):
    """
    Decide cap for the year, returning (cap_nom, label). Compares taxable_ytd against caps in NOMINAL units.
      - 'no_limit' → (None, 'no_limit')
      - 'fill the bracket' → top of current federal ordinary bracket (NOMINAL)
      - 'XX%' (e.g., '22%') → cap to the bracket with that marginal rate (NOMINAL)
    Person policy can be under 'roth_conversion_policy' or 'conversion_policy'.
    """
    conv = person_cfg.get("conversion_policy", {}) or person_cfg.get("roth_conversion_policy", {}) or {}
    setting = str(conv.get("keepit_below_max_marginal_fed_rate", "no_limit")).strip().lower()

    brackets = tax_cfg.get("FED_ORD", [])
    std_ded = float(tax_cfg.get("FED_STD_DED", 0.0))

    taxable_ytd_nom = max(0.0, float(taxable_ytd_cur) - std_ded) * float(year_defl)

    if setting == "no_limit":
        return None, "no_limit"
    if setting == "fill the bracket":
        for br in brackets:
            cap = br.get("up_to")
            if cap is None:
                return None, "top"
            if taxable_ytd_nom < float(cap):
                return float(cap), "fill the bracket"
        return None, "top"
    # Specific percent target
    try:
        target_pct = float(setting.strip("%")) / 100.0
    except Exception:
        return None, "invalid"
    for br in brackets:
        if abs(float(br.get("rate", 0.0)) - target_pct) < 1e-9:
            cap = br.get("up_to")
            return (None if cap is None else float(cap)), f"{int(target_pct*100)}%"
    return None, "unknown"


def report_conversions_bracket_fill(res,
                                    tax_cfg,
                                    years,
                                    defl,
                                    acct_eoy_current_post_mean,
                                    out_dir,
                                    person_cfg,
                                    ext_ord_vec=None,
                                    ext_qual_vec=None,
                                    ext_cg_vec=None,
                                    ext_conv_fund_vec=None):
    """
    Prints a Roth conversion table in current USD:
      - Policy cap label and fed taxable base (pre-conversion) — CURRENT USD
      - Conversion principal sized vs cap and TRAD_IRA value — CURRENT USD
      - Ordinary taxes (Fed/State) on conversion principal — CURRENT USD (computed from NOMINAL then deflated)
      - Funding breakdown: conversion fund → ordinary income → capital gains raise — CURRENT USD
      - Pre/Post balances for BROKERAGE/TRAD_IRA/ROTH_IRA — CURRENT USD means

    Inputs:
      res: simulator result dict (may include 'roth_conversions_current')
      tax_cfg: unified tax dict
      years: np.arange(1..YEARS)
      defl: per-year deflator (future→current), cumulative ∏(1+inflation_y)
      acct_eoy_current_post_mean: dict of current USD means per account
      person_cfg: includes conversion policy (cap rules)
      ext_*_vec: optional external vectors (ordinary income and conversion fund) in CURRENT USD
    """
    years = np.asarray(years, dtype=int)
    defl = np.asarray(defl, dtype=float)
    conv_series_cur = np.asarray(res.get("roth_conversions_current", np.zeros_like(years, dtype=float)))

    # Ordinary dividends future mean deflated to current (proxy for ytd ordinary stack)
    gross_div_ord_fut_mean = np.asarray(res.get("gross_div_ord", np.zeros_like(years, dtype=float)))
    port_ord_cur = gross_div_ord_fut_mean / np.maximum(defl, 1e-12)

    # External inputs
    ext_ord_vec  = np.zeros_like(years, dtype=float) if ext_ord_vec  is None else np.asarray(ext_ord_vec, dtype=float)
    ext_conv_fund_vec = np.zeros_like(years, dtype=float) if ext_conv_fund_vec is None else np.asarray(ext_conv_fund_vec, dtype=float)

    # Account current means
    b_cur = np.asarray(acct_eoy_current_post_mean.get("BROKERAGE", np.zeros_like(years, dtype=float)))
    t_cur = np.asarray(acct_eoy_current_post_mean.get("TRAD_IRA",  np.zeros_like(years, dtype=float)))
    r_cur = np.asarray(acct_eoy_current_post_mean.get("ROTH_IRA",  np.zeros_like(years, dtype=float)))

    rows = []
    for i, y in enumerate(years):
        year_defl = float(defl[i])

        suggested_cur = float(conv_series_cur[i])
        ytd_ord_cur   = float(port_ord_cur[i] + ext_ord_vec[i])

        # Policy cap in NOMINAL units, labeled
        cap_nom, cap_label = _policy_target_cap_for_year(tax_cfg, person_cfg, taxable_ytd_cur=ytd_ord_cur, year_defl=year_defl)

        # Conversion amount (CURRENT USD): min(TRAD value_cur, suggested_cur, cap room converted to current)
        conv_amt_cur = float(t_cur[i])  # default: all TRAD value
        if suggested_cur > 1e-6:
            conv_amt_cur = min(conv_amt_cur, suggested_cur)

        if cap_nom is not None:
            taxable_base_cur = max(0.0, ytd_ord_cur - float(tax_cfg.get("FED_STD_DED", 0.0)))
            taxable_base_nom = taxable_base_cur * year_defl
            room_nom = max(0.0, float(cap_nom) - taxable_base_nom)
            room_cur = room_nom / max(year_defl, 1e-12)
            conv_amt_cur = min(conv_amt_cur, room_cur)

        if conv_amt_cur <= 1e-6:
            continue  # no conversion

        # Taxes: compute in NOMINAL, then convert to CURRENT
        fed_std   = float(tax_cfg.get("FED_STD_DED", 0.0))
        state_std = float(tax_cfg.get("STATE_STD_DED", 0.0))

        fed_base_after_cur   = max(0.0, ytd_ord_cur + conv_amt_cur - fed_std)
        state_base_after_cur = max(0.0, ytd_ord_cur + conv_amt_cur - state_std)

        fed_base_after_nom   = fed_base_after_cur * year_defl
        state_base_after_nom = state_base_after_cur * year_defl

        fed_tax_nom   = _calc_progressive_tax(fed_base_after_nom,   0.0, tax_cfg.get("FED_ORD", []))
        state_tax_nom = 0.0 if tax_cfg.get("STATE_TYPE", "none") == "none" else _calc_progressive_tax(state_base_after_nom, 0.0, tax_cfg.get("STATE_ORD", []))
        total_tax_nom = fed_tax_nom + state_tax_nom

        # Convert taxes back to current USD for presentation/funding
        fed_tax_cur   = fed_tax_nom   / max(year_defl, 1e-12)
        state_tax_cur = state_tax_nom / max(year_defl, 1e-12)
        total_tax_cur = fed_tax_cur + state_tax_cur

        # Funding priority: conversion fund → ordinary income cash → capital gains raise (CURRENT USD)
        fund_from_income_cur = float(min(ext_conv_fund_vec[i], total_tax_cur))
        remaining_tax_cur    = total_tax_cur - fund_from_income_cur
        tax_from_ord_cur     = min(ytd_ord_cur, remaining_tax_cur)
        tax_from_cg_cur      = max(0.0, remaining_tax_cur - tax_from_ord_cur)

        # Pre/Post balances (CURRENT USD)
        b_pre = float(b_cur[i])
        t_pre = float(t_cur[i])
        r_pre = float(r_cur[i])

        b_post = max(0.0, b_pre - total_tax_cur)  # brokerage pays taxes
        t_post = max(0.0, t_pre - conv_amt_cur)
        r_post = r_pre + conv_amt_cur

        rows.append([
            f"Year {y:2d}",
            cap_label,
            f"${(max(0.0, ytd_ord_cur - fed_std)):,.0f}",
            f"${conv_amt_cur:,.0f}",
            f"${total_tax_cur:,.0f}",
            f"${fed_tax_cur:,.0f}",
            f"${state_tax_cur:,.0f}",
            f"${fund_from_income_cur:,.0f}",
            f"${tax_from_ord_cur:,.0f}",
            f"${tax_from_cg_cur:,.0f}",
            f"${b_pre:,.0f}", f"${b_post:,.0f}",
            f"${t_pre:,.0f}", f"${t_post:,.0f}",
            f"${r_pre:,.0f}", f"${r_post:,.0f}"
        ])

    if rows:
        header = [
            "Year",
            "Policy Cap",
            "Fed Taxable Base (Pre Conv)",
            "Conversion",
            "Total Ord Tax",
            "Fed Tax",
            "State Tax",
            "Tax from Income JSON",
            "Tax from Ordinary",
            "Tax from Cap Gains",
            "BROKERAGE Pre", "BROKERAGE Post",
            "TRAD_IRA Pre", "TRAD_IRA Post",
            "ROTH_IRA Pre", "ROTH_IRA Post",
        ]
        _print_table(header, rows, title="=== Roth Conversions (Current USD) — Cap/Taxes/Funding & Pre/Post Balances ===")


