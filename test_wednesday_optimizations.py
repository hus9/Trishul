"""Wednesday-Specific Quantitative Deep Dive & Optimization Suite.

Investigates why Wednesday is choppy and tests:
1. Delayed Entry Time on Wednesday (e.g., after 10:00, 10:30, 11:00 IST).
2. Max Trades Cap on Wednesday (1 trade vs 2 trades vs 3 trades).
3. Trailing Stop Loss on Wednesday (15%, 20%, 25%, 30%).
4. OTM Strike selection on Wednesday (ATM vs OTM1 / 50 pts OTM).
5. Supertrend Multiplier / Period tuning specifically on Wednesday.
"""

import pandas as pd
import numpy as np
from nifty_options_supertrend_pivots import supertrend, standard_pivot_points, PositionType
from costs import total_cost

# Load 6-month 5m data
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


def test_wednesday_custom(
    wed_start_time="09:15:00",
    wed_cutoff_time="14:15:00",
    wed_max_trades=3,
    wed_tsl_pct=0.20,
    wed_hard_cap=0.35,
    wed_use_15m=True,
    wed_strike_offset_pts=0,  # 0 for ATM, 50 for OTM1 (sell safer OTM)
    wed_st_mult=3.0,
    wed_st_period=7,
):
    # If custom supertrend params for Wednesday:
    if wed_st_mult != 3.0 or wed_st_period != 7:
        st_l_5m, st_d_5m = supertrend(df_5m, period=wed_st_period, multiplier=wed_st_mult)
    else:
        st_l_5m, st_d_5m = st_line_5m, st_dir_5m

    trades = []
    lot_size = 65
    square_off_time = pd.to_datetime("15:15:00").time()
    w_start = pd.to_datetime(wed_start_time).time()
    w_cutoff = pd.to_datetime(wed_cutoff_time).time()

    # Filter to Wednesdays only
    wed_dates = [d for d in session_dates if pd.Timestamp(d).day_name() == "Wednesday"]

    for s_date in wed_dates:
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

            # Position Management
            if active_pos:
                delta_move = close_p - active_pos["entry_spot"]
                if active_pos["type"] == PositionType.SHORT_PE:
                    curr_opt = max(1.0, active_pos["entry_price"] - (0.45 * delta_move))
                else:
                    curr_opt = max(1.0, active_pos["entry_price"] + (0.45 * delta_move))
                
                active_pos["curr_opt_price"] = curr_opt
                active_pos["lowest_opt_price"] = min(active_pos["lowest_opt_price"], curr_opt)
                
                entry_p = active_pos["entry_price"]
                lowest_opt = active_pos["lowest_opt_price"]

                # Hard Stop
                if wed_hard_cap and curr_opt >= entry_p * (1.0 + wed_hard_cap):
                    exit_p = entry_p * (1.0 + wed_hard_cap)
                    gross = (entry_p - exit_p) * lot_size
                    cost = total_cost(entry_p, exit_p, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "HARD_CAP", "date": s_date})
                    active_pos = None
                    continue

                # Trailing Stop
                if wed_tsl_pct:
                    trail_level = lowest_opt * (1.0 + wed_tsl_pct)
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

            # Entries on Wednesday
            if active_pos is None and daily_trades < wed_max_trades and w_start <= c_time < w_cutoff:
                mtf_ok = True
                if wed_use_15m:
                    ts_15m = ts.floor("15min")
                    if ts_15m in st_dir_15m.index:
                        st_15m_d = st_dir_15m.loc[ts_15m]
                    else:
                        st_15m_d = st_d

                # Pricing model with OTM strike offset
                # If OTM1 (50 pts OTM), base premium is ~85% of ATM premium
                base_atm_p = close_p * 0.008
                base_p = base_atm_p if wed_strike_offset_pts == 0 else base_atm_p * 0.82

                if close_p > st_val and close_p > r1:
                    if not wed_use_15m or st_15m_d == 1:
                        active_pos = {
                            "type": PositionType.SHORT_PE, "entry_spot": close_p,
                            "entry_price": base_p, "curr_opt_price": base_p,
                            "lowest_opt_price": base_p
                        }
                        daily_trades += 1

                elif close_p < st_val and close_p < s1:
                    if not wed_use_15m or st_15m_d == -1:
                        active_pos = {
                            "type": PositionType.SHORT_CE, "entry_spot": close_p,
                            "entry_price": base_p, "curr_opt_price": base_p,
                            "lowest_opt_price": base_p
                        }
                        daily_trades += 1

    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "max_dd": 0, "profit_factor": 0, "avg_trade": 0}
    
    wins = (df_t["pnl"] > 0).sum()
    wr = (wins / len(df_t)) * 100
    net = df_t["pnl"].sum()
    avg_trade = df_t["pnl"].mean()
    
    cum = df_t["pnl"].cumsum()
    peak = cum.cummax()
    dd = (cum - peak).min()
    
    g_win = df_t[df_t["gross"] > 0]["gross"].sum()
    g_loss = abs(df_t[df_t["gross"] < 0]["gross"].sum())
    pf = g_win / (g_loss if g_loss > 0 else 1e-6)
    
    return {
        "trades": len(df_t), "net_pnl": net, "win_rate": wr,
        "max_dd": abs(dd), "profit_factor": pf, "avg_trade": avg_trade,
        "reasons": df_t["reason"].value_counts().to_dict()
    }


