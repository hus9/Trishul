"""Comprehensive Quantitative Deep Dive & Optimization Suite for Monday & Thursday.

Under the Tuesday Expiry Cycle:
- Monday: 1 DTE (Pre-Expiry, Weekend gap digestion, rapid theta acceleration).
- Thursday: 4-5 DTE (Cycle Day 2, Post-Wednesday trend continuation).

Tests on each day:
1. Delayed Entry Time (09:15 vs 09:30 vs 09:45 vs 10:00).
2. TSL Sensitivity (10%, 15%, 20%, 25%, 30%).
3. Max Trades Cap (1 vs 2 vs 3).
4. Strike Selection (ATM vs OTM1 50-pt buffer).
5. Supertrend Multiplier (2.5 vs 3.0 vs 3.5).
6. Time-of-Day Cutoffs (13:00 vs 14:15 vs 15:00).
"""

import pandas as pd
import numpy as np
from nifty_options_supertrend_pivots import supertrend, standard_pivot_points, PositionType
from costs import total_cost

df_5m = pd.read_csv("../Garuda/data/nifty_5min.csv")
df_5m["date"] = pd.to_datetime(df_5m["date"]).dt.tz_localize(None)
df_5m = df_5m.set_index("date").sort_index()

df_daily = df_5m.resample("D").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
}).dropna()

df_15m = df_5m.resample("15min").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
}).dropna()

st_line_5m, st_dir_5m = supertrend(df_5m, period=7, multiplier=3.0)
st_line_15m, st_dir_15m = supertrend(df_15m, period=7, multiplier=3.0)
pivots = standard_pivot_points(df_daily)
session_dates = sorted(set(df_5m.index.date))


def run_day_simulation(
    target_day="Monday",
    start_time="09:15:00",
    cutoff_time="14:15:00",
    max_trades=3,
    tsl_pct=0.20,
    hard_cap=0.35,
    use_15m=True,
    strike_offset_pts=0,
    st_mult=3.0,
    st_period=7,
):
    if st_mult != 3.0 or st_period != 7:
        st_l_5m, st_d_5m = supertrend(df_5m, period=st_period, multiplier=st_mult)
    else:
        st_l_5m, st_d_5m = st_line_5m, st_dir_5m

    trades = []
    lot_size = 65
    square_off_time = pd.to_datetime("15:15:00").time()
    t_start = pd.to_datetime(start_time).time()
    t_cutoff = pd.to_datetime(cutoff_time).time()

    day_dates = [d for d in session_dates if pd.Timestamp(d).day_name() == target_day]

    # Delta sensitivity approximation based on DTE:
    # Monday (1 DTE) has faster delta response (~0.50), Thursday (4 DTE) ~0.45
    delta_factor = 0.50 if target_day == "Monday" else 0.45

    for s_date in day_dates:
        day_bars = df_5m[df_5m.index.date == s_date]
        day_pivots = pivots[pivots.index.date == s_date]
        if day_pivots.empty or len(day_bars) < 7:
            continue
        r1 = day_pivots["r1"].iloc[0]
        s1 = day_pivots["s1"].iloc[0]

        daily_trades = 0
        active_pos = None

        for ts, candle in day_bars.iterrows():
            c_time = ts.time()
            close_p = candle["close"]
            st_val = st_l_5m.loc[ts]
            st_d = st_d_5m.loc[ts]

            # EOD Square-off
            if c_time >= square_off_time:
                if active_pos:
                    exit_p = active_pos["curr_opt_price"]
                    gross = (active_pos["entry_price"] - exit_p) * lot_size
                    cost = total_cost(active_pos["entry_price"], exit_p, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "EOD", "date": s_date})
                    active_pos = None
                continue

            # Active position management
            if active_pos:
                delta_move = close_p - active_pos["entry_spot"]
                if active_pos["type"] == PositionType.SHORT_PE:
                    curr_opt = max(1.0, active_pos["entry_price"] - (delta_factor * delta_move))
                else:
                    curr_opt = max(1.0, active_pos["entry_price"] + (delta_factor * delta_move))
                
                active_pos["curr_opt_price"] = curr_opt
                active_pos["lowest_opt_price"] = min(active_pos["lowest_opt_price"], curr_opt)
                
                entry_p = active_pos["entry_price"]
                lowest_opt = active_pos["lowest_opt_price"]

                # Hard Cap
                if hard_cap and curr_opt >= entry_p * (1.0 + hard_cap):
                    exit_p = entry_p * (1.0 + hard_cap)
                    gross = (entry_p - exit_p) * lot_size
                    cost = total_cost(entry_p, exit_p, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "HARD_CAP", "date": s_date})
                    active_pos = None
                    continue

                # Trailing Stop
                if tsl_pct:
                    trail_level = lowest_opt * (1.0 + tsl_pct)
                    if curr_opt >= trail_level:
                        gross = (entry_p - trail_level) * lot_size
                        cost = total_cost(entry_p, trail_level, lot_size, "MIS")
                        trades.append({"pnl": gross - cost, "gross": gross, "reason": "TSL", "date": s_date})
                        active_pos = None
                        continue

                # Supertrend Flip
                if active_pos["type"] == PositionType.SHORT_PE and (close_p < st_val or st_d == -1):
                    gross = (entry_p - curr_opt) * lot_size
                    cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "ST_FLIP", "date": s_date})
                    active_pos = None
                    continue
                elif active_pos["type"] == PositionType.SHORT_CE and (close_p > st_val or st_d == 1):
                    gross = (entry_p - curr_opt) * lot_size
                    cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "ST_FLIP", "date": s_date})
                    active_pos = None
                    continue

            # Entries
            if active_pos is None and daily_trades < max_trades and t_start <= c_time < t_cutoff:
                mtf_ok = True
                if use_15m:
                    ts_15m = ts.floor("15min")
                    if ts_15m in st_dir_15m.index:
                        st_15m_d = st_dir_15m.loc[ts_15m]
                    else:
                        st_15m_d = st_d

                base_atm_p = close_p * 0.008
                base_p = base_atm_p if strike_offset_pts == 0 else base_atm_p * 0.82

                if close_p > st_val and close_p > r1:
                    if not use_15m or st_15m_d == 1:
                        active_pos = {
                            "type": PositionType.SHORT_PE, "entry_spot": close_p,
                            "entry_price": base_p, "curr_opt_price": base_p,
                            "lowest_opt_price": base_p
                        }
                        daily_trades += 1

                elif close_p < st_val and close_p < s1:
                    if not use_15m or st_15m_d == -1:
                        active_pos = {
                            "type": PositionType.SHORT_CE, "entry_spot": close_p,
                            "entry_price": base_p, "curr_opt_price": base_p,
                            "lowest_opt_price": base_p
                        }
                        daily_trades += 1

    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "profit_factor": 0, "avg_trade": 0, "max_win": 0, "max_loss": 0, "reasons": {}}
    
    wins = (df_t["pnl"] > 0).sum()
    wr = (wins / len(df_t)) * 100
    net = df_t["pnl"].sum()
    avg_trade = df_t["pnl"].mean()
    max_w = df_t["pnl"].max()
    max_l = df_t["pnl"].min()
    
    g_win = df_t[df_t["gross"] > 0]["gross"].sum()
    g_loss = abs(df_t[df_t["gross"] < 0]["gross"].sum())
    pf = g_win / (g_loss if g_loss > 0 else 1e-6)
    
    return {
        "trades": len(df_t), "net_pnl": net, "win_rate": wr,
        "profit_factor": pf, "avg_trade": avg_trade, "max_win": max_w, "max_loss": max_l,
        "reasons": df_t["reason"].value_counts().to_dict()
    }


