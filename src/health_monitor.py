import MetaTrader5 as mt5
from datetime import datetime

from src.notifier import send_telegram_message
from src.trade_tracker import load_trades
from src.logger import logger


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


def send_heartbeat(symbol: str, force=False):
    global LAST_HEARTBEAT

    now = datetime.now()

    # send every 10 minutes
    if not force and LAST_HEARTBEAT:
        if (now - LAST_HEARTBEAT).seconds < 600:
            return

    LAST_HEARTBEAT = now

    snapshot = _get_heartbeat_trade_snapshot(
        symbol
    )

    physical_open_count = snapshot.get(
        "physical_open_count"
    )

    tracked_open_count = snapshot.get(
        "tracked_open_count",
        0,
    )

    pending_reconciliation_count = snapshot.get(
        "pending_reconciliation_count"
    )

    open_trades_text = (
        str(physical_open_count)
        if physical_open_count is not None
        else "UNKNOWN"
    )

    pending_text = (
        str(pending_reconciliation_count)
        if pending_reconciliation_count is not None
        else "UNKNOWN"
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
        f"Open Trades: {open_trades_text}\n"
        f"Tracked Open: {tracked_open_count}\n"
        f"Pending Reconciliation: {pending_text}\n"
        f"MT5: {'Connected' if mt5_connected else 'Disconnected'}\n"
        f"Time: {now.strftime('%H:%M:%S')}"
    )

    send_telegram_message(
        message
    )

    logger.info(
        "[HEARTBEAT] Sent bot alive status | "
        f"symbol={symbol} "
        f"physical_open={open_trades_text} "
        f"tracked_open={tracked_open_count} "
        f"pending_reconciliation={pending_text}"
    )


def send_critical_alert(message: str):
    send_telegram_message(f"🔴 CRITICAL ALERT\n{message}")
    logger.error(f"[CRITICAL] {message}")