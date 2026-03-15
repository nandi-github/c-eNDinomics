# filename: api_types.py

"""
Typed structures and constants used across the simulator stack.
Supports both legacy single-mix allocations and multi-portfolio allocations
(weight_pct, classes_pct), while keeping existing modules compatible.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

# -----------------------------
# Global configuration
# -----------------------------
# YEARS is a legacy default. All simulation code now receives n_years as a parameter.
# zeros_years() and zeros_paths_years() below are unused — kept for reference only.
YEARS: int = 30
DEFAULT_STEPS_PER_YEAR: int = 4
DEFAULT_PATHS: int = 2000

# Baseline inflation config
INFL_BASELINE_ANNUAL: float = 0.035
INFL_VOL_ANNUAL: float = 0.010
INFL_SHOCK_DOWN_PROB: float = 0.05
INFL_SHOCK_DOWN: float = -0.010
INFL_MAX: float = 0.08
INFL_MIN: float = -0.02

# Guardrails (engine defaults)
GUARDRAILS: Dict[str, Any] = {
    "dd_cut_thresholds": [(0.10, 0.95), (0.20, 0.85), (0.30, 0.70), (0.40, 0.60)],
    "restore_step": 0.05,
    "min_multiplier": 0.50,
    "recession_extra_cut": 0.90,
}

# Canonical asset classes (informational; simulator treats strings canonically)
CANONICAL_CLASSES: Tuple[str, ...] = (
    "US_STOCKS",
    "INTL_STOCKS",
    "LONG_TREAS",
    "INT_TREAS",
    "TIPS",
    "GOLD",
    "COMMOD",
    "OTHER",
)

# -----------------------------
# Tax configuration
# -----------------------------
@dataclass
class TaxBracket:
    up_to: Optional[float]  # None → no cap (top bracket)
    rate: float


@dataclass
class TaxCfg:
    filing_status: str
    state: str

    # Federal
    FED_ORD: List[Dict[str, float]]                  # ordinary brackets [{up_to, rate}, ...]
    FED_QUAL: List[Dict[str, float]]                 # qualified/LTCG brackets
    FED_STD_DED: float                               # standard deduction
    NIIT_RATE: float                                 # 3.8% typical
    NIIT_THRESH: float                               # threshold by filing status

    # State
    STATE_TYPE: str                                  # "none"|"flat"|"progressive"
    STATE_TREAT_QUAL_AS_ORD: bool
    STATE_ORD: List[Dict[str, float]]
    STATE_QUAL: List[Dict[str, float]]
    STATE_STD_DED: float
    STATE_CG_EXCISE: Optional[Dict[str, float]]      # e.g., {"rate": 0.07, "threshold": 250000}


# -----------------------------
# Accounts configuration
# -----------------------------
@dataclass
class AccountsCfg:
    accounts: Dict[str, str]              # name -> type ("taxable", "traditional_ira", "roth_ira")
    starting: Dict[str, float]            # initial balances (USD)
    deposits: Dict[str, np.ndarray]       # yearly deposits by account (shape: YEARS,)
    withdrawal_policy: Dict[str, Any] = field(default_factory=dict)  # optional policy knobs


# -----------------------------
# Allocation (legacy single-mix or multi-portfolio)
# -----------------------------
@dataclass
class HoldingPct:
    ticker: str
    pct: float  # 0..100 (remainder implicitly OTHER)


@dataclass
class PortfolioSpec:
    # Normalized weight in account (0..1); loaders compute from weight_pct.
    weight: float
    # Class weights in this portfolio (0..1), loaders compute from classes_pct.
    classes: Dict[str, float]
    # Per-class holdings specified as percentages (sum ≤ 100; remainder → OTHER).
    holdings_pct: Dict[str, List[HoldingPct]] = field(default_factory=dict)


@dataclass
class AllocYearForAccount:
    # name → portfolio spec
    portfolios: Dict[str, PortfolioSpec] = field(default_factory=dict)


@dataclass
class AllocAccounts:
    accounts: Dict[str, str]  # name -> type
    # Per account, list of per-year portfolio specs (length = YEARS).
    per_year_portfolios: Dict[str, List[AllocYearForAccount]] = field(default_factory=dict)
    # Optional warnings emitted during normalization/override application.
    warnings: List[str] = field(default_factory=list)


# -----------------------------
# Person configuration
# -----------------------------
@dataclass
class PersonCfg:
    current_age: float
    assumed_death_age: float
    filing_status: str
    spouse: Dict[str, Any]
    beneficiaries: Dict[str, Any]
    conversion_policy: Dict[str, Any]  # normalized from loaders.load_person


# -----------------------------
# Economic policy
# -----------------------------
@dataclass
class EconomicPolicy:
    # Per-year arrays (length = YEARS)
    bad_market_drawdown_threshold: np.ndarray         # float[YEARS]
    bad_market_use_recession: np.ndarray              # bool[YEARS]
    cash_reserve_months: np.ndarray                   # float[YEARS]
    cash_use_cash_only_in_bad: np.ndarray             # bool[YEARS]
    cash_allow_dip_below_reserve: np.ndarray          # bool[YEARS]

    reb_global_drift_threshold: np.ndarray            # float[YEARS]
    reb_require_cash_above_reserve: np.ndarray        # bool[YEARS]
    reb_suppress_in_bad_market: np.ndarray            # bool[YEARS]
    reb_brokerage_capgain_limit_k: np.ndarray         # float[YEARS]
    reb_brokerage_enabled: np.ndarray                 # bool[YEARS]

    # Withdraw sequencing (account-level and optional portfolio-level)
    order_good_market: List[List[str]]                # list per year
    order_bad_market: List[List[str]]                 # list per year
    order_good_market_portfolio: List[List[str]]      # optional (empty lists if unused)
    order_bad_market_portfolio: List[List[str]]       # optional

    wseq_tira_age_gate: np.ndarray                    # float[YEARS]
    wseq_roth_last_resort: np.ndarray                 # bool[YEARS]

    # Withdrawals shock-aware knobs
    w_drawdown_threshold: np.ndarray                  # float[YEARS]
    w_min_scaling_factor: np.ndarray                  # float[YEARS]
    w_scale_curve: np.ndarray                         # object[str][YEARS]
    w_scale_poly_alpha: np.ndarray                    # float[YEARS]
    w_scale_exp_lambda: np.ndarray                    # float[YEARS]
    w_use_recession_flag: np.ndarray                  # bool[YEARS]
    w_makeup_enabled: np.ndarray                      # bool[YEARS]
    w_makeup_ratio: np.ndarray                        # float[YEARS]
    w_makeup_cap_per_year: np.ndarray                 # float[YEARS]


# -----------------------------
# Shock configuration (optional)
# -----------------------------
@dataclass
class ShockEvent:
    clazz: str
    start_year: int
    start_quarter: int
    depth: float
    dip_quarters: int
    recovery_quarters: int
    override_mode: str
    recovery_to: str
    dip_profile: Dict[str, Any]
    rise_profile: Dict[str, Any]
    correlated_to: Optional[str] = None
    scale: Optional[float] = None
    coimpact_down: Optional[Dict[str, Any]] = None
    corecovery_up: Optional[Dict[str, Any]] = None


@dataclass
class ShocksCfg:
    mode: str  # "augment" | "override"
    events: List[ShockEvent]


# -----------------------------
# Simulation result (minimal typed view)
# -----------------------------
@dataclass
class SimResult:
    # Nominal yearly totals (paths × years)
    yearly_values: np.ndarray
    # Account-level EoY nominal paths (per account)
    acct_eoy_future_paths: Dict[str, np.ndarray] = field(default_factory=dict)
    # Portfolio-level EoY nominal paths (per account → portfolio)
    acct_portfolio_eoy_future_paths: Dict[str, Dict[str, np.ndarray]] = field(default_factory=dict)
    # Inflation yearly (if available) for downstream deflation
    inflation_yearly: List[float] = field(default_factory=list)
    # Summary metrics (success rate, drawdowns, etc.)
    summary: Dict[str, Any] = field(default_factory=dict)
    # Taxes breakdowns for reporting
    tax_fed_ord: np.ndarray = field(default_factory=lambda: np.zeros(YEARS, dtype=float))
    tax_state: np.ndarray = field(default_factory=lambda: np.zeros(YEARS, dtype=float))
    tax_niit: np.ndarray = field(default_factory=lambda: np.zeros(YEARS, dtype=float))


# -----------------------------
# Helpers to create zero arrays
# -----------------------------
def zeros_years() -> np.ndarray:
    return np.zeros(YEARS, dtype=float)


def zeros_paths_years(paths: int) -> np.ndarray:
    return np.zeros((paths, YEARS), dtype=float)

# --- End of file ---

