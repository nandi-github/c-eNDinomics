"""
insights.py — eNDinomics Insights Engine
=========================================
Standalone module that analyses simulation results + profile/global config
and returns structured findings for display in the UI.

Architecture
------------
- Pure function: compute_insights(result, profile_cfg, global_cfg) -> InsightReport
- No simulator imports, no side effects, no I/O
- Each insight rule is a self-contained function: _rule_*(ctx) -> Insight | None
- InsightContext bundles pre-computed derived values so rules stay concise
- Rules are registered in RULES list — add/remove/reorder freely
- Future: chat endpoint can call ask_insights(report, question) -> str

Usage (from api.py)
-------------------
    from insights import compute_insights
    report = compute_insights(res, person_cfg, tax_cfg)
    # report.to_dict() goes into the API response as result["insights"]

Usage (standalone / testing)
-----------------------------
    python3 insights.py               # runs demo against Test profile snapshot
    python3 insights.py --json        # prints full JSON report
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Insight:
    """A single finding produced by a rule."""
    id:       str                       # unique snake_case identifier
    severity: str                       # "warn" | "tip" | "good" | "info"
    title:    str                       # short headline (shown even when collapsed)
    body:     str                       # 1-3 sentence explanation
    data:     Dict[str, Any] = field(default_factory=dict)  # machine-readable facts
    actions:  List[str]      = field(default_factory=list)   # suggested next steps

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InsightReport:
    """Full insights result attached to a simulation run."""
    insights:       List[Insight]
    rules_fired:    int
    rules_checked:  int
    engine_version: str = "1.0"

    def to_dict(self) -> dict:
        return {
            "insights":       [i.to_dict() for i in self.insights],
            "rules_fired":    self.rules_fired,
            "rules_checked":  self.rules_checked,
            "engine_version": self.engine_version,
        }


# ---------------------------------------------------------------------------
# Insight context — pre-computed derived values, shared across all rules
# ---------------------------------------------------------------------------

@dataclass
class InsightContext:
    """
    Pre-computed facts derived from result + config.
    Rules read from ctx instead of re-parsing raw dicts.
    """
    # Raw inputs
    result:      Dict[str, Any]
    profile_cfg: Dict[str, Any]   # person.json
    global_cfg:  Dict[str, Any]   # tax_cfg (FED_ORD, STATE_ORD, NIIT_THRESH, …)

    # Derived — populated by _build_context()
    years:          int   = 0
    rmd_start_idx:  int   = 20   # index of first RMD year (age 75 default)
    current_age:    int   = 55

    # Tax arrays (current USD, mean across paths)
    fed_yr:       List[float] = field(default_factory=list)
    state_yr:     List[float] = field(default_factory=list)
    niit_yr:      List[float] = field(default_factory=list)
    excise_yr:    List[float] = field(default_factory=list)
    total_tax_yr: List[float] = field(default_factory=list)

    # Withdrawal arrays
    planned_yr:    List[float] = field(default_factory=list)
    total_wd_yr:   List[float] = field(default_factory=list)
    rmd_yr:        List[float] = field(default_factory=list)
    reinvested_yr: List[float] = field(default_factory=list)

    # Conversion arrays
    conv_cur_yr:  List[float] = field(default_factory=list)
    conv_tax_yr:  List[float] = field(default_factory=list)

    # Effective rates
    eff_rate_pre:     List[float] = field(default_factory=list)  # pre-RMD years
    eff_rate_rmd:     List[float] = field(default_factory=list)  # RMD years
    mean_eff_pre:     float = 0.0
    mean_eff_rmd:     float = 0.0

    # Summary scalars
    total_fed_tax_30yr:   float = 0.0
    total_state_tax_30yr: float = 0.0
    total_niit_30yr:      float = 0.0
    total_conv_cur_30yr:  float = 0.0
    total_conv_tax_30yr:  float = 0.0
    success_rate:         float = 1.0

    # Account level balances (nom, mean) keyed by account name
    acct_levels: Dict[str, List[float]] = field(default_factory=dict)

    # Derived account groups
    brokerage_bal_yr: List[float] = field(default_factory=list)
    trad_bal_yr:      List[float] = field(default_factory=list)
    roth_bal_yr:      List[float] = field(default_factory=list)

    # Profile-derived policy flags
    conv_enabled:         bool  = False
    conv_bracket_fill:    bool  = False
    conv_window_end_age:  int   = 75
    avoid_niit:           bool  = True
    rmd_extra_handling:   str   = "reinvest_in_brokerage"


def _build_context(
    result: Dict[str, Any],
    profile_cfg: Dict[str, Any],
    global_cfg: Dict[str, Any],
) -> InsightContext:
    """Build a fully populated InsightContext from raw inputs."""

    ctx = InsightContext(result=result, profile_cfg=profile_cfg, global_cfg=global_cfg)

    W  = result.get("withdrawals", {}) or {}
    C  = result.get("conversions",  {}) or {}
    S  = result.get("summary",      {}) or {}
    AL = (result.get("returns_acct_levels", {}) or {}).get("inv_nom_levels_mean_acct", {}) or {}

    ctx.years = len(result.get("years", []) or [])
    ctx.acct_levels = {k: v for k, v in AL.items() if not k.endswith(("__inv_med", "__agg_nom", "__agg_real"))}

    # Person config
    ctx.current_age = int((profile_cfg or {}).get("current_age", 55))
    rmd_start_age   = int((profile_cfg or {}).get("rmd_start_age", 75))
    ctx.rmd_start_idx = max(0, rmd_start_age - ctx.current_age)

    # Tax arrays
    def _arr(d, key) -> List[float]:
        raw = d.get(key) or []
        return [float(v or 0) for v in raw]

    ctx.fed_yr       = _arr(W, "taxes_fed_current_mean")
    ctx.state_yr     = _arr(W, "taxes_state_current_mean")
    ctx.niit_yr      = _arr(W, "taxes_niit_current_mean")
    ctx.excise_yr    = _arr(W, "taxes_excise_current_mean")
    n = ctx.years or len(ctx.fed_yr)
    ctx.total_tax_yr = [
        (ctx.fed_yr[i] if i < len(ctx.fed_yr) else 0) +
        (ctx.state_yr[i] if i < len(ctx.state_yr) else 0) +
        (ctx.niit_yr[i] if i < len(ctx.niit_yr) else 0) +
        (ctx.excise_yr[i] if i < len(ctx.excise_yr) else 0)
        for i in range(n)
    ]

    # Withdrawal arrays
    ctx.planned_yr    = _arr(W, "planned_current")
    ctx.total_wd_yr   = _arr(W, "total_withdraw_current_mean")
    ctx.rmd_yr        = _arr(W, "rmd_current_mean")
    ctx.reinvested_yr = _arr(W, "rmd_extra_current")

    # Conversion arrays
    ctx.conv_cur_yr = _arr(C, "conversion_cur_mean_by_year")
    ctx.conv_tax_yr = _arr(C, "conversion_tax_cur_mean_by_year")

    # Effective rates per year
    for i in range(n):
        gross = ctx.total_wd_yr[i] if i < len(ctx.total_wd_yr) else 0
        if gross <= 0:
            gross = ctx.planned_yr[i] if i < len(ctx.planned_yr) else 0
        tax   = ctx.total_tax_yr[i] if i < len(ctx.total_tax_yr) else 0
        rate  = tax / gross * 100.0 if gross > 0 else 0.0
        if i < ctx.rmd_start_idx:
            ctx.eff_rate_pre.append(rate)
        else:
            ctx.eff_rate_rmd.append(rate)

    ctx.mean_eff_pre = _mean(ctx.eff_rate_pre)
    ctx.mean_eff_rmd = _mean(ctx.eff_rate_rmd)

    # Summary scalars
    ctx.total_fed_tax_30yr   = float(S.get("taxes_fed_total_current",   0) or 0)
    ctx.total_state_tax_30yr = float(S.get("taxes_state_total_current", 0) or 0)
    ctx.total_niit_30yr      = float(S.get("taxes_niit_total_current",  0) or 0)
    ctx.total_conv_cur_30yr  = float(C.get("total_converted_cur_mean",  0) or 0)
    ctx.total_conv_tax_30yr  = float(C.get("total_tax_cost_cur_mean",   0) or 0)
    ctx.success_rate         = float(S.get("success_rate", 1.0) or 1.0)

    # Account group balances (sum across same-type accounts, per year)
    ctx.brokerage_bal_yr = _sum_accounts(ctx.acct_levels, "BROKERAGE", n)
    ctx.trad_bal_yr      = _sum_accounts(ctx.acct_levels, "TRAD",      n)
    ctx.roth_bal_yr      = _sum_accounts(ctx.acct_levels, "ROTH",      n)

    # Policy flags from profile
    roth_policy = (profile_cfg or {}).get("roth_conversion_policy", {}) or {}
    ctx.conv_enabled      = bool(roth_policy.get("enabled", False))
    ctx.conv_bracket_fill = bool(roth_policy.get("keepit_below_max_marginal_fed_rate") is not None
                                  or roth_policy.get("bracket_fill", False))
    window_str = str(roth_policy.get("window", "now-75"))
    try:
        ctx.conv_window_end_age = int(window_str.split("-")[-1])
    except (ValueError, IndexError):
        ctx.conv_window_end_age = 75
    ctx.avoid_niit          = bool(roth_policy.get("avoid_niit", True))
    ctx.rmd_extra_handling  = str((profile_cfg or {}).get("rmd_extra_handling", "reinvest_in_brokerage"))

    return ctx


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _mean(lst: List[float]) -> float:
    return sum(lst) / len(lst) if lst else 0.0

def _fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.0f}k"
    return f"${v:.0f}"

def _sum_accounts(acct_levels: Dict[str, List[float]], prefix: str, n: int) -> List[float]:
    total = [0.0] * n
    for k, v in acct_levels.items():
        if k.startswith(prefix) and "__" not in k:
            for i in range(min(n, len(v))):
                total[i] += float(v[i] or 0)
    return total


# ---------------------------------------------------------------------------
# Rule functions — each returns Insight | None
# ---------------------------------------------------------------------------

def _rule_conv_underutilized(ctx: InsightContext) -> Optional[Insight]:
    """
    Fires when Roth conversion window has low effective rates but RMD years
    will face high rates — a missed optimization opportunity.
    """
    if not ctx.conv_enabled:
        return None
    if ctx.mean_eff_rmd < 35:
        return None     # RMD rate not particularly high — no urgency
    if ctx.mean_eff_pre >= 5:
        return None     # Pre-RMD rate already substantial — conversions working

    gap = ctx.mean_eff_rmd - ctx.mean_eff_pre
    trad_at_rmd = ctx.trad_bal_yr[ctx.rmd_start_idx] if ctx.rmd_start_idx < len(ctx.trad_bal_yr) else 0
    rmd_approx  = trad_at_rmd / 28.0  # IRS factor at age 75 ≈ 27.4

    return Insight(
        id="conv_underutilized",
        severity="warn",
        title="Roth conversion window may be underutilized",
        body=(
            f"Pre-RMD effective rate is {ctx.mean_eff_pre:.1f}% while RMD-era rate is "
            f"{ctx.mean_eff_rmd:.1f}% — a {gap:.0f}pp gap. "
            f"The current bracket-fill strategy converts conservatively, leaving a large "
            f"TRAD balance (~{_fmt_usd(trad_at_rmd)}) that will generate RMDs of roughly "
            f"{_fmt_usd(rmd_approx)}/yr. Converting more now at lower rates could "
            f"significantly reduce lifetime tax burden."
        ),
        data={
            "mean_eff_pre_pct":    round(ctx.mean_eff_pre, 1),
            "mean_eff_rmd_pct":    round(ctx.mean_eff_rmd, 1),
            "gap_pp":              round(gap, 1),
            "trad_at_rmd_start":   round(trad_at_rmd),
            "approx_rmd_yr1":      round(rmd_approx),
        },
        actions=[
            "Increase bracket-fill ceiling to 22% or 24% federal bracket",
            "Extend conversion window past age 75 (consult tax advisor)",
            "Model a fixed conversion amount in conversions.json",
        ],
    )


def _rule_rmd_cliff(ctx: InsightContext) -> Optional[Insight]:
    """
    Fires when TRAD balance at RMD start implies a large income cliff —
    RMD would be many multiples of the planned spending withdrawal.
    """
    idx = ctx.rmd_start_idx
    if idx >= len(ctx.trad_bal_yr):
        return None
    trad_at_rmd  = ctx.trad_bal_yr[idx]
    planned_at_rmd = ctx.planned_yr[idx] if idx < len(ctx.planned_yr) else 200_000
    if planned_at_rmd <= 0:
        return None
    approx_rmd = trad_at_rmd / 27.4   # IRS uniform lifetime factor at age 75
    ratio = approx_rmd / max(planned_at_rmd, 1)

    if ratio < 5:
        return None

    rmd_age = ctx.current_age + idx

    return Insight(
        id="rmd_cliff",
        severity="warn",
        title=f"Large RMD income spike expected at age {rmd_age}",
        body=(
            f"TRAD balance at RMD start (~{_fmt_usd(trad_at_rmd)}) implies an annual RMD of "
            f"~{_fmt_usd(approx_rmd)}, which is {ratio:.0f}× your planned {_fmt_usd(planned_at_rmd)} withdrawal. "
            f"This creates a sharp taxable income cliff, pushing well into the top federal bracket "
            f"and triggering NIIT. Reducing the TRAD balance through pre-RMD conversions is the "
            f"primary lever."
        ),
        data={
            "trad_at_rmd_start":    round(trad_at_rmd),
            "approx_rmd_yr1":       round(approx_rmd),
            "planned_withdrawal":   round(planned_at_rmd),
            "rmd_to_planned_ratio": round(ratio, 1),
            "rmd_start_age":        rmd_age,
        },
        actions=[
            "Increase Roth conversion amount during pre-RMD window",
            "Consider Qualified Charitable Distributions (QCDs) up to $105k/yr after age 70½",
            "Model rmd_extra_handling = cash_out vs reinvest to see tax impact",
        ],
    )


def _rule_brokerage_depletion(ctx: InsightContext) -> Optional[Insight]:
    """
    Fires when taxable brokerage balance hits zero early, shortening
    the 0% LTCG window and forcing early TRAD draws.
    """
    depletion_yr = None
    for i, bal in enumerate(ctx.brokerage_bal_yr):
        if i > 0 and i < ctx.rmd_start_idx and bal < 1_000:
            depletion_yr = i + 1   # 1-based year
            break
    if depletion_yr is None:
        return None

    depletion_age = ctx.current_age + depletion_yr - 1
    return Insight(
        id="brokerage_depletion",
        severity="warn",
        title=f"Taxable brokerage depletes at year {depletion_yr} (age {depletion_age})",
        body=(
            f"Mean brokerage balance drops near zero by year {depletion_yr}. "
            f"This collapses the 0% federal LTCG window prematurely and forces withdrawals "
            f"from TRAD accounts at ordinary income rates. The conversion tax debited from "
            f"the brokerage is also accelerating its depletion."
        ),
        data={
            "depletion_year":     depletion_yr,
            "depletion_age":      depletion_age,
        },
        actions=[
            "Reduce planned withdrawal spending in early years",
            "Add more to BROKERAGE (taxable) before retirement",
            "Reduce conversion size — less tax debit from brokerage",
        ],
    )


def _rule_roth_balance_low(ctx: InsightContext) -> Optional[Insight]:
    """
    Fires when ROTH ends up as a small fraction of total portfolio —
    missed opportunity for tax-free income and inheritance planning.
    """
    n = ctx.years
    if n == 0:
        return None
    roth_end   = ctx.roth_bal_yr[-1]   if ctx.roth_bal_yr   else 0.0
    trad_end   = ctx.trad_bal_yr[-1]   if ctx.trad_bal_yr   else 0.0
    brok_end   = ctx.brokerage_bal_yr[-1] if ctx.brokerage_bal_yr else 0.0
    total_end  = roth_end + trad_end + brok_end
    if total_end <= 0:
        return None
    roth_pct = roth_end / total_end * 100

    if roth_pct >= 15:
        return None

    return Insight(
        id="roth_balance_low",
        severity="tip",
        title=f"Roth balance is {roth_pct:.0f}% of total portfolio at year {n}",
        body=(
            f"ROTH accounts end at {_fmt_usd(roth_end)} ({roth_pct:.0f}% of {_fmt_usd(total_end)} total). "
            f"A larger Roth share provides tax-free income flexibility in late retirement, "
            f"avoids RMDs, and passes to heirs income-tax-free. "
            f"The pre-RMD window is the best time to shift more balance from TRAD to ROTH."
        ),
        data={
            "roth_end_balance":   round(roth_end),
            "total_end_balance":  round(total_end),
            "roth_end_pct":       round(roth_pct, 1),
        },
        actions=[
            "Increase conversion bracket ceiling from 10% to 22%",
            "Model a fixed conversion_amount_k in conversions.json",
        ],
    )


def _rule_niit_exposure(ctx: InsightContext) -> Optional[Insight]:
    """
    Fires when NIIT is non-zero — especially interesting when avoid_niit=True
    because it means income spikes are overriding the guard.
    """
    if ctx.total_niit_30yr <= 0:
        return None

    niit_pct_of_total = (
        ctx.total_niit_30yr /
        max(ctx.total_fed_tax_30yr + ctx.total_state_tax_30yr + ctx.total_niit_30yr, 1)
        * 100
    )

    avoid_str = "despite avoid_niit being enabled" if ctx.avoid_niit else "with avoid_niit disabled"

    return Insight(
        id="niit_exposure",
        severity="tip",
        title=f"NIIT exposure: {_fmt_usd(ctx.total_niit_30yr)} over 30 years",
        body=(
            f"3.8% Net Investment Income Tax totals {_fmt_usd(ctx.total_niit_30yr)} ({niit_pct_of_total:.0f}% of total taxes) "
            f"{avoid_str}. "
            f"In RMD years, large distributions push investment income well above the threshold. "
            f"Reducing TRAD balance through pre-RMD conversions is the most effective mitigation."
        ),
        data={
            "niit_total_30yr_cur":  round(ctx.total_niit_30yr),
            "niit_pct_of_total":    round(niit_pct_of_total, 1),
            "avoid_niit_flag":      ctx.avoid_niit,
        },
        actions=[
            "Reduce TRAD balance through more aggressive pre-RMD conversions",
            "Spread investment income across years where possible",
        ],
    )


def _rule_success_rate(ctx: InsightContext) -> Optional[Insight]:
    """
    Fires when success rate drops below 95% — portfolio may not last 30 years.
    """
    sr = ctx.success_rate
    if sr >= 0.95:
        return None
    return Insight(
        id="success_rate_low",
        severity="warn",
        title=f"Portfolio success rate is {sr*100:.0f}% (target ≥ 95%)",
        body=(
            f"{sr*100:.0f}% of Monte Carlo paths sustain the portfolio through year {ctx.years}. "
            f"A {100-sr*100:.0f}% shortfall probability is meaningful — consider reducing "
            f"planned spending, increasing equity allocation, or delaying retirement."
        ),
        data={
            "success_rate_pct": round(sr * 100, 1),
            "years":            ctx.years,
        },
        actions=[
            "Reduce planned withdrawal in economic.json or withdraw.json",
            "Review allocation — more equity improves long-run survival",
            "Run with shocks=none to see best-case baseline",
        ],
    )


def _rule_all_clear(ctx: InsightContext, any_fired: bool) -> Optional[Insight]:
    """Fires only when no other rule produced a warn-level finding."""
    if any_fired:
        return None
    return Insight(
        id="all_clear",
        severity="good",
        title="No significant issues detected",
        body=(
            "The simulation results look well-structured. Effective tax rates, RMD sizing, "
            "brokerage longevity, and account allocation all appear reasonable given the current profile."
        ),
        data={},
    )


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------
# Each entry: (rule_fn, needs_all_clear_flag)
# Add new rules here — order determines display order.

RULES = [
    _rule_success_rate,
    _rule_rmd_cliff,
    _rule_conv_underutilized,
    _rule_brokerage_depletion,
    _rule_roth_balance_low,
    _rule_niit_exposure,
]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_insights(
    result:      Dict[str, Any],
    profile_cfg: Dict[str, Any],
    global_cfg:  Dict[str, Any],
) -> InsightReport:
    """
    Analyse simulation result + config and return a structured InsightReport.

    Parameters
    ----------
    result      : full dict returned by run_accounts_new()
    profile_cfg : person.json dict (loaded by load_person())
    global_cfg  : tax_cfg dict (built by build_tax_cfg() in api.py)

    Returns
    -------
    InsightReport — call .to_dict() to embed in the API response
    """
    ctx = _build_context(result, profile_cfg or {}, global_cfg or {})

    insights: List[Insight] = []
    for rule_fn in RULES:
        try:
            ins = rule_fn(ctx)
            if ins is not None:
                insights.append(ins)
        except Exception as exc:
            # Never let an insight rule crash the API response
            insights.append(Insight(
                id=f"rule_error_{rule_fn.__name__}",
                severity="info",
                title=f"Insight rule failed: {rule_fn.__name__}",
                body=str(exc),
            ))

    # All-clear fires only if no warn/tip insights
    any_actionable = any(i.severity in ("warn", "tip") for i in insights)
    clear = _rule_all_clear(ctx, any_actionable)
    if clear:
        insights.append(clear)

    return InsightReport(
        insights=insights,
        rules_fired=len(insights),
        rules_checked=len(RULES) + 1,   # +1 for all_clear
    )


# ---------------------------------------------------------------------------
# Chat stub — future interactive layer
# ---------------------------------------------------------------------------

def ask_insights(report: InsightReport, question: str, llm_backend: Any = None) -> str:
    """
    Future: answer a user question about the insights using an LLM.

    Parameters
    ----------
    report      : InsightReport from compute_insights()
    question    : free-text question from the user
    llm_backend : pluggable backend (Anthropic API, local model, etc.)

    Returns
    -------
    str — natural language answer

    Notes
    -----
    This is a stub. The report.to_dict() is the context that will be
    injected into the system prompt. Each insight's data dict provides
    the precise numbers to ground the answer.
    """
    # Stub: return a canned response until the LLM backend is wired in
    findings = [f"- [{i.severity.upper()}] {i.title}" for i in report.insights]
    return (
        f"I found {len(report.insights)} insight(s) in this run:\n"
        + "\n".join(findings)
        + f"\n\nYou asked: '{question}'\n"
        + "(Chat integration coming soon — LLM backend not yet wired.)"
    )


# ---------------------------------------------------------------------------
# Standalone demo / test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    # Try to load a real snapshot from the latest test run
    test_dir = os.path.join(os.path.dirname(__file__), "testresults")
    snapshot_file = None
    if os.path.isdir(test_dir):
        jsons = sorted(
            [f for f in os.listdir(test_dir) if f.endswith(".json")],
            reverse=True,
        )
        if jsons:
            snapshot_file = os.path.join(test_dir, jsons[0])

    if snapshot_file and os.path.isfile(snapshot_file):
        print(f"[insights demo] Loading snapshot: {snapshot_file}")
        with open(snapshot_file) as f:
            raw = json.load(f)
        # test_comprehensive JSON is a test report, not a sim snapshot
        # Fall through to demo data
        result = {}
    else:
        result = {}

    # Demo with synthetic data matching Test profile characteristics
    if not result:
        print("[insights demo] Using synthetic Test-profile data")
        years = list(range(1, 31))
        fed  = [0.0]*20 + [2_273_826, 2_728_443, 3_334_875, 3_965_394, 5_186_007,
                           6_300_416, 7_565_245, 10_541_395, 12_791_880, 16_026_793]
        stat = [542, 507, 529, 477, 458, 419, 363, 350, 337, 324,
                364, 339, 324, 329, 315, 292, 282, 291, 278, 278,
                749_856, 901_293, 1_102_658, 1_311_932, 1_717_418,
                2_087_528, 2_507_879, 3_496_868, 4_244_895, 5_320_109]
        niit = [0.0]*20 + [240_233, 286_684, 349_314, 414_191, 539_748,
                           654_204, 784_129, 1_089_908, 1_321_164, 1_653_387]
        planned = [150_000]*5 + [200_000]*25
        rmd     = [0.0]*20 + [6_124_559, 7_592_804, 9_233_901, 10_940_889, 14_242_069,
                              17_254_613, 20_674_025, 28_719_238, 34_802_651, 43_546_484]
        total_wd = planned[:20] + rmd[20:]
        conv_cur = [23_850]*20 + [0.0]*10
        conv_tax = [2_667]*20  + [0.0]*10

        brok_bal = [417_652, 378_000, 342_000, 308_000, 276_000,
                    310_000, 280_000, 253_000, 228_000, 205_000,
                    184_000, 165_000, 148_000, 133_000, 119_000,
                    107_000,  96_000,  86_000,  77_000,  69_000,
                    2_500_000, 3_200_000, 4_100_000, 5_200_000, 6_600_000,
                    8_300_000, 10_500_000, 13_000_000, 16_500_000, 21_000_000]
        trad_bal = [4_800_000 + i*240_000 for i in range(20)] + \
                   [max(0, 4_800_000 + 20*240_000 - i*5_500_000) for i in range(10)]
        roth_bal = [370_000 + i*23_000 for i in range(30)]

        acct_levels = {
            "BROKERAGE-1":  brok_bal,
            "TRAD_IRA-1":   trad_bal,
            "ROTH_IRA-1":   roth_bal,
        }

        result = {
            "years": years,
            "withdrawals": {
                "taxes_fed_current_mean":   fed,
                "taxes_state_current_mean": stat,
                "taxes_niit_current_mean":  niit,
                "taxes_excise_current_mean": [0.0]*30,
                "planned_current":          planned,
                "total_withdraw_current_mean": total_wd,
                "rmd_current_mean":         rmd,
                "rmd_extra_current":        [max(0, r - p) for r, p in zip(rmd, planned)],
            },
            "conversions": {
                "conversion_cur_mean_by_year":     conv_cur,
                "conversion_tax_cur_mean_by_year": conv_tax,
                "total_converted_cur_mean":        sum(conv_cur),
                "total_tax_cost_cur_mean":         sum(conv_tax),
            },
            "summary": {
                "success_rate":              0.97,
                "taxes_fed_total_current":   sum(fed),
                "taxes_state_total_current": sum(stat),
                "taxes_niit_total_current":  sum(niit),
            },
            "returns_acct_levels": {
                "inv_nom_levels_mean_acct": acct_levels,
            },
        }

    profile_cfg = {
        "current_age": 55,
        "rmd_start_age": 75,
        "roth_conversion_policy": {
            "enabled": True,
            "keepit_below_max_marginal_fed_rate": "fill the bracket",
            "window": "now-75",
            "avoid_niit": True,
        },
        "rmd_extra_handling": "reinvest_in_brokerage",
    }

    report = compute_insights(result, profile_cfg, global_cfg={})

    if "--json" in sys.argv:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"\n{'='*64}")
        print(f"  eNDinomics Insights Demo  |  {report.rules_fired} findings")
        print(f"{'='*64}\n")
        for ins in report.insights:
            icon = {"warn": "⚠️ ", "tip": "💡", "good": "✅", "info": "ℹ️ "}.get(ins.severity, "  ")
            print(f"{icon}  [{ins.severity.upper()}] {ins.title}")
            print(f"    {ins.body[:120]}{'...' if len(ins.body) > 120 else ''}")
            if ins.actions:
                print(f"    → {ins.actions[0]}")
            print()

        # Demo chat stub
        print(f"{'─'*64}")
        print("Chat stub demo:")
        print(ask_insights(report, "Why is my effective rate so high in RMD years?"))
