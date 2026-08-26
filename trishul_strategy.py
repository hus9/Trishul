"""NIFTY 50 Intraday Options Selling Strategy — Optimized Production Engine.

========================================================================================
STRATEGY SPECIFICATION & ARCHITECTURE
========================================================================================
- Underlying Instrument : NIFTY 50 Spot Index (Used for signals & indicators)
- Traded Instrument     : NIFTY Weekly Options (ATM Strike, nearest 50-strike round-off)
- Timeframe             : 5-minute OHLCV candles (Primary) + 15-minute (MTF Confirmation)
- Trading Segment       : NFO Options (MIS Intraday Product)
- Position Sizing       : 1 Lot (65 units) per active trade
- Daily Trade Cap       : Maximum 3 trades per session

Indicators & Filters:
1. Primary Supertrend: Period = 7, Multiplier = 3.0 (on 5-minute Spot Close)
2. Standard Daily Floor Pivots: Computed from prior session Spot H/L/C:
   PP = (H_prev + L_prev + C_prev) / 3
   R1 = 2 * PP - L_prev
   S1 = 2 * PP - H_prev
3. Multi-Timeframe Filter: 15-minute Supertrend (7, 3.0) direction must confirm 5-minute signal.

Entry Logic (Checked strictly at 5-minute candle close before 14:15 IST):
- Bullish Trigger (Sell ATM Put):
  * (5m Close > 5m Supertrend) AND (5m Close > Daily R1) AND (15m Supertrend is Bullish)
  * Action: Identify ATM strike, fetch weekly Put (PE), place MARKET SELL for 1 Lot.
- Bearish Trigger (Sell ATM Call):
  * (5m Close < 5m Supertrend) AND (5m Close < Daily S1) AND (15m Supertrend is Bearish)
  * Action: Identify ATM strike, fetch weekly Call (CE), place MARKET SELL for 1 Lot.

Exit Logic & Triple-Protection Risk Guardrails:
1. Dynamic Trailing Stop Loss (TSL):
   * Trailing 20% on the option premium from the lowest option price reached.
   * Ratchets down as the short option decays, locking in accumulated theta gains.
2. Hard Emergency Loss Cap:
   * Fixed 35% maximum loss from entry premium to prevent single-candle spike risk.
3. Supertrend Reversal Flip:
   * Short PE exits immediately if 5-min Close < Supertrend (flips Red).
   * Short CE exits immediately if 5-min Close > Supertrend (flips Green).
4. End of Day Square-Off:
   * Unconditional Market Buy to square off all open positions at 15:15 IST.
5. Time-of-Day Execution Cutoff:
   * No new entries permitted after 14:15 IST (manages existing positions only).

Cost Model:
- Exact 2026 Indian Equity Derivatives taxation and friction (STT, Zerodha brokerage cap
  of Rs 20/order, Exchange turnover fee, SEBI turnover charge, Stamp duty, and 18% GST).
"""

from __future__ import annotations

import datetime
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException

from costs import total_cost
from indicators import atr as atr_indicator, standard_pivot_points, supertrend

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("NiftyOptionsOptimizedStrategy")


# ============================================================================
# Optimized Strategy Configuration
# ============================================================================

@dataclass(frozen=True)
class StrategyConfig:
    underlying_name: str = "NIFTY"
    underlying_exchange: str = "NSE"
    nfo_exchange: str = "NFO"
    strike_step: int = 50
    lot_size: int = 65  # 1 lot standard
    max_trades_per_day: int = 3
    supertrend_period: int = 7
    supertrend_multiplier: float = 3.0
    product: str = "MIS"  # Margin Intraday Square-off
    trail_stop_pct: float = 0.20  # 20% Trailing Stop Loss on option premium
    hard_loss_cap_pct: float = 0.35  # 35% hard emergency stop-loss
    target_profit_pct: Optional[float] = None  # Optional profit target (e.g. 0.60)
    use_15m_mtf_filter: bool = True  # 15-minute Supertrend multi-timeframe filter
    entry_cutoff_time: datetime.time = datetime.time(14, 15, 0)  # No entries after 14:15 IST
    square_off_time: datetime.time = datetime.time(15, 15, 0)   # Mandatory EOD exit
    market_open_time: datetime.time = datetime.time(9, 15, 0)
    candle_timeframe_minutes: int = 5


class PositionType(str, Enum):
    SHORT_PE = "SHORT_PE"
    SHORT_CE = "SHORT_CE"


