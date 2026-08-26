Automated Algorithmic Trading Architecture for the Indian Equity Market: A Comprehensive Blueprint
1. Introduction to the Quantitative Trading Ecosystem in India
The structural evolution of programmatic market access within the Indian equity markets has radically transformed the landscape for retail and proprietary quantitative traders. Historically characterized by institutional exclusivity and prohibitive latency barriers, the modern environment—facilitated by advanced RESTful application programming interfaces (APIs) and WebSocket streaming protocols provided by leading discount brokerages—now permits the deployment of highly sophisticated algorithmic systems1. For a quantitative framework operating with a defined, limited capital base, such as an initial allocation of ₹5,00,000, the architectural rigor and risk mitigation protocols must be indistinguishable from institutional setups. This is necessary to mitigate technical debt, minimize execution slippage, and ensure survival during anomalous market micro-structure events.
This comprehensive report details the design, deployment, and operational architecture of a hybrid algorithmic trading system specifically engineered for the National Stock Exchange of India (NSE). The operational parameters mandate the development of a dynamic stock selection matrix exclusively targeting the Nifty 500 index universe. The execution engine is required to deploy bidirectional (long and short) intraday strategies capable of navigating diverse market regimes, alongside long-only, multi-day swing strategies designed to hold positions for durations spanning one to five days3.
Furthermore, the code architecture must natively handle complex state management. This includes the dynamic tracking of trailing stop-loss mechanics for multi-day swing positions, highly resilient WebSocket connection management to gracefully handle 24-hour server recycling and abnormal transport closures, and the enforcement of a strict initial and scaling risk framework. Finally, the blueprint dictates that all theoretical backtesting must be executed through high-performance vectorized environments that natively incorporate the exact 2026 Indian taxation and brokerage cost structures, culminating in a daily automated summary dashboard for performance attribution and monitoring4.
2. Capital Stratification and Strict Risk Management Framework
Operating a multi-strategy automated system on a ₹5,00,000 capital base demands a mathematically sound capital scaling and risk distribution model. Without structural constraints and hard-coded kill switches, intraday volatility or overnight gap-downs can induce irrecoverable drawdowns that permanently impair the trading capital. The risk architecture must compartmentalize capital to prevent margin contention between the high-frequency intraday engine and the multi-day swing engine.
2.1 Segmented Capital Allocation and Margin Mechanics
The initial ₹5,00,000 capital must be bifurcated based on the regulatory margin requirements of the Indian exchange segments. The Securities and Exchange Board of India (SEBI) imposes distinct leverage restrictions on intraday trades versus overnight delivery trades. The system allocates this capital into two distinct programmatic silos.
Capital Segment
Allocated Base
Product Code
Maximum Allowed Leverage
Purchasing Power
Intraday Engine
₹2,00,000
Margin Intraday Square-off (MIS)
Up to 5x
₹10,00,000
Swing Engine
₹3,00,000
Cash and Carry (CNC)
1x (No Leverage)
₹3,00,000

The intraday allocation of ₹2,00,000 capitalizes on the broker's MIS product code, which permits up to 5x leverage for approved equity instruments7. Consequently, this allocation translates to a maximum theoretical intraday purchasing power of ₹10,00,000. Conversely, overnight equity positions must be fully funded under CNC rules, as leverage is restricted and positions must be settled via the depository system8. Therefore, the swing allocation remains fixed at its ₹3,00,000 cash value. This strict separation ensures that an aggressive intraday drawdown cannot force a margin call that automatically liquidates a profitable multi-day swing position.
2.2 Micro and Macro Risk Thresholds
A rigid risk management framework dictates survival in quantitative trading. The system must enforce mathematical constraints at the trade, strategy, and overall portfolio levels. The foundational metric is the Risk Per Trade (RPT), which is strictly capped at 1% of the allocated segment capital. For an intraday trade, the maximum acceptable loss is ₹2,000. For a swing trade, the maximum risk is calculated as ₹3,00,000 multiplied by 1%, yielding ₹3,000.
Position sizing is not based on purchasing a fixed quantity of shares; rather, it is dynamically calculated as the Risk Per Trade divided by the absolute distance to the Initial Stop Loss (ISL).

