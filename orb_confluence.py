"""ORB breakout, confluence-filtered entry + ATR trailing exit.

orb_vwap.py trades instruction.md's literal spec (VWAP-line stop) and its own trade log
shows why that loses: trades stopped out on a VWAP pullback average -Rs163, trades held
to forced close average +Rs230 (out/orb_vwap_trades.csv). The exit is too tight for the
entry's noise, not a lack of edge.

This keeps the same ORB+volume signal, adds two confirmations to skip breakouts that are
already exhausted (RSI zone, MACD direction agreement) instead of blindly raising the
volume threshold, and replaces the VWAP-line stop with an ATR Chandelier-style trailing
stop so a normal pullback doesn't end the trade.

Signal:       close breaks first-OR_BARS high/low + volume >= OR_VOLUME_MULT x 5-day avg
Confirmation: price on the right side of VWAP, RSI in a trending-not-exhausted zone,
              MACD line agrees with direction
Exit:         ATR trailing stop, CHANDELIER_MULT x ATR(14) on the 5-min bar scale,
              ratchets in favor only; forced close at FORCE_CLOSE_IST regardless (MIS,
              same-day square-off).

The ATR here is computed on each symbol's CONTINUOUS 5-min series (like
bollinger_meanrev.py's bands), not reset per session and not the daily-bar ATR:
- a same-session-only ATR(14), calculated fresh from each day's first ~70 minutes,
  measures the quiet pre-breakout period, not the move about to happen -- stopped 92%
  of trades out prematurely in an earlier version of this file.
- the prior day's DAILY ATR is the wrong scale entirely -- 2.5x a full day's range as an
  intraday trail practically never triggers, which just turned this back into "hold to
  forced close no matter what" (tried, gross fell to Rs4,557 vs orb_vwap's Rs8,454).
Continuous 5-min ATR keeps the right timescale while still having real history to draw
on the moment a session opens.
"""

import pandas as pd

from backtest import Trade, position_size
from config import (
    FORCE_CLOSE_IST,
    OR_BARS,
    OR_VOLUME_LOOKBACK_DAYS,
    OR_VOLUME_MULT,
)
from indicators import atr as atr_indicator
from indicators import macd, rsi, session_vwap
from orb_vwap import _avg_or_volume, _or_volume

FORCE_CLOSE_TIME = pd.to_datetime(FORCE_CLOSE_IST).time()
# swept 2.5-10x on cached data (see instruction.md 9.6) -- 5.0x was the net-PnL peak;
# below it the stop clips winners before they run, above it gives back the gain in costs
# from holding through more chop without materially raising gross.
CHANDELIER_MULT = 5.0
RSI_PERIOD = 14
RSI_LONG_ZONE = (50, 75)   # trending but not exhausted
RSI_SHORT_ZONE = (25, 50)


def _scan_session(symbol: str, day_bars: pd.DataFrame, avg_or_vol: float, day_atr: pd.Series) -> Trade | None:
    if len(day_bars) <= OR_BARS or avg_or_vol != avg_or_vol or avg_or_vol == 0:
        return None
    or_high = day_bars["high"].iloc[:OR_BARS].max()
    or_low = day_bars["low"].iloc[:OR_BARS].min()
    if _or_volume(day_bars) < OR_VOLUME_MULT * avg_or_vol:
        return None

    vwap = session_vwap(day_bars)
    close = day_bars["close"]
    r = rsi(close, RSI_PERIOD)
    macd_line, signal_line = macd(close)

    start = max(OR_BARS, RSI_PERIOD)
    for i in range(start, len(day_bars)):
        side = None
        if (close.iloc[i] > or_high and close.iloc[i] > vwap.iloc[i]
                and RSI_LONG_ZONE[0] <= r.iloc[i] <= RSI_LONG_ZONE[1]
                and macd_line.iloc[i] > signal_line.iloc[i]):
            side = "long"
        elif (close.iloc[i] < or_low and close.iloc[i] < vwap.iloc[i]
                and RSI_SHORT_ZONE[0] <= r.iloc[i] <= RSI_SHORT_ZONE[1]
                and macd_line.iloc[i] < signal_line.iloc[i]):
            side = "short"
        if side is None or pd.isna(day_atr.iloc[i]):
            continue

        entry_idx, entry_price, entry_atr = i, close.iloc[i], day_atr.iloc[i]
        stop_distance = CHANDELIER_MULT * entry_atr
        extreme = entry_price  # highest high (long) or lowest low (short) since entry
        for j in range(entry_idx + 1, len(day_bars)):
            bar = day_bars.iloc[j]
            atr_j = day_atr.iloc[j] if not pd.isna(day_atr.iloc[j]) else entry_atr
            if side == "long":
                extreme = max(extreme, bar["high"])
                trail_stop = extreme - CHANDELIER_MULT * atr_j
                stopped = bar["low"] <= trail_stop
            else:
                extreme = min(extreme, bar["low"])
                trail_stop = extreme + CHANDELIER_MULT * atr_j
                stopped = bar["high"] >= trail_stop
            if stopped:
                return Trade(symbol=symbol, entry_time=day_bars.index[entry_idx],
                              exit_time=day_bars.index[j], entry_price=entry_price,
                              exit_price=trail_stop, shares=0, exit_reason="trailing_stop",
                              stage="orb_confluence", risk_per_share=stop_distance,
                              product="MIS", side=side)
            if bar.name.time() >= FORCE_CLOSE_TIME:
                return Trade(symbol=symbol, entry_time=day_bars.index[entry_idx],
                              exit_time=day_bars.index[j], entry_price=entry_price,
                              exit_price=bar["close"], shares=0, exit_reason="forced_close",
                              stage="orb_confluence", risk_per_share=stop_distance,
                              product="MIS", side=side)
        last = day_bars.iloc[-1]
        return Trade(symbol=symbol, entry_time=day_bars.index[entry_idx],
                      exit_time=day_bars.index[-1], entry_price=entry_price,
                      exit_price=last["close"], shares=0, exit_reason="eod_data_end",
                      stage="orb_confluence", risk_per_share=stop_distance,
                      product="MIS", side=side)
    return None


def run_orb_confluence(intraday_bars_by_symbol: dict[str, pd.DataFrame]) -> list[Trade]:
    trades = []
    for symbol, bars in intraday_bars_by_symbol.items():
        atr_series = atr_indicator(bars, RSI_PERIOD)  # continuous 5-min-bar ATR, see module docstring
        for session_date in sorted(set(bars.index.date)):
            day_bars = bars[bars.index.date == session_date]
            day_atr = atr_series[atr_series.index.date == session_date]
            avg_or_vol = _avg_or_volume(bars, session_date, OR_VOLUME_LOOKBACK_DAYS)
            trade = _scan_session(symbol, day_bars, avg_or_vol, day_atr)
            if trade is None:
                continue
            trade.shares = position_size(trade.entry_price)
            if trade.shares > 0:
                trades.append(trade)
    return trades