@dataclass
class OptionPosition:
    position_type: PositionType
    tradingsymbol: str
    instrument_token: int
    strike: int
    option_type: str  # "CE" or "PE"
    expiry: datetime.date
    quantity: int
    entry_time: pd.Timestamp
    entry_price: float
    entry_spot: float
    lowest_opt_price: float
    extreme_spot: float
    order_id: Optional[str] = None


@dataclass
class StrategyTradeRecord:
    trade_id: int
    date: datetime.date
    position_type: PositionType
    tradingsymbol: str
    strike: int
    expiry: str
    quantity: int
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    entry_price: float
    exit_price: Optional[float]
    entry_spot: float
    exit_spot: Optional[float]
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    brokerage_and_taxes: float


# ============================================================================
# Option Contract & Strike Resolver
# ============================================================================

class OptionContractResolver:
    """Resolves NIFTY weekly expiry option contracts and ATM strikes via Kite."""

    def __init__(self, kite: KiteConnect, nfo_exchange: str = "NFO"):
        self.kite = kite
        self.nfo_exchange = nfo_exchange
        self._nfo_instruments: Optional[pd.DataFrame] = None
        self._last_fetch_date: Optional[datetime.date] = None

    def refresh_instruments(self, force: bool = False) -> None:
        today = datetime.date.today()
        if self._nfo_instruments is None or self._last_fetch_date != today or force:
            logger.info("Fetching fresh instrument dump from %s...", self.nfo_exchange)
            records = self.kite.instruments(self.nfo_exchange)
            df = pd.DataFrame(records)
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
            self._nfo_instruments = df[df["name"] == "NIFTY"]
            self._last_fetch_date = today
            logger.info("Loaded %d NIFTY option instruments.", len(self._nfo_instruments))

    def get_current_weekly_expiry(self, current_date: datetime.date) -> datetime.date:
        self.refresh_instruments()
        assert self._nfo_instruments is not None
        valid_expiries = sorted(
            [exp for exp in self._nfo_instruments["expiry"].unique() if exp >= current_date]
        )
        if not valid_expiries:
            raise ValueError(f"No active option expiries found on or after {current_date}")
        return valid_expiries[0]

    def resolve_atm_strike(self, spot_price: float, strike_step: int = 50) -> int:
        return int(round(spot_price / strike_step) * strike_step)

    def resolve_contract(
        self, spot_price: float, option_type: str, current_date: datetime.date
    ) -> Tuple[str, int, int, datetime.date]:
        self.refresh_instruments()
        assert self._nfo_instruments is not None
        
        strike = self.resolve_atm_strike(spot_price)
        expiry = self.get_current_weekly_expiry(current_date)
        
        df = self._nfo_instruments
        matches = df[
            (df["expiry"] == expiry)
            & (df["strike"] == strike)
            & (df["instrument_type"] == option_type.upper())
        ]
        if matches.empty:
            raise ValueError(
                f"Option contract not found for NIFTY {expiry} {strike} {option_type}"
            )
        
        row = matches.iloc[0]
        return row["tradingsymbol"], int(row["instrument_token"]), strike, expiry


# ============================================================================
# Order Execution Engine
# ============================================================================

class ExecutionManager:
    """Manages order placement, retries, and market square-offs on Kite Connect."""

    def __init__(self, kite: KiteConnect, config: StrategyConfig):
        self.kite = kite
        self.config = config

    def place_market_sell(self, tradingsymbol: str, quantity: int) -> Optional[str]:
        return self._execute_order(
            tradingsymbol=tradingsymbol,
            transaction_type=self.kite.TRANSACTION_TYPE_SELL,
            quantity=quantity,
            order_type=self.kite.ORDER_TYPE_MARKET,
            product=self.config.product,
            tag="ENTRY_SELL",
        )

    def place_market_buy(self, tradingsymbol: str, quantity: int) -> Optional[str]:
        return self._execute_order(
            tradingsymbol=tradingsymbol,
            transaction_type=self.kite.TRANSACTION_TYPE_BUY,
            quantity=quantity,
            order_type=self.kite.ORDER_TYPE_MARKET,
            product=self.config.product,
            tag="EXIT_BUY",
        )

    def _execute_order(
        self,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        tag: str,
        max_retries: int = 3,
    ) -> Optional[str]:
        for attempt in range(1, max_retries + 1):
            try:
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.config.nfo_exchange,
                    tradingsymbol=tradingsymbol,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    product=product,
                    order_type=order_type,
                    tag=tag,
                )
                logger.info(
                    "Order placed: %s %d %s [%s] -> OrderID: %s",
                    transaction_type,
                    quantity,
                    tradingsymbol,
                    product,
                    order_id,
                )
                return order_id
            except KiteException as e:
                logger.error("Kite error placing order (attempt %d/%d): %s", attempt, max_retries, e)
            except Exception as e:
                logger.error("Network error placing order (attempt %d/%d): %s", attempt, max_retries, e)
            time.sleep(1.0 * attempt)
        return None

    def fetch_execution_price(self, order_id: Optional[str], default_price: float) -> float:
        if not order_id:
            return default_price
        try:
            order_history = self.kite.order_history(order_id)
            for state in reversed(order_history):
                if state.get("status") == "COMPLETE" and state.get("average_price", 0) > 0:
                    return float(state["average_price"])
        except Exception as e:
            logger.warning("Could not fetch execution price for order %s: %s", order_id, e)
        return default_price


