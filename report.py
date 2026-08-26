"""Trade log CSV, win rate, profit factor, avg R, max drawdown, equity curve chart."""

import csv
from pathlib import Path

import pandas as pd

from backtest import Trade
from config import CAPITAL


def metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {}
    gross = pd.Series([t.pnl for t in trades])
    net = pd.Series([t.net_pnl for t in trades])
    wins = net[net > 0]
    losses = net[net <= 0]
    r_multiples = [t.r_multiple for t in trades if t.r_multiple is not None]
    equity_curve = CAPITAL + net.cumsum()
    return {
        "trade_count": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf"),
        "avg_r": sum(r_multiples) / len(r_multiples) if r_multiples else None,
        "max_drawdown": (equity_curve.cummax() - equity_curve).max(),
        "final_equity": CAPITAL + net.sum(),
        "total_return": net.sum() / CAPITAL,
        "gross_pnl": gross.sum(),
        "net_pnl": net.sum(),
        "total_costs": gross.sum() - net.sum(),
    }


def write_trade_log(trades: list[Trade], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "stage", "product", "entry_time", "exit_time", "entry_price",
                          "exit_price", "shares", "gross_pnl", "net_pnl", "r_multiple", "exit_reason"])
        for t in sorted(trades, key=lambda t: t.entry_time):
            writer.writerow([t.symbol, t.stage, t.product, t.entry_time, t.exit_time, t.entry_price,
                              t.exit_price, t.shares, round(t.pnl, 2), round(t.net_pnl, 2),
                              round(t.r_multiple, 2) if t.r_multiple is not None else "",
                              t.exit_reason])


def plot_equity_curve(trades: list[Trade], path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not trades:
        return
    ordered = sorted(trades, key=lambda t: t.entry_time)
    equity = CAPITAL + pd.Series([t.net_pnl for t in ordered]).cumsum()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range(len(equity)), equity)
    ax.set_xlabel("trade #")
    ax.set_ylabel("equity (INR)")
    ax.set_title("Equity curve")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def print_report(label: str, trades: list[Trade]) -> None:
    m = metrics(trades)
    print(f"=== {label} ===")
    if not trades:
        print("  no trades")
        return
    avg_r_str = f"avg_r={m['avg_r']:.2f} " if m["avg_r"] is not None else ""
    print(f"  trades={m['trade_count']} win_rate={m['win_rate']:.2%} "
          f"profit_factor={m['profit_factor']:.2f} {avg_r_str}")
    print(f"  gross_pnl=₹{m['gross_pnl']:.0f} costs=₹{m['total_costs']:.0f} net_pnl=₹{m['net_pnl']:.0f}")
    print(f"  max_drawdown=₹{m['max_drawdown']:.0f} final_equity=₹{m['final_equity']:.0f} "
          f"total_return={m['total_return']:.2%}")
