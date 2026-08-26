"""Optimization & Trailing Stop Loss Sweep for NIFTY Options Strategy."""

import pandas as pd
import numpy as np
from nifty_options_supertrend_pivots import StrategyConfig, supertrend, standard_pivot_points, PositionType
from costs import total_cost

df_5m = pd.read_csv("../Garuda/data/nifty_5min.csv")
df_5m["date"] = pd.to_datetime(df_5m["date"]).dt.tz_localize(None)
df_5m = df_5m.set_index("date").sort_index()

df_daily = df_5m.resample("D").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
}).dropna()

st_line, st_dir = supertrend(df_5m, period=7, multiplier=3.0)
pivots = standard_pivot_points(df_daily)
session_dates = sorted(set(df_5m.index.date))


def run_backtest_with_tsl(trail_pct=None, breakeven_trigger_pct=None, target_profit_pct=None, max_loss_pct=None):
    trades = []
    lot_size = 65
    max_trades_per_day = 3
    square_off_time = pd.to_datetime("15:15:00").time()

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
            st_val = st_line.loc[ts]
            st_d = st_dir.loc[ts]

            # 1. EOD Square-off
            if c_time >= square_off_time:
                if active_pos:
                    exit_p = active_pos["curr_opt_price"]
                    gross = (active_pos["entry_price"] - exit_p) * lot_size
                    cost = total_cost(active_pos["entry_price"], exit_p, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "EOD", "date": s_date})
                    active_pos = None
                continue

            # Update current option price if holding
            if active_pos:
                delta_move = close_p - active_pos["entry_spot"]
                if active_pos["type"] == PositionType.SHORT_PE:
                    curr_opt = max(1.0, active_pos["entry_price"] - (0.50 * delta_move))
                else:
                    curr_opt = max(1.0, active_pos["entry_price"] + (0.50 * delta_move))
                
                active_pos["curr_opt_price"] = curr_opt
                active_pos["lowest_price"] = min(active_pos["lowest_price"], curr_opt)
                
                entry_p = active_pos["entry_price"]
                lowest_p = active_pos["lowest_price"]
                
                # Check Target Profit Exit
                if target_profit_pct and curr_opt <= entry_p * (1.0 - target_profit_pct):
                    gross = (entry_p - curr_opt) * lot_size
                    cost = total_cost(entry_p, curr_opt, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "TARGET_PROFIT", "date": s_date})
                    active_pos = None
                    continue

                # Check Hard Max Loss Stop Exit
                if max_loss_pct and curr_opt >= entry_p * (1.0 + max_loss_pct):
                    exit_p = entry_p * (1.0 + max_loss_pct)
                    gross = (entry_p - exit_p) * lot_size
                    cost = total_cost(entry_p, exit_p, lot_size, "MIS")
                    trades.append({"pnl": gross - cost, "gross": gross, "reason": "MAX_LOSS_CAP", "date": s_date})
                    active_pos = None
                    continue

                # Check Trailing Stop Loss Exit
                if trail_pct:
                    be_active = True
                    if breakeven_trigger_pct:
                        if (entry_p - lowest_p) / entry_p < breakeven_trigger_pct:
                            be_active = False
                    
                    if be_active:
                        stop_level = lowest_p * (1.0 + trail_pct)
                        if breakeven_trigger_pct:
                            stop_level = min(stop_level, entry_p)
                        
                        if curr_opt >= stop_level:
                            gross = (entry_p - stop_level) * lot_size
                            cost = total_cost(entry_p, stop_level, lot_size, "MIS")
                            trades.append({"pnl": gross - cost, "gross": gross, "reason": "TRAILING_STOP", "date": s_date})
                            active_pos = None
                            continue

                # Check Supertrend Flip Exit
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

            # 2. Check Entries
            if active_pos is None and daily_trades < max_trades_per_day:
                base_atm_p = close_p * 0.008
                if close_p > st_val and close_p > r1:
                    active_pos = {
                        "type": PositionType.SHORT_PE, "entry_spot": close_p,
                        "entry_price": base_atm_p, "curr_opt_price": base_atm_p,
                        "lowest_price": base_atm_p
                    }
                    daily_trades += 1
                elif close_p < st_val and close_p < s1:
                    active_pos = {
                        "type": PositionType.SHORT_CE, "entry_spot": close_p,
                        "entry_price": base_atm_p, "curr_opt_price": base_atm_p,
                        "lowest_price": base_atm_p
                    }
                    daily_trades += 1

    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "max_dd": 0, "profit_factor": 0, "max_loss": 0}
    
    wins = (df_t["pnl"] > 0).sum()
    wr = (wins / len(df_t)) * 100
    net = df_t["pnl"].sum()
    max_loss = df_t["pnl"].min()
    
    cum = df_t["pnl"].cumsum()
    peak = cum.cummax()
    dd = (cum - peak).min()
    
    g_win = df_t[df_t["gross"] > 0]["gross"].sum()
    g_loss = abs(df_t[df_t["gross"] < 0]["gross"].sum())
    pf = g_win / (g_loss if g_loss > 0 else 1e-6)
    
    return {
        "trades": len(df_t), "net_pnl": net, "win_rate": wr,
        "max_dd": abs(dd), "profit_factor": pf, "max_loss": max_loss,
        "reasons": df_t["reason"].value_counts().to_dict()
    }


