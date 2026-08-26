"""2026 Zerodha fee/tax model (instruction.md section 6.1) -- asymmetric MIS (intraday)
vs CNC (delivery/swing) charges, applied to a round-trip trade's buy and sell legs.
"""

_BROKERAGE_RATE = 0.0003        # 0.03%, capped at flat Rs20/order, whichever lower
_BROKERAGE_CAP = 20.0
_STT_INTRADAY_SELL = 0.00025    # 0.025%, sell side only
_STT_DELIVERY = 0.001           # 0.1%, both sides
_EXCHANGE_TXN = 0.0000297       # NSE
_SEBI_CHARGE = 0.000001         # Rs10/crore
_STAMP_INTRADAY_BUY = 0.00003   # 0.003%, buy side only
_STAMP_DELIVERY_BUY = 0.00015   # 0.015%, buy side only
_DP_CHARGE = 13.5 * 1.18        # flat, sell leg only, delivery


def total_cost(entry_price: float, exit_price: float, shares: int, product: str) -> float:
    """Round-trip cost in INR for one trade. product: 'MIS' or 'CNC'."""
    buy_turnover = entry_price * shares
    sell_turnover = exit_price * shares
    exchange = _EXCHANGE_TXN * (buy_turnover + sell_turnover)
    sebi = _SEBI_CHARGE * (buy_turnover + sell_turnover)

    if product == "MIS":
        brokerage = min(_BROKERAGE_CAP, _BROKERAGE_RATE * buy_turnover) + \
            min(_BROKERAGE_CAP, _BROKERAGE_RATE * sell_turnover)
        stt = _STT_INTRADAY_SELL * sell_turnover
        stamp = _STAMP_INTRADAY_BUY * buy_turnover
        dp = 0.0
    elif product == "CNC":
        brokerage = 0.0
        stt = _STT_DELIVERY * (buy_turnover + sell_turnover)
        stamp = _STAMP_DELIVERY_BUY * buy_turnover
        dp = _DP_CHARGE
    else:
        raise ValueError(f"unknown product {product!r}, expected 'MIS' or 'CNC'")

    gst = 0.18 * (brokerage + exchange + sebi)
    return brokerage + stt + exchange + sebi + stamp + gst + dp


def option_total_cost(
    entry_price: float,
    exit_price: float,
    shares: int,
    broker: str = "zerodha",
    stt_rate: float = 0.0010,  # 0.10% on option sell premium (Oct 2024 - Mar 2026, 0.15% from Apr 2026)
    nse_opt_txn_rate: float = 0.0003503,  # 0.03503% NSE single-slab option turnover charge
) -> float:
    """Computes exact round-trip regulatory friction & brokerage for NIFTY Option Selling (MIS).

    Args:
        entry_price: Option sell price at entry (INR)
        exit_price: Option buy price at exit (INR)
        shares: Quantity traded (e.g. 65 units for 1 lot)
        broker: 'zerodha' (flat Rs 20/order) or 'flattrade' (flat Rs 0 zero brokerage)
        stt_rate: 0.0010 (0.10%) or 0.0015 (0.15% post-April 2026)
        nse_opt_txn_rate: 0.03503% NSE transaction fee on premium turnover

    Returns:
        Total round-trip cost in INR.
    """
    sell_turnover = entry_price * shares  # Entry is SELL
    buy_turnover = exit_price * shares    # Exit is BUY
    total_turnover = sell_turnover + buy_turnover

    # 1. Brokerage
    broker_lower = broker.lower()
    if broker_lower == "zerodha":
        brokerage = 20.0 + 20.0  # Rs 20 entry sell + Rs 20 exit buy
    elif broker_lower in ("flattrade", "zero"):
        brokerage = 0.0          # FlatTrade Zero Brokerage
    else:
        brokerage = 40.0         # Default standard discount broker cap

    # 2. STT (Securities Transaction Tax) - Charged only on SELL turnover of options
    stt = stt_rate * sell_turnover

    # 3. Exchange Transaction Charges (NSE F&O Options)
    exchange = nse_opt_txn_rate * total_turnover

    # 4. SEBI Turnover Charge (Rs 10 / Crore)
    sebi = 0.000001 * total_turnover

    # 5. Stamp Duty (0.003% on BUY side turnover only)
    stamp = 0.00003 * buy_turnover

    # 6. GST (18% on Brokerage + Exchange Charges + SEBI Charge)
    gst = 0.18 * (brokerage + exchange + sebi)

    return brokerage + stt + exchange + sebi + stamp + gst