def main():
    print("==========================================================================================")
    print("  WEDNESDAY DEEP-DIVE: PARAMETER OPTIMIZATIONS TO TRANSFORM WEDNESDAY")
    print("==========================================================================================\n")

    base = test_wednesday_custom()
    print(f"1. BASELINE WEDNESDAY (09:15 - 14:15, ATM, Max 3 trades, TSL 20%):")
    print(f"   Net PnL: ₹{base['net_pnl']:>9,.2f} | WR: {base['win_rate']:>5.1f}% | PF: {base['profit_factor']:.2f} | Trades: {base['trades']} | Avg PnL: ₹{base['avg_trade']:,.2f}")
    print(f"   Exits: {base['reasons']}\n")

    # A. Delayed Start Time on Wednesday (Avoiding Opening Settlement Volatility)
    print("--- LEVER 1: DELAYED ENTRY TIME (Letting Wednesday Morning Noise Settle) ---")
    for start in ["09:30:00", "10:00:00", "10:30:00", "11:00:00"]:
        r = test_wednesday_custom(wed_start_time=start)
        print(f"   Enter After {start[:5]} IST: Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2} | Avg PnL = ₹{r['avg_trade']:>7,.2f}")
    print()

    # B. Max Trades Cap on Wednesday (Limiting Chop Re-entries)
    print("--- LEVER 2: MAX TRADES CAP ON WEDNESDAY (1 Trade vs 2 Trades vs 3 Trades) ---")
    for cap in [1, 2, 3]:
        r = test_wednesday_custom(wed_max_trades=cap)
        print(f"   Max {cap} Trade/Day:     Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2} | Avg PnL = ₹{r['avg_trade']:>7,.2f}")
    print()

    # C. Trailing Stop Loss on Wednesday (Tight 15% vs Moderate 25% vs Wide 30%)
    print("--- LEVER 3: TSL SENSITIVITY ON WEDNESDAY (Higher DTE / Slower Decay) ---")
    for tsl in [0.10, 0.15, 0.20, 0.25, 0.30]:
        r = test_wednesday_custom(wed_tsl_pct=tsl)
        print(f"   TSL {int(tsl*100)}%:              Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2} | Avg PnL = ₹{r['avg_trade']:>7,.2f}")
    print()

    # D. Selling 1 Strike OTM (OTM1) on Wednesday
    print("--- LEVER 4: STRIKE SELECTION ON WEDNESDAY (Selling ATM vs 50-pt OTM) ---")
    r_atm = test_wednesday_custom(wed_strike_offset_pts=0)
    r_otm = test_wednesday_custom(wed_strike_offset_pts=50)
    print(f"   ATM Strikes (Delta ~0.50): Net = ₹{r_atm['net_pnl']:>9,.2f} | WR = {r_atm['win_rate']:>5.1f}% | PF = {r_atm['profit_factor']:.2f}")
    print(f"   OTM1 Strikes (Delta ~0.35):Net = ₹{r_otm['net_pnl']:>9,.2f} | WR = {r_otm['win_rate']:>5.1f}% | PF = {r_otm['profit_factor']:.2f}")
    print()

    # E. Supertrend Period/Multiplier on Wednesday
    print("--- LEVER 5: SUPERTREND SENSITIVITY (Smoothing Wednesday Noise) ---")
    for mult in [2.5, 3.0, 3.5, 4.0]:
        r = test_wednesday_custom(wed_st_mult=mult)
        print(f"   ST (7, {mult:.1f}):            Net = ₹{r['net_pnl']:>9,.2f} | WR = {r['win_rate']:>5.1f}% | PF = {r['profit_factor']:.2f} | Trades = {r['trades']:<2}")
    print()

    # F. Combined Optimized Wednesday Model
    print("--- ⭐ FINAL OPTIMIZED WEDNESDAY RECIPE ---")
    # Combination: Delay start to 10:30 IST + Max 1 trade per Wednesday + TSL 25% + ST (7, 3.5)
    r_comb = test_wednesday_custom(
        wed_start_time="10:30:00",
        wed_max_trades=1,
        wed_tsl_pct=0.25,
        wed_st_mult=3.5,
    )
    print(f"   Optimized Wednesday Configuration:")
    print(f"   (Enter after 10:30 IST + Max 1 Trade + TSL 25% + ST 3.5 Mult)")
    print(f"   Net PnL: ₹{r_comb['net_pnl']:>9,.2f} | WR: {r_comb['win_rate']:>5.1f}% | PF: {r_comb['profit_factor']:.2f} | Trades: {r_comb['trades']} | Avg PnL: ₹{r_comb['avg_trade']:,.2f}")
    print(f"   Exits: {r_comb['reasons']}")


if __name__ == "__main__":
    main()
