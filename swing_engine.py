"""Multi-day swing strategy -- instruction.md section 4.2.

Long-only, CNC (delivery, no leverage), 1-5 day holding period, on daily bars only
(the 5-min-candle TSL update in instruction.md is a live-execution granularity choice,
not something a daily-bar backtest needs -- daily is what's cached and what the entry
signal itself runs on).

Entry: fast SWING_FAST_EMA crosses above slow SWING_SLOW_EMA, confirmed by a positive
and expanding MACD histogram (MACD line - signal line), signal on day t close, entry at
day t+1 open.

Exit: Chandelier Exit -- trailing_stop = highest_high_since_entry - SWING_CHANDELIER_MULT
* ATR(SWING_ATR_PERIOD), ratcheting up only, exits the day price closes/lows below it. Hard
cap at SWING_MAX_HOLD_DAYS if the chandelier stop never triggers.

Position sizing: shares = risk_per_trade / initial_stop_distance (instruction.md formula),
where initial_stop_distance is the same chandelier distance at entry. Also capped so a
single position never exceeds SWING_CAPITAL notional -- this backtest doesn't track
concurrent capital draw-down across open positions (that's a portfolio-level accounting
concern, not a per-trade signal one); flag if you need concurrent-capital limits enforced.
"""

import pandas as pd

from backtest import Trade
from config import (
    SWING_ATR_PERIOD,
    SWING_CAPITAL,
    SWING_CHANDELIER_MULT,
    SWING_FAST_EMA,
    SWING_MAX_HOLD_DAYS,
    SWING_RISK_PER_TRADE,
    SWING_SLOW_EMA,
)
from indicators import atr as atr_indicator
from indicators import macd


def _entry_signal(bars: pd.DataFrame) -> pd.Series:
    ema_fast = bars["close"].ewm(span=SWING_FAST_EMA, adjust=False).mean()
    ema_slow = bars["close"].ewm(span=SWING_SLOW_EMA, adjust=False).mean()
    cross_up = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    macd_line, signal_line = macd(bars["close"])
    hist = macd_line - signal_line
    expanding = (hist > 0) & (hist > hist.shift(1))
    return cross_up & expanding


def run_swing(daily_bars_by_symbol: dict[str, pd.DataFrame]) -> list[Trade]:
    trades = []
    for symbol, bars in daily_bars_by_symbol.items():
        if len(bars) < SWING_SLOW_EMA + SWING_ATR_PERIOD:
            continue
        signal = _entry_signal(bars)
        atr_series = atr_indicator(bars, SWING_ATR_PERIOD)
        n = len(bars)
        i = 0
        while i < n - 1:
            if not signal.iloc[i] or pd.isna(atr_series.iloc[i]):
                i += 1
                continue
            entry_idx = i + 1
            entry_price = bars["open"].iloc[entry_idx]
            stop_distance = SWING_CHANDELIER_MULT * atr_series.iloc[i]
            if stop_distance <= 0:
                i += 1
                continue
            shares = int(SWING_RISK_PER_TRADE / stop_distance)
            shares = min(shares, int(SWING_CAPITAL / entry_price))
            if shares == 0:
                i += 1
                continue

            highest = entry_price
            exit_idx, exit_price, exit_reason = None, None, None
            hold_end = min(entry_idx + SWING_MAX_HOLD_DAYS, n)
            for j in range(entry_idx, hold_end):
                bar = bars.iloc[j]
                highest = max(highest, bar["high"])
                atr_j = atr_series.iloc[j]
                if pd.isna(atr_j):
                    atr_j = atr_series.iloc[i]
                trail_stop = highest - SWING_CHANDELIER_MULT * atr_j
                if bar["low"] <= trail_stop:
                    exit_idx, exit_price, exit_reason = j, trail_stop, "chandelier_stop"
                    break
            if exit_idx is None:
                exit_idx = hold_end - 1
                exit_price = bars["close"].iloc[exit_idx]
                exit_reason = "max_hold_exit"

            trades.append(Trade(
                symbol=symbol, entry_time=bars.index[entry_idx], exit_time=bars.index[exit_idx],
                entry_price=entry_price, exit_price=exit_price, shares=shares,
                exit_reason=exit_reason, stage="swing", risk_per_share=stop_distance, product="CNC",
            ))
            i = exit_idx + 1
    return trades
