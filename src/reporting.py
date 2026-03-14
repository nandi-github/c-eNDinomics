# filename: reporting.py

import os
from typing import Any, Dict, Optional, List
import numpy as np

# Non-GUI backend for CLI runs
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt

INFL_BASELINE_ANNUAL = 0.035


def _fmt_row(cols, widths, seps="  "):
    out = []
    for i, c in enumerate(cols):
        w = widths[i] if i < len(widths) else 12
        s = f"{c}"
        is_num_like = isinstance(c, (int, float)) or (
            isinstance(c, str)
            and (s.strip().startswith(("$", "-")) or any(ch.isdigit() for ch in s))
        )
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


def _save_csv(path: str, headers: List[str], rows: List[List[Any]]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(",".join(headers) + "\n")
            for r in rows:
                f.write(",".join(str(x) for x in r) + "\n")
    except Exception as e:
        print(f"[WARN] Failed to save CSV {path}: {e}")


def _plot_lines(out_path, years, series_dict, title, ylabel):
    try:
        fig = plt.figure(figsize=(9, 4.5))
        for label, arr in series_dict.items():
            a = np.asarray(arr, dtype=float).reshape(-1)
            if a.size != len(years):
                print(
                    f"[DEBUG] _plot_lines '{title}' skipping series '{label}' "
                    f"due to length mismatch: years={len(years)} vs series={a.size}"
                )
                continue
            plt.plot(years, a, label=label)
        plt.title(title)
        plt.xlabel("Year")
        plt.ylabel(ylabel)
        plt.grid(True, alpha=0.25)
        plt.legend(loc="best", fontsize=9)
        plt.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        print(f"[DEBUG] Saved plot '{title}' to {out_path}")
    except Exception as e:
        print(f"[WARN] Failed to plot '{title}' to {out_path}: {e}")


def _plot_aggregate_band(
    out_path: str,
    years: List[int],
    mean: List[float],
    median: List[float],
    p10: List[float],
    p90: List[float],
    title: str,
    ylabel: str = "USD",
):
    """
    Plot one aggregate:
      - X: years
      - mean & median lines
      - green shaded band P10–P90
      - pink lines at P10 and P90
    """
    try:
        y = np.asarray(years, dtype=float)
        m = np.asarray(mean, dtype=float)
        med = np.asarray(median, dtype=float)
        lo = np.asarray(p10, dtype=float)
        hi = np.asarray(p90, dtype=float)

        if not (len(y) == len(m) == len(med) == len(lo) == len(hi)):
            print(
                "[WARN] _plot_aggregate_band length mismatch:",
                len(y), len(m), len(med), len(lo), len(hi),
            )
            return

        fig, ax = plt.subplots(figsize=(9, 4.5))

        # Shaded band P10–P90
        ax.fill_between(
            y,
            lo,
            hi,
            color="green",
            alpha=0.15,
            label="P10–P90 band",
        )
        # Pink lines at P10 and P90
        ax.plot(y, lo, color="pink", alpha=0.6, linewidth=1, label="P10")
        ax.plot(y, hi, color="pink", alpha=0.6, linewidth=1, label="P90")

        # Mean & median lines
        ax.plot(y, m, color="blue", linewidth=2, label="Mean")
        ax.plot(y, med, color="orange", linewidth=2, label="Median")

        ax.set_title(title)
        ax.set_xlabel("Year")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        print(f"[DEBUG] Saved aggregate band plot '{title}' to {out_path}")
    except Exception as e:
        print(f"[WARN] Failed to plot aggregate band '{title}' to {out_path}: {e}")


def compute_account_ending_balances(
    inv_nom_levels_mean_acct: Dict[str, List[Any]],
    inv_real_levels_mean_acct: Dict[str, List[Any]],
    inv_nom_levels_med_acct: Optional[Dict[str, List[Any]]] = None,
    inv_real_levels_med_acct: Optional[Dict[str, List[Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Compute ending (final-year) balances per account in both Future (nominal)
    and Current (real) dollars — median (primary) and mean (secondary).
    """
    accounts = sorted(inv_nom_levels_mean_acct.keys())
    med_nom = inv_nom_levels_med_acct or {}
    med_real = inv_real_levels_med_acct or {}
    out: List[Dict[str, Any]] = []
    for acct in accounts:
        fn_mean = inv_nom_levels_mean_acct.get(acct, []) or []
        cr_mean = inv_real_levels_mean_acct.get(acct, []) or []
        fn_med  = med_nom.get(acct, []) or []
        cr_med  = med_real.get(acct, []) or []
        out.append({
            "account":              acct,
            "ending_future_mean":   float(fn_mean[-1]) if fn_mean else 0.0,
            "ending_current_mean":  float(cr_mean[-1]) if cr_mean else 0.0,
            "ending_future_median": float(fn_med[-1])  if fn_med  else float(fn_mean[-1]) if fn_mean else 0.0,
            "ending_current_median":float(cr_med[-1])  if cr_med  else float(cr_mean[-1]) if cr_mean else 0.0,
        })
    return out

def report_and_plot_accounts(
    res: Dict[str, Any],
    args: Any,
    out_dir: str,
    alloc_accounts: Dict[str, Any],
    tax_cfg: Dict[str, Any],
    person_cfg: Dict[str, Any],
    benchmarks_path: Optional[str] = None,
):
    # High-level debug on input result structure
    print("\n[DEBUG] report_and_plot_accounts: start")
    print("[DEBUG] res top-level keys:", list(res.keys()))
    meta = res.get("meta", {}) or {}
    if isinstance(meta, dict):
        print("[DEBUG] meta keys:", list(meta.keys()))
        if "success" in meta:
            print("[DEBUG] meta['success']:", meta.get("success"))

    years = res.get("portfolio", {}).get("years", list(range(1, 31)))
    print("[DEBUG] years len:", len(years))
    if years:
        print("[DEBUG] years[0:5]:", years[:5])

    # Portfolio totals
    P = res.get("portfolio", {}) or {}
    print("[DEBUG] portfolio keys:", list(P.keys()))
    fut_mean = P.get("future_mean", [])
    fut_med = P.get("future_median", [])
    fut_p10 = P.get("future_p10_mean", [])
    fut_p90 = P.get("future_p90_mean", [])
    cur_mean = P.get("current_mean", [])
    cur_med = P.get("current_median", [])
    cur_p10 = P.get("current_p10_mean", [])
    cur_p90 = P.get("current_p90_mean", [])

    # Withdrawals and taxes
    W = res.get("withdrawals", {}) or {}
    print("[DEBUG] withdrawals dict keys:", list(W.keys()))
    print("[DEBUG] planned_current sample:", W.get("planned_current", [])[:5])
    print(
        "[DEBUG] realized_current_mean sample:",
        W.get("realized_current_mean", [])[:5],
    )
    print(
        "[DEBUG] realized_future_mean sample:",
        W.get("realized_future_mean", [])[:5],
    )
    print(
        "[DEBUG] shortfall_current_mean sample:",
        W.get("shortfall_current_mean", [])[:5],
    )

    wPlan = W.get("planned_current", [])
    wRealCur = W.get("realized_current_mean", [])
    wRealFut = W.get("realized_future_mean", [])
    wShort = W.get("shortfall_current_mean", [])

    # Phase 2 tax components (optional)
    txFed = W.get("taxes_fed_current_mean", [])
    txState = W.get("taxes_state_current_mean", [])
    txNIIT = W.get("taxes_niit_current_mean", [])
    txExc = W.get("taxes_excise_current_mean", [])
    txShort = W.get("tax_shortfall_current_mean", [])
    gains = W.get("realized_gains_current_mean", [])

    print(
        "[DEBUG] taxes samples:",
        "Fed:", txFed[:3],
        "State:", txState[:3],
        "NIIT:", txNIIT[:3],
        "Excise:", txExc[:3],
        "TaxShort:", txShort[:3],
        "Gains:", gains[:3],
    )

    # Phase 3 RMD metrics (optional)
    rmdMean = W.get("rmd_current_mean", [])
    rmdTxFed = W.get("rmd_taxes_fed_current_mean", [])
    rmdTxState = W.get("rmd_taxes_state_current_mean", [])
    rmdTxNIIT = W.get("rmd_taxes_niit_current_mean", [])
    rmdShort = W.get("rmd_shortfall_current_mean", [])

    print(
        "[DEBUG] RMD samples:",
        "RMD:", rmdMean[:3],
        "RMD Fed:", rmdTxFed[:3],
        "RMD State:", rmdTxState[:3],
        "RMD NIIT:", rmdTxNIIT[:3],
        "RMD Short:", rmdShort[:3],
    )

    # Returns series
    R = res.get("returns", {}) or {}
    print("[DEBUG] returns keys:", list(R.keys()))
    nomWithW = R.get("nom_withdraw_yoy_mean_pct", [])
    realWithW = R.get("real_withdraw_yoy_mean_pct", [])
    invNom = R.get("inv_nom_yoy_mean_pct", [])
    invReal = R.get("inv_real_yoy_mean_pct", [])
    print(
        "[DEBUG] returns samples:",
        "nom_withdraw:", nomWithW[:3],
        "real_withdraw:", realWithW[:3],
        "inv_nom:", invNom[:3],
        "inv_real:", invReal[:3],
    )

    # ... keep the rest of your existing reporting.py from here down unchanged ...


    # Console tables: Total Portfolio (Future USD)
    header_future = [
        "Year",
        "Future mean",
        "Current mean",
        "Future Median",
        "Future P10",
        "Future P90",
        "YoY Future Nominal (w/withdrawals)",
        "YoY Future Real (w/withdrawals)",
        "YoY Future Nominal Investment",
        "YoY Future Real Investment",
    ]
    rows_future = []
    for i, y in enumerate(years):
        rows_future.append(
            [
                int(y),
                int(fut_mean[i]) if i < len(fut_mean) else "",
                int(cur_mean[i]) if i < len(cur_mean) else "",
                int(fut_med[i]) if i < len(fut_med) else "",
                int(fut_p10[i]) if i < len(fut_p10) else "",
                int(fut_p90[i]) if i < len(fut_p90) else "",
                f"{float(nomWithW[i]):.2f}%" if i < len(nomWithW) else "",
                f"{float(realWithW[i]):.2f}%" if i < len(realWithW) else "",
                f"{float(invNom[i]):.2f}%" if i < len(invNom) else "",
                f"{float(invReal[i]):.2f}%" if i < len(invReal) else "",
            ]
        )
    _print_table(header_future, rows_future, title="Total Portfolio (Future USD)")

    # Console tables: Total Portfolio (Current USD)
    header_current = [
        "Year",
        "Current mean",
        "Future mean",
        "Current Median",
        "Current P10",
        "Current P90",
        "YoY Current Nominal (w/withdrawals)",
        "YoY Current Real (w/withdrawals)",
        "YoY Current Nominal Investment",
        "YoY Current Real Investment",
    ]
    rows_current = []
    for i, y in enumerate(years):
        rows_current.append(
            [
                int(y),
                int(cur_mean[i]) if i < len(cur_mean) else "",
                int(fut_mean[i]) if i < len(fut_mean) else "",
                int(cur_med[i]) if i < len(cur_med) else "",
                int(cur_p10[i]) if i < len(cur_p10) else "",
                int(cur_p90[i]) if i < len(cur_p90) else "",
                f"{float(nomWithW[i]):.2f}%" if i < len(nomWithW) else "",
                f"{float(realWithW[i]):.2f}%" if i < len(realWithW) else "",
                f"{float(invNom[i]):.2f}%" if i < len(invNom) else "",
                f"{float(invReal[i]):.2f}%" if i < len(invReal) else "",
            ]
        )
    _print_table(header_current, rows_current, title="Total Portfolio (Current USD)")

    # Save totals CSVs
    _save_csv(
        os.path.join(out_dir, "totals_future.csv"),
        [
            "Year",
            "FutureMean",
            "CurrentMean",
            "FutureMedian",
            "FutureP10",
            "FutureP90",
            "YoYNomWithW",
            "YoYRealWithW",
            "YoYInvNom",
            "YoYInvReal",
        ],
        rows_future,
    )
    _save_csv(
        os.path.join(out_dir, "totals_current.csv"),
        [
            "Year",
            "CurrentMean",
            "FutureMean",
            "CurrentMedian",
            "CurrentP10",
            "CurrentP90",
            "YoYNomWithW",
            "YoYRealWithW",
            "YoYInvNom",
            "YoYInvReal",
        ],
        rows_current,
    )

    # Plots: Portfolio
    _plot_lines(
        os.path.join(out_dir, "portfolio_future_summary.png"),
        years,
        {
            "Future mean": fut_mean,
            "Future median": fut_med,
            "Future p10": fut_p10,
            "Future p90": fut_p90,
        },
        "Portfolio summary (Future USD)",
        "USD",
    )
    _plot_lines(
        os.path.join(out_dir, "portfolio_current_summary.png"),
        years,
        {
            "Current mean": cur_mean,
            "Current median": cur_med,
            "Current p10": cur_p10,
            "Current p90": cur_p90,
        },
        "Portfolio summary (Current USD)",
        "USD",
    )

    # Accounts — Investment YoY
    RA = res.get("returns_acct", {}) or {}
    RL = res.get("returns_acct_levels", {}) or {}
    inv_nom_yoy_mean_pct_acct = RA.get("inv_nom_yoy_mean_pct_acct", {}) or {}
    inv_real_yoy_mean_pct_acct = RA.get("inv_real_yoy_mean_pct_acct", {}) or {}
    inv_nom_levels_mean_acct = RL.get("inv_nom_levels_mean_acct", {}) or {}
    inv_nom_levels_med_acct = RL.get("inv_nom_levels_med_acct", {}) or {}
    inv_nom_levels_p10_acct = RL.get("inv_nom_levels_p10_acct", {}) or {}
    inv_nom_levels_p90_acct = RL.get("inv_nom_levels_p90_acct", {}) or {}
    inv_real_levels_mean_acct = RL.get("inv_real_levels_mean_acct", {}) or {}
    inv_real_levels_med_acct = RL.get("inv_real_levels_med_acct", {}) or {}
    inv_real_levels_p10_acct = RL.get("inv_real_levels_p10_acct", {}) or {}
    inv_real_levels_p90_acct = RL.get("inv_real_levels_p90_acct", {}) or {}

    accounts = sorted(list(inv_nom_yoy_mean_pct_acct.keys()))

    # Accounts — Investment YoY (Future USD)
    header_acct_future = ["Year"]
    for acct in accounts:
        header_acct_future += [
            f"{acct} $Future(mean)",
            f"{acct} $Future(median)",
            f"{acct} $Future(p10)",
            f"{acct} $Future(p90)",
            f"{acct} NominalYoY(mean)",
            f"{acct} RealYoY(mean)",
        ]
    rows_acct_future = []
    for i, y in enumerate(years):
        row = [int(y)]
        for acct in accounts:
            fn_mean = inv_nom_levels_mean_acct.get(acct, [])
            fn_med = inv_nom_levels_med_acct.get(acct, [])
            fn_p10 = inv_nom_levels_p10_acct.get(acct, [])
            fn_p90 = inv_nom_levels_p90_acct.get(acct, [])
            yo_nom = inv_nom_yoy_mean_pct_acct.get(acct, [])
            yo_real = inv_real_yoy_mean_pct_acct.get(acct, [])
            row += [
                int(fn_mean[i]) if i < len(fn_mean) else "",
                int(fn_med[i]) if i < len(fn_med) else "",
                int(fn_p10[i]) if i < len(fn_p10) else "",
                int(fn_p90[i]) if i < len(fn_p90) else "",
                f"{float(yo_nom[i]):.2f}%" if i < len(yo_nom) else "",
                f"{float(yo_real[i]):.2f}%" if i < len(yo_real) else "",
            ]
        rows_acct_future.append(row)
    _print_table(
        header_acct_future,
        rows_acct_future,
        title="Accounts — Investment YoY (Future USD)",
    )
    _save_csv(
        os.path.join(out_dir, "accounts_future_investment_yoy.csv"),
        header_acct_future,
        rows_acct_future,
    )

    # Accounts — Investment YoY (Current USD)
    header_acct_current = ["Year"]
    for acct in accounts:
        header_acct_current += [
            f"{acct} $Current(mean)",
            f"{acct} $Current(median)",
            f"{acct} $Current(p10)",
            f"{acct} $Current(p90)",
            f"{acct} NominalYoY(mean)",
            f"{acct} RealYoY(mean)",
        ]
    rows_acct_current = []
    for i, y in enumerate(years):
        row = [int(y)]
        for acct in accounts:
            cr_mean = inv_real_levels_mean_acct.get(acct, [])
            cr_med = inv_real_levels_med_acct.get(acct, [])
            cr_p10 = inv_real_levels_p10_acct.get(acct, [])
            cr_p90 = inv_real_levels_p90_acct.get(acct, [])
            yo_nom = inv_nom_yoy_mean_pct_acct.get(acct, [])
            yo_real = inv_real_yoy_mean_pct_acct.get(acct, [])
            row += [
                int(cr_mean[i]) if i < len(cr_mean) else "",
                int(cr_med[i]) if i < len(cr_med) else "",
                int(cr_p10[i]) if i < len(cr_p10) else "",
                int(cr_p90[i]) if i < len(cr_p90) else "",
                f"{float(yo_nom[i]):.2f}%" if i < len(yo_nom) else "",
                f"{float(yo_real[i]):.2f}%" if i < len(yo_real) else "",
            ]
        rows_acct_current.append(row)
    _print_table(
        header_acct_current,
        rows_acct_current,
        title="Accounts — Investment YoY (Current USD)",
    )
    _save_csv(
        os.path.join(out_dir, "accounts_current_investment_yoy.csv"),
        header_acct_current,
        rows_acct_current,
    )

    # Accounts — Ending Balances (final year, Future & Current mean)
    ending_balances = compute_account_ending_balances(
        inv_nom_levels_mean_acct=inv_nom_levels_mean_acct,
        inv_real_levels_mean_acct=inv_real_levels_mean_acct,
    )

    if ending_balances:
        header_ending = ["Account", "EndingFutureMean", "EndingCurrentMean"]
        ending_rows: List[List[Any]] = [
            [e["account"], int(e["ending_future_mean"]), int(e["ending_current_mean"])]
            for e in ending_balances
        ]
        _print_table(
            header_ending,
            ending_rows,
            title="Accounts — Ending Balances (Final Year)",
        )
        _save_csv(
            os.path.join(out_dir, "accounts_ending_balances.csv"),
            header_ending,
            ending_rows,
        )

    # Aggregate balances (Current USD) — plot with mean/median and P10–P90 band
    print("[DEBUG] Starting aggregate balance computation (Current USD)")
    print("[DEBUG] accounts list:", accounts)
    try:
        n_years = len(years)
        agg_cur = {
            "brokerage": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
            "traditional_ira": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
            "roth_ira": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
            "total": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
        }

        for acct in accounts:
            acct_upper = acct.upper()

            if "BROKERAGE" in acct_upper:
                key = "brokerage"
            elif "TRAD_IRA" in acct_upper or "TRADITIONAL" in acct_upper:
                key = "traditional_ira"
            elif "ROTH_IRA" in acct_upper or "ROTH" in acct_upper:
                key = "roth_ira"
            else:
                continue

            cr_mean = np.asarray(
                inv_real_levels_mean_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]
            cr_med = np.asarray(
                inv_real_levels_med_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]
            cr_p10 = np.asarray(
                inv_real_levels_p10_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]
            cr_p90 = np.asarray(
                inv_real_levels_p90_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]

            agg_cur[key]["mean"] += cr_mean
            agg_cur[key]["med"] += cr_med
            agg_cur[key]["p10"] += cr_p10
            agg_cur[key]["p90"] += cr_p90

        for field in ("mean", "med", "p10", "p90"):
            agg_cur["total"][field] = (
                agg_cur["brokerage"][field]
                + agg_cur["traditional_ira"][field]
                + agg_cur["roth_ira"][field]
            )

        y_int = [int(y) for y in years]

        print(
            "[DEBUG] agg_cur sums:",
            "brokerage=",
            float(np.sum(agg_cur["brokerage"]["mean"])),
            "trad=",
            float(np.sum(agg_cur["traditional_ira"]["mean"])),
            "roth=",
            float(np.sum(agg_cur["roth_ira"]["mean"])),
            "total=",
            float(np.sum(agg_cur["total"]["mean"])),
        )

        def _has_any(series: np.ndarray) -> bool:
            return np.any(series != 0.0)

        if _has_any(agg_cur["brokerage"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_brokerage_current.png"),
                y_int,
                agg_cur["brokerage"]["mean"].tolist(),
                agg_cur["brokerage"]["med"].tolist(),
                agg_cur["brokerage"]["p10"].tolist(),
                agg_cur["brokerage"]["p90"].tolist(),
                title="Brokerage Aggregate Balances (Current USD)",
                ylabel="Current USD",
            )

        if _has_any(agg_cur["traditional_ira"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_traditional_ira_current.png"),
                y_int,
                agg_cur["traditional_ira"]["mean"].tolist(),
                agg_cur["traditional_ira"]["med"].tolist(),
                agg_cur["traditional_ira"]["p10"].tolist(),
                agg_cur["traditional_ira"]["p90"].tolist(),
                title="Traditional IRA Aggregate Balances (Current USD)",
                ylabel="Current USD",
            )

        if _has_any(agg_cur["roth_ira"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_roth_ira_current.png"),
                y_int,
                agg_cur["roth_ira"]["mean"].tolist(),
                agg_cur["roth_ira"]["med"].tolist(),
                agg_cur["roth_ira"]["p10"].tolist(),
                agg_cur["roth_ira"]["p90"].tolist(),
                title="Roth IRA Aggregate Balances (Current USD)",
                ylabel="Current USD",
            )

        if _has_any(agg_cur["total"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_total_current.png"),
                y_int,
                agg_cur["total"]["mean"].tolist(),
                agg_cur["total"]["med"].tolist(),
                agg_cur["total"]["p10"].tolist(),
                agg_cur["total"]["p90"].tolist(),
                title="Total Aggregate Balances (Current USD)",
                ylabel="Current USD",
            )

    except Exception as e:
        print(f"[WARN] Failed to compute/plot aggregate balances (Current USD): {e}")

    # Aggregate balances (Future USD) — plot with mean/median and P10–P90 band
    print("[DEBUG] Starting aggregate balance computation (Future USD)")
    print("[DEBUG] accounts list:", accounts)
    try:
        n_years = len(years)
        agg_fut = {
            "brokerage": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
            "traditional_ira": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
            "roth_ira": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
            "total": {
                "mean": np.zeros(n_years),
                "med": np.zeros(n_years),
                "p10": np.zeros(n_years),
                "p90": np.zeros(n_years),
            },
        }

        for acct in accounts:
            acct_upper = acct.upper()

            if "BROKERAGE" in acct_upper:
                key = "brokerage"
            elif "TRAD_IRA" in acct_upper or "TRADITIONAL" in acct_upper:
                key = "traditional_ira"
            elif "ROTH_IRA" in acct_upper or "ROTH" in acct_upper:
                key = "roth_ira"
            else:
                continue

            fn_mean = np.asarray(
                inv_nom_levels_mean_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]
            fn_med = np.asarray(
                inv_nom_levels_med_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]
            fn_p10 = np.asarray(
                inv_nom_levels_p10_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]
            fn_p90 = np.asarray(
                inv_nom_levels_p90_acct.get(acct, [0.0] * n_years),
                dtype=float,
            )[:n_years]

            agg_fut[key]["mean"] += fn_mean
            agg_fut[key]["med"] += fn_med
            agg_fut[key]["p10"] += fn_p10
            agg_fut[key]["p90"] += fn_p90

        for field in ("mean", "med", "p10", "p90"):
            agg_fut["total"][field] = (
                agg_fut["brokerage"][field]
                + agg_fut["traditional_ira"][field]
                + agg_fut["roth_ira"][field]
            )

        y_int = [int(y) for y in years]

        print(
            "[DEBUG] agg_fut sums:",
            "brokerage=",
            float(np.sum(agg_fut["brokerage"]["mean"])),
            "trad=",
            float(np.sum(agg_fut["traditional_ira"]["mean"])),
            "roth=",
            float(np.sum(agg_fut["roth_ira"]["mean"])),
            "total=",
            float(np.sum(agg_fut["total"]["mean"])),
        )

        def _has_any(series: np.ndarray) -> bool:
            return np.any(series != 0.0)

        if _has_any(agg_fut["brokerage"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_brokerage_future.png"),
                y_int,
                agg_fut["brokerage"]["mean"].tolist(),
                agg_fut["brokerage"]["med"].tolist(),
                agg_fut["brokerage"]["p10"].tolist(),
                agg_fut["brokerage"]["p90"].tolist(),
                title="Brokerage Aggregate Balances (Future USD)",
                ylabel="Future USD",
            )

        if _has_any(agg_fut["traditional_ira"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_traditional_ira_future.png"),
                y_int,
                agg_fut["traditional_ira"]["mean"].tolist(),
                agg_fut["traditional_ira"]["med"].tolist(),
                agg_fut["traditional_ira"]["p10"].tolist(),
                agg_fut["traditional_ira"]["p90"].tolist(),
                title="Traditional IRA Aggregate Balances (Future USD)",
                ylabel="Future USD",
            )

        if _has_any(agg_fut["roth_ira"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_roth_ira_future.png"),
                y_int,
                agg_fut["roth_ira"]["mean"].tolist(),
                agg_fut["roth_ira"]["med"].tolist(),
                agg_fut["roth_ira"]["p10"].tolist(),
                agg_fut["roth_ira"]["p90"].tolist(),
                title="Roth IRA Aggregate Balances (Future USD)",
                ylabel="Future USD",
            )

        if _has_any(agg_fut["total"]["mean"]):
            _plot_aggregate_band(
                os.path.join(out_dir, "aggregate_total_future.png"),
                y_int,
                agg_fut["total"]["mean"].tolist(),
                agg_fut["total"]["med"].tolist(),
                agg_fut["total"]["p10"].tolist(),
                agg_fut["total"]["p90"].tolist(),
                title="Total Aggregate Balances (Future USD)",
                ylabel="Future USD",
            )

    except Exception as e:
        print(f"[WARN] Failed to compute/plot aggregate balances (Future USD): {e}")

    # Taxes & RMDs (Current USD) — Yearly summary
    show_tax_rmd = any(
        len(x) > 0
        for x in [
            txFed,
            txState,
            txNIIT,
            txExc,
            txShort,
            gains,
            rmdMean,
            rmdTxFed,
            rmdTxState,
            rmdTxNIIT,
            rmdShort,
        ]
    )
    if show_tax_rmd:
        header_tax = [
            "Year",
            "FedTax",
            "StateTax",
            "NIIT",
            "Excise",
            "TaxShortfall",
            "RealizedGains",
            "RMD",
            "RMD FedTax",
            "RMD StateTax",
            "RMD NIIT",
            "RMD Shortfall",
        ]
        rows_tax = []
        for i, y in enumerate(years):
            rows_tax.append(
                [
                    int(y),
                    int(txFed[i]) if i < len(txFed) else "",
                    int(txState[i]) if i < len(txState) else "",
                    int(txNIIT[i]) if i < len(txNIIT) else "",
                    int(txExc[i]) if i < len(txExc) else "",
                    int(txShort[i]) if i < len(txShort) else "",
                    int(gains[i]) if i < len(gains) else "",
                    int(rmdMean[i]) if i < len(rmdMean) else "",
                    int(rmdTxFed[i]) if i < len(rmdTxFed) else "",
                    int(rmdTxState[i]) if i < len(rmdTxState) else "",
                    int(rmdTxNIIT[i]) if i < len(rmdTxNIIT) else "",
                    int(rmdShort[i]) if i < len(rmdShort) else "",
                ]
            )
        _print_table(header_tax, rows_tax, title="Taxes & RMDs (Current USD)")
        _save_csv(
            os.path.join(out_dir, "taxes_rmd_current_by_year.csv"),
            header_tax,
            rows_tax,
        )

        _plot_lines(
            os.path.join(out_dir, "taxes_current_components.png"),
            years,
            {
                "FedTax": txFed,
                "StateTax": txState,
                "NIIT": txNIIT,
                "Excise": txExc,
                "TaxShortfall": txShort,
                "RealizedGains": gains,
            },
            "Taxes (Current USD) — Components",
            "USD",
        )
        _plot_lines(
            os.path.join(out_dir, "rmd_current_components.png"),
            years,
            {
                "RMD": rmdMean,
                "RMD FedTax": rmdTxFed,
                "RMD StateTax": rmdTxState,
                "RMD NIIT": rmdTxNIIT,
                "RMD Shortfall": rmdShort,
            },
            "RMDs (Current USD) — Components",
            "USD",
        )

# --- End of file ---
