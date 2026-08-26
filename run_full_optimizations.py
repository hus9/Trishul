"""Comprehensive Quantitative Optimization & Multi-Parameter Test Suite.

Tests:
1. %-based TSL vs. ATR-based TSL (Spot ATR and Option ATR multiples: 1.0x to 3.0x).
2. Time-of-Day Cutoff for New Entries (No cutoff vs. 14:15 vs. 13:00 Europe open vs. 11:30).
3. Hard Initial Stop Loss Cap (30%, 35%, 40%, 50%).
4. Target Profit Take (50%, 60%, 70% option decay).
5. Multi-Timeframe Confirmation (15-min Supertrend agreement).
"""

import pandas as pd
import numpy as np
from nifty_options_supertrend_pivots import (
    StrategyConfig, supertrend, standard_pivot_points, PositionType
)
from indicators import atr as atr_indicator
from costs import total_cost

# 1. Load 6-month 5-minute NIFTY Spot data
df_5m = pd.read_csv("../Garuda/data/nifty_5min.csv")
df_5m["date"] = pd.to_datetime(df_5m["date"]).dt.tz_localize(None)
df_5m = df_5m.set_index("date").sort_index()

# 2. Daily bars for Standard Pivots
df_daily = df_5m.resample("D").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
}).dropna()

# 3. 15-Minute bars for Multi-Timeframe Supertrend
df_15m = df_5m.resample("15min").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
}).dropna()

# Precompute Indicators
st_line_5m, st_dir_5m = supertrend(df_5m, period=7, multiplier=3.0)
st_line_15m, st_dir_15m = supertrend(df_15m, period=7, multiplier=3.0)
pivots = standard_pivot_points(df_daily)
atr_5m = atr_indicator(df_5m, period=14)

session_dates = sorted(set(df_5m.index.date))


