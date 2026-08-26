"""One-off sanity check: does the Engine I pipeline work against real Kite data?

Loads pre-fetched JSON (pulled once via the interactive MCP session, not kiteconnect --
no .env/API credentials needed for this check) for a handful of liquid large-caps, and
runs the actual screener/confirm/backtest code on it. Not a real backtest (5 symbols,
~2y daily + 10 days intraday is far too small a sample) -- just proof the pipeline runs
end to end against real NSE data before committing to the full fetch.
"""

import json
from pathlib import Path

import pandas as pd

from backtest import run_stage1_only, run_stage1_plus_stage2
from report import print_report

CACHE_DIR = Path("/tmp/kite_check")
SYMBOLS = ["RELIANCE", "TCS", "INFY", "TATASTEEL", "ADANIENT"]


def _load(path: Path) -> pd.DataFrame:
    records = json.loads(path.read_text())
    df = pd.DataFrame(records).set_index("date")[["open", "high", "low", "close", "volume"]]
    idx = pd.to_datetime(df.index)
    df.index = idx.tz_convert("Asia/Kolkata").tz_localize(None) if idx.tz is not None else idx
    return df


if __name__ == "__main__":
    daily_bars = {s: _load(CACHE_DIR / f"{s}_daily.json") for s in SYMBOLS}
    intraday_bars = {s: _load(CACHE_DIR / f"{s}_intraday.json") for s in SYMBOLS}

    for s in SYMBOLS:
        print(f"{s}: {len(daily_bars[s])} daily bars, {len(intraday_bars[s])} intraday bars, "
              f"daily range {daily_bars[s].index[0].date()} - {daily_bars[s].index[-1].date()}, "
              f"intraday range {intraday_bars[s].index[0]} - {intraday_bars[s].index[-1]}")

    print()
    stage1_trades = run_stage1_only(daily_bars)
    print_report("Stage 1 only (5 symbols, real data)", stage1_trades)

    combined_trades = run_stage1_plus_stage2(daily_bars, intraday_bars)
    print_report("Stage 1+2 combined (5 symbols, real data)", combined_trades)
