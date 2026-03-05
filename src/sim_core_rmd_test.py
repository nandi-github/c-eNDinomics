# filename: sim_core_rmd_test.py

from loaders import load_allocation_yearly_accounts, load_person
from simulation_core import simulate_balances
from rmd_core import build_rmd_factors, compute_rmd_schedule_nominal
import numpy as np

YEARS = 30


def main() -> None:
    alloc = load_allocation_yearly_accounts("profiles/Test/allocation_yearly.json")
    person_cfg = load_person("profiles/Test/person.json")

    owner_current_age = float(person_cfg.get("current_age", 60.0))

    rmd_factors = build_rmd_factors(
        rmd_table_path="profiles/Test/rmd.json",
        owner_current_age=owner_current_age,
        years=YEARS,
    )

    print("RMD factors first 10 years:", rmd_factors[:10])

    paths = 200
    spy = 2

    # Run the modular core to get account balances (no withdrawals, no shocks)
    acct_eoy_nom, total_nom_paths, total_real_paths = simulate_balances(
        paths=paths,
        years=YEARS,
        spy=spy,
        alloc_accounts=alloc,
        assets_path="assets.json",
        shocks_events=[],      # no shocks in this test
        shocks_mode="augment", # unused when events=[]
        infl_yearly=None,      # core uses baseline inflation if None
    )

    # Restrict to TRAD IRA accounts in Test profile
    trad_accounts = [name for name in acct_eoy_nom.keys() if "TRAD_IRA" in name or "TRAD-IRA" in name]
    if not trad_accounts:
        print("No TRAD IRA accounts found in Test profile; nothing to do.")
        return

    # Build RMD schedule for TRAD balances
    rmd_total_nom_paths, rmd_per_acct_nom = compute_rmd_schedule_nominal(
        trad_ira_balances_nom={acct: acct_eoy_nom[acct] for acct in trad_accounts},
        rmd_factors=rmd_factors,
    )

    # Convert nominal RMDs to current USD using a simple deflator = 1 (for now),
    # you can later plug in your real deflator if you want current dollars.
    rmd_total_cur_paths = rmd_total_nom_paths.copy()

    # Print summary stats
    print("RMD total nominal mean first 10 years:",
          rmd_total_nom_paths.mean(axis=0)[:10].tolist())

    for acct in trad_accounts:
        print(f"Account {acct} RMD nominal mean first 10 years:",
              rmd_per_acct_nom[acct].mean(axis=0)[:10].tolist())


if __name__ == "__main__":
    main()

