"""Fetches data via Kite Connect, runs both stages, writes reports. Backtest-only,
no live trading, no order placement.

Stage 1 only: full daily history (years=8), next-session open-to-close.
Stage 1+2 combined: last INTRADAY_HISTORY_DAYS days of 5-min bars.
"""

from pathlib import Path

from backtest import run_stage1_only, run_stage1_plus_stage2
from config import INTRADAY_HISTORY_DAYS, NIFTY_500
from data_fetch import fetch_daily_bars, fetch_intraday_bars, resolve_tokens
from kite_auth import get_kite
from report import plot_equity_curve, print_report, write_trade_log

if __name__ == "__main__":
    Path("out").mkdir(exist_ok=True)
    kite = get_kite()

    print(f"resolving {len(NIFTY_500)} symbols to instrument tokens...")
    tokens = resolve_tokens(kite, NIFTY_500)
    print(f"{len(tokens)} resolved\n")

    print("fetching daily bars (8y)...")
    daily_bars = {}
    for symbol, token in tokens.items():
        bars = fetch_daily_bars(kite, token, years=8)
        if len(bars) >= 260:
            daily_bars[symbol] = bars
    print(f"{len(daily_bars)} symbols with usable daily history\n")

    stage1_trades = run_stage1_only(daily_bars)
    print_report("Stage 1 only (full daily history)", stage1_trades)
    write_trade_log(stage1_trades, "out/stage1_trades.csv")
    plot_equity_curve(stage1_trades, "out/stage1_equity.png")

    print(f"\nfetching 5-min bars (last {INTRADAY_HISTORY_DAYS}d)...")
    intraday_bars = {}
    for symbol, token in tokens.items():
        bars = fetch_intraday_bars(kite, token, days=INTRADAY_HISTORY_DAYS)
        if len(bars) > 0:
            intraday_bars[symbol] = bars
    print(f"{len(intraday_bars)} symbols with usable intraday history\n")

    combined_trades = run_stage1_plus_stage2(daily_bars, intraday_bars)
    print_report(f"Stage 1+2 combined (last ~{INTRADAY_HISTORY_DAYS}d)", combined_trades)
    write_trade_log(combined_trades, "out/stage1plus2_trades.csv")
    plot_equity_curve(combined_trades, "out/stage1plus2_equity.png")