This volatility-adjusted sizing ensures that trades with wider stop-losses naturally incur smaller position sizes, maintaining a constant portfolio heat regardless of the individual asset's price action.
At the macro level, the system must feature a hard "kill switch" triggered by consecutive losses or abnormal market conditions9. This Daily Value at Risk (VaR) mechanism monitors the cumulative realized and unrealized intraday equity curve. If the daily intraday loss breaches ₹6,000 (representing 3% of the intraday capital), the execution engine is programmed to halt all new signal generation, flatten all existing intraday positions via marketable limit orders, cancel all pending resting orders, and transition the system into a "halted" state until the subsequent trading day10.
Capital scaling mechanisms are employed to ensure asymmetric compounding. The base capital utilized for the RPT and position sizing calculations is recalibrated on a weekly epoch, rather than continuously. Profits are not immediately compounded into the subsequent trade, which protects against rapid mean-reversion following a winning streak. Instead, a high-water mark system updates the base capital only if the portfolio equity closes the week strictly 5% above the previous baseline.
3. Nifty 500 Universe Selection and Dynamic Filtering
The Nifty 500 index represents a massive swath of the Indian equity market, encompassing approximately 92.04% of the free-float market capitalization of all stocks listed on the NSE and capturing roughly 84.07% of the total traded value11. While this provides a highly diverse universe for strategy generation, indiscriminately trading all 500 components is technologically intensive and exposes the execution engine to severe liquidity risks at the lower-cap spectrum of the index.
3.1 Automated Universe Ingestion
The daily constitution of the Nifty 500 is not static; it is subject to corporate actions, delistings, and periodic index reshuffles by the exchange. The system architecture must natively ingest the latest constituent list. Utilizing Python libraries such as nsepython or executing direct REST API requests to the NSE server enables the automated downloading of the official .csv index constituent files12. The extraction routine must be scheduled via a cron job to execute daily at 08:00 AM IST, ensuring the trading engine initializes with a perfectly accurate symbol mapping before the pre-market session opens14.
3.2 Liquidity and Volatility Filtering Matrix
To entirely avoid execution slippage, mitigate the impact cost of market orders, and ensure rapid order routing, the raw list of 500 stocks must be programmatically filtered into a highly curated "Tradeable Universe." The engine runs a daily pre-market calculation assessing 30 days of historical volume and volatility data, applying a strict filtering matrix.
Filter Parameter
Threshold Requirement
Economic Rationale
Average Daily Volume (ADV)
> 1,000,000 shares over 30 days
Ensures sufficient market depth to absorb algorithmic market orders without moving the spread.
Daily Turnover
> ₹50 Crores consistently
Eliminates low-liquidity mid-caps susceptible to operator manipulation or upper/lower circuit freezes.
Price Constraint
Between ₹100 and ₹10,000
Eliminates penny stock volatility and highly illiquid absolute-priced assets that exhibit massive bid-ask spreads.
Average True Range (ATR)
14-day ATR > 2% of asset price
Ensures sufficient intraday and multi-day volatility exists to justify the frictional transaction costs (brokerage and STT).

This cascading filtering matrix typically distills the Nifty 500 down to a highly liquid, volatile subset of 120 to 150 equities. This focused universe is perfectly suited for algorithmic targeting, drastically reducing the computational overhead on the WebSocket data ingestion engine while simultaneously maximizing the probability of clean order fills.
4. Algorithmic Strategy Logic and Mathematical Frameworks
The core intelligence of the system relies on executing uncorrelated strategies across distinct time horizons. By deploying market-neutral intraday strategies alongside long-biased momentum swing strategies, the system benefits from diversification of both timeline and market regime3.
4.1 Intraday Trading Engine (Long and Short Execution)
Intraday strategies must function independently of the broader macroeconomic regime, seeking to extract alpha from short-term liquidity imbalances and behavioral overreactions. In the Indian cash market, naked short selling is exclusively permitted via MIS (intraday) product codes and must be strictly squared off before 3:20 PM IST by the broker's automated risk management systems7.
The intraday engine deploys a dual-pronged approach. The primary model is a Momentum Breakout (Trend Following) strategy utilizing the Volume Weighted Average Price (VWAP) anchored to the daily open, combined with an Opening Range Breakout (ORB) metric. The logic dictates that if a stock breaches its first 15-minute high with a simultaneous 2x expansion in volume relative to its 5-day average, and the price sustains above the VWAP, a long position is initiated. The stop loss is trailed immediately below the VWAP line. Conversely, breaking the 15-minute low below the VWAP triggers a short position, capitalizing on early morning institutional distribution.
To combat sideways, mean-reverting market regimes where breakout strategies suffer continuous false triggers (whipsaws), a secondary Mean Reversion strategy operates concurrently. This logic utilizes standard Bollinger Bands configured to a 20-period simple moving average with 2 standard deviations, paired with a 14-period Relative Strength Index (RSI). A short signal is generated when the price action pierces and closes outside the upper Bollinger Band while the RSI simultaneously reads above 80, indicating an overbought extreme. The algorithm initiates a short position, targeting the 20-period SMA as the mean-reversion exit point.
4.2 Multi-Day Swing Trading Engine (Long Only)
Quantitative research specifically analyzing the Nifty 500 demonstrates that momentum investment strategies applied over multi-day horizons yield superior, statistically significant returns, particularly when robust entry mechanics are paired with disciplined trailing stops3. Because overnight short positions in the Indian cash market are prohibited for retail participants without engaging in complex and capital-intensive Stock Lending and Borrowing (SLB) mechanisms, the swing engine is structurally restricted to long-only trades.
The strategy parameters target a 1 to 5-day holding period utilizing a Dual Moving Average Crossover (DMAC) combined with moving average convergence/divergence (MACD) histogram expansions6. Entry logic requires the fast 10-period Exponential Moving Average (EMA) to cross above the slow 30-period EMA, strictly validated by a positive and expanding MACD histogram.
Trailing stop-losses are critical for swing trades. Fixed percentage trailing stops often fall victim to standard market noise, resulting in premature exits. Therefore, the architecture mandates an Average True Range (ATR) based trailing stop, explicitly utilizing a Chandelier Exit methodology15.