# ============================================================================
# Optimized Strategy State Machine
# ============================================================================

class NiftyOptionsSupertrendStrategy:
    """Core Strategy State Machine incorporating TSL, Hard Cap, and MTF filters."""

    def __init__(
        self,
        config: Optional[StrategyConfig] = None,
        kite: Optional[KiteConnect] = None,
        contract_resolver: Optional[OptionContractResolver] = None,
        execution_manager: Optional[ExecutionManager] = None,
    ):
        self.config = config or StrategyConfig()
        self.kite = kite
        self.resolver = contract_resolver or (OptionContractResolver(kite) if kite else None)
        self.executor = execution_manager or (ExecutionManager(kite, self.config) if kite else None)

        self.current_date: Optional[datetime.date] = None
        self.daily_trade_count: int = 0
        self.active_position: Optional[OptionPosition] = None
        self.trade_history: List[StrategyTradeRecord] = []
        self._trade_id_counter: int = 0

    def reset_session(self, session_date: datetime.date) -> None:
        self.current_date = session_date
        self.daily_trade_count = 0
        self.active_position = None
        logger.info("Session initialized for %s. Daily trade count reset.", session_date)

    def evaluate_candle(
        self,
        current_candle: pd.Series,
        supertrend_val: float,
        supertrend_dir: int,
        pivot_r1: float,
        pivot_s1: float,
        candle_timestamp: pd.Timestamp,
        supertrend_15m_dir: int = 0,
        current_option_ltp: Optional[float] = None,
    ) -> Optional[str]:
        candle_date = candle_timestamp.date()
        candle_time = candle_timestamp.time()
        close_price = current_candle["close"]

        if self.current_date != candle_date:
            self.reset_session(candle_date)

        # ---------------------------------------------------------------------
        # 1. Mandatory End of Day Square-Off (15:15 IST)
        # ---------------------------------------------------------------------
        if candle_time >= self.config.square_off_time:
            if self.active_position is not None:
                self._exit_position(
                    exit_time=candle_timestamp,
                    exit_spot=close_price,
                    exit_option_price=current_option_ltp or 0.0,
                    exit_reason="EOD_FORCED_SQUARE_OFF",
                )
            return "SQUARE_OFF_EOD"

        # ---------------------------------------------------------------------
        # 2. Position Management & Exit Evaluation (TSL, Hard Cap, Flip)
        # ---------------------------------------------------------------------
        if self.active_position is not None:
            pos = self.active_position
            entry_p = pos.entry_price
            curr_opt = current_option_ltp if current_option_ltp is not None else entry_p

            # Update lowest option price reached (peak decay profit)
            pos.lowest_opt_price = min(pos.lowest_opt_price, curr_opt)
            lowest_p = pos.lowest_opt_price

            # Exit Rule A: Profit Target (if configured)
            if self.config.target_profit_pct and curr_opt <= entry_p * (1.0 - self.config.target_profit_pct):
                self._exit_position(
                    exit_time=candle_timestamp,
                    exit_spot=close_price,
                    exit_option_price=curr_opt,
                    exit_reason="TARGET_PROFIT",
                )
                return "EXIT_TARGET_PROFIT"

            # Exit Rule B: Hard Emergency Loss Cap
            if self.config.hard_loss_cap_pct and curr_opt >= entry_p * (1.0 + self.config.hard_loss_cap_pct):
                self._exit_position(
                    exit_time=candle_timestamp,
                    exit_spot=close_price,
                    exit_option_price=entry_p * (1.0 + self.config.hard_loss_cap_pct),
                    exit_reason="HARD_LOSS_CAP",
                )
                return "EXIT_HARD_LOSS_CAP"

            # Exit Rule C: 20% Trailing Stop Loss on Option Premium
            if self.config.trail_stop_pct:
                trail_stop_price = lowest_p * (1.0 + self.config.trail_stop_pct)
                if curr_opt >= trail_stop_price:
                    self._exit_position(
                        exit_time=candle_timestamp,
                        exit_spot=close_price,
                        exit_option_price=trail_stop_price,
                        exit_reason="TRAILING_STOP_20PCT",
                    )
                    return "EXIT_TRAILING_STOP"

            # Exit Rule D: Supertrend Trend Reversal Flip
            if pos.position_type == PositionType.SHORT_PE:
                if close_price < supertrend_val or supertrend_dir == -1:
                    self._exit_position(
                        exit_time=candle_timestamp,
                        exit_spot=close_price,
                        exit_option_price=curr_opt,
                        exit_reason="SUPERTREND_FLIP_BEARISH",
                    )
                    return "EXIT_SHORT_PE"

            elif pos.position_type == PositionType.SHORT_CE:
                if close_price > supertrend_val or supertrend_dir == 1:
                    self._exit_position(
                        exit_time=candle_timestamp,
                        exit_spot=close_price,
                        exit_option_price=curr_opt,
                        exit_reason="SUPERTREND_FLIP_BULLISH",
                    )
                    return "EXIT_SHORT_CE"

            return "HOLDING_POSITION"

        # ---------------------------------------------------------------------
        # 3. Check Daily Trade Limits & Time-of-Day Cutoff
        # ---------------------------------------------------------------------
        if self.daily_trade_count >= self.config.max_trades_per_day:
            return "DAILY_TRADE_LIMIT_REACHED"

        if candle_time >= self.config.entry_cutoff_time:
            return "AFTER_ENTRY_CUTOFF"

        # ---------------------------------------------------------------------
        # 4. Entry Signal Checks (with 15m MTF Confirmation)
        # ---------------------------------------------------------------------
        mtf_bullish = not self.config.use_15m_mtf_filter or (supertrend_15m_dir == 1)
        mtf_bearish = not self.config.use_15m_mtf_filter or (supertrend_15m_dir == -1)

        is_bullish = (close_price > supertrend_val) and (close_price > pivot_r1) and mtf_bullish
        is_bearish = (close_price < supertrend_val) and (close_price < pivot_s1) and mtf_bearish

        if is_bullish:
            self._enter_position(
                position_type=PositionType.SHORT_PE,
                spot_price=close_price,
                candle_high=current_candle["high"],
                candle_low=current_candle["low"],
                entry_time=candle_timestamp,
                option_ltp=current_option_ltp,
            )
            return "ENTRY_SHORT_PE"

        elif is_bearish:
            self._enter_position(
                position_type=PositionType.SHORT_CE,
                spot_price=close_price,
                candle_high=current_candle["high"],
                candle_low=current_candle["low"],
                entry_time=candle_timestamp,
                option_ltp=current_option_ltp,
            )
            return "ENTRY_SHORT_CE"

        return "NO_SIGNAL"

    def _enter_position(
        self,
        position_type: PositionType,
        spot_price: float,
        candle_high: float,
        candle_low: float,
        entry_time: pd.Timestamp,
        option_ltp: Optional[float] = None,
    ) -> None:
        option_type = "PE" if position_type == PositionType.SHORT_PE else "CE"
        strike = int(round(spot_price / self.config.strike_step) * self.config.strike_step)
        order_id = None
        tradingsymbol = f"NIFTY_{strike}_{option_type}"
        token = 0
        expiry = entry_time.date()

        if self.resolver and self.kite:
            try:
                tradingsymbol, token, strike, expiry = self.resolver.resolve_contract(
                    spot_price=spot_price,
                    option_type=option_type,
                    current_date=entry_time.date(),
                )
            except Exception as e:
                logger.error("Failed to resolve contract: %s", e)

        if self.executor and self.kite:
            order_id = self.executor.place_market_sell(tradingsymbol, self.config.lot_size)
            fill_price = self.executor.fetch_execution_price(order_id, option_ltp or 100.0)
        else:
            fill_price = option_ltp if option_ltp is not None else 100.0

        self.active_position = OptionPosition(
            position_type=position_type,
            tradingsymbol=tradingsymbol,
            instrument_token=token,
            strike=strike,
            option_type=option_type,
            expiry=expiry,
            quantity=self.config.lot_size,
            entry_time=entry_time,
            entry_price=fill_price,
            entry_spot=spot_price,
            lowest_opt_price=fill_price,
            extreme_spot=candle_high if position_type == PositionType.SHORT_PE else candle_low,
            order_id=order_id,
        )
        self.daily_trade_count += 1
        logger.info(
            "Entered [%s] %s @ %.2f (Spot: %.2f) | Trade #%d today",
            position_type.value,
            tradingsymbol,
            fill_price,
            spot_price,
            self.daily_trade_count,
        )

    def _exit_position(
        self,
        exit_time: pd.Timestamp,
        exit_spot: float,
        exit_option_price: float,
        exit_reason: str,
    ) -> None:
        pos = self.active_position
        if pos is None:
            return

        exit_price = exit_option_price
        if self.executor and self.kite:
            exit_order_id = self.executor.place_market_buy(pos.tradingsymbol, pos.quantity)
            exit_price = self.executor.fetch_execution_price(exit_order_id, exit_option_price)

        gross_pnl = (pos.entry_price - exit_price) * pos.quantity
        costs = total_cost(pos.entry_price, exit_price, pos.quantity, self.config.product)
        net_pnl = gross_pnl - costs

        self._trade_id_counter += 1
        record = StrategyTradeRecord(
            trade_id=self._trade_id_counter,
            date=exit_time.date(),
            position_type=pos.position_type,
            tradingsymbol=pos.tradingsymbol,
            strike=pos.strike,
            expiry=str(pos.expiry),
            quantity=pos.quantity,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_spot=pos.entry_spot,
            exit_spot=exit_spot,
            exit_reason=exit_reason,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            brokerage_and_taxes=costs,
        )
        self.trade_history.append(record)
        logger.info(
            "Exited [%s] %s @ %.2f [%s] | Net PnL: ₹%.2f (Friction: ₹%.2f)",
            pos.position_type.value,
            pos.tradingsymbol,
            exit_price,
            exit_reason,
            net_pnl,
            costs,
        )
        self.active_position = None


