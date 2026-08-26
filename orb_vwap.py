"""Opening Range Breakout + VWAP, long and short -- instruction.md section 4.1 primary
model. Distinct from confirm_intraday.py's swing-high breakout (that's this project's
existing custom variant); this is the literal first-15-min high/low breakout the
instructions specify, with a VWAP trailing stop instead of ATR.

Long: session close breaks above the first-15-min high, price sustains above VWAP,
first-15-min volume >= OR_VOLUME_MULT x its OR_VOLUME_LOOKBACK_DAYS-day average.
Short: symmetric break below the first-15-min low, price below VWAP.

Stop: trailed immediately at the VWAP line itself (instruction.md 4.1) -- exits the bar
the price closes back through VWAP against the position, or at FORCE_CLOSE_IST.
"""

import pandas as pd

from backtest import Trade, position_size
from config import FORCE_CLOSE_IST, OR_BARS, OR_VOLUME_LOOKBACK_DAYS, OR_VOLUME_MULT
from indicators import session_vwap

FORCE_CLOSE_TIME = pd.to_datetime(FORCE_CLOSE_IST).time()


def _or_volume(day_bars: pd.DataFrame) -> float:
    return day_bars["volume"].iloc[:OR_BARS].sum()


def _avg_or_volume(intraday_bars: pd.DataFrame, before_date, lookback_days: int) -> float:
    prior = intraday_bars[intraday_bars.index.date < before_date]
    if prior.empty:
        return float("nan")
    by_day = prior.groupby(prior.index.date)
    daily_or_vol = by_day.apply(_or_volume, include_groups=False)
    return daily_or_vol.iloc[-lookback_days:].mean()


def _scan_session(symbol: str, day_bars: pd.DataFrame, avg_or_vol: float) -> Trade | None:
    if len(day_bars) <= OR_BARS or avg_or_vol != avg_or_vol or avg_or_vol == 0:
        return None
    or_high = day_bars["high"].iloc[:OR_BARS].max()
    or_low = day_bars["low"].iloc[:OR_BARS].min()
    or_vol = _or_volume(day_bars)
    if or_vol < OR_VOLUME_MULT * avg_or_vol:
        return None

    vwap = session_vwap(day_bars)
    close = day_bars["close"]

    for i in range(OR_BARS, len(day_bars)):
        side = None
        if close.iloc[i] > or_high and close.iloc[i] > vwap.iloc[i]:
            side = "long"
        elif close.iloc[i] < or_low and close.iloc[i] < vwap.iloc[i]:
            side = "short"
        if side is None:
            continue

        entry_idx, entry_price = i, close.iloc[i]
        for j in range(entry_idx + 1, len(day_bars)):
            bar = day_bars.iloc[j]
            crossed_back = bar["close"] < vwap.iloc[j] if side == "long" else bar["close"] > vwap.iloc[j]
            if crossed_back:
                return Trade(symbol=symbol, entry_time=day_bars.index[entry_idx],
                              exit_time=day_bars.index[j], entry_price=entry_price,
                              exit_price=bar["close"], shares=0, exit_reason="vwap_cross",
                              stage="orb_vwap", risk_per_share=abs(entry_price - vwap.iloc[entry_idx]),
                              product="MIS", side=side)
            if bar.name.time() >= FORCE_CLOSE_TIME:
                return Trade(symbol=symbol, entry_time=day_bars.index[entry_idx],
                              exit_time=day_bars.index[j], entry_price=entry_price,
                              exit_price=bar["close"], shares=0, exit_reason="forced_close",
                              stage="orb_vwap", risk_per_share=abs(entry_price - vwap.iloc[entry_idx]),
                              product="MIS", side=side)
        last = day_bars.iloc[-1]
        return Trade(symbol=symbol, entry_time=day_bars.index[entry_idx],
                      exit_time=day_bars.index[-1], entry_price=entry_price,
                      exit_price=last["close"], shares=0, exit_reason="eod_data_end",
                      stage="orb_vwap", risk_per_share=abs(entry_price - vwap.iloc[entry_idx]),
                      product="MIS", side=side)
    return None


def run_orb_vwap(intraday_bars_by_symbol: dict[str, pd.DataFrame]) -> list[Trade]:
    trades = []
    for symbol, bars in intraday_bars_by_symbol.items():
        for session_date in sorted(set(bars.index.date)):
            day_bars = bars[bars.index.date == session_date]
            avg_or_vol = _avg_or_volume(bars, session_date, OR_VOLUME_LOOKBACK_DAYS)
            trade = _scan_session(symbol, day_bars, avg_or_vol)
            if trade is None:
                continue
            trade.shares = position_size(trade.entry_price)
            if trade.shares > 0:
                trades.append(trade)
    return trades
