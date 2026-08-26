"""Loads already-fetched bars straight from .cache/*.pkl by symbol, no Kite session
needed. tokens.json only has 200 of the 500 symbol->token mappings persisted (the
full-500 run that produced out/stage1_trades.csv resolved tokens in-process and never
saved that fuller map) -- today's Kite session token is expired and re-auth needs an
interactive browser login, so this loader works with the 200 symbols we can name.
"""

import json
import pickle
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).parent / ".cache"


def load_symbol_bars(daily_years: float | None = None) -> tuple[dict, dict]:
    """-> (daily_bars_by_symbol, intraday_bars_by_symbol), restricted to symbols with
    both a known token (tokens.json) and cached data of each kind.

    daily_years: if set, trims each symbol's daily bars to the trailing N years (e.g.
    2). Intraday bars are NOT trimmed by this -- the cache only holds the last
    INTRADAY_HISTORY_DAYS (60) days regardless, a Kite Connect free-plan cap on minute
    data, not a caching choice; there's no 2-year intraday history to slice down to.
    """
    tokens = json.loads((CACHE_DIR / "tokens.json").read_text())
    daily_by_token = pickle.loads((CACHE_DIR / "daily_bars.pkl").read_bytes())
    intraday_by_token = pickle.loads((CACHE_DIR / "intraday_bars.pkl").read_bytes())

    intraday_by_token = {key[0]: bars for key, bars in intraday_by_token.items()}

    daily = {}
    intraday = {}
    for symbol, token in tokens.items():
        if token in daily_by_token and len(daily_by_token[token]) >= 260:
            bars = daily_by_token[token]
            if daily_years is not None:
                cutoff = bars.index.max() - pd.DateOffset(years=daily_years)
                bars = bars[bars.index >= cutoff]
            daily[symbol] = bars
        if token in intraday_by_token and len(intraday_by_token[token]) > 0:
            intraday[symbol] = intraday_by_token[token]
    return daily, intraday
