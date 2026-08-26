import datetime
import unittest
import numpy as np
import pandas as pd

from indicators import standard_pivot_points, supertrend
from trishul_strategy import (
    NiftyOptionsSupertrendStrategy,
    OptionPosition,
    PositionType,
    StrategyConfig,
    run_nifty_options_backtest,
)



def _generate_synthetic_spot_data():
    dates = pd.date_range("2026-08-01", periods=5, freq="D")
    daily_records = []
    intraday_records = []

    spot = 24000.0
    for d in dates:
        open_p = spot
        high_p = open_p + 150
        low_p = open_p - 100
        close_p = open_p + 50
        spot = close_p
        daily_records.append({
            "open": open_p, "high": high_p, "low": low_p, "close": close_p, "volume": 1000000
        })

        # Generate 75 5-min bars for intraday (09:15 to 15:30)
        times = pd.date_range(f"{d.strftime('%Y-%m-%d')} 09:15", f"{d.strftime('%Y-%m-%d')} 15:25", freq="5min")
        curr_price = open_p
        for t in times:
            step = np.random.uniform(-10, 15)
            c_open = curr_price
            c_close = curr_price + step
            c_high = max(c_open, c_close) + 5
            c_low = min(c_open, c_close) - 5
            curr_price = c_close
            intraday_records.append({
                "date": t, "open": c_open, "high": c_high, "low": c_low, "close": c_close, "volume": 10000
            })

    daily_df = pd.DataFrame(daily_records, index=dates)
    intraday_df = pd.DataFrame(intraday_records).set_index("date")
    return daily_df, intraday_df


class TestNiftyOptionsStrategy(unittest.TestCase):



    def test_supertrend_and_pivots_calculation(self):
        daily_df, intraday_df = _generate_synthetic_spot_data()
        st_line, st_dir = supertrend(intraday_df, period=7, multiplier=3.0)
        pivots = standard_pivot_points(daily_df)

        self.assertEqual(len(st_line), len(intraday_df))
        self.assertEqual(len(st_dir), len(intraday_df))
        self.assertTrue("pp" in pivots.columns and "r1" in pivots.columns and "s1" in pivots.columns)
        self.assertTrue(set(st_dir.unique()).issubset({-1, 1}))

    def test_strategy_trade_limit_and_exits(self):
        config = StrategyConfig(max_trades_per_day=3, use_15m_mtf_filter=False, trail_stop_pct=0.20)
        strat = NiftyOptionsSupertrendStrategy(config=config)
        
        session_date = datetime.date(2026, 8, 20)
        strat.reset_session(session_date)
        self.assertEqual(strat.daily_trade_count, 0)

        candle = pd.Series({"open": 24100, "high": 24120, "low": 24090, "close": 24110})
        ts = pd.Timestamp("2026-08-20 09:30:00")
        
        # 1. Bullish Trigger (Close > ST and Close > R1)
        res = strat.evaluate_candle(
            current_candle=candle,
            supertrend_val=24050,
            supertrend_dir=1,
            pivot_r1=24080,
            pivot_s1=23950,
            candle_timestamp=ts,
            current_option_ltp=150.0,
        )
        self.assertEqual(res, "ENTRY_SHORT_PE")
        self.assertIsNotNone(strat.active_position)
        self.assertEqual(strat.active_position.position_type, PositionType.SHORT_PE)
        self.assertEqual(strat.daily_trade_count, 1)

        # 2. Option decays to 100 -> lowest_opt_price = 100, TSL @ 120
        decay_candle = pd.Series({"open": 24150, "high": 24180, "low": 24140, "close": 24170})
        ts_decay = pd.Timestamp("2026-08-20 10:00:00")
        strat.evaluate_candle(
            current_candle=decay_candle,
            supertrend_val=24060,
            supertrend_dir=1,
            pivot_r1=24080,
            pivot_s1=23950,
            candle_timestamp=ts_decay,
            current_option_ltp=100.0,
        )
        self.assertEqual(strat.active_position.lowest_opt_price, 100.0)

        # 3. Option rises back to 125 -> triggers 20% TSL (100 * 1.20 = 120)
        reversal_candle = pd.Series({"open": 24140, "high": 24145, "low": 24080, "close": 24090})
        ts_rev = pd.Timestamp("2026-08-20 10:30:00")
        res_exit = strat.evaluate_candle(
            current_candle=reversal_candle,
            supertrend_val=24060,
            supertrend_dir=1,
            pivot_r1=24080,
            pivot_s1=23950,
            candle_timestamp=ts_rev,
            current_option_ltp=125.0,
        )
        self.assertEqual(res_exit, "EXIT_TRAILING_STOP")
        self.assertIsNone(strat.active_position)
        self.assertEqual(len(strat.trade_history), 1)
        self.assertEqual(strat.trade_history[0].exit_reason, "TRAILING_STOP_20PCT")

    def test_backtest_runner(self):
        daily_df, intraday_df = _generate_synthetic_spot_data()
        trades, df = run_nifty_options_backtest(daily_df, intraday_df)
        self.assertIsInstance(trades, list)


if __name__ == "__main__":
    unittest.main()