def analyze_day(day_name):
    print(f"==========================================================================================")
    print(f"  QUANTITATIVE DEEP-DIVE FOR {day_name.upper()} (6-MONTH HISTORICAL DATA)")
    print(f"==========================================================================================\n")

    b = run_day_simulation(target_day=day_name)
    print(f"1. BASELINE {day_name.upper()} (09:15 - 14:15, ATM, Max 3 Trades, 20% TSL):")
    print(f"   Net PnL: ₹{b['net_pnl']:>9,.2f} | WR: {b['win_rate']:>5.1f}% | PF: {b['profit_factor']:.2f} | Trades: {b['trades']} | Avg PnL: ₹{b['avg_trade']:,.2f}")
    print(f"   Worst Loss: ₹{b['max_loss']:,.2f} | Max Win: ₹{b['max_win']:,.2f} | Exits: {b['reasons']}\n")

    # 1. Start Time
    print("--- LEVER 1: DELAYED ENTRY START TIME ---")
    for start in ["09:15:00", "09:30:00", "09:45:00", "10:00:00", "10:30:00"]:
        r = run_day_simulation(target_day=day_name, start_time=start)
        print(f"   Start @ {start[:5]} IST: Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2} | Avg PnL = ₹{r['avg_trade']:>7,.2f}")
    print()

    # 2. TSL Sweep
    print("--- LEVER 2: TRAILING STOP LOSS SENSITIVITY ---")
    for tsl in [0.10, 0.15, 0.20, 0.25, 0.30]:
        r = run_day_simulation(target_day=day_name, tsl_pct=tsl)
        print(f"   TSL {int(tsl*100)}%:        Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2} | Avg PnL = ₹{r['avg_trade']:>7,.2f} | Worst: ₹{r['max_loss']:,.2f}")
    print()

    # 3. Max Trades Cap
    print("--- LEVER 3: MAX TRADES CAP PER DAY ---")
    for cap in [1, 2, 3]:
        r = run_day_simulation(target_day=day_name, max_trades=cap)
        print(f"   Max {cap} Trade/Day: Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2} | Avg PnL = ₹{r['avg_trade']:>7,.2f}")
    print()

    # 4. Strike Selection (ATM vs OTM1)
    print("--- LEVER 4: STRIKE SELECTION (ATM vs OTM1 50-pt) ---")
    r_atm = run_day_simulation(target_day=day_name, strike_offset_pts=0)
    r_otm = run_day_simulation(target_day=day_name, strike_offset_pts=50)
    print(f"   ATM Strike (Delta ~0.50):  Net = ₹{r_atm['net_pnl']:>9,.2f} | WR = {r_atm['win_rate']:>5.1f}% | PF = {r_atm['profit_factor']:.2f}")
    print(f"   OTM1 Strike (Delta ~0.35): Net = ₹{r_otm['net_pnl']:>9,.2f} | WR = {r_otm['win_rate']:>5.1f}% | PF = {r_otm['profit_factor']:.2f}")
    print()

    # 5. Supertrend Multiplier
    print("--- LEVER 5: SUPERTREND SENSITIVITY ---")
    for mult in [2.5, 3.0, 3.5, 4.0]:
        r = run_day_simulation(target_day=day_name, st_mult=mult)
        print(f"   ST (7, {mult:.1f}):      Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2}")
    print()


if __name__ == "__main__":
    analyze_day("Monday")
    analyze_day("Thursday")
