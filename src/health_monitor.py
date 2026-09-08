import MetaTrader5 as mt5
from datetime import datetime

from src.notifier import send_telegram_message
from src.trade_tracker import load_trades
from src.logger import logger


from src.market_outlook_engine import load_latest_market_outlook

LAST_HEARTBEAT = None


def _get_heartbeat_trade_snapshot(symbol: str):
    """
    Read-only heartbeat exposure snapshot.

    Physical MT5 positions are authoritative for actual
    currently open trades.

    Tracker OPEN records remain diagnostic only because
    close reconciliation may intentionally leave missing
    positions OPEN while waiting for matching deal history.
    """
    trades = load_trades()

    tracked_open = []

    for position_key, trade in trades.items():
        if not isinstance(trade, dict):
            continue

        if trade.get("symbol") != symbol:
            continue

        if trade.get("status") != "OPEN":
            continue

        position_id = str(
            trade.get(
                "position_id",
                position_key,
            )
        )

        tracked_open.append(
            position_id
        )

    try:
        positions = mt5.positions_get(
            symbol=symbol
        )
    except Exception as exc:
        logger.warning(
            f"[HEARTBEAT] positions_get failed | "
            f"symbol={symbol} error={exc}"
        )

        positions = None

    if positions is None:
        return {
            "physical_open_count": None,
            "tracked_open_count": len(tracked_open),
            "pending_reconciliation_count": None,
        }

    physical_ids = {
        str(position.ticket)
        for position in positions
        if getattr(
            position,
            "ticket",
            None,
        ) is not None
    }

    pending_reconciliation = sum(
        1
        for position_id in tracked_open
        if position_id not in physical_ids
    )

    return {
        "physical_open_count": len(positions),
        "tracked_open_count": len(tracked_open),
        "pending_reconciliation_count": pending_reconciliation,
    }


def _get_heartbeat_market_context(symbol: str):
    """
    Read-only heartbeat market context.

    Price is the live MT5 bid/ask midpoint.
    Bias reuses the latest saved Phase 6S combined HTF bias.

    This function is display-only and cannot affect trading.
    """
    price = None
    price_source = "UNAVAILABLE"

    try:
        tick = mt5.symbol_info_tick(symbol)
    except Exception as exc:
        logger.warning(
            f"[HEARTBEAT] symbol_info_tick failed | "
            f"symbol={symbol} error={exc}"
        )
        tick = None

    if tick is not None:
        try:
            bid = float(getattr(tick, "bid", 0.0) or 0.0)
            ask = float(getattr(tick, "ask", 0.0) or 0.0)
        except Exception:
            bid = 0.0
            ask = 0.0

        if bid > 0 and ask > 0:
            price = round(
                (bid + ask) / 2.0,
                2,
            )
            price_source = "MT5_BID_ASK_MID"

        elif bid > 0:
            price = round(bid, 2)
            price_source = "MT5_BID"

        elif ask > 0:
            price = round(ask, 2)
            price_source = "MT5_ASK"

    bias = "UNKNOWN"

    try:
        outlook = load_latest_market_outlook(
            symbol,
            "scenario_update",
        )
    except Exception as exc:
        logger.warning(
            f"[HEARTBEAT] market outlook load failed | "
            f"symbol={symbol} error={exc}"
        )
        outlook = None

    if isinstance(outlook, dict):
        candidate = str(
            outlook.get(
                "combined_htf_bias",
                "",
            )
            or ""
        ).upper()

        if candidate:
            bias = candidate

    return {
        "price": price,
        "price_source": price_source,
        "bias": bias,
    }


def send_heartbeat(symbol: str, force=False):
    global LAST_HEARTBEAT

    now = datetime.now()

    # send every 10 minutes
    if not force and LAST_HEARTBEAT:
        if (now - LAST_HEARTBEAT).seconds < 600:
            return

    LAST_HEARTBEAT = now

    trade_snapshot = _get_heartbeat_trade_snapshot(
        symbol
    )

    market_context = _get_heartbeat_market_context(
        symbol
    )

    physical_open_count = trade_snapshot.get(
        "physical_open_count"
    )

    tracked_open_count = trade_snapshot.get(
        "tracked_open_count",
        0,
    )

    pending_reconciliation_count = trade_snapshot.get(
        "pending_reconciliation_count"
    )

    open_trades_text = (
        str(physical_open_count)
        if physical_open_count is not None
        else "UNKNOWN"
    )

    price = market_context.get(
        "price"
    )

    price_text = (
        str(price)
        if price is not None
        else "UNKNOWN"
    )

    bias = str(
        market_context.get(
            "bias",
            "UNKNOWN",
        )
        or "UNKNOWN"
    )

    try:
        mt5_connected = (
            mt5.terminal_info()
            is not None
        )
    except Exception:
        mt5_connected = False

    message = (
        f"🟢 Bot Alive\n"
        f"Symbol: {symbol}\n"
        f"Price: {price_text}\n"
        f"Bias: {bias}\n"
        f"Open Trades: {open_trades_text}\n"
        f"MT5: {'Connected' if mt5_connected else 'Disconnected'}\n"
        f"Time: {now.strftime('%H:%M:%S')}"
    )

    send_telegram_message(
        message
    )

    # Tracker diagnostics stay internal.
    logger.info(
        "[HEARTBEAT] Sent bot alive status | "
        f"symbol={symbol} "
        f"price={price_text} "
        f"price_source={market_context.get('price_source')} "
        f"bias={bias} "
        f"physical_open={open_trades_text} "
        f"tracked_open={tracked_open_count} "
        f"pending_reconciliation={pending_reconciliation_count}"
    )


def send_critical_alert(message: str):
    send_telegram_message(f"🔴 CRITICAL ALERT\n{message}")
    logger.error(f"[CRITICAL] {message}")