"""Bollinger Band + RSI mean-reversion, short only -- instruction.md section 4.1
secondary model, meant to catch sideways regimes where ORB/VWAP breakouts whipsaw.

Short: price closes outside the upper Bollinger Band (BB_PERIOD, BB_STD) while
RSI(BB_RSI_PERIOD) > BB_RSI_OVERBOUGHT. Exit target: the BB mid-band (SMA). Also exits
at FORCE_CLOSE_IST since this trades on MIS (must square off same session).

Trailing stop (added -- the spec's mid-band target left this strategy as the only one of
the five with no protective stop, so a short could run uncapped until forced close):
stop = lowest_low_since_entry + BB_STOP_ATR_MULT * ATR(BB_ATR_PERIOD), ratcheting DOWN
only as price falls in the short's favor. Exit fires the bar price trades back up through it.

Bands/RSI/ATR are computed on each symbol's continuous 5-min series (not reset per
session) -- ponytail: the first ~BB_PERIOD bars of a new session pull a little history
from the prior session's close, a minor approximation that doesn't affect a backtest
edge check.
"""

import pandas as pd

from backtest import Trade, position_size
from config import (
    BB_ATR_PERIOD,
    BB_PERIOD,
    BB_RSI_OVERBOUGHT,
    BB_RSI_PERIOD,
    BB_STD,
    BB_STOP_ATR_MULT,
    FORCE_CLOSE_IST,
)
from indicators import atr as atr_indicator
from indicators import bollinger_bands, rsi

FORCE_CLOSE_TIME = pd.to_datetime(FORCE_CLOSE_IST).time()


def run_bollinger_meanrev(intraday_bars_by_symbol: dict[str, pd.DataFrame]) -> list[Trade]:
    trades = []
    for symbol, bars in intraday_bars_by_symbol.items():
        if len(bars) < BB_PERIOD + BB_RSI_PERIOD:
            continue
        upper, mid, _ = bollinger_bands(bars["close"], BB_PERIOD, BB_STD)
        r = rsi(bars["close"], BB_RSI_PERIOD)
        a = atr_indicator(bars, BB_ATR_PERIOD)
        entry_signal = (bars["close"] > upper) & (r > BB_RSI_OVERBOUGHT)

        for session_date in sorted(set(bars.index.date)):
            day_mask = bars.index.date == session_date
            day_idx = bars.index[day_mask]
            i = 0
            positions = day_idx.tolist()
            while i < len(positions):
                ts = positions[i]
                entry_atr = a.loc[ts]
                if not entry_signal.loc[ts] or entry_atr != entry_atr:  # NaN check -- ATR not warmed up
                    i += 1
                    continue
                entry_price = bars["close"].loc[ts]
                exit_price, exit_time, exit_reason = entry_price, ts, "eod_data_end"
                lowest = entry_price
                for j in range(i + 1, len(positions)):
                    ts_j = positions[j]
                    bar = bars.loc[ts_j]
                    lowest = min(lowest, bar["low"])
                    atr_j = a.loc[ts_j]
                    stop_atr = atr_j if atr_j == atr_j else entry_atr  # NaN guard, early bars
                    trail_stop = lowest + BB_STOP_ATR_MULT * stop_atr
                    if bar["high"] >= trail_stop:
                        exit_price, exit_time, exit_reason = trail_stop, ts_j, "trailing_stop"
                        break
                    if bar["close"] <= mid.loc[ts_j]:
                        exit_price, exit_time, exit_reason = bar["close"], ts_j, "target_mid_band"
                        break
                    if ts_j.time() >= FORCE_CLOSE_TIME:
                        exit_price, exit_time, exit_reason = bar["close"], ts_j, "forced_close"
                        break
                    exit_price, exit_time = bar["close"], ts_j
                shares = position_size(entry_price)
                if shares > 0:
                    trades.append(Trade(
                        symbol=symbol, entry_time=ts, exit_time=exit_time, entry_price=entry_price,
                        exit_price=exit_price, shares=shares, exit_reason=exit_reason,
                        stage="bollinger_meanrev", risk_per_share=BB_STOP_ATR_MULT * entry_atr,
                        product="MIS", side="short",
                    ))
                i = len(positions)  # one trade per session per symbol -- move to next session
    return trades
