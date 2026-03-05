# filename: sim_core_conversions_test.py

from loaders import load_allocation_yearly_accounts, load_person
from simulation_core import simulate_balances
import numpy as np

YEARS = 30


def main() -> None:
    # Use Test profile
    alloc = load_allocation_yearly_accounts("profiles/Test/allocation_yearly.json")
    person_cfg = load_person("profiles/Test/person.json")

    paths = 200
    spy = 2

    # Core Monte Carlo (no withdrawals, no shocks, baseline inflation)
    acct_eoy_nom, total_nom_paths, total_real_paths = simulate_balances(
        paths=paths,
        years=YEARS,
        spy=spy,
        alloc_accounts=alloc,
        assets_path="assets.json",
        shocks_events=[],         # no shocks in this test
        shocks_mode="augment",    # unused when events=[]
        infl_yearly=None,         # baseline inflation in core
    )

    acct_names = list(acct_eoy_nom.keys())

    def _is_trad(name: str) -> bool:
        nu = name.upper()
        return (("TRAD" in nu) or ("TRAD-IRA" in nu) or ("TRADITIONAL" in nu)) and ("ROTH" not in nu)

    def _is_roth(name: str) -> bool:
        nu = name.upper()
        return "ROTH" in nu

    trad_accounts = [a for a in acct_names if _is_trad(a)]
    roth_accounts = [a for a in acct_names if _is_roth(a)]

    print("TRAD accounts:", trad_accounts)
    print("ROTH accounts:", roth_accounts)

    if not trad_accounts or not roth_accounts:
        print("Need at least one TRAD and one ROTH account for conversions; exiting.")
        return

    # Simple conversion policy for test:
    # - Use person_cfg["roth_conversion_policy"]["window_years"] if present,
    #   interpret ["now-75"] as current_age..75
    # - Convert a fixed 50k nominal per year from trad to roth (pro-rata across TRAD accounts)
    policy = person_cfg.get("roth_conversion_policy", {}) or {}
    current_age = float(person_cfg.get("current_age", 60.0))

    window_years = policy.get("window_years", [])
    window_end_age = None
    if isinstance(window_years, list) and window_years:
        token = str(window_years[0]).strip()
        if token.startswith("now-"):
            try:
                window_end_age = float(token.split("now-")[1])
            except Exception:
                window_end_age = None

    # If no usable window, just convert in all years for this test
    if window_end_age is None:
        window_start_y = 0
        window_end_y = YEARS
    else:
        window_start_y = 0  # "now" = current_year
        window_end_y = min(YEARS, int(window_end_age - current_age) + 1)

    print(f"Conversion window years (0-based index): [{window_start_y}, {window_end_y})")

    paths = acct_eoy_nom[trad_accounts[0]].shape[0]

    # Conversion income in nominal dollars (for now) per path/year
    conversion_nom_paths = np.zeros((paths, YEARS), dtype=float)

    # Fixed annual nominal conversion amount for this test
    annual_conv_nom = 50_000.0

    # Apply simple conversions year by year
    for y in range(window_start_y, window_end_y):
        # Total TRAD balance across all trad accounts at start of year y
        total_trad_bal_y = np.zeros(paths, dtype=float)
        for a in trad_accounts:
            bal = np.where(
                np.isfinite(acct_eoy_nom[a][:, y]),
                acct_eoy_nom[a][:, y],
                0.0,
            )
            total_trad_bal_y += bal

        # Conversion amount per path: up to annual_conv_nom, capped by total TRAD balance
        conv_amount_y = np.minimum(total_trad_bal_y, annual_conv_nom)

        if not np.any(conv_amount_y > 1e-12):
            continue

        # Pro-rata split of conversion across trad accounts based on their balances
        remaining_conv = conv_amount_y.copy()
        total_prior = total_trad_bal_y.copy()

        for a in trad_accounts:
            bal = np.where(
                np.isfinite(acct_eoy_nom[a][:, y]),
                acct_eoy_nom[a][:, y],
                0.0,
            )
            share = np.where(total_prior > 1e-12, bal / total_prior, 0.0)
            take = remaining_conv * share

            # Move from TRAD to ROTH
            acct_eoy_nom[a][:, y] = bal - take
            remaining_conv -= take

            # For simplicity, send all converted balance into the first ROTH account
            first_roth = roth_accounts[0]
            roth_bal = np.where(
                np.isfinite(acct_eoy_nom[first_roth][:, y]),
                acct_eoy_nom[first_roth][:, y],
                0.0,
            )
            acct_eoy_nom[first_roth][:, y] = roth_bal + take

        # Record conversion income (nominal) for year y
        conversion_nom_paths[:, y] = conv_amount_y

    # Summaries
    print("Conversion nominal mean per year (first 10 years):",
          conversion_nom_paths.mean(axis=0)[:10].tolist())

    for a in trad_accounts:
        print(f"TRAD {a} nominal end mean first 5 years:",
              acct_eoy_nom[a].mean(axis=0)[:5].tolist())

    for a in roth_accounts:
        print(f"ROTH {a} nominal end mean first 5 years:",
              acct_eoy_nom[a].mean(axis=0)[:5].tolist())


if __name__ == "__main__":
    main()

