# filename: sim_rmd_birth_year_test.py
#
# Tests for SECURE 2.0 RMD start-age logic and birth_year wiring.
#
# Three test groups:
#   1. Unit: rmd_start_age() — all boundary conditions
#   2. Unit: build_rmd_factors() — correct first RMD year per birth year
#   3. Integration: run_accounts_new() with Test profile — RMD output reflects
#      birth_year=1971 (start age 75, first RMD at sim year 21)
#
# Run from the project src/ directory:
#   python3 sim_rmd_birth_year_test.py
#
# All assertions raise AssertionError with a descriptive message on failure.
# A final "ALL TESTS PASSED" confirms success.

import sys
import numpy as np

from rmd_core import rmd_start_age, build_rmd_factors
from loaders import (
    load_allocation_yearly_accounts,
    load_inflation_yearly,
    load_sched,
    load_person,
    load_income,
    load_tax_unified,
)
from income_core import build_income_streams
from simulator_new import run_accounts_new

YEARS = 30
TEST_PROFILE = "profiles/Test"


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def assert_eq(label, got, expected):
    assert got == expected, f"FAIL [{label}]: expected {expected!r}, got {got!r}"
    print(f"  OK  {label}")


def assert_close(label, got, expected, tol=0.01):
    assert abs(got - expected) <= tol, (
        f"FAIL [{label}]: expected ~{expected}, got {got}"
    )
    print(f"  OK  {label}  ({got})")


def assert_true(label, condition, detail=""):
    assert condition, f"FAIL [{label}]  {detail}"
    print(f"  OK  {label}")


def first_nonzero_year(factors):
    """Return 1-based sim year of first non-zero RMD factor, or None."""
    for y, f in enumerate(factors):
        if f > 0.0:
            return y + 1
    return None


# ---------------------------------------------------------------------------
# Group 1: rmd_start_age() boundary conditions  (pure unit, no I/O)
# ---------------------------------------------------------------------------

def test_rmd_start_age():
    print("\n=== Group 1: rmd_start_age() boundaries ===")
    assert_eq("born 1945 (pre-SECURE)",     rmd_start_age(1945), 70.5)
    assert_eq("born 1950 (boundary <= 1950)", rmd_start_age(1950), 70.5)
    assert_eq("born 1951 (SECURE Act)",      rmd_start_age(1951), 73.0)
    assert_eq("born 1959 (boundary <= 1959)", rmd_start_age(1959), 73.0)
    assert_eq("born 1960 (SECURE 2.0)",      rmd_start_age(1960), 75.0)
    assert_eq("born 1971 (Test profile)",    rmd_start_age(1971), 75.0)
    assert_eq("born 2000 (young owner)",     rmd_start_age(2000), 75.0)
    assert_eq("unknown — None",              rmd_start_age(None), 73.0)
    assert_eq("unknown — 0",                 rmd_start_age(0),    73.0)


# ---------------------------------------------------------------------------
# Group 2: build_rmd_factors() — correct first non-zero year per birth year
# ---------------------------------------------------------------------------

def test_build_rmd_factors():
    print("\n=== Group 2: build_rmd_factors() first RMD year ===")
    rmd_path = "rmd.json"  # system-level file at APP_ROOT, not per-profile

    # born 1971, current_age 55 → start_age 75 → first RMD sim year 21 (age 75)
    f71 = build_rmd_factors(rmd_path, owner_current_age=55.0,
                            years=YEARS, owner_birth_year=1971)
    assert_eq("born 1971 | first RMD sim year",        first_nonzero_year(f71), 21)
    assert_eq("born 1971 | years 1-20 all zero",       list(f71[:20]), [0.0] * 20)
    assert_close("born 1971 | factor at age 75 (yr 21)", f71[20], 24.6)

    # born 1955, current_age 55 → start_age 73 → first RMD sim year 19 (age 73)
    f55 = build_rmd_factors(rmd_path, owner_current_age=55.0,
                            years=YEARS, owner_birth_year=1955)
    assert_eq("born 1955 | first RMD sim year",        first_nonzero_year(f55), 19)
    assert_eq("born 1955 | years 1-18 all zero",       list(f55[:18]), [0.0] * 18)
    assert_close("born 1955 | factor at age 73 (yr 19)", f55[18], 26.5)

    # born 1948, current_age 55 → start_age 70.5 → gate opens at age 70.
    # BUT the IRS Uniform Lifetime Table starts at age 73 — there are no factors
    # for ages 70/71/72. So even though the gate passes at age 70, the first
    # non-zero factor is still at age 73 = sim year 19, same as born 1955.
    # The 70.5 gate only makes a difference if a custom rmd.json supplies
    # pre-73 legacy factors.
    f48 = build_rmd_factors(rmd_path, owner_current_age=55.0,
                            years=YEARS, owner_birth_year=1948)
    assert_eq("born 1948 | first non-zero factor (table starts at 73)", first_nonzero_year(f48), 19)

    # unknown birth year → defaults to 73 → same as born 1955 above
    f_unk = build_rmd_factors(rmd_path, owner_current_age=55.0,
                              years=YEARS, owner_birth_year=None)
    assert_eq("unknown birth year | defaults start age 73 | first RMD sim year",
              first_nonzero_year(f_unk), 19)

    # Regression: rmd.json flat-dict schema loaded correctly (not silently using built-in)
    # Built-in has age 80 = 20.3; profile rmd.json has 20.2 — catches schema B breakage
    age80_idx = 80 - 55  # zero-based index
    assert_close("rmd.json schema B: age 80 factor = 20.2 (not built-in 20.3)",
                 f71[age80_idx], 20.2, tol=0.05)


