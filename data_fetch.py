"""Kite Connect historical-data wrappers.

Kite's historical API caps the date span per request (interval-dependent), not total
history retained -- unlike yfinance's hard ~60-day minute-data wall, Kite will serve
5-min bars from a year+ back if you chunk the requests. So Stage 2 here isn't stuck at
60 days the way MomentumUS was; INTRADAY_HISTORY_DAYS in config just picks how far back
you ask for.

Backtest-only: no live/real-time fetching or order placement anywhere in this project.
"""

import pickle
import time
from pathlib import Path

import pandas as pd
import requests

from config import EXCHANGE

# Kite's per-request max span (days) by interval -- from Kite Connect API docs.
_MAX_SPAN_DAYS = {"day": 2000, "minute": 60, "5minute": 100, "15minute": 200, "60minute": 400}

_instrument_cache: dict[str, int] | None = None

# On-disk bar cache, keyed by instrument_token -- avoids re-hitting Kite's rate-limited
# historical API for data already fetched. daily cached by token only (years is always
# the same full-history call); intraday cached by (token, days, interval) since those vary.
_CACHE_DIR = Path(__file__).parent / ".cache"
_DAILY_CACHE_PATH = _CACHE_DIR / "daily_bars.pkl"
_INTRADAY_CACHE_PATH = _CACHE_DIR / "intraday_bars.pkl"
_daily_cache: dict[int, pd.DataFrame] | None = None
_intraday_cache: dict[tuple, pd.DataFrame] | None = None


def _load_pickle(path: Path) -> dict:
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return {}


def _save_pickle(path: Path, obj: dict) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def resolve_tokens(kite, symbols: list[str]) -> dict[str, int]:
    """symbol -> instrument_token, via a single instruments() dump (cached in-process)."""
    global _instrument_cache
    if _instrument_cache is None:
        dump = kite.instruments(EXCHANGE)
        _instrument_cache = {row["tradingsymbol"]: row["instrument_token"] for row in dump}
    missing = [s for s in symbols if s not in _instrument_cache]
    if missing:
        print(f"not found on {EXCHANGE}: {missing}")
    return {s: _instrument_cache[s] for s in symbols if s in _instrument_cache}


def _clean(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(records).set_index("date")[["open", "high", "low", "close", "volume"]]
    idx = pd.to_datetime(df.index)
    # Kite returns tz-aware IST timestamps -- drop the tz tag but keep the IST wall-clock
    # value (tz_localize(None) on an already-aware index would raise; tz_convert first
    # is a no-op here since it's already IST, then tz_localize(None) strips the tag).
    df.index = idx.tz_convert("Asia/Kolkata").tz_localize(None) if idx.tz is not None else idx
    return df


def _fetch_chunked(kite, token: int, interval: str, from_date: pd.Timestamp,
                    to_date: pd.Timestamp) -> pd.DataFrame:
    """Kite rejects requests spanning more than _MAX_SPAN_DAYS[interval] -- walk
    backward in chunks and concatenate. One rate-limit-friendly sleep between calls."""
    span = pd.Timedelta(days=_MAX_SPAN_DAYS[interval])
    chunks = []
    window_end = to_date
    while window_end > from_date:
        window_start = max(from_date, window_end - span)
        for attempt in range(3):
            try:
                records = kite.historical_data(token, window_start, window_end, interval)
                break
            except requests.exceptions.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))  # transient network blip -- backoff and retry
        chunks.append(_clean(records))
        window_end = window_start - pd.Timedelta(days=1)
        time.sleep(0.35)  # Kite historical API: ~3 req/sec limit
    if not chunks:
        return _clean([])
    return pd.concat(chunks).sort_index().loc[~pd.concat(chunks).sort_index().index.duplicated()]


def fetch_daily_bars(kite, token: int, years: int = 8) -> pd.DataFrame:
    global _daily_cache
    if _daily_cache is None:
        _daily_cache = _load_pickle(_DAILY_CACHE_PATH)
    if token in _daily_cache:
        return _daily_cache[token]
    to_date = pd.Timestamp.now().normalize()
    from_date = to_date - pd.Timedelta(days=365 * years)
    bars = _fetch_chunked(kite, token, "day", from_date, to_date)
    _daily_cache[token] = bars
    _save_pickle(_DAILY_CACHE_PATH, _daily_cache)
    return bars


def fetch_intraday_bars(kite, token: int, days: int, interval: str = "5minute") -> pd.DataFrame:
    global _intraday_cache
    if _intraday_cache is None:
        _intraday_cache = _load_pickle(_INTRADAY_CACHE_PATH)
    key = (token, days, interval)
    if key in _intraday_cache:
        return _intraday_cache[key]
    to_date = pd.Timestamp.now()
    from_date = to_date - pd.Timedelta(days=days)
    bars = _fetch_chunked(kite, token, interval, from_date, to_date)
    _intraday_cache[key] = bars
    _save_pickle(_INTRADAY_CACHE_PATH, _intraday_cache)
    return bars
