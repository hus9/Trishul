"""Generates a standalone, interactive HTML performance dashboard for the
NIFTY Options Intraday Selling Strategy.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd


def generate_dashboard():
    csv_path = Path("out/nifty_options_trades.csv")
    if not csv_path.exists():
        print("Error: out/nifty_options_trades.csv does not exist.")
        return

    df = pd.read_csv(csv_path)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["duration_mins"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60.0

    # Calculate Cumulative Equity and Drawdown
    initial_capital = 200000.0  # ₹2 Lakhs intraday MIS capital
    df["cum_net_pnl"] = df["net_pnl"].cumsum()
    df["equity"] = initial_capital + df["cum_net_pnl"]
    df["peak_equity"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] - df["peak_equity"]
    df["drawdown_pct"] = (df["drawdown"] / df["peak_equity"]) * 100.0

    # Key Performance Metrics
    total_trades = len(df)
    wins = df[df["net_pnl"] > 0]
    losses = df[df["net_pnl"] <= 0]
    num_wins = len(wins)
    num_losses = len(losses)
    win_rate = (num_wins / total_trades) * 100 if total_trades > 0 else 0

    total_gross = df["gross_pnl"].sum()
    total_net = df["net_pnl"].sum()
    total_costs = total_gross - total_net

    gross_profit = wins["gross_pnl"].sum() if num_wins > 0 else 0
    gross_loss = abs(losses["gross_pnl"].sum()) if num_losses > 0 else 1e-6
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_win = wins["net_pnl"].mean() if num_wins > 0 else 0
    avg_loss = losses["net_pnl"].mean() if num_losses > 0 else 0
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    max_drawdown = abs(df["drawdown"].min())
    max_drawdown_pct = abs(df["drawdown_pct"].min())
    avg_duration = df["duration_mins"].mean()

    # Consecutive Wins & Losses
    pnl_sign = (df["net_pnl"] > 0).astype(int)
    streaks = []
    current_streak = 0
    current_type = None
    for s in pnl_sign:
        if s == current_type:
            current_streak += 1
        else:
            if current_type is not None:
                streaks.append((current_type, current_streak))
            current_type = s
            current_streak = 1
    if current_type is not None:
        streaks.append((current_type, current_streak))

    max_consec_wins = max([streak for st_type, streak in streaks if st_type == 1], default=0)
    max_consec_losses = max([streak for st_type, streak in streaks if st_type == 0], default=0)

    # Breakdowns
    by_type = df.groupby("position_type").agg(
        trades=("trade_id", "count"),
        net_pnl=("net_pnl", "sum"),
        win_rate=("net_pnl", lambda x: (x > 0).mean() * 100),
    ).to_dict(orient="index")

    by_reason = df.groupby("exit_reason").agg(
        trades=("trade_id", "count"),
        net_pnl=("net_pnl", "sum"),
        win_rate=("net_pnl", lambda x: (x > 0).mean() * 100),
    ).to_dict(orient="index")

    # Day of Week Aggregation
    df["date"] = pd.to_datetime(df["date"])
    df["day_name"] = df["date"].dt.day_name()
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    by_day = []
    for d in days_order:
        sub = df[df["day_name"] == d]
        if len(sub) == 0:
            continue
        w = (sub["net_pnl"] > 0).sum()
        by_day.append({
            "day": d,
            "trades": len(sub),
            "wins": int(w),
            "losses": int(len(sub) - w),
            "win_rate": round(w / len(sub) * 100, 1),
            "net_pnl": round(sub["net_pnl"].sum(), 2),
            "avg_pnl": round(sub["net_pnl"].mean(), 2),
            "profit_factor": round(sub[sub["gross_pnl"] > 0]["gross_pnl"].sum() / (abs(sub[sub["gross_pnl"] < 0]["gross_pnl"].sum()) if abs(sub[sub["gross_pnl"] < 0]["gross_pnl"].sum()) > 0 else 1e-6), 2)
        })

    day_labels = [x["day"] for x in by_day]
    day_pnl_data = [x["net_pnl"] for x in by_day]
    day_winrate_data = [x["win_rate"] for x in by_day]

    # Time series for charts
    dates_list = df["exit_time"].dt.strftime("%Y-%m-%d %H:%M").tolist()
    equity_curve = df["equity"].round(2).tolist()
    drawdown_curve = df["drawdown"].round(2).tolist()
    pnl_series = df["net_pnl"].round(2).tolist()


    # Build trades table JSON
    trades_json = df[[
        "trade_id", "date", "position_type", "tradingsymbol", "strike", "quantity",
        "entry_time", "exit_time", "entry_price", "exit_price", "exit_reason",
        "gross_pnl", "net_pnl", "duration_mins"
    ]].copy()
    trades_json["entry_time"] = trades_json["entry_time"].dt.strftime("%H:%M")
    trades_json["exit_time"] = trades_json["exit_time"].dt.strftime("%H:%M")
    trades_json["gross_pnl"] = trades_json["gross_pnl"].round(2)
    trades_json["net_pnl"] = trades_json["net_pnl"].round(2)
    trades_json["duration_mins"] = trades_json["duration_mins"].round(0).astype(int)
    table_data = trades_json.to_dict(orient="records")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Options Trading Strategy Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-card: #1e293b;
            --border: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-purple: #a855f7;
            --accent-amber: #f59e0b;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }}
        body {{
            background-color: var(--bg-primary);
            color: var(--text-primary);
            padding: 24px;
            min-height: 100vh;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 24px;
        }}
        .header-title h1 {{
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .badge {{
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-weight: 600;
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-blue);
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}
        .grid-kpi {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        .kpi-title {{
            font-size: 13px;
            color: var(--text-secondary);
            font-weight: 500;
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .kpi-val {{
            font-size: 26px;
            font-weight: 700;
        }}
        .kpi-sub {{
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 4px;
        }}
        .text-green {{ color: var(--accent-green); }}
        .text-red {{ color: var(--accent-red); }}
        .text-blue {{ color: var(--accent-blue); }}
        
        .grid-params-charts {{
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }}
        @media (max-width: 1024px) {{
            .grid-params-charts {{
                grid-template-columns: 1fr;
            }}
        }}
        .param-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .param-table tr {{
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .param-table td {{
            padding: 8px 0;
        }}
        .param-label {{
            color: var(--text-secondary);
        }}
        .param-val {{
            text-align: right;
            font-weight: 600;
            color: var(--text-primary);
        }}
        
        .chart-container {{
            position: relative;
            height: 280px;
            width: 100%;
        }}
        .charts-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }}
        @media (max-width: 768px) {{
            .charts-row {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 14px;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .table-responsive {{
            overflow-x: auto;
            max-height: 400px;
        }}
        table.trade-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}
        table.trade-table th {{
            position: sticky;
            top: 0;
            background: #24344d;
            padding: 10px 12px;
            color: var(--text-secondary);
            font-weight: 600;
            border-bottom: 1px solid var(--border);
        }}
        table.trade-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        table.trade-table tr:hover {{
            background: rgba(255, 255, 255, 0.02);
        }}
        .tag {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .tag-pe {{ background: rgba(34, 197, 94, 0.15); color: var(--accent-green); border: 1px solid rgba(34, 197, 94, 0.3); }}
        .tag-ce {{ background: rgba(239, 68, 68, 0.15); color: var(--accent-red); border: 1px solid rgba(239, 68, 68, 0.3); }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h1>PROJECT TRISHUL: NIFTY Intraday Options Selling Dashboard</h1>
            <span class="badge">3-Pillar Dual Momentum &amp; Daily Pivots + 20% Ratcheting Safety Net</span>
        </div>
        <div>
            <span style="font-size: 13px; color: var(--text-secondary);">Automated Execution Engine (FlatTrade &amp; Zerodha MIS)</span>
        </div>
    </div>


    <!-- Top KPI Cards -->
    <div class="grid-kpi">
        <div class="card">
            <div class="kpi-title">Net PnL</div>
            <div class="kpi-val text-green">₹{total_net:,.2f}</div>
            <div class="kpi-sub">Gross: ₹{total_gross:,.2f} | Costs: ₹{total_costs:,.2f}</div>
        </div>
        <div class="card">
            <div class="kpi-title">Win Rate</div>
            <div class="kpi-val text-blue">{win_rate:.1f}%</div>
            <div class="kpi-sub">{num_wins} Wins / {num_losses} Losses ({total_trades} Total)</div>
        </div>
        <div class="card">
            <div class="kpi-title">Profit Factor</div>
            <div class="kpi-val">{profit_factor:.2f}</div>
            <div class="kpi-sub">Win/Loss Ratio: {win_loss_ratio:.2f}</div>
        </div>
        <div class="card">
            <div class="kpi-title">Max Drawdown</div>
            <div class="kpi-val text-red">₹{max_drawdown:,.2f}</div>
            <div class="kpi-sub">{max_drawdown_pct:.2f}% of peak equity</div>
        </div>
        <div class="card">
            <div class="kpi-title">Consecutive Streaks</div>
            <div class="kpi-val">{max_consec_wins}W / {max_consec_losses}L</div>
            <div class="kpi-sub">Avg Trade Duration: {avg_duration:.0f} mins</div>
        </div>
    </div>

    <!-- Main Grid: Parameters & Main Chart -->
    <div class="grid-params-charts">
        <!-- Strategy Parameters Card -->
        <div class="card">
            <div class="section-title">Strategy Specifications</div>
            <table class="param-table">
                <tr><td class="param-label">Underlying Instrument</td><td class="param-val">NIFTY 50 Spot</td></tr>
                <tr><td class="param-label">Trading Instrument</td><td class="param-val">Weekly NIFTY Options</td></tr>
                <tr><td class="param-label">Candle Timeframe</td><td class="param-val">5 Minutes</td></tr>
                <tr><td class="param-label">Execution Mode</td><td class="param-val">MIS (Intraday Market)</td></tr>
                <tr><td class="param-label">Position Sizing</td><td class="param-val">1 Lot (65 units)</td></tr>
                <tr><td class="param-label">Max Trades / Day</td><td class="param-val">3 Trades Max</td></tr>
                <tr><td class="param-label">Supertrend Config</td><td class="param-val">Period: 7, Mult: 3.0</td></tr>
                <tr><td class="param-label">Pivot Points</td><td class="param-val">Standard (PP, R1, S1)</td></tr>
                <tr><td class="param-label">Bullish Entry</td><td class="param-val">Close > ST & Close > R1</td></tr>
                <tr><td class="param-label">Bearish Entry</td><td class="param-val">Close < ST & Close < S1</td></tr>
                <tr><td class="param-label">Exit Rules</td><td class="param-val">ST Flip / 15:15 IST Square-Off</td></tr>
                <tr><td class="param-label">Initial Base Capital</td><td class="param-val">₹2,00,000</td></tr>
            </table>

            <div class="section-title" style="margin-top: 20px;">Exit Attribution</div>
            <table class="param-table">
                {"".join([f"<tr><td class='param-label'>{k}</td><td class='param-val'>{v['trades']} ({v['win_rate']:.0f}% win | ₹{v['net_pnl']:,.0f})</td></tr>" for k, v in by_reason.items()])}
            </table>
        </div>

        <!-- Cumulative Equity Chart Card -->
        <div class="card">
            <div class="section-title">Cumulative Portfolio Equity Curve (₹)</div>
            <div class="chart-container">
                <canvas id="equityChart"></canvas>
            </div>
        </div>
    </div>

    <!-- Secondary Charts Row -->
    <div class="charts-row">
        <div class="card">
            <div class="section-title">Day-of-Week Net Profit (₹) & Seasonality</div>
            <div class="chart-container">
                <canvas id="dayProfitChart"></canvas>
            </div>
        </div>
        <div class="card">
            <div class="section-title">Underwater Drawdown Curve (₹)</div>
            <div class="chart-container">
                <canvas id="drawdownChart"></canvas>
            </div>
        </div>
    </div>

    <!-- Day-Wise Breakdown Table Card -->
    <div class="card" style="margin-bottom: 24px;">
        <div class="section-title">Day-Wise Profitability Breakdown (Which Days to Trade)</div>
        <table class="param-table">
            <tr style="border-bottom: 1px solid var(--border); font-weight: 600; color: var(--text-secondary);">
                <td>Day of Week</td>
                <td style="text-align:center;">Trades</td>
                <td style="text-align:center;">Win Rate</td>
                <td style="text-align:center;">Profit Factor</td>
                <td style="text-align:center;">Avg PnL / Trade</td>
                <td style="text-align:right;">Net Realized PnL</td>
            </tr>
            {"".join([f"""<tr>
                <td style='font-weight:600;'>{x['day']}</td>
                <td style='text-align:center;'>{x['trades']} ({x['wins']}W / {x['losses']}L)</td>
                <td style='text-align:center;'>{x['win_rate']:.1f}%</td>
                <td style='text-align:center;'>{x['profit_factor']:.2f}</td>
                <td style='text-align:center;' class='{"text-green" if x["avg_pnl"]>0 else "text-red"}'>₹{x['avg_pnl']:,.2f}</td>
                <td style='text-align:right;' class='{"text-green" if x["net_pnl"]>0 else "text-red"}' style='font-weight:700;'>₹{x['net_pnl']:,.2f}</td>
            </tr>""" for x in by_day])}
        </table>
    </div>


    <!-- Trade History Table -->
    <div class="card">
        <div class="section-title">
            <span>Completed Strategy Trades ({total_trades})</span>
        </div>
        <div class="table-responsive">
            <table class="trade-table" id="tradeTable">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Date</th>
                        <th>Position</th>
                        <th>Contract</th>
                        <th>Strike</th>
                        <th>Qty</th>
                        <th>Entry Time</th>
                        <th>Exit Time</th>
                        <th>Duration</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>Exit Reason</th>
                        <th>Gross PnL</th>
                        <th>Net PnL</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f"""<tr>
                        <td>{t['trade_id']}</td>
                        <td>{t['date']}</td>
                        <td><span class="tag {'tag-pe' if t['position_type']=='SHORT_PE' else 'tag-ce'}">{t['position_type']}</span></td>
                        <td>{t['tradingsymbol']}</td>
                        <td>{t['strike']}</td>
                        <td>{t['quantity']}</td>
                        <td>{t['entry_time']}</td>
                        <td>{t['exit_time']}</td>
                        <td>{t['duration_mins']}m</td>
                        <td>₹{t['entry_price']:.2f}</td>
                        <td>₹{t['exit_price']:.2f}</td>
                        <td>{t['exit_reason']}</td>
                        <td class="{'text-green' if t['gross_pnl']>0 else 'text-red'}">₹{t['gross_pnl']:,.2f}</td>
                        <td class="{'text-green' if t['net_pnl']>0 else 'text-red'}" style="font-weight:600;">₹{t['net_pnl']:,.2f}</td>
                    </tr>""" for t in table_data])}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const labels = {json.dumps(dates_list)};
        const equityData = {json.dumps(equity_curve)};
        const drawdownData = {json.dumps(drawdown_curve)};
        const pnlData = {json.dumps(pnl_series)};

        // 1. Equity Chart
        new Chart(document.getElementById('equityChart'), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'Portfolio Equity (₹)',
                    data: equityData,
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.1)',
                    fill: true,
                    tension: 0.2,
                    borderWidth: 2,
                    pointRadius: 3,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    x: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8', maxTicksLimit: 8 }} }},
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }}
                }}
            }}
        }});

        // 2. Day-of-Week Net Profit Chart
        new Chart(document.getElementById('dayProfitChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(day_labels)},
                datasets: [{{
                    label: 'Net PnL (₹)',
                    data: {json.dumps(day_pnl_data)},
                    backgroundColor: {json.dumps(day_pnl_data)}.map(v => v > 0 ? '#22c55e' : '#ef4444'),
                    borderRadius: 6,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8' }} }},
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }}
                }}
            }}
        }});


        // 3. Drawdown Chart
        new Chart(document.getElementById('drawdownChart'), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'Drawdown (₹)',
                    data: drawdownData,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.15)',
                    fill: true,
                    tension: 0.2,
                    borderWidth: 1.5,
                    pointRadius: 2,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8', maxTicksLimit: 6 }} }},
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }}
                }}
            }}
        }});

        // 3. Trade Net PnL Bar Chart
        new Chart(document.getElementById('pnlBarChart'), {{
            type: 'bar',
            data: {{
                labels: labels.map((_, i) => '#' + (i + 1)),
                datasets: [{{
                    label: 'Net PnL (₹)',
                    data: pnlData,
                    backgroundColor: pnlData.map(v => v > 0 ? '#22c55e' : '#ef4444'),
                    borderRadius: 4,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', maxTicksLimit: 12 }} }},
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

    out_file = Path("out/trishul_dashboard.html")
    out_file.write_text(html_content, encoding="utf-8")
    Path("out/nifty_options_dashboard.html").write_text(html_content, encoding="utf-8")
    print(f"Dashboard successfully generated at: {out_file.resolve()}")



if __name__ == "__main__":
    generate_dashboard()
