
# filename: generate_assets_from_market_data.py
"""
Generate NDinomics-style asset characteristics (mu, sigma, yield, qualified_ratio)
from live market data using Yahoo Finance via yfinance.

Schema of output assets.json:

{
  "assets": {
    "VTI": {
      "class": "US_STOCKS",
      "mu_annual": 0.065,
      "sigma_annual": 0.16,
      "expense_ratio": 0.0003,
      "tracking_error": 0.01,
      "dist": {
        "yield_annual": 0.017,
        "qualified_ratio": 0.90
      }
    },
    ...
  },
  "correlations": {
    "assets_order": ["VTI", "VXUS", ...],
    "matrix": [[1.0, 0.8, ...], [...]]
  }
}

Run from the command line (after installing deps):

  python generate_assets_from_market_data.py \
      --tickers VTI VXUS TLT IEF GLD DBC \
      --classes US_STOCKS INTL_STOCKS LONG_TREAS INT_TREAS GOLD COMMOD \
      --years 10 \
      --out assets.json
"""

import argparse
import datetime as dt
import json
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


# -----------------------
# Helpers
# -----------------------

def _estimate_return_and_vol(prices: pd.Series) -> Tuple[float, float]:
    """
    Estimate annualized geometric mean return and volatility from daily prices.
    Assumes US trading calendar ~252 days/year.
    """
    prices = prices.dropna()
    if prices.size < 64:
        return 0.0, 0.0

    rets = prices.pct_change().dropna()
    if rets.empty:
        return 0.0, 0.0

    mean_daily = rets.mean()
    var_daily = rets.var()

    mu_annual = (1.0 + mean_daily) ** 252 - 1.0
    sigma_annual = float(np.sqrt(var_daily * 252))

    return float(mu_annual), float(sigma_annual)


def _estimate_dividend_yield(dividends: pd.Series, prices: pd.Series) -> float:
    """
    Estimate trailing 12m dividend yield = (sum of last 12 months' dividends)
    / last price.

    Returns 0.0 if not enough data.
    """
    dividends = dividends.dropna()
    prices = prices.dropna()
    if prices.empty:
        return 0.0

    if dividends.empty:
        return 0.0

    last_date = dividends.index.max()
    twelve_months_ago = last_date - pd.DateOffset(years=1)
    trailing_divs = dividends[dividends.index > twelve_months_ago]
    if trailing_divs.empty:
        return 0.0

    total_div = trailing_divs.sum()
    last_price = prices.iloc[-1]
    if last_price <= 0:
        return 0.0

    return float(total_div / last_price)


def _download_history(
    ticker: str,
    start: dt.date,
    end: dt.date,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Download OHLCV + dividends using yfinance.
    Returns (price_df, dividends_series).
    """
    data = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if data.empty:
        return pd.DataFrame(), pd.Series(dtype=float)

    # Use 'Adj Close' if present; fall back to 'Close'
    if "Adj Close" in data.columns:
        price_series = data["Adj Close"]
    else:
        price_series = data["Close"]

    dividends = data.get("Dividends", pd.Series(dtype=float))

    return price_series, dividends


# -----------------------
# Core generator
# -----------------------

def build_assets_config(
    tickers: List[str],
    classes: List[str],
    years: int = 10,
    default_expense_ratio: float = 0.0005,
    default_tracking_error: float = 0.01,
    default_qualified_ratio_by_class: Dict[str, float] = None,
) -> Dict:
    """
    Build an NDinomics-style assets.json mapping from a list of tickers and classes.

    Parameters
    ----------
    tickers: list of tickers (e.g. ["VTI", "VXUS", "TLT"])
    classes: list of asset classes, same length as tickers
             (e.g. ["US_STOCKS", "INTL_STOCKS", "LONG_TREAS"])
    years: lookback window for history (in calendar years)
    default_expense_ratio: used when we don't know the true ER
    default_tracking_error: used as a generic TE guess
    default_qualified_ratio_by_class: map class -> qualified dividend ratio;
                                      falls back to 0.0 if not specified

    Returns
    -------
    dict ready to json.dump() as assets.json
    """
    if len(tickers) != len(classes):
        raise ValueError("tickers and classes must have the same length")

    if default_qualified_ratio_by_class is None:
        default_qualified_ratio_by_class = {
            "US_STOCKS": 0.90,
            "INTL_STOCKS": 0.80,
            "LONG_TREAS": 0.00,
            "INT_TREAS": 0.00,
            "TIPS": 0.00,
            "GOLD": 0.00,
            "COMMOD": 0.00,
        }

    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=365 * years)

    assets_cfg: Dict[str, Dict] = {}
    price_matrix = []

    for ticker, cls in zip(tickers, classes):
        print(f"Fetching {ticker} ...")
        prices, dividends = _download_history(ticker, start=start_date, end=end_date)

        if prices.empty:
            print(f"  WARNING: no data for {ticker}, using zeros.")
            mu_annual = 0.0
            sigma_annual = 0.0
            yield_annual = 0.0
        else:
            mu_annual, sigma_annual = _estimate_return_and_vol(prices)
            yield_annual = _estimate_dividend_yield(dividends, prices)
            # Save aligned prices for correlation
            price_matrix.append(prices.rename(ticker))

        q_ratio = float(default_qualified_ratio_by_class.get(cls, 0.0))

        assets_cfg[ticker] = {
            "class": cls,
            "mu_annual": float(mu_annual),
            "sigma_annual": float(sigma_annual),
            "expense_ratio": float(default_expense_ratio),
            "tracking_error": float(default_tracking_error),
            "dist": {
                "yield_annual": float(yield_annual),
                "qualified_ratio": q_ratio,
            },
        }

    # Build correlation matrix on overlapping daily returns
    correlations = {"assets_order": tickers}
    if price_matrix:
        price_df = pd.concat(price_matrix, axis=1, join="inner")
        rets = price_df.pct_change().dropna()
        if rets.shape[0] > 0:
            corr = rets.corr().values
        else:
            corr = np.eye(len(tickers))
        correlations["matrix"] = corr.tolist()
    else:
        correlations["matrix"] = np.eye(len(tickers)).tolist()

    return {
        "assets": assets_cfg,
        "correlations": correlations,
    }


# -----------------------
# CLI
# -----------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate NDinomics-style assets.json from Yahoo Finance"
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="List of tickers (e.g. VTI VXUS TLT IEF GLD DBC)",
    )
    p.add_argument(
        "--classes",
        nargs="+",
        required=True,
        help="List of asset classes, same length as tickers "
             "(e.g. US_STOCKS INTL_STOCKS LONG_TREAS INT_TREAS GOLD COMMOD)",
    )
    p.add_argument(
        "--years",
        type=int,
        default=10,
        help="Lookback window in years for historical data (default: 10)",
    )
    p.add_argument(
        "--out",
        type=str,
        default="assets.json",
        help="Output JSON file path (default: assets.json)",
    )
    return p.parse_args()


def main():
    args = parse_args()

    config = build_assets_config(
        tickers=args.tickers,
        classes=args.classes,
        years=args.years,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Wrote assets configuration for {len(args.tickers)} tickers to {args.out}")


if __name__ == "__main__":
    main()

