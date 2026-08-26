"""Runs the existing strategy plus the three new instruction.md strategies against the
same cached bars, all through the same net-of-cost report. Backtest-only.
"""

from pathlib import Path

from backtest import run_stage1_only, run_stage1_plus_stage2
from bollinger_meanrev import run_bollinger_meanrev
from cached_data import load_symbol_bars
from orb_confluence import run_orb_confluence
from orb_vwap import run_orb_vwap
from report import plot_equity_curve, print_report, write_trade_log
from swing_engine import run_swing

if __name__ == "__main__":
    Path("out").mkdir(exist_ok=True)
    daily_bars, intraday_bars = load_symbol_bars(daily_years=2)
    print(f"{len(daily_bars)} symbols w/ daily history (last 2y), {len(intraday_bars)} w/ intraday "
          f"(cache cap: last 60d, can't be widened to 2y)\n")

    runs = {
        "stage1_only": lambda: run_stage1_only(daily_bars),
        "stage1plus2": lambda: run_stage1_plus_stage2(daily_bars, intraday_bars),
        "swing": lambda: run_swing(daily_bars),
        "orb_vwap": lambda: run_orb_vwap(intraday_bars),
        "orb_confluence": lambda: run_orb_confluence(intraday_bars),
        "bollinger_meanrev": lambda: run_bollinger_meanrev(intraday_bars),
    }

    for name, run in runs.items():
        trades = run()
        print_report(name, trades)
        write_trade_log(trades, f"out/{name}_trades.csv")
        plot_equity_curve(trades, f"out/{name}_equity.png")
        print()