# ============================================================================
# Optimized Historical Backtesting Engine
# ============================================================================

def run_nifty_options_backtest(
    spot_daily_bars: pd.DataFrame,
    spot_intraday_bars: pd.DataFrame,
    config: Optional[StrategyConfig] = None,
) -> Tuple[List[StrategyTradeRecord], pd.DataFrame]:
    cfg = config or StrategyConfig()
    strategy = NiftyOptionsSupertrendStrategy(config=cfg)

    # Precompute 5-minute and 15-minute Supertrend
    st_line_5m, st_dir_5m = supertrend(
        spot_intraday_bars,
        period=cfg.supertrend_period,
        multiplier=cfg.supertrend_multiplier,
    )
    df_15m = spot_intraday_bars.resample("15min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna()
    st_line_15m, st_dir_15m = supertrend(
        df_15m,
        period=cfg.supertrend_period,
        multiplier=cfg.supertrend_multiplier,
    )
    pivots = standard_pivot_points(spot_daily_bars)

    session_dates = sorted(set(spot_intraday_bars.index.date))

    for s_date in session_dates:
        day_bars = spot_intraday_bars[spot_intraday_bars.index.date == s_date]
        day_pivots = pivots[pivots.index.date == s_date]
        if day_pivots.empty or len(day_bars) < cfg.supertrend_period:
            continue

        r1 = day_pivots["r1"].iloc[0]
        s1 = day_pivots["s1"].iloc[0]

        strategy.reset_session(s_date)

        for ts, candle in day_bars.iterrows():
            st_val = st_line_5m.loc[ts]
            st_direction = st_dir_5m.loc[ts]

            # 15m MTF direction lookup
            ts_15m = ts.floor("15min")
            st_15m_d = st_dir_15m.loc[ts_15m] if ts_15m in st_dir_15m.index else st_direction

            spot_close = candle["close"]
            base_atm_premium = spot_close * 0.008

            if strategy.active_position:
                pos = strategy.active_position
                spot_delta_move = spot_close - pos.entry_spot
                if pos.position_type == PositionType.SHORT_PE:
                    simulated_opt_price = max(1.0, pos.entry_price - (0.50 * spot_delta_move))
                else:
                    simulated_opt_price = max(1.0, pos.entry_price + (0.50 * spot_delta_move))
            else:
                simulated_opt_price = base_atm_premium

            strategy.evaluate_candle(
                current_candle=candle,
                supertrend_val=st_val,
                supertrend_dir=st_direction,
                pivot_r1=r1,
                pivot_s1=s1,
                candle_timestamp=pd.Timestamp(ts),
                supertrend_15m_dir=st_15m_d,
                current_option_ltp=simulated_opt_price,
            )

    trades = strategy.trade_history
    trade_df = pd.DataFrame([t.__dict__ for t in trades]) if trades else pd.DataFrame()
    return trades, trade_df


if __name__ == "__main__":
    print("NIFTY Options Optimized Strategy Loaded.")