def main():
    print("=========================================================================================")
    print("  6-MONTH OPTIMIZATION & TRAILING STOP LOSS (TSL) EXPERIMENT REPORT")
    print("=========================================================================================\n")
    
    b = run_backtest_with_tsl()
    print(f"1. BASELINE (No TSL, Supertrend Flip Only):")
    print(f"   Net PnL: ₹{b['net_pnl']:,.2f} | Win Rate: {b['win_rate']:.1f}% | Profit Factor: {b['profit_factor']:.2f}")
    print(f"   Max Drawdown: ₹{b['max_dd']:,.2f} | Worst Trade Loss: ₹{b['max_loss']:,.2f}")
    print(f"   Exit Distribution: {b['reasons']}\n")

    print(f"2. TRAILING STOP LOSS (TSL) SWEEP (Trailing % from lowest option price):")
    for trail in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        r = run_backtest_with_tsl(trail_pct=trail)
        print(f"   TSL {int(trail*100):02d}%: Net = ₹{r['net_pnl']:>9,.2f} | Win Rate = {r['win_rate']:>5.1f}% | Max DD = ₹{r['max_dd']:>8,.2f} | PF = {r['profit_factor']:.2f} | Worst Loss = ₹{r['max_loss']:>8,.2f} | Exits: {r['reasons']}")
    print()

    print(f"3. BREAKEVEN PROFIT-LOCK + TRAILING STOP (Move SL to Breakeven at +X% gain, then trail 20%):")
    for be in [0.15, 0.20, 0.25, 0.30]:
        r = run_backtest_with_tsl(trail_pct=0.20, breakeven_trigger_pct=be)
        print(f"   BE @ +{int(be*100)}% + 20% TSL: Net = ₹{r['net_pnl']:>9,.2f} | Win Rate = {r['win_rate']:>5.1f}% | Max DD = ₹{r['max_dd']:>8,.2f} | PF = {r['profit_factor']:.2f}")
    print()

    print(f"4. HARD LOSS CAP + TARGET PROFIT + TRAILING STOP (The Institutional Triple-Protection Model):")
    for ml in [0.30, 0.40]:
        for tp in [0.50, 0.60]:
            r = run_backtest_with_tsl(max_loss_pct=ml, target_profit_pct=tp, trail_pct=0.25)
            print(f"   Cap {int(ml*100)}% Loss + Target {int(tp*100)}% Profit + 25% TSL: Net = ₹{r['net_pnl']:>9,.2f} | Win Rate = {r['win_rate']:>5.1f}% | Max DD = ₹{r['max_dd']:>8,.2f} | PF = {r['profit_factor']:.2f} | Worst Loss = ₹{r['max_loss']:>8,.2f}")


if __name__ == "__main__":
    main()
