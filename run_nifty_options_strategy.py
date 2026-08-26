"""Backtest & Execution Runner for NIFTY Options Supertrend + Pivot Strategy.

Can run with:
1. Cached data / proxy ETF / Index data
2. Direct live/historical Kite Connect data (if session active)
"""

import sys
from pathlib import Path
import pandas as pd

from cached_data import load_symbol_bars
from nifty_options_supertrend_pivots import (
    StrategyConfig,
    run_nifty_options_backtest,
)


def main():
    Path("out").mkdir(exist_ok=True)
    print("===================================================================")
    print("  NIFTY Options Intraday Selling Strategy: Supertrend + Daily Pivots")
    print("===================================================================\n")

    # Check if we have cached daily & intraday bars
    daily_bars, intraday_bars = load_symbol_bars(daily_years=2)
    print(f"Loaded cached symbols: {len(daily_bars)} daily, {len(intraday_bars)} intraday")

    # Pick a heavyweight NIFTY proxy from cache (e.g. RELIANCE / HDFCBANK / ICICIBANK)
    # or synthetic/NIFTY index if available
    proxy_symbol = "RELIANCE" if "RELIANCE" in intraday_bars else list(intraday_bars.keys())[0]
    print(f"Running strategy evaluation on {proxy_symbol} (Proxy/Underlying)...")

    daily = daily_bars[proxy_symbol]
    intraday = intraday_bars[proxy_symbol]

    config = StrategyConfig(
        lot_size=65,
        max_trades_per_day=3,
        supertrend_period=7,
        supertrend_multiplier=3.0,
    )

    trades, df = run_nifty_options_backtest(daily, intraday, config=config)

    if df.empty:
        print("No trades generated during the tested period.")
        return

    print(f"\nGenerated {len(trades)} trades across {len(set(df['date']))} trading sessions.\n")

    wins = df[df["gross_pnl"] > 0]
    losses = df[df["gross_pnl"] < 0]
    win_rate = (len(wins) / len(df)) * 100 if len(df) > 0 else 0
    total_gross = df["gross_pnl"].sum()
    total_net = df["net_pnl"].sum()

    print(f"Total Trades     : {len(df)}")
    print(f"Win Rate         : {win_rate:.2f}% ({len(wins)} wins, {len(losses)} losses)")
    print(f"Gross PnL (₹)    : ₹{total_gross:,.2f}")
    print(f"Net PnL (₹)      : ₹{total_net:,.2f}")
    print(f"Avg PnL / Trade  : ₹{df['net_pnl'].mean():,.2f}")
    print(f"Exit Reasons     :\n{df['exit_reason'].value_counts().to_string()}\n")

    out_csv = "out/nifty_options_trades.csv"
    df.to_csv(out_csv, index=False)
    print(f"Trade log saved to: {out_csv}")


if __name__ == "__main__":
    main()
