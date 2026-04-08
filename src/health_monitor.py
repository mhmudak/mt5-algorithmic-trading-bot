import MetaTrader5 as mt5
from datetime import datetime

from src.notifier import send_telegram_message
from src.trade_tracker import load_trades
from src.logger import logger


LAST_HEARTBEAT = None


def send_heartbeat(symbol: str, force=False):
    global LAST_HEARTBEAT

    now = datetime.now()

    # send every 10 minutes
    if not force and LAST_HEARTBEAT:
        if (now - LAST_HEARTBEAT).seconds < 600:
            return

    LAST_HEARTBEAT = now

    trades = load_trades()
    open_trades = [t for t in trades.values() if t.get("status") == "OPEN"]

    mt5_connected = mt5.terminal_info() is not None

    message = (
        f"🟢 Bot Alive\n"
        f"Symbol: {symbol}\n"
        f"Open Trades: {len(open_trades)}\n"
        f"MT5: {'Connected' if mt5_connected else 'Disconnected'}\n"
        f"Time: {now.strftime('%H:%M:%S')}"
    )

    send_telegram_message(message)

    logger.info("[HEARTBEAT] Sent bot alive status")


def send_critical_alert(message: str):
    send_telegram_message(f"🔴 CRITICAL ALERT\n{message}")
    logger.error(f"[CRITICAL] {message}")