As the asset establishes new highs during the holding period, the TSL ratchets upwards. The engine never lowers the TSL; it only moves unidirectionally upwards to lock in unrealized profits.
4.3 State Persistence and Localized Database Schemas
A critical architectural challenge arises because swing trades span multiple days. The internal memory (RAM) of a running Python process cannot be relied upon to maintain the state of the strategy over a 5-day period. Server reboots, scheduled weekend maintenance, or unhandled exceptions would entirely wipe the tracking variable representing the "Highest High Since Entry," thereby destroying the Chandelier Exit logic16.
Consequently, the execution engine must integrate a localized SQLite database designed to persistently log the state of all open positions16. A dedicated Positions table is structured to constantly log the asset symbol, the entry_price, the dynamic highest_high, the current_atr, and the calculated tsl_value. The execution engine is programmed so that upon every daily initialization, it reads this database, cross-references it with the broker's REST API holdings, and perfectly restores the mathematical state of all active swing trades before the market opens.
5. System Architecture, Authentication, and Execution Engine
The infrastructural backbone of the system interacts primarily with the Zerodha Kite Connect API. This gateway provides a RESTful interface for order management and a WebSocket protocol for streaming live market tick data, engineered to process millions of client requests daily2.
5.1 Automated Authentication Protocol (OAuth 2.0 and External TOTP)
A major hurdle in automated trading is continuous, unassisted authentication. Zerodha mandates a daily token regeneration architecture driven by stringent SEBI security guidelines17. Access tokens forcibly expire precisely at 06:00 AM IST daily to prevent long-standing session hijacking18. Relying on manual login via a browser neutralizes the fundamental purpose of an automated, server-deployed system.
The architecture must utilize an autonomous headless login mechanism using the Python requests and pyotp libraries, deliberately avoiding the use of heavy, fragile, and memory-intensive browser automation tools like Selenium WebDriver19. The authentication state machine follows a strict sequence: A chronometric scheduler executes the login.py script daily at 06:05 AM IST18. The script initiates a POST request passing the encrypted user_id and password. Upon receiving a request_id from the authentication server, the system utilizes the pyotp.TOTP(totp_key).now() function to autonomously generate the 6-digit Time-based One Time Password required for Two-Factor Authentication21. A secondary POST request submits this TOTP, bypassing the visual session, and catches the redirect URL to extract the request_token20. This token is immediately exchanged with the exchange server for a permanent access_token, which is saved securely in a local configuration file or the SQLite database for the remainder of the trading session18.
5.2 Resilient WebSocket Data Ingestion and Abnormal Closure Handling
Live tick data must be strictly streamed via WebSockets. Attempting to poll the REST API for real-time data will instantly breach the restrictive polling limits (1 request per second for quotes), leading to HTTP 429 "Too Many Requests" bans22. However, WebSocket connections in production environments frequently suffer from silent disconnections, commonly throwing a 1006 Abnormal Closure error. This occurs due to external load balancers, ISP drops, cloud NAT gateway timeouts, or the exchange's own 24-hour socket recycling protocols24.
To prevent the trading bot from silently trading on stale data or experiencing a catastrophic "reconnect storm" that crashes the local network interface, the architecture implements advanced transport-layer resilience:

Resilience Protocol
Technical Implementation
Operational Rationale
Application-Level Heartbeats
Dispatch a ping frame every 15 seconds. Expect pong within 5 seconds.
TCP keepalives are notoriously slow (often defaulting to 2 hours). Application heartbeats detect dead, hanging sockets immediately25.
Jittered Exponential Backoff
Delay reconnections by  seconds.
Prevents all disconnected clients from hammering the exchange server simultaneously. Jitter spreads the network load and prevents immediate rate-limiting24.
REST State Reconciliation
Fetch full REST API order book and positions snapshot upon successful WebSocket reconnect.
A gap in the WebSocket stream implies limit orders or stop-losses may have executed during the downtime. The bot must sync its internal state machine before processing new ticks24.

Treating a 1006 error not as a fatal exception, but rather as a scheduled infrastructure event, fundamentally shifts the code from being defensive to being highly resilient24.
5.3 Order Routing and Rate Limit Compliance
The Kite Connect API imposes stringent rate limits designed to protect the exchange infrastructure, which dictate how the execution engine routes orders. April 2026 mandates dictate that order placement is exclusively restricted to whitelisted, static IP addresses26. Therefore, deployment on a cloud provider (such as AWS EC2 or Google Cloud Compute) utilizing an Elastic IP is mandatory.
The system is mathematically restricted to a maximum of 10 orders per second (OPS), 200 orders per minute, and a strict cap of 5,000 total orders per day across all segments23. It is critical to note that invalid orders (orders rejected for margin shortfall or formatting errors) still consume this quota. Iceberg orders, used to slice large quantities, constitute a single order for the API but consume multiple limits on the exchange side26.
Furthermore, order modification is heavily restricted to a maximum of 25 modifications per individual order27. This profoundly impacts the Trailing Stop Loss logic. The system cannot blindly modify the exchange resting order on every minor price tick; it must buffer modifications, only updating the exchange order if the newly calculated TSL differs by greater than 0.5% from the prior TSL, thereby conserving modification limits while maintaining safety.
6. Comprehensive Backtesting and Cost Analysis via VectorBT
A pervasive fallacy in retail algorithmic trading is the development of strategies based on gross theoretical returns, entirely neglecting the severe friction of real-world transaction costs. To ensure absolute realism, the backtesting engine requires integration with VectorBT, a highly optimized, pandas and Numba-accelerated Python library6. VectorBT is capable of evaluating millions of parameter permutations via vectorized operations natively suited for the data-heavy Indian markets, bypassing the crippling slowness of traditional Python for loops28.
6.1 The Zerodha 2026 Tax and Brokerage Schedule
The VectorBT portfolio simulator must accurately model the highly complex, asymmetrical Indian regulatory tax structure. Specifically, it must incorporate the April 1, 2026, Budget revisions to the Securities Transaction Tax (STT), which altered the calculus for algorithmic profitability5.
The following table details the precise frictional costs that the backtesting engine must deduct from every simulated trade to arrive at a realistic net return profile:
Frictional Cost Component
Equity Intraday (MIS Segment)
Equity Delivery (Swing/CNC Segment)
Brokerage
Flat ₹20 per executed order or 0.03% (whichever is mathematically lower)
₹0 (Zero brokerage for delivery)
Securities Transaction Tax (STT)
0.025% applied strictly on the Sell Side only
0.1% applied on BOTH the Buy and Sell sides
Exchange Transaction Charge
NSE: 0.00297% / BSE: 0.00375%
NSE: 0.00297% / BSE: 0.00375%
Goods and Services Tax (GST)
18% levied on the sum of (Brokerage + SEBI + Exchange Txn charges)
18% levied on the sum of (Brokerage + SEBI + Exchange Txn charges)
SEBI Regulatory Charges
₹10 per Crore of turnover (0.0001%)
₹10 per Crore of turnover (0.0001%)
State Stamp Duty
0.003% applied on the Buy side only
0.015% applied on the Buy side only
Depository Participant (DP) Charges
Not Applicable
₹13.5 + 18% GST (applied uniquely on Sell delivery transactions)

(Source Data: Zerodha Official Tariff Parameters & 2026 STT Revisions4)
6.2 Custom VectorBT Cost Array Implementation
Because the transaction costs are highly asymmetrical—for example, STT applies differently to buys versus sells in intraday trading, and flat DP charges are applied solely upon the liquidation of delivery assets—standard percentage-based fee metrics found in generic backtesting engines produce vastly inaccurate equity curves.
The system architecture requires a custom slippage and fee function array injected directly into the core of VectorBT28. The engine simulates these frictions by iterating over execution signals, computing the exact rupee-value transaction cost based on the notional size of the trade, subtracting this aggregate tax burden from the theoretical gross profit and loss (PnL), and logging the true net PnL. Furthermore, to simulate the impact cost of executing market orders within the mid-cap heavy Nifty 500, a constant absolute slippage penalty of 0.05% is calculated against the theoretical execution price. Only strategies that survive this rigorous, friction-heavy simulation are approved for live capital deployment.
7. Performance Tracking and the Daily Summary Dashboard
An automated system must operate transparently, providing the quantitative developer with immediate insights into system health and capital allocation without requiring manual database queries. The architecture dictates the inclusion of a reporting module that activates post-market (e.g., at 16:00 IST, following the market close at 15:30 IST) to aggregate daily trading logs from the local SQLite database and cross-reference them against the Zerodha REST API holdings() and positions() endpoints.
This data is processed and visualized via a daily summary dashboard, generated using Python's Streamlit framework or via standard HTML/CSS rendering combined with Plotly graphical objects6. The dashboard provides immediate operational intelligence, detailing macro PnL metrics such as Gross Realized PnL, Net Realized PnL (after the simulated 2026 tax deductions), and the Unrealized PnL of open swing trades. It audits trade execution efficiency by monitoring the total orders placed against the 5,000 daily exchange limit and analyzing average execution slippage.
Crucially, the dashboard visually maps drawdown alerts, comparing current capital against the weekly high-water mark to ensure the sizing algorithms remain accurately calibrated. For the multi-day engine, it generates a tabular view of all active swing positions, their original entry prices, the current market price, and the precise level of the persisted Trailing Stop Loss pulled directly from the SQLite database. This ensures complete observability into the automated decision-making matrix.
8. Conclusion
Constructing an algorithmic trading framework for the Indian equity markets with a constrained ₹5,00,000 capital base requires a seamless integration of robust execution architecture, precise risk mitigation, and sophisticated programmatic state management. By relying on a headless OAuth flow, implementing deep transport-layer resilience against WebSocket 1006 terminations, persistently storing multiday trailing stop-loss values in an SQLite schema, and vectorizing backtests with rigorous 2026 transaction tax modeling, the system distances itself from fragile, amateur retail scripts. The structural separation of the high-frequency intraday and multi-day swing modules natively hedges the portfolio, capturing rapid market micro-structure movements while simultaneously participating in overarching macroeconomic momentum, culminating in a highly robust, automated financial engine.
9. Backtest Results (as implemented in EngineI/, updated 2026-08-03)
This section records what has actually been built and tested against real cached Nifty 500 data, so a future session can pick up from here instead of re-deriving it.

9.1 Implementation status
The codebase implements five strategies, not the three named above -- the project had a pre-existing custom variant before this instruction file was written, kept as-is rather than replaced:
- stage1_only / stage1plus2 (screener_eod.py, confirm_intraday.py, backtest.py): the project's original long-only intraday strategy. EOD pre-screen (gain>2%, close near high, rvol>=2) then next-session gap-up + break of prior 5-day swing high + VWAP hold + RSI>45 rising + MACD cross. Not identical to section 4.1's ORB -- swing-high break instead of a literal first-15-min opening-range high, plus an EOD pre-filter and RSI/MACD gate the spec doesn't call for. ATR-trailing stop, forced close 15:15 IST, MIS.
- swing (swing_engine.py): section 4.2 as specified -- 10/30 EMA cross + expanding MACD histogram entry, Chandelier Exit (highest_high - 3xATR14) trailing stop, 1-5 day hold cap, CNC, long-only. Runs on daily bars (no SQLite state -- not needed for a vectorized backtest, only for live position persistence).
- orb_vwap (orb_vwap.py): section 4.1's primary model as literally specified -- first-15-min high/low breakout + 2x volume expansion vs 5-day average, VWAP-line trailing stop, both long and short.
- bollinger_meanrev (bollinger_meanrev.py): section 4.1's secondary model -- BB(20, 2sigma) + RSI(14)>80 short, target the mid-band. Originally built with NO stop (the spec only defines a target); a trailing stop was added afterward (see 9.3) since it was the only one of the five with no protective exit.
- costs.py: the section 6.1 fee table (asymmetric MIS vs CNC -- brokerage, STT, exchange txn, SEBI, GST, stamp duty, DP charges) implemented and wired into Trade.net_pnl on every strategy. Backtest.py previously reported gross PnL only; all report.py output is now net-of-cost.
- cached_data.py / compare_backtests.py: loads all five strategies off the same cached bars (.cache/daily_bars.pkl, .cache/intraday_bars.pkl) and runs them through one report for direct comparison.

9.2 Data coverage caveat
Comparisons run on 194-200 symbols (out of Nifty 500), not the full universe -- the full 500-symbol token map from an earlier run was only ever held in-process and never persisted; tokens.json only has 200 symbol->token pairs saved. Today's Kite session token is expired; extending to the full 500 needs one interactive browser re-login (kite_auth.py), not a code change. Daily bars go back ~8 years and can be windowed (cached_data.load_symbol_bars(daily_years=N)); intraday 5-min bars are capped at the last 60 days regardless of window requested -- that's a Kite Connect free-plan limit on minute data, not a caching choice, so none of the intraday strategies (stage1plus2, orb_vwap, bollinger_meanrev) can be evaluated over a longer intraday history without a paid plan.

9.3 Results (net of 2026 fees/taxes, last 2 years of daily history / last 60 days of intraday, ~194-200 symbols)
| Strategy | Trades | Win rate | Net PnL | Return |
|---|---|---|---|---|
| stage1_only | 1,436 | 44.2% | Rs -73,109 | -24.4% |
| stage1plus2 (original) | 34 | 41.2% | Rs +695 | +0.23% |
| swing | 1,329 | 44.1% | Rs -297,808 | -99.3% |
| orb_vwap | 806 | 33.9% | Rs -16,320 | -5.4% |
| bollinger_meanrev (no stop) | 2,895 | 50.8% | Rs -101,216 | -33.7% |

Only stage1plus2 (the pre-existing strategy, not one of the three named in this spec) is near breakeven, and that's on just 34 trades -- too few to trust. None of the three instruction.md strategies show an edge as literally specified on this data/sample. swing's large loss was double-checked for a position-sizing bug (average notional ~Rs 38.7k, nowhere near the Rs 3L capital cap) -- it's a real negative-edge result, not a cost-model artifact.

9.4 Trailing-stop experiment on bollinger_meanrev
Added an ATR-based trailing stop (stop = lowest_low_since_entry + mult x ATR(14), ratchets down only) since it was the one strategy with no protective exit. Swept the multiplier:

| ATR mult | Win rate | Profit factor | Net PnL | Max drawdown |
|---|---|---|---|---|
| 0.75x | 19.1% | 0.25 | Rs -92,269 | Rs 92,326 |
| 1.0x | 17.0% | 0.18 | Rs -127,610 | Rs 127,591 |
| 1.5x | 23.3% | 0.29 | Rs -144,683 | Rs 144,714 |
| 2.0x | 32.2% | 0.44 | Rs -135,870 | Rs 136,325 |
| 2.5x | 38.8% | 0.52 | Rs -126,024 | Rs 126,669 |
| 3.0x | 43.7% | 0.56 | Rs -119,802 | Rs 120,432 |
| none (target-only) | 50.8% | 0.64 | Rs -101,216 | Rs 102,993 |

Finding: tighter stops make this strategy strictly worse, not better -- narrower multiples get whipsawed out before the mean-reversion has room to play out (win rate collapses to ~17-19% below 1x ATR), and profit factor climbs monotonically as the stop widens toward the no-stop case. The strategy's weak edge here partly depends on trades recovering rather than being cut early. Still net-negative at every multiplier tested; 4x/5x was flagged as a next step (not yet run) to see whether it turns net-positive or just keeps approaching the no-stop baseline from below. Conclusion so far: this strategy needs either a wider stop than typical (>3x ATR) or a fundamentally different exit design, not a standard tight risk stop.

9.5 Open next steps (superseded in part by 9.6-9.7 below)
- Extend token map to the full Nifty 500 universe (needs interactive Kite re-login).
- swing has not had its exit parameters tuned yet (still at instruction.md's literal 3x ATR Chandelier default) -- worth the same sweep treatment before concluding it lacks edge.
- No strategy here is net-profitable yet; none should move toward live/paper trading on current results.

9.6 Diagnosing orb_vwap's overtrading, and the confluence rebuild (orb_confluence.py)
orb_vwap was the standout of the five -- the only one with positive GROSS PnL (Rs8,454 on 806 trades), meaning the ORB+volume signal itself has real edge; it loses net (Rs-16,320) purely to fee drag from trading too often (806 x ~Rs31/trade = Rs24,775, 3x the gross edge).

Broke the trade log down by exit_reason to find out why it trades so often and what's actually driving the loss:
| Exit reason | Trades | Avg net PnL |
|---|---|---|
| vwap_cross (stopped out) | 511 (63%) | Rs -163 |
| forced_close (held to EOD) | 291 (36%) | Rs +230 |

The VWAP-line trailing stop specified in section 4.1 is too tight for this signal's noise -- two-thirds of trades get whipsawed out on a normal pullback through VWAP, and those trades lose money on average, while trades simply held to end of day make money on average. The exit design was the problem, not a lack of edge or a need for more filters.

Built orb_confluence.py to test the fix directly: same ORB+volume signal, same VWAP trend-side check, PLUS two more confirmations (RSI(14) in a trending-not-exhausted zone -- 50-75 long / 25-50 short -- and MACD line agreeing with direction) to skip already-exhausted breakouts, and swapped the VWAP-line stop for an ATR Chandelier-style trailing stop (highest-high-since-entry minus mult x ATR, ratchets in favor only).

Two false starts on the ATR itself, both instructive:
- ATR(14) computed fresh each session from that day's own first ~70 minutes: even tighter than the VWAP stop, 675/731 trades (92%) stopped out.
- Prior day's DAILY ATR as the stop distance: wrong scale entirely -- 2.5x a full day's range as an intraday trail essentially never triggers (1/731 stopped), which just reproduces "hold to forced close regardless," and gross fell to Rs4,557 (still below orb_vwap's Rs8,454) because the confirmations without a working stop changed which trades got taken for the worse.
- Fix: ATR(14) computed on the symbol's CONTINUOUS 5-min series (not reset per session, correct timescale) -- then swept the Chandelier multiplier:

| ATR mult | Win rate | Profit factor | Gross PnL | Net PnL | Max DD |
|---|---|---|---|---|---|
| 2.5x | 30.4% | 0.58 | Rs -3,865 | Rs -26,329 | Rs 26,626 |
| 3.5x | 34.6% | 0.75 | Rs 3,800 | Rs -18,662 | -- |
| 4.5x | 39.3% | 0.86 | Rs 11,657 | Rs -10,801 | Rs 13,240 |
| **5.0x (chosen default)** | 39.5% | 0.91 | Rs 14,975 | Rs -7,480 | Rs 12,317 |
| 5.5x | 40.9% | 0.91 | Rs 14,557 | Rs -7,896 | Rs 12,663 |
| 6.0x | 42.0% | 0.90 | Rs 14,087 | Rs -8,366 | Rs 12,271 |
| 10.0x | 44.3% | 0.89 | Rs 11,362 | Rs -11,089 | -- |

5.0x ATR is the peak (net PnL, profit factor, and max drawdown all best or near-best there) and is now the default CHANDELIER_MULT in orb_confluence.py. Net result vs. the original: net loss cut from Rs-16,320 to Rs-7,480 (54% reduction) at a similar trade count (731 vs 806), gross PnL nearly doubled (Rs14,975 vs Rs8,454), and max drawdown roughly halved (Rs12,317 vs Rs18,046). Still net-negative, but this is the closest any strategy has come to breakeven at a meaningful sample size (706-731 trades vs. stage1plus2's 34).

9.7 Updated ranking and next steps
orb_confluence is now the standout: real gross edge, cheapest-to-run instrument type (MIS), closest to breakeven at a real sample size, and the failure mode (fee drag on marginal trades) is well-understood and directly addressable -- unlike swing or bollinger_meanrev, whose signals themselves are net-negative gross.
- Natural next move: combine orb_confluence's tighter entry filters with position-size scaling (larger positions dilute the ~Rs20-capped MIS brokerage as a % of trade) rather than just raising the volume threshold further -- untested so far.
- Re-run orb_confluence and stage1plus2 against the full 500-symbol universe once re-authenticated, to get stage1plus2 past its 34-trade sample-size problem.
- swing's Chandelier multiplier has still never been swept (open item carried over from 9.5) -- same treatment likely worth doing before writing it off, given how much the equivalent sweep moved orb_confluence and bollinger_meanrev.
- Still no strategy is net-profitable; none should move toward live/paper trading yet.

Appendix: Comprehensive AI Coding Prompt
The following highly detailed and structured prompt is designed to be extracted and fed directly into an advanced Large Language Model (e.g., Claude 3.5 Sonnet, GPT-4o) to generate the complete, production-ready Python codebase representing the exact system architecture detailed in this report.
System Prompt for AI Developer:
"You are an expert quantitative developer, financial engineer, and Python software architect specializing in the Indian equity markets. Your specific task is to write a complete, production-ready, modular Python algorithmic trading system using the Zerodha Kite Connect API (specifically adhering to the 2026 rate limits, static IP rules, and STT tax specifications).
Context & Operational Constraints:
Total Capital: ₹5,00,000. This must be structurally split into ₹2,00,000 for Intraday (MIS product, utilizing up to 5x leverage) and ₹3,00,000 for Swing trading (CNC product, zero leverage).
Trading Universe: Nifty 500 constituents exclusively.
Approved Libraries: kiteconnect, pandas, numpy, pyotp, requests, vectorbt, sqlite3, schedule, websockets, streamlit. (CRITICAL: DO NOT use Selenium under any circumstances).
Please output complete, modular Python code for the following required files. Do not use placeholders, # TODO comments, or mock logic for critical functions; write the full mathematical and operational logic required for live execution.
File 1: database.py (State Management & Persistence)
Implement a robust SQLite database connection utilizing Python's sqlite3.
Create a positions table explicitly to track multiday swing trades. Required columns must include: symbol, trade_type, entry_price, quantity, highest_high, current_atr, trailing_stop_loss, status (OPEN/CLOSED), and timestamp.
Create a secondary daily_metrics table intended for dashboard tracking (columns: date, gross_pnl, net_pnl, estimated_tax).
File 2: auth_manager.py (Headless Auto-Login)
Implement a purely headless OAuth login sequence that accepts api_key, api_secret, user_id, password, and a totp_secret.
Utilize pyotp.TOTP(totp_secret).now() to autonomously generate the 2FA code.
Utilize requests.Session() to execute POST requests to https://kite.zerodha.com/api/login and subsequently to https://kite.zerodha.com/api/twofa.
Extract the request_token from the resulting redirect URL, generate the API access_token using kite.generate_session(), and save it persistently to an access_token.txt file.
Include initialization logic to validate the token on startup; if it throws a TokenException (expired at 6:00 AM), autonomously re-run the login flow.
File 3: universe_selector.py (Dynamic Stock Filtering)
Write a function to dynamically fetch the latest Nifty 500 CSV (using the direct NSE URL or the nsepython library).
Implement a Pandas-based filtering method using 30-day historical OHLCV data. The function must return a list of symbols strictly meeting these criteria: Price is between ₹100 and ₹10,000, 30-day Average Daily Volume > 1,000,000, and 14-day ATR > 2% of the current price.
File 4: websocket_engine.py (Live Data & 1006 Error Handling)
Implement the KiteTicker WebSocket client to stream live ticks.
Include a custom application-level heartbeat mechanism (ping/pong) to detect silent network drops.
Implement sophisticated reconnection logic specifically designed for '1006 Abnormal Closure': Implement an exponential backoff algorithm integrated with random jitter (e.g., base delay 1-2s, max delay 30s) to prevent reconnect storms.
Include a callback function that triggers a REST API snapshot fetch (updating order statuses and open positions) immediately after a successful reconnection, ensuring the state machine is synced before processing any new ticks.
File 5: strategy_engine.py (Intraday & Swing Logic)
Intraday Module: Write a class that handles real-time tick data for the filtered universe. Logic: Initiate a Long if the price > VWAP and breaches the 15-minute Opening Range high. Initiate a Short if the price < VWAP and breaches the OR low. Use the MIS product type. Enforce a daily Value at Risk (kill switch): if total intraday MTM drops below -₹6,000, immediately halt all trading and close all open MIS positions.
Swing Module: Write a class for 1-5 day holding periods. Logic: DMAC (10, 30 EMA crossover) with MACD expansion. Position sizing must strictly adhere to the formula: , where Risk is capped at a maximum of ₹3,000 per trade. Use the CNC product type.
Trailing Stop Logic: Write a method that executes on every new 5-minute candle to update the SQLite database. The Highest High since entry must be tracked. Trailing Stop = Highest High - (3 * 14-period ATR). If the current live price drops below this calculated Trailing Stop, immediately generate a SELL market order.
File 6: backtest_vectorbt.py (Vectorized Cost Analysis)
Utilize the vectorbt library. Set up the EMA crossover backtest framework.
Implement a custom fee function array matching exactly the April 2026 Indian tax brackets. The logic must calculate asymmetrical fees:
Swing (Delivery/CNC): 0 brokerage, 0.1% STT (applied to both Buy and Sell), 0.00297% Exchange txn, 18% GST on (Brokerage+SEBI+Exc), 0.015% Stamp Duty (Buy only), and a Flat ₹13.5 DP charge applied only on the sell leg.
Intraday (MIS): 0.03% Brokerage (strictly capped at ₹20 per leg), 0.025% STT (Sell only), 0.00297% Exchange txn, 0.003% Stamp Duty (Buy only).
Output a tearsheet showing the net ROI, Max Drawdown, and Sharpe Ratio after these specific frictions.
File 7: dashboard.py (EOD Summary)
A monitoring script utilizing Pandas and Streamlit to read the SQLite database and the kite.positions() REST endpoint.
Display a clean graphical interface showing: Today's Net PnL, Total Brokerage and STT paid, a table of active swing positions with their exact persistence trailing stop levels, and a visual equity curve.
Ensure all code includes robust exception handling (especially for catching Kite API rate limits - HTTP 429 Too Many Requests), comprehensive inline comments explaining the quantitative logic, logging to a rotating file using Python's logging module, and strict adherence to PEP-8 standards. Begin generating the Python code blocks immediately."
This is for informational purposes only. For medical advice or diagnosis, consult a professional.
Works cited
Zerodha Kite Connect API 2026: Python Automation Complete Guide - Jayadev Rana, https://jayadevrana.com/zerodhas-new-api-2025-how-to-automate-kite-connect-with-python/
Kite Connect APIs: Trading and investment HTTP APIs - Zerodha, https://zerodha.com/products/api/
Momentum Strategy Performance in Nifty 500 | PDF | Investing | Student's T Test - Scribd, https://www.scribd.com/document/881920521/Performance-of-Momentum-Investment-Strategy-During-Stock-Market-Swings
Zerodha Stock Trading, Demat, Brokerage and Reviews 2026 - Chittorgarh, https://www.chittorgarh.com/stockbroker/zerodha/18/
Revision in Securities Transaction Tax (STT) from 1st April 2026 - Zerodha, https://zerodha.com/marketintel/bulletin/445377/revision-in-stt-securities-transaction-tax-from-1st-april-2026
VectorBT: Getting started, https://vectorbt.dev/
Zerodha API (Algo Trading) Review - Chittorgarh, https://www.chittorgarh.com/broker/zerodha/api-for-algo-trading-review/18/
Brokerage calculator - Zerodha, https://zerodha.com/brokerage-calculator/
Python Crypto Trading Bot India: Guide 2026 - CoinSwitch, https://coinswitch.co/switch/crypto/python-crypto-trading-bot-india/
Python Trading Bot: Build, Backtest, and Run Your First Algorithmic Strategy, https://wundertrading.com/journal/en/python-trading-bot
Nifty 500 Index - NSE India, https://www.nseindia.com/static/products-services/indices-nifty500-index
nsepython - PyPI, https://pypi.org/project/nsepython/
Download Latest NIFTY 50 Stocks List 2022 using Two Lines of Python Code-SaralGyaan, https://medium.com/@uditvashisht/download-latest-nifty-50-stocks-list-2022-using-two-lines-of-python-code-saralgyaan-a99b45253dcf
niftystocks - PyPI, https://pypi.org/project/niftystocks/
ATR Trailing Stop loss Strategy Python - Kite Connect Trading APIs, https://kite.trade/forum/discussion/14090/atr-trailing-stop-loss-strategy-python
Managing Orders in Live Engine : r/algotrading - Reddit, https://www.reddit.com/r/algotrading/comments/1fdl4zm/managing_orders_in_live_engine/
How to Automate Your Zerodha Account in 2026 (Step by Step) - Sleeping Trade India, https://sleepingtrade.in/blog/post-7.html
How to Fully Automate Your Zerodha Kite API Login with Python | by Yashesh Lele - Medium, https://medium.com/@yasheshlele/how-to-fully-automate-your-zerodha-kite-api-login-with-python-1bf6001f34fe
rajivgpta/kite-api-autologin - GitHub, https://github.com/rajivgpta/kite-api-autologin
Automating Zerodha Login without Selenium: A Pythonic Approach - DEV Community, https://dev.to/sagamantus/automating-zerodha-login-without-selenium-a-pythonic-approach-3b8o
How to Automate Zerodha Kite API Login - Fabtrader, https://fabtrader.in/blog/how-to-automate-zerodha-kite-api-login-free-token-paid-api-with-python
API rate limiting - Kite Connect developer forum, https://kite.trade/forum/discussion/257/api-rate-limiting
Rate Limits - Kite Connect developer forum, https://kite.trade/forum/discussion/13397/rate-limits
WebSocket Reconnection That Actually Works: Auto-Reconnect Guide for Trading Bots, https://dev.to/turboline_ai_/websocket-reconnection-that-actually-works-auto-reconnect-guide-for-trading-bots-3ak3
WebSocket closed with 1006: why trading bots lose connection without an error code, https://dev.to/matrixtrak/websocket-closed-with-1006-why-trading-bots-lose-connection-without-an-error-code-26ld
Kite connect API - FAQs - Support Zerodha, https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs
Why is the error "Maximum allowed order requests exceeded" displayed? - Support Zerodha, https://support.zerodha.com/category/trading-and-markets/alerts-and-nudges/kite-error-messages/articles/order-rate-limits-on-kite
VectorBT Mastery - Indian Stock Market Backtesting Tutorial, https://vectorbt.marketcalls.in/
Securities Transaction Tax (STT): Rates and how to calculate it - Support Zerodha, https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/how-is-the-securities-transaction-tax-stt-calculated
Zerodha Brokerage Charges 2026: Fees, Demat & Trading - Chittorgarh, https://www.chittorgarh.com/brokerage_charges/zerodha/18/
Resources - VectorBT, https://vectorbt.dev/getting-started/resources/
</content>