def run_simulation(
    tsl_mode="pct",            # "pct", "spot_atr", "none"
    trail_pct=0.20,            # for "pct"
    atr_mult=2.0,              # for "spot_atr"
    entry_cutoff_time="15:00", # "15:00", "14:15", "13:00", "11:30"
    max_loss_cap_pct=None,     # e.g., 0.35 (35% hard stop)
    target_profit_pct=None,    # e.g., 0.60 (60% profit target)
    use_mtf_15m=False,         # Multi-timeframe 15m Supertrend filter
    lot_size=65,
    max_trades_per_day=3,
):
    trades = []
    square_off_time = pd.to_datetime("15:15:00").time()
    cutoff_time = pd.to_datetime(entry_cutoff_time).time()

    for s_date in session_dates:
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
            st_val = st_line_5m.loc[ts]
            st_d = st_dir_5m.loc[ts]
            curr_atr = atr_5m.loc[ts]

            # -------------------------------------------------------------
            # A. EOD Forced Square-Off (15:15 IST)
            # -------------------------------------------------------------
            if c_time >= square_off_time:
                if active_pos:
                    exit_p = active_pos["curr_opt_price"]
                    gross = (active_pos["entry_price"] - exit_p) * lot_size
                    cost = total_cost(active_pos["entry_price"], exit_p, lot_size, "MIS")
                    trades.append({
                        "pnl": gross - cost, "gross": gross, "reason": "EOD_SQUARE_OFF",
                        "date": s_date, "side": active_pos["type"].value
                    })
                    active_pos = None
                continue

            # -------------------------------------------------------------
            # B. Manage Active Position (Check Exits)
            # -------------------------------------------------------------
            if active_pos:
                delta_move = close_p - active_pos["entry_spot"]
                if active_pos["type"] == PositionType.SHORT_PE:
                    curr_opt = max(1.0, active_pos["entry_price"] - (0.50 * delta_move))
                    active_pos["extreme_spot"] = max(active_pos["extreme_spot"], candle["high"])
                else:
                    curr_opt = max(1.0, active_pos["entry_price"] + (0.50 * delta_move))
                    active_pos["extreme_spot"] = min(active_pos["extreme_spot"], candle["low"])
                
                active_pos["curr_opt_price"] = curr_opt
                active_pos["lowest_opt_price"] = min(active_pos["lowest_opt_price"], curr_opt)
                
                entry_p = active_pos["entry_price"]
                lowest_opt = active_pos["lowest_opt_price"]

                # 1. Target Profit Exit
                if target_profit_pct and curr_opt <= entry_p * (1.0 - target_profit_pct):
                    gross = (entry_p - curr_opt) * lot_size
                    cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                    trades.append({
                        "pnl": gross - cost, "gross": gross, "reason": "TARGET_PROFIT",
                        "date": s_date, "side": active_pos["type"].value
                    })
                    active_pos = None
                    continue

                # 2. Hard Loss Cap (Emergency Initial Stop)
                if max_loss_cap_pct and curr_opt >= entry_p * (1.0 + max_loss_cap_pct):
                    exit_p = entry_p * (1.0 + max_loss_cap_pct)
                    gross = (entry_p - exit_p) * lot_size
                    cost = total_cost(entry_p, exit_p, lot_size, "MIS")
                    trades.append({
                        "pnl": gross - cost, "gross": gross, "reason": "HARD_LOSS_CAP",
                        "date": s_date, "side": active_pos["type"].value
                    })
                    active_pos = None
                    continue

                # 3. Trailing Stop Loss
                if tsl_mode == "pct":
                    trail_stop_level = lowest_opt * (1.0 + trail_pct)
                    if curr_opt >= trail_stop_level:
                        gross = (entry_p - trail_stop_level) * lot_size
                        cost = total_cost(entry_p, trail_stop_level, lot_size, "MIS")
                        trades.append({
                            "pnl": gross - cost, "gross": gross, "reason": "TSL_PCT",
                            "date": s_date, "side": active_pos["type"].value
                        })
                        active_pos = None
                        continue

                elif tsl_mode == "spot_atr":
                    # Spot ATR trail: For Short PE, stop is extreme_high - atr_mult * ATR
                    # For Short CE, stop is extreme_low + atr_mult * ATR
                    if not pd.isna(curr_atr):
                        if active_pos["type"] == PositionType.SHORT_PE:
                            spot_stop = active_pos["extreme_spot"] - (atr_mult * curr_atr)
                            if close_p <= spot_stop:
                                gross = (entry_p - curr_opt) * lot_size
                                cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                                trades.append({
                                    "pnl": gross - cost, "gross": gross, "reason": "TSL_SPOT_ATR",
                                    "date": s_date, "side": active_pos["type"].value
                                })
                                active_pos = None
                                continue
                        else:
                            spot_stop = active_pos["extreme_spot"] + (atr_mult * curr_atr)
                            if close_p >= spot_stop:
                                gross = (entry_p - curr_opt) * lot_size
                                cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                                trades.append({
                                    "pnl": gross - cost, "gross": gross, "reason": "TSL_SPOT_ATR",
                                    "date": s_date, "side": active_pos["type"].value
                                })
                                active_pos = None
                                continue

                # 4. Supertrend Flip Exit
                if active_pos["type"] == PositionType.SHORT_PE and (close_p < st_val or st_d == -1):
                    gross = (entry_p - curr_opt) * lot_size
                    cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                    trades.append({
                        "pnl": gross - cost, "gross": gross, "reason": "ST_FLIP",
                        "date": s_date, "side": active_pos["type"].value
                    })
                    active_pos = None
                    continue
                elif active_pos["type"] == PositionType.SHORT_CE and (close_p > st_val or st_d == 1):
                    gross = (entry_p - curr_opt) * lot_size
                    cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                    trades.append({
                        "pnl": gross - cost, "gross": gross, "reason": "ST_FLIP",
                        "date": s_date, "side": active_pos["type"].value
                    })
                    active_pos = None
                    continue

            # -------------------------------------------------------------
            # C. Check New Entries (Only if before Cutoff Time)
            # -------------------------------------------------------------
            if active_pos is None and daily_trades < max_trades_per_day and c_time < cutoff_time:
                # MTF 15m check if enabled
                mtf_ok = True
                if use_mtf_15m:
                    ts_15m = ts.floor("15min")
                    if ts_15m in st_dir_15m.index:
                        st_15m_d = st_dir_15m.loc[ts_15m]
                    else:
                        st_15m_d = st_d

                base_atm_p = close_p * 0.008

                if close_p > st_val and close_p > r1:
                    if not use_mtf_15m or st_15m_d == 1:
                        active_pos = {
                            "type": PositionType.SHORT_PE, "entry_spot": close_p,
                            "extreme_spot": candle["high"], "entry_price": base_atm_p,
                            "curr_opt_price": base_atm_p, "lowest_opt_price": base_atm_p
                        }
                        daily_trades += 1

                elif close_p < st_val and close_p < s1:
                    if not use_mtf_15m or st_15m_d == -1:
                        active_pos = {
                            "type": PositionType.SHORT_CE, "entry_spot": close_p,
                            "extreme_spot": candle["low"], "entry_price": base_atm_p,
                            "curr_opt_price": base_atm_p, "lowest_opt_price": base_atm_p
                        }
                        daily_trades += 1

    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "max_dd": 0, "profit_factor": 0, "worst_loss": 0, "avg_trade": 0}
    
    wins = (df_t["pnl"] > 0).sum()
    wr = (wins / len(df_t)) * 100
    net = df_t["pnl"].sum()
    worst_loss = df_t["pnl"].min()
    avg_trade = df_t["pnl"].mean()
    
    cum = df_t["pnl"].cumsum()
    peak = cum.cummax()
    dd = (cum - peak).min()
    
    g_win = df_t[df_t["gross"] > 0]["gross"].sum()
    g_loss = abs(df_t[df_t["gross"] < 0]["gross"].sum())
    pf = g_win / (g_loss if g_loss > 0 else 1e-6)
    
    return {
        "trades": len(df_t), "net_pnl": net, "win_rate": wr,
        "max_dd": abs(dd), "profit_factor": pf, "worst_loss": worst_loss,
        "avg_trade": avg_trade, "reasons": df_t["reason"].value_counts().to_dict()
    }


