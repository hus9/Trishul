"""Stage 1 -- EOD screen on daily bars, unlimited history.

For each ticker, each day, flags it as next-session watchlist material if all of:
1. close-to-close gain > MIN_DAILY_GAIN_PCT
2. close near the day's high: close >= high - CLOSE_NEAR_HIGH_FRACTION*(high-low)
3. relative volume >= MIN_RELATIVE_VOLUME
"""

import pandas as pd

from config import CLOSE_NEAR_HIGH_FRACTION, MIN_DAILY_GAIN_PCT, MIN_RELATIVE_VOLUME
from indicators import relative_volume


def screen_ticker(bars: pd.DataFrame) -> pd.Series:
    """Returns a bool Series aligned to bars.index -- True on days that pass all 3 checks."""
    gain = bars["close"].pct_change() > MIN_DAILY_GAIN_PCT
    near_high = bars["close"] >= bars["high"] - CLOSE_NEAR_HIGH_FRACTION * (bars["high"] - bars["low"])
    rvol = relative_volume(bars["volume"]) >= MIN_RELATIVE_VOLUME
    return gain & near_high & rvol


def build_watchlists(bars_by_ticker: dict[str, pd.DataFrame]) -> dict[pd.Timestamp, list[str]]:
    """date -> tickers that passed the Stage 1 screen on that date, i.e. the
    watchlist to run Stage 2 confirmation against on the *next* session."""
    watchlists: dict[pd.Timestamp, list[str]] = {}
    for ticker, bars in bars_by_ticker.items():
        passed = screen_ticker(bars)
        for date in bars.index[passed]:
            watchlists.setdefault(date, []).append(ticker)
    return watchlists
