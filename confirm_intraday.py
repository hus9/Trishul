"""Stage 2 -- intraday confirmation on 5-min bars.

For each Stage-1 watchlist symbol, on the following session, checks:
4. gap up at open: open >= prior_close * GAP_UP_THRESHOLD
5. first 15-min volume >= MIN_FIRST_15MIN_RELATIVE_VOLUME x its 20-day average
6. price breaks above prior SWING_HIGH_LOOKBACK_DAYS-day swing high
7. price stays above intraday session VWAP
8. RSI(14) > RSI_MIN and rising, AND MACD line > signal line

Checks 4-5 are session-level gates (known ~15min after open). Checks 6-8 are scanned
bar-by-bar through the session using only data up to that bar (no lookahead) -- fires
the first moment all conditions align, entry priced at that bar's close. Same design as
the NASDAQ version (MomentumUS/confirm_intraday.py), where checking only the last bar of
the day was found to be a look-ahead bug.

Ranks passing symbols: PRIMARY = highest relative volume + strongest VWAP distance.
BACKUP = next 2-3 ranked candidates.
"""

from dataclasses import dataclass

import pandas as pd

from config import (
    GAP_UP_THRESHOLD,
    MIN_FIRST_15MIN_RELATIVE_VOLUME,
    RSI_MIN,
    RSI_PERIOD,
    SWING_HIGH_LOOKBACK_DAYS,
)
from indicators import macd, rsi, session_vwap

FIRST_15MIN_BARS = 3  # 3 x 5-min bars = first 15 minutes of the session


@dataclass
class Confirmation:
    symbol: str
    passed: bool
    entry_idx: int = 0  # position within that session's day_bars where confirmed
    relative_volume: float = 0.0
    vwap_distance: float = 0.0  # (close - vwap) / vwap at the confirmed bar
    reason: str = ""


def _first_15min_volume(day_bars: pd.DataFrame) -> float:
    return day_bars["volume"].iloc[:FIRST_15MIN_BARS].sum()


def _avg_first_15min_volume(intraday_bars: pd.DataFrame, lookback_days: int = 20) -> float:
    by_day = intraday_bars.groupby(intraday_bars.index.date)
    daily_first15 = by_day.apply(_first_15min_volume, include_groups=False)
    return daily_first15.iloc[-(lookback_days + 1):-1].mean()  # exclude today


def confirm_symbol(symbol: str, daily_bars: pd.DataFrame, intraday_bars: pd.DataFrame,
                    session_date: pd.Timestamp) -> Confirmation:
    """intraday_bars covers up through session_date; daily_bars covers the days before it."""
    day_bars = intraday_bars[intraday_bars.index.date == session_date.date()]
    if day_bars.empty:
        return Confirmation(symbol, False, reason="no intraday bars for session")

    prior_daily = daily_bars[daily_bars.index.date < session_date.date()]
    if len(prior_daily) < SWING_HIGH_LOOKBACK_DAYS:
        return Confirmation(symbol, False, reason="insufficient daily history")
    prior_close = prior_daily["close"].iloc[-1]
    swing_high = prior_daily["high"].iloc[-SWING_HIGH_LOOKBACK_DAYS:].max()

    session_open = day_bars["open"].iloc[0]
    if session_open < prior_close * GAP_UP_THRESHOLD:
        return Confirmation(symbol, False, reason="no gap up")

    if len(day_bars) <= FIRST_15MIN_BARS:
        return Confirmation(symbol, False, reason="session too short to confirm")

    prior_intraday = intraday_bars[intraday_bars.index.date < session_date.date()]
    avg_first15 = _avg_first_15min_volume(prior_intraday) if len(prior_intraday) else float("nan")
    first15_vol = _first_15min_volume(day_bars)
    rvol = first15_vol / avg_first15 if avg_first15 and avg_first15 == avg_first15 else 0.0
    if rvol < MIN_FIRST_15MIN_RELATIVE_VOLUME:
        return Confirmation(symbol, False, relative_volume=rvol, reason="first-15min volume too low")

    vwap = session_vwap(day_bars)
    close = day_bars["close"]
    r = rsi(close, RSI_PERIOD)
    macd_line, signal_line = macd(close)

    start = max(FIRST_15MIN_BARS, RSI_PERIOD)
    for i in range(start, len(day_bars)):
        if close.iloc[i] <= swing_high:
            continue
        if (close.iloc[:i + 1] < vwap.iloc[:i + 1]).any():
            continue
        if not (r.iloc[i] > RSI_MIN and r.iloc[i] > r.iloc[i - 1] and macd_line.iloc[i] > signal_line.iloc[i]):
            continue
        vwap_distance = (close.iloc[i] - vwap.iloc[i]) / vwap.iloc[i]
        return Confirmation(symbol, True, entry_idx=i, relative_volume=rvol, vwap_distance=vwap_distance)

    return Confirmation(symbol, False, relative_volume=rvol, reason="breakout/VWAP/RSI-MACD never aligned")


def rank_candidates(confirmations: list[Confirmation]) -> tuple[Confirmation | None, list[Confirmation]]:
    """(primary, backups) -- ranked by relative_volume + vwap_distance, highest first."""
    passed = [c for c in confirmations if c.passed]
    passed.sort(key=lambda c: c.relative_volume + c.vwap_distance, reverse=True)
    if not passed:
        return None, []
    return passed[0], passed[1:4]
