# filename: sim_core_withdrawals_test.py

from loaders import load_allocation_yearly_accounts, load_inflation_yearly, load_sched
from simulator_new import run_accounts_new
import numpy as np

YEARS = 30

def main():
    alloc = load_allocation_yearly_accounts("profiles/default/allocation_yearly.json")
    infl = load_inflation_yearly("profiles/default/inflation_yearly.json", years_count=YEARS)
    sched, floor_k = load_sched("profiles/default/withdrawal_schedule.json")

    res = run_accounts_new(
        paths=200,
        spy=2,
        infl_yearly=infl,
        alloc_accounts=alloc,
        assets_path="assets.json",
        sched=sched,
        apply_withdrawals=True,
        withdraw_sequence=None,  # default sequence
    )

    fut_mean = np.array(res["portfolio"]["future_mean"])
    print("Future mean first 5 with withdrawals:", fut_mean[:5])
    print("Future mean last 5 with withdrawals:", fut_mean[-5:])
    print("Nominal YoY (with withdrawals) first 5:",
          res["returns"]["nom_withdraw_yoy_mean_pct"][:5])

if __name__ == "__main__":
    main()

