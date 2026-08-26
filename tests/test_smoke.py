import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from backtest import Trade, _simulate_intraday_exit, position_size, run_stage1_only
from bollinger_meanrev import run_bollinger_meanrev
from confirm_intraday import confirm_symbol
from costs import total_cost
from camarilla import camarilla_levels, run_camarilla
from indicators import bollinger_bands, macd, relative_volume, rsi, session_vwap
from orb_confluence import run_orb_confluence
from orb_vwap import run_orb_vwap
from screener_eod import screen_ticker
from swing_engine import run_swing


def _fake_daily_bars(n=300, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    close = pd.Series(100 + rng.normal(0, 1, n).cumsum(), index=dates)
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(rng.uniform(1e6, 2e6, n), index=dates)
    close.iloc[250] = close.iloc[249] * 1.05
    high.iloc[250] = close.iloc[250] + 0.05
    low.iloc[250] = close.iloc[249]
    volume.iloc[250] = volume.iloc[230:250].mean() * 5
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def _fake_intraday_day(date, base_price=100.0, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    times = pd.date_range(f"{date} 09:15", f"{date} 15:25", freq="5min")
    close = pd.Series(base_price + np.linspace(0, 2, len(times)) + rng.normal(0, 0.05, len(times)), index=times)
    high = close + 0.05
    low = close - 0.05
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(rng.uniform(5e4, 1e5, len(times)), index=times)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_indicators_run_and_bounded():
    bars = _fake_daily_bars()
    r = rsi(bars["close"])
    assert ((r.dropna() >= 0) & (r.dropna() <= 100)).all()
    macd_line, signal_line = macd(bars["close"])
    assert len(macd_line) == len(bars)
    rvol = relative_volume(bars["volume"])
    assert rvol.dropna().gt(0).all()


def test_session_vwap_within_day_range():
    day = _fake_intraday_day("2024-06-03")
    vwap = session_vwap(day)
    assert (vwap.dropna() >= day["low"].min()).all()
    assert (vwap.dropna() <= day["high"].max()).all()


def test_screen_ticker_flags_injected_signal():
    bars = _fake_daily_bars()
    passed = screen_ticker(bars)
    assert passed.iloc[250]
    assert passed.sum() < len(bars) * 0.2


def test_position_size_uses_capital_pct():
    shares = position_size(entry_price=100.0, capital=300_000)
    assert shares == int(300_000 * 0.10 / 100.0)


def test_simulate_intraday_exit_hits_stop():
    day = _fake_intraday_day("2024-06-03")
    day.loc[day.index[1], "low"] = 50.0
    exit_time, exit_price, reason = _simulate_intraday_exit(day, entry_idx=0, entry_price=100.0, initial_stop=95.0)
    assert reason == "stop"
    assert exit_price == 95.0


def test_confirm_symbol_rejects_without_gap():
    daily = _fake_daily_bars()
    session_date = daily.index[260]
    intraday = _fake_intraday_day(str(session_date.date()), base_price=daily["close"].iloc[259])
    result = confirm_symbol("FAKE", daily.iloc[:260], intraday, session_date)
    assert result.passed is False
    assert result.reason == "no gap up"


def test_run_stage1_only_produces_trades():
    bars = {"FAKE": _fake_daily_bars()}
    trades = run_stage1_only(bars)
    assert len(trades) >= 1
    assert all(t.stage == "stage1" for t in trades)


def test_total_cost_mis_vs_cnc_asymmetry():
    mis_cost = total_cost(entry_price=100.0, exit_price=102.0, shares=100, product="MIS")
    cnc_cost = total_cost(entry_price=100.0, exit_price=102.0, shares=100, product="CNC")
    assert mis_cost > 0 and cnc_cost > 0
    # CNC has zero brokerage but higher STT and a flat DP charge -- neither dominates
    # uniformly, but both must be materially smaller than the notional traded.
    assert mis_cost < 100.0 * 100
    assert cnc_cost < 100.0 * 100


def test_net_pnl_deducts_costs():
    t = Trade(symbol="FAKE", entry_time=pd.Timestamp("2024-01-01"), exit_time=pd.Timestamp("2024-01-01"),
               entry_price=100.0, exit_price=105.0, shares=50, exit_reason="test", stage="test", product="MIS")
    assert t.net_pnl < t.pnl
    assert t.pnl == 250.0


def test_short_trade_pnl_sign():
    t = Trade(symbol="FAKE", entry_time=pd.Timestamp("2024-01-01"), exit_time=pd.Timestamp("2024-01-01"),
               entry_price=100.0, exit_price=90.0, shares=10, exit_reason="test", stage="test",
               product="MIS", side="short")
    assert t.pnl == 100.0  # price dropped 10, short profits


def test_bollinger_bands_bracket_price():
    bars = _fake_daily_bars()
    upper, mid, lower = bollinger_bands(bars["close"])
    valid = upper.dropna().index
    assert (upper.loc[valid] >= mid.loc[valid]).all()
    assert (mid.loc[valid] >= lower.loc[valid]).all()


def _fake_swing_bars(n=200, seed=2) -> pd.DataFrame:
    """Daily bars with an injected clean uptrend (EMA10>EMA30, expanding MACD hist)
    starting mid-series, so run_swing has something to enter."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    close = pd.Series(100 + rng.normal(0, 0.3, n), index=dates)
    close.iloc[100:] = close.iloc[100] + np.arange(n - 100) * 0.8  # strong steady uptrend
    high = close + 0.5
    low = close - 0.5
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(rng.uniform(1e6, 2e6, n), index=dates)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_run_swing_enters_on_uptrend():
    trades = run_swing({"FAKE": _fake_swing_bars()})
    assert len(trades) >= 1
    assert all(t.stage == "swing" and t.product == "CNC" and t.side == "long" for t in trades)


def test_run_orb_vwap_handles_empty_gracefully():
    day = _fake_intraday_day("2024-06-03")
    trades = run_orb_vwap({"FAKE": day})
    assert all(t.stage == "orb_vwap" for t in trades)  # may be 0 trades, must not crash


def test_run_bollinger_meanrev_handles_empty_gracefully():
    day = _fake_intraday_day("2024-06-03")
    trades = run_bollinger_meanrev({"FAKE": day})
    assert all(t.stage == "bollinger_meanrev" and t.side == "short" for t in trades)


def test_run_orb_confluence_handles_empty_gracefully():
    day = _fake_intraday_day("2024-06-03")
    trades = run_orb_confluence({"FAKE": day})
    assert all(t.stage == "orb_confluence" for t in trades)  # may be 0 trades, must not crash


def test_camarilla_levels_ordering():
    bars = _fake_daily_bars()
    levels = camarilla_levels(bars)
    valid = levels.dropna()
    assert (valid["r4"] > valid["r3"]).all()
    assert (valid["r3"] > valid["s3"]).all()
    assert (valid["s3"] > valid["s4"]).all()


def test_run_camarilla_handles_empty_gracefully():
    daily = _fake_daily_bars()
    day = _fake_intraday_day("2024-06-03")
    trades = run_camarilla({"FAKE": daily}, {"FAKE": day})
    assert all(t.stage == "camarilla" for t in trades)  # may be 0 trades, must not crash


def test_camarilla_target_hit_is_never_a_loss():
    # regression: entries that gap straight past both r3 and r4 in one bar used to
    # exit at "target_hit" priced BELOW entry, mislabeling a loss as a win.
    daily = _fake_daily_bars()
    day = _fake_intraday_day("2024-06-03")
    trades = run_camarilla({"FAKE": daily}, {"FAKE": day})
    for t in trades:
        if t.exit_reason == "target_hit":
            assert t.pnl >= 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok: {name}")
    print("all smoke tests passed")
