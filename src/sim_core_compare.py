# filename: sim_core_compare.py

from loaders import load_allocation_yearly_accounts, load_inflation_yearly
from simulation_core import simulate_balances

YEARS = 30

def main():
    alloc = load_allocation_yearly_accounts("profiles/default/allocation_yearly.json")
    infl = load_inflation_yearly("profiles/default/inflation_yearly.json", years_count=YEARS)

    paths = 200
    spy = 2

    acct_eoy_nom, total_nom_paths, total_real_paths = simulate_balances(
        paths=paths,
        years=YEARS,
        spy=spy,
        alloc_accounts=alloc,
        assets_path="assets.json",
        shocks_events=[],      # shocks=none
        shocks_mode="augment", # mode unused when events=[]
        infl_yearly=infl,
    )

    # Core nominal path: mean over paths
    fut_mean_core = total_nom_paths.mean(axis=0)
    print("Core Future mean first 5:", fut_mean_core[:5])
    print("Core Future mean last 5:", fut_mean_core[-5:])

    # Simple nominal YoY from core (percent)
    prev = fut_mean_core[:-1]
    curr = fut_mean_core[1:]
    yoy_core = (curr / prev - 1.0) * 100.0
    print("Core nominal YoY first 5:", [0.0] + yoy_core[:4].tolist())

if __name__ == "__main__":
    main()

