# filename: sim_core_test.py

from loaders import load_allocation_yearly_accounts, load_inflation_yearly
from simulation_core import simulate_balances
import numpy as np

YEARS = 30


def pct_change_paths(series_2d: np.ndarray) -> np.ndarray:
    """
    Compute per-path year-over-year returns as FRACTIONS:
    r[:, y] = series[:, y] / series[:, y-1] - 1
    r[:, 0] = 0.
    """
    s = np.asarray(series_2d, dtype=float)
    if s.ndim != 2:
        s = s.reshape(s.shape[0], -1)
    P, Y = s.shape
    r = np.zeros_like(s)
    if Y < 2:
        return r
    prev = np.maximum(s[:, :-1], 1e-12)
    r[:, 1:] = (s[:, 1:] / prev - 1.0)
    return r


def main() -> None:
    # Load profile config (same as app)
    alloc = load_allocation_yearly_accounts("profiles/default/allocation_yearly.json")
    infl = load_inflation_yearly("profiles/default/inflation_yearly.json", years_count=YEARS)

    paths = 200
    spy = 2

    # Core Monte Carlo: no shocks
    acct_eoy_nom, total_nom_paths, total_real_paths = simulate_balances(
        paths=paths,
        years=YEARS,
        spy=spy,
        alloc_accounts=alloc,
        #assets_path="assets.json",
	assets_path = "assets.json"  ,

        shocks_events=[],          # no shocks
        shocks_mode="augment",     # mode unused when events=[]
        infl_yearly=infl,
    )

    # Portfolio-level Future mean / Current mean
    fut_mean = total_nom_paths.mean(axis=0)
    cur_mean = total_real_paths.mean(axis=0)

    print("Core Future mean first 5:", fut_mean[:5])
    print("Core Future mean last 5:", fut_mean[-5:])
    print("Core Current mean first 5:", cur_mean[:5])
    print("Core Current mean last 5:", cur_mean[-5:])

    # Investment nominal YoY (same convention as app: fraction * 100)
    inv_nom_yoy_paths = pct_change_paths(total_nom_paths)
    inv_nom_yoy_mean_pct = inv_nom_yoy_paths.mean(axis=0) * 100.0
    print("Core nominal YoY first 5:", inv_nom_yoy_mean_pct[:5].tolist())

    # Investment real YoY
    inv_real_yoy_paths = pct_change_paths(total_real_paths)
    inv_real_yoy_mean_pct = inv_real_yoy_paths.mean(axis=0) * 100.0
    print("Core real YoY first 5:", inv_real_yoy_mean_pct[:5].tolist())


if __name__ == "__main__":
    main()

