"""RSI, MACD, VWAP, ATR, relative volume -- shared by the EOD screen and intraday confirm."""

import pandas as pd


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    prior_close = bars["close"].shift(1)
    tr = pd.concat([
        bars["high"] - bars["low"],
        (bars["high"] - prior_close).abs(),
        (bars["low"] - prior_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    macd_line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def relative_volume(volume: pd.Series, lookback: int = 20) -> pd.Series:
    return volume / volume.rolling(lookback).mean()


def bollinger_bands(close: pd.Series, period: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + num_std * std, mid, mid - num_std * std


def session_vwap(intraday_bars: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP reset at each session's first bar. intraday_bars.index is
    naive local (US/Eastern) timestamps, one row per session-day grouping key."""
    typical = (intraday_bars["high"] + intraday_bars["low"] + intraday_bars["close"]) / 3
    pv = typical * intraday_bars["volume"]
    day = intraday_bars.index.date
    cum_pv = pv.groupby(day).cumsum()
    cum_vol = intraday_bars["volume"].groupby(day).cumsum()
    return cum_pv / cum_vol


def supertrend(bars: pd.DataFrame, period: int = 7, multiplier: float = 3.0) -> tuple[pd.Series, pd.Series]:
    """Computes Supertrend indicator on OHLC bars.
    Returns:
        (supertrend_line, direction)
        direction: +1 for Bullish (Green, Close > Supertrend), -1 for Bearish (Red, Close < Supertrend)
    """
    hl2 = (bars["high"] + bars["low"]) / 2.0
    prior_close = bars["close"].shift(1)
    tr = pd.concat([
        bars["high"] - bars["low"],
        (bars["high"] - prior_close).abs(),
        (bars["low"] - prior_close).abs(),
    ], axis=1).max(axis=1)
    
    # Wilder's smoothing for ATR
    atr_val = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    
    basic_upper = hl2 + (multiplier * atr_val)
    basic_lower = hl2 - (multiplier * atr_val)
    
    n = len(bars)
    final_upper = [0.0] * n
    final_lower = [0.0] * n
    trend = [1] * n  # 1: green/bullish, -1: red/bearish
    st_line = [0.0] * n
    
    close = bars["close"].values
    b_upper = basic_upper.values
    b_lower = basic_lower.values
    
    for i in range(1, n):
        # Final Upper Band
        if b_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = b_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]
            
        # Final Lower Band
        if b_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = b_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]
            
        # Supertrend direction
        prev_trend = trend[i - 1]
        if prev_trend == 1:
            if close[i] < final_lower[i]:
                trend[i] = -1
                st_line[i] = final_upper[i]
            else:
                trend[i] = 1
                st_line[i] = final_lower[i]
        else:
            if close[i] > final_upper[i]:
                trend[i] = 1
                st_line[i] = final_lower[i]
            else:
                trend[i] = -1
                st_line[i] = final_upper[i]
                
    st_series = pd.Series(st_line, index=bars.index)
    dir_series = pd.Series(trend, index=bars.index)
    return st_series, dir_series


def standard_pivot_points(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """Standard Floor Pivot Points (PP, R1, S1) computed from the PRIOR session's H/L/C.
    Returns:
        DataFrame with columns ['pp', 'r1', 's1'] indexed by daily_bars.index
    """
    prior_high = daily_bars["high"].shift(1)
    prior_low = daily_bars["low"].shift(1)
    prior_close = daily_bars["close"].shift(1)
    
    pp = (prior_high + prior_low + prior_close) / 3.0
    r1 = (2.0 * pp) - prior_low
    s1 = (2.0 * pp) - prior_high
    
    return pd.DataFrame({"pp": pp, "r1": r1, "s1": s1}, index=daily_bars.index)