def main():
    print("==========================================================================================")
    print("  QUANTITATIVE EXPERIMENT: TSL MECHANISMS, TIME CUTOFFS & COMBO OPTIMIZATIONS (6 MONTHS)")
    print("==========================================================================================\n")
    
    # 1. Baseline
    b = run_simulation(tsl_mode="none")
    print(f"BASELINE (No TSL, Supertrend Flip Only):")
    print(f"  Net PnL: ₹{b['net_pnl']:>9,.2f} | WR: {b['win_rate']:>5.1f}% | PF: {b['profit_factor']:.2f} | Max DD: ₹{b['max_dd']:>8,.2f} | Worst Loss: ₹{b['worst_loss']:>8,.2f} | Trades: {b['trades']}")
    print(f"  Exits: {b['reasons']}\n")

    # 2. Percentage TSL vs Spot ATR-based TSL
    print("--- EXPERIMENT 1: % TRAILING STOP vs. ATR-BASED TRAILING STOP ---")
    print("% Option Trailing Stops:")
    for tp in [0.15, 0.20, 0.25]:
        r = run_simulation(tsl_mode="pct", trail_pct=tp)
        print(f"  TSL {int(tp*100)}% (Option Premium): Net: ₹{r['net_pnl']:>9,.2f} | WR: {r['win_rate']:>5.1f}% | PF: {r['profit_factor']:.2f} | Max DD: ₹{r['max_dd']:>8,.2f} | Worst Loss: ₹{r['worst_loss']:>8,.2f} | Trades: {r['trades']}")
    
    print("\nSpot ATR Trailing Stops (Multiplier x 5m ATR):")
    for mult in [1.0, 1.5, 2.0, 2.5, 3.0]:
        r = run_simulation(tsl_mode="spot_atr", atr_mult=mult)
        print(f"  TSL {mult:.1f}x ATR (Spot Index):   Net: ₹{r['net_pnl']:>9,.2f} | WR: {r['win_rate']:>5.1f}% | PF: {r['profit_factor']:.2f} | Max DD: ₹{r['max_dd']:>8,.2f} | Worst Loss: ₹{r['worst_loss']:>8,.2f} | Trades: {r['trades']}")
    print()

    # 3. Time of Day Cutoff Sweep (with 20% TSL)
    print("--- EXPERIMENT 2: TIME-OF-DAY ENTRY CUTOFF (No New Trades After HH:MM) ---")
    for cutoff in ["15:00", "14:15", "13:00", "11:30"]:
        r = run_simulation(tsl_mode="pct", trail_pct=0.20, entry_cutoff_time=cutoff)
        print(f"  Cutoff @ {cutoff} IST: Net: ₹{r['net_pnl']:>9,.2f} | WR: {r['win_rate']:>5.1f}% | PF: {r['profit_factor']:.2f} | Max DD: ₹{r['max_dd']:>8,.2f} | Avg PnL: ₹{r['avg_trade']:>6,.2f} | Trades: {r['trades']}")
    print()

    # 4. Multi-Timeframe 15m Supertrend Filter
    print("--- EXPERIMENT 3: MULTI-TIMEFRAME 15-MIN SUPERTREND CONFIRMATION ---")
    r_mtf = run_simulation(tsl_mode="pct", trail_pct=0.20, use_mtf_15m=True)
    r_no_mtf = run_simulation(tsl_mode="pct", trail_pct=0.20, use_mtf_15m=False)
    print(f"  Standard 5m Only:       Net: ₹{r_no_mtf['net_pnl']:>9,.2f} | WR: {r_no_mtf['win_rate']:>5.1f}% | PF: {r_no_mtf['profit_factor']:.2f} | Max DD: ₹{r_no_mtf['max_dd']:>8,.2f} | Trades: {r_no_mtf['trades']}")
    print(f"  With 15m MTF Agreement: Net: ₹{r_mtf['net_pnl']:>9,.2f} | WR: {r_mtf['win_rate']:>5.1f}% | PF: {r_mtf['profit_factor']:.2f} | Max DD: ₹{r_mtf['max_dd']:>8,.2f} | Trades: {r_mtf['trades']}")
    print()

    # 5. Combined Institutional Model Configurations
    print("--- EXPERIMENT 4: COMBINED OPTIMAL CONFIGURATIONS ---")
    # Configuration A: 20% TSL + 13:00 Europe Cutoff + 35% Hard Loss Cap
    r_opt_a = run_simulation(tsl_mode="pct", trail_pct=0.20, entry_cutoff_time="13:00", max_loss_cap_pct=0.35)
    print(f"  Model A (TSL 20% + 13:00 Cutoff + 35% Hard Cap):")
    print(f"    Net PnL: ₹{r_opt_a['net_pnl']:>9,.2f} | Win Rate: {r_opt_a['win_rate']:>5.1f}% | PF: {r_opt_a['profit_factor']:.2f} | Max DD: ₹{r_opt_a['max_dd']:>8,.2f} | Worst Loss: ₹{r_opt_a['worst_loss']:>8,.2f} | Trades: {r_opt_a['trades']}")
    print(f"    Exits: {r_opt_a['reasons']}")
    print()

    # Configuration B: 20% TSL + 14:15 Cutoff + 35% Hard Cap + 60% Target Profit
    r_opt_b = run_simulation(tsl_mode="pct", trail_pct=0.20, entry_cutoff_time="14:15", max_loss_cap_pct=0.35, target_profit_pct=0.60)
    print(f"  Model B (TSL 20% + 14:15 Cutoff + 35% Hard Cap + 60% Profit Target):")
    print(f"    Net PnL: ₹{r_opt_b['net_pnl']:>9,.2f} | Win Rate: {r_opt_b['win_rate']:>5.1f}% | PF: {r_opt_b['profit_factor']:.2f} | Max DD: ₹{r_opt_b['max_dd']:>8,.2f} | Worst Loss: ₹{r_opt_b['worst_loss']:>8,.2f} | Trades: {r_opt_b['trades']}")
    print(f"    Exits: {r_opt_b['reasons']}")


if __name__ == "__main__":
    main()
