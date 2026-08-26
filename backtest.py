"""Runs both stages across historical range, applies position sizing/exits, logs trades.

Backtest-only: no live/real-time fetching or order placement.

- run_stage1_only: full daily history (years) -- next-session open-to-close simulation,
  no intraday confirmation, tests whether the raw EOD screen has edge on its own.
- run_stage1_plus_stage2: last INTRADAY_HISTORY_DAYS days -- full Stage 1 -> Stage 2 ->
  intraday trade simulation with stops/trailing/forced close.

Stop distance uses ATR(14) computed on the session's own 5-min bars, not daily bars --
a daily-scale ATR is unreachable as a same-day stop and never triggers, silently turning
every trade into a hold-to-forced-close (found and fixed in the MomentumUS/NASDAQ sibling
of this project before porting the design here).
"""

from dataclasses import dataclass

import pandas as pd

from config import (
    ATR_STOP_MULT,
    CAPITAL,
    CAPITAL_PCT_PER_TRADE,
    FORCE_CLOSE_IST,
    MAX_CONCURRENT_POSITIONS,
    SWING_HIGH_LOOKBACK_DAYS,
)
from confirm_intraday import confirm_symbol, rank_candidates
from costs import total_cost
from indicators import atr as atr_indicator
from screener_eod import build_watchlists

FORCE_CLOSE_TIME = pd.to_datetime(FORCE_CLOSE_IST).time()


@dataclass
class Trade:
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    exit_reason: str
    stage: str  # "stage1", "stage1+2", or "swing"
    risk_per_share: float | None = None
    product: str = "MIS"  # "MIS" (intraday) or "CNC" (delivery) -- drives cost model
    side: str = "long"    # "long" or "short"

    @property
    def pnl(self) -> float:
        direction = 1 if self.side == "long" else -1
        return (self.exit_price - self.entry_price) * self.shares * direction

    @property
    def net_pnl(self) -> float:
        return self.pnl - total_cost(self.entry_price, self.exit_price, self.shares, self.product)

    @property
    def r_multiple(self) -> float | None:
        if not self.risk_per_share:
            return None
        direction = 1 if self.side == "long" else -1
        return (self.exit_price - self.entry_price) / self.risk_per_share * direction


def position_size(entry_price: float, capital: float = CAPITAL) -> int:
    return max(0, int((capital * CAPITAL_PCT_PER_TRADE) / entry_price))


# ---- Stage 1 only: next-session open-to-close, full daily history ----------

def run_stage1_only(bars_by_symbol: dict[str, pd.DataFrame]) -> list[Trade]:
    watchlists = build_watchlists(bars_by_symbol)
    trades = []
    for flag_date, symbols in sorted(watchlists.items()):
        for symbol in symbols:
            bars = bars_by_symbol[symbol]
            pos = bars.index.get_indexer([flag_date])[0]
            if pos + 1 >= len(bars):
                continue
            entry_bar = bars.iloc[pos + 1]
            shares = position_size(entry_bar["open"])
            if shares == 0:
                continue
            trades.append(Trade(
                symbol=symbol, entry_time=bars.index[pos + 1], exit_time=bars.index[pos + 1],
                entry_price=entry_bar["open"], exit_price=entry_bar["close"], shares=shares,
                exit_reason="session_close", stage="stage1",
            ))
    return trades


# ---- Stage 1 + Stage 2: intraday-confirmed entries, ATR/trail/forced exit --

def _simulate_intraday_exit(day_bars: pd.DataFrame, entry_idx: int, entry_price: float,
                             initial_stop: float) -> tuple[pd.Timestamp, float, str]:
    trail_distance = entry_price - initial_stop
    highest = entry_price
    stop = initial_stop
    for i in range(entry_idx + 1, len(day_bars)):
        bar = day_bars.iloc[i]
        if bar["low"] <= stop:
            return day_bars.index[i], stop, "stop"
        highest = max(highest, bar["high"])
        stop = max(stop, highest - trail_distance)
        if bar.name.time() >= FORCE_CLOSE_TIME:
            return day_bars.index[i], bar["close"], "forced_close"
    last = day_bars.iloc[-1]
    return day_bars.index[-1], last["close"], "eod_data_end"


def run_stage1_plus_stage2(daily_bars_by_symbol: dict[str, pd.DataFrame],
                            intraday_bars_by_symbol: dict[str, pd.DataFrame]) -> list[Trade]:
    watchlists = build_watchlists(daily_bars_by_symbol)
    trades = []

    all_session_dates = sorted({
        pd.Timestamp(d) for bars in intraday_bars_by_symbol.values() for d in bars.index.date
    })

    for session_date in all_session_dates:
        flagged = set()
        for flag_date, symbols in watchlists.items():
            if flag_date.date() < session_date.date():
                flagged.update(symbols)

        confirmations = []
        for symbol in flagged:
            if symbol not in intraday_bars_by_symbol or symbol not in daily_bars_by_symbol:
                continue
            intraday_bars = intraday_bars_by_symbol[symbol]
            if session_date.date() not in intraday_bars.index.date:
                continue
            daily_bars = daily_bars_by_symbol[symbol]
            confirmations.append(confirm_symbol(symbol, daily_bars, intraday_bars, session_date))

        primary, backups = rank_candidates(confirmations)
        chosen = [c for c in [primary, *backups] if c][:MAX_CONCURRENT_POSITIONS]

        for c in chosen:
            daily_bars = daily_bars_by_symbol[c.symbol]
            intraday_bars = intraday_bars_by_symbol[c.symbol]
            day_bars = intraday_bars[intraday_bars.index.date == session_date.date()]
            entry_price = day_bars["close"].iloc[c.entry_idx]

            intraday_atr = atr_indicator(day_bars).iloc[c.entry_idx]
            prior_daily = daily_bars[daily_bars.index.date < session_date.date()]
            swing_low = prior_daily["low"].iloc[-SWING_HIGH_LOOKBACK_DAYS:].min()
            atr_stop = entry_price - ATR_STOP_MULT * intraday_atr
            initial_stop = max(atr_stop, swing_low)  # tighter of the two

            shares = position_size(entry_price)
            if shares == 0:
                continue
            exit_time, exit_price, reason = _simulate_intraday_exit(
                day_bars, c.entry_idx, entry_price, initial_stop)
            trades.append(Trade(
                symbol=c.symbol, entry_time=day_bars.index[c.entry_idx], exit_time=exit_time,
                entry_price=entry_price, exit_price=exit_price, shares=shares,
                exit_reason=reason, stage="stage1+2", risk_per_share=entry_price - initial_stop,
            ))
    return trades