# ---------------------------------------------------------------------------
# Group 3: Integration — run_accounts_new with Test profile
# ---------------------------------------------------------------------------

def test_integration_rmd_start_year():
    print("\n=== Group 3: Integration — run_accounts_new RMD start year ===")

    alloc      = load_allocation_yearly_accounts(f"{TEST_PROFILE}/allocation_yearly.json")
    infl       = load_inflation_yearly(f"{TEST_PROFILE}/inflation_yearly.json", years_count=YEARS)
    sched, _   = load_sched(f"{TEST_PROFILE}/withdrawal_schedule.json")
    person_cfg = load_person(f"{TEST_PROFILE}/person.json")
    income_cfg = load_income(f"{TEST_PROFILE}/income.json")
    tax_cfg    = load_tax_unified(
        f"{TEST_PROFILE}/taxes_states_mfj_single.json", "California", "MFJ"
    )

    # Confirm loader correctly picked up birth_year from person.json
    assert_eq("person_cfg has birth_year=1971", person_cfg.get("birth_year"), 1971)

    # Build income paths
    paths = 200
    (w2, rental, interest, ord_other, qual_div, cap_gains) = build_income_streams(
        income_cfg, years=YEARS
    )
    ordinary_income_cur_paths = np.zeros((paths, YEARS), dtype=float)
    qual_div_cur_paths         = np.zeros((paths, YEARS), dtype=float)
    cap_gains_cur_paths        = np.zeros((paths, YEARS), dtype=float)
    ytd_income_nom_paths       = np.zeros((paths, YEARS), dtype=float)
    for y in range(YEARS):
        ordinary_income_cur_paths[:, y] = w2[y] + rental[y] + interest[y] + ord_other[y]
        qual_div_cur_paths[:, y]         = qual_div[y]
        cap_gains_cur_paths[:, y]        = cap_gains[y]
        ytd_income_nom_paths[:, y]       = ordinary_income_cur_paths[:, y]

    res = run_accounts_new(
        paths=paths,
        spy=2,
        infl_yearly=infl,
        alloc_accounts=alloc,
        assets_path="assets.json",
        sched=sched,
        apply_withdrawals=True,
        withdraw_sequence=None,
        tax_cfg=tax_cfg,
        ordinary_income_cur_paths=ordinary_income_cur_paths,
        qual_div_cur_paths=qual_div_cur_paths,
        cap_gains_cur_paths=cap_gains_cur_paths,
        ytd_income_nom_paths=ytd_income_nom_paths,
        person_cfg=person_cfg,
        rmd_table_path="rmd.json",  # system-level file at APP_ROOT
        rmds_enabled=True,
    )

    withdrawals      = res.get("withdrawals", {})
    rmd_future_mean  = np.array(withdrawals.get("rmd_future_mean",  []), dtype=float)
    rmd_current_mean = np.array(withdrawals.get("rmd_current_mean", []), dtype=float)

    assert_true("res has withdrawals.rmd_future_mean (length 30)",
                len(rmd_future_mean) == YEARS,
                f"got length {len(rmd_future_mean)}")

    # birth_year=1971 → start age 75 → sim years 1-20 must be zero
    zeros_before = rmd_future_mean[:20]
    assert_true(
        "RMD zero for sim years 1-20 (age 55-74, birth_year=1971)",
        np.all(zeros_before == 0.0),
        f"non-zero values: {zeros_before[zeros_before > 0]}",
    )

    # Sim year 21 (age 75) must be the first non-zero RMD
    assert_true(
        "RMD non-zero at sim year 21 (age 75, first RMD year)",
        rmd_future_mean[20] > 0.0,
        f"got {rmd_future_mean[20]}",
    )

    print(f"  INFO  RMD at sim year 21: "
          f"${rmd_future_mean[20]:,.0f} future  /  ${rmd_current_mean[20]:,.0f} current")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        test_rmd_start_age()
        test_build_rmd_factors()
        test_integration_rmd_start_year()
        print("\n✓ ALL TESTS PASSED")
    except AssertionError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)
