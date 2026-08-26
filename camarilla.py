"""Camarilla pivot range breakout, long and short -- prior day's H/L/C build eight
levels (R1-R4, S1-S4); a break above R3 or below S3 signals the day is trending out of
its normal range rather than staying range-bound inside it (the classic Indian
day-trading "range breakout" read on Camarilla levels).

Signal:       session close breaks above R3 (long) or below S3 (short)
Confirmation: breakout bar's volume >= CAMARILLA_VOLUME_MULT x its rolling average
              (skips breakouts on thin, unconvincing volume), and price on the trend
              side of VWAP (same confirmation that worked for orb_confluence)
Exit:         target at R4/S4 (the next Camarilla level out), OR an ATR trailing stop
              (CAMARILLA_ATR_MULT x continuous 5-min ATR, ratchets in favor only) if hit
              first, OR forced close at FORCE_CLOSE_IST (MIS, same-day square-off)

ATR_MULT starts at 5.0 -- the value that turned out to be the net-PnL peak for
orb_confluence's exit (2.5x-10x swept there, see instruction.md 9.6). Worth its own
sweep here since the entry dynamics differ, but not assumed identical without checking.
"""

import pandas as pd

from backtest import Trade, position_size
from config import (
    CAMARILLA_ATR_MULT,
    CAMARILLA_ATR_PERIOD,
    CAMARILLA_VOLUME_LOOKBACK_BARS,
    CAMARILLA_VOLUME_MULT,
    FORCE_CLOSE_IST,
)
from indicators import atr as atr_indicator
from indicators import session_vwap

FORCE_CLOSE_TIME = pd.to_datetime(FORCE_CLOSE_IST).time()


def camarilla_levels(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """R3/R4/S3/S4 for each day, built from the PRIOR day's H/L/C (shift(1) --
    the level a session trades against is set before that session opens)."""
    prior_high = daily_bars["high"].shift(1)
    prior_low = daily_bars["low"].shift(1)
    prior_close = daily_bars["close"].shift(1)
    rng = prior_high - prior_low
    return pd.DataFrame({
        "r3": prior_close + rng * 1.1 / 4,
        "r4": prior_close + rng * 1.1 / 2,
        "s3": prior_close - rng * 1.1 / 4,
        "s4": prior_close - rng * 1.1 / 2,
    }, index=daily_bars.index)


def _scan_session(symbol: str, day_bars: pd.DataFrame, r3: float, r4: float, s3: float,
                   s4: float, day_atr: pd.Series) -> Trade | None:
    if len(day_bars) < CAMARILLA_VOLUME_LOOKBACK_BARS + 2 or any(pd.isna(x) for x in (r3, r4, s3, s4)):
        return None

    close = day_bars["close"]
    vwap = session_vwap(day_bars)
    rvol = day_bars["volume"] / day_bars["volume"].rolling(CAMARILLA_VOLUME_LOOKBACK_BARS).mean()

    start = CAMARILLA_VOLUME_LOOKBACK_BARS
    for i in range(start, len(day_bars)):
        side = None
        # entry must still be BETWEEN r3/s3 and the target (r4/s4) -- a bar that gaps
        # straight through both would otherwise "hit its target" on the very next tick
        # while already priced below entry, mislabeling a loss as a target_hit win.
        if r3 < close.iloc[i] < r4 and close.iloc[i] > vwap.iloc[i] and rvol.iloc[i] >= CAMARILLA_VOLUME_MULT:
            side = "long"
        elif s4 < close.iloc[i] < s3 and close.iloc[i] < vwap.iloc[i] and rvol.iloc[i] >= CAMARILLA_VOLUME_MULT:
            side = "short"
        if side is None or pd.isna(day_atr.iloc[i]):
            continue

        entry_idx, entry_price, entry_atr = i, close.iloc[i], day_atr.iloc[i]
        target = r4 if side == "long" else s4
        extreme = entry_price
        for j in range(entry_idx + 1, len(day_bars)):
            bar = day_bars.iloc[j]
            atr_j = day_atr.iloc[j] if not pd.isna(day_atr.iloc[j]) else entry_atr
            if side == "long":
                extreme = max(extreme, bar["high"])
                trail_stop = extreme - CAMARILLA_ATR_MULT * atr_j
                if bar["high"] >= target:
                    return _trade(symbol, day_bars, entry_idx, j, entry_price, target,
                                   side, entry_atr, "target_hit")
                if bar["low"] <= trail_stop:
                    return _trade(symbol, day_bars, entry_idx, j, entry_price, trail_stop,
                                   side, entry_atr, "trailing_stop")
            else:
                extreme = min(extreme, bar["low"])
                trail_stop = extreme + CAMARILLA_ATR_MULT * atr_j
                if bar["low"] <= target:
                    return _trade(symbol, day_bars, entry_idx, j, entry_price, target,
                                   side, entry_atr, "target_hit")
                if bar["high"] >= trail_stop:
                    return _trade(symbol, day_bars, entry_idx, j, entry_price, trail_stop,
                                   side, entry_atr, "trailing_stop")
            if bar.name.time() >= FORCE_CLOSE_TIME:
                return _trade(symbol, day_bars, entry_idx, j, entry_price, bar["close"],
                               side, entry_atr, "forced_close")
        last = day_bars.iloc[-1]
        return _trade(symbol, day_bars, entry_idx, len(day_bars) - 1, entry_price,
                       last["close"], side, entry_atr, "eod_data_end")
    return None


def _trade(symbol, day_bars, entry_idx, exit_idx, entry_price, exit_price, side, entry_atr, reason) -> Trade:
    return Trade(symbol=symbol, entry_time=day_bars.index[entry_idx], exit_time=day_bars.index[exit_idx],
                 entry_price=entry_price, exit_price=exit_price, shares=0, exit_reason=reason,
                 stage="camarilla", risk_per_share=CAMARILLA_ATR_MULT * entry_atr, product="MIS", side=side)


def run_camarilla(daily_bars_by_symbol: dict[str, pd.DataFrame],
                   intraday_bars_by_symbol: dict[str, pd.DataFrame]) -> list[Trade]:
    trades = []
    for symbol, bars in intraday_bars_by_symbol.items():
        daily_bars = daily_bars_by_symbol.get(symbol)
        if daily_bars is None:
            continue
        levels = camarilla_levels(daily_bars)
        atr_series = atr_indicator(bars, CAMARILLA_ATR_PERIOD)  # continuous 5-min ATR

        for session_date in sorted(set(bars.index.date)):
            level_rows = levels[levels.index.date == session_date]
            if level_rows.empty:
                continue
            row = level_rows.iloc[0]
            day_bars = bars[bars.index.date == session_date]
            day_atr = atr_series[atr_series.index.date == session_date]
            trade = _scan_session(symbol, day_bars, row["r3"], row["r4"], row["s3"], row["s4"], day_atr)
            if trade is None:
                continue
            trade.shares = position_size(trade.entry_price)
            if trade.shares > 0:
                trades.append(trade)
    return trades
