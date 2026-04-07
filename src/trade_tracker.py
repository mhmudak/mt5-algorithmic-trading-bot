import json
from pathlib import Path
from datetime import datetime

import MetaTrader5 as mt5

from src.logger import logger
from src.notifier import send_telegram_message


TRACKER_FILE = Path("data/trades.json")


def load_trades():
    if not TRACKER_FILE.exists():
        return {}

    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[TRACKER] Failed to load trades: {e}")
        return {}


def save_trades(trades):
    try:
        TRACKER_FILE.parent.mkdir(exist_ok=True)
        with open(TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[TRACKER] Failed to save trades: {e}")


def register_executed_trade(symbol, signal, trade_plan, result):
    trades = load_trades()

    position_id = str(result.order if result.order else result.deal)

    trades[position_id] = {
        "position_id": position_id,
        "symbol": symbol,
        "signal": signal,
        "entry_price": trade_plan["entry_price"],
        "stop_loss": trade_plan["stop_loss"],
        "take_profit": trade_plan["take_profit"],
        "initial_volume": trade_plan["lot"],
        "remaining_volume": trade_plan["lot"],
        "closed_volume": 0.0,
        "status": "OPEN",
        "open_time": datetime.now().isoformat(),
        "deal_id": result.deal,
        "order_id": result.order,
        "partial_closes": [],
    }

    save_trades(trades)

    logger.info(f"[TRACKER] Registered trade {position_id}")

    send_telegram_message(
        f"✅ *Trade Opened*\n"
        f"Position: {position_id}\n"
        f"Symbol: {symbol}\n"
        f"Side: {signal}\n"
        f"Volume: {trade_plan['lot']}\n"
        f"Entry: {trade_plan['entry_price']}\n"
        f"SL: {trade_plan['stop_loss']}\n"
        f"TP: {trade_plan['take_profit']}"
    )


def update_trade_lifecycle(symbol: str):
    trades = load_trades()
    if not trades:
        logger.info("[TRACKER] No tracked trades")
        return

    open_positions = mt5.positions_get(symbol=symbol)
    open_positions_map = {}

    if open_positions is not None:
        for pos in open_positions:
            open_positions_map[str(pos.ticket)] = pos

    for position_id, trade in list(trades.items()):
        if trade["symbol"] != symbol:
            continue

        if trade["status"] == "CLOSED":
            continue

        tracked_remaining = float(trade["remaining_volume"])
        current_position = open_positions_map.get(position_id)

        # Case 1: fully closed
        if current_position is None:
            if tracked_remaining > 0:
                closed_now = tracked_remaining
                trade["closed_volume"] = round(float(trade["closed_volume"]) + closed_now, 2)
                trade["remaining_volume"] = 0.0
                trade["status"] = "CLOSED"
                trade["close_time"] = datetime.now().isoformat()

                save_trades(trades)

                logger.info(f"[TRACKER] Trade fully closed {position_id}")

                send_telegram_message(
                    f"🏁 *Trade Fully Closed*\n"
                    f"Position: {position_id}\n"
                    f"Symbol: {trade['symbol']}\n"
                    f"Side: {trade['signal']}\n"
                    f"Initial Volume: {trade['initial_volume']}\n"
                    f"Closed Volume: {trade['closed_volume']}\n"
                    f"Remaining Volume: 0.0"
                )
            continue

        # Case 2: partial close
        current_volume = round(float(current_position.volume), 2)

        if current_volume < tracked_remaining:
            closed_now = round(tracked_remaining - current_volume, 2)

            trade["partial_closes"].append(
                {
                    "time": datetime.now().isoformat(),
                    "closed_volume": closed_now,
                    "remaining_volume": current_volume,
                }
            )

            trade["closed_volume"] = round(float(trade["closed_volume"]) + closed_now, 2)
            trade["remaining_volume"] = current_volume

            save_trades(trades)

            logger.info(
                f"[TRACKER] Partial close detected | "
                f"position={position_id} closed_now={closed_now} remaining={current_volume}"
            )

            send_telegram_message(
                f"📉 *Partial Close*\n"
                f"Position: {position_id}\n"
                f"Symbol: {trade['symbol']}\n"
                f"Closed Volume: {closed_now}\n"
                f"Remaining Volume: {current_volume}"
            )