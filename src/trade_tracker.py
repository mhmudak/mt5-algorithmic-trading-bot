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


def _build_trade_record(
    *,
    position_id,
    main_position_id,
    trade_role,
    symbol,
    signal,
    entry_price,
    stop_loss,
    take_profit,
    initial_volume,
    remaining_volume,
    deal_id,
    order_id,
    imported_manually=False,
):
    return {
        "position_id": str(position_id),
        "main_position_id": str(main_position_id),
        "trade_role": trade_role,
        "symbol": symbol,
        "signal": signal,
        "entry_price": float(entry_price),
        "stop_loss": float(stop_loss) if stop_loss is not None else 0.0,
        "take_profit": float(take_profit) if take_profit is not None else 0.0,
        "initial_volume": float(initial_volume),
        "remaining_volume": float(remaining_volume),
        "closed_volume": 0.0,
        "status": "OPEN",
        "open_time": datetime.now().isoformat(),
        "deal_id": deal_id,
        "order_id": order_id,
        "partial_closes": [],
        "stage_1_done": False,
        "stage_2_done": False,
        "stage_3_done": False,
        "imported_manually": imported_manually,
    }


def _find_open_main_trade_id(trades, symbol, signal):
    for position_id, trade in trades.items():
        if (
            trade.get("symbol") == symbol
            and trade.get("signal") == signal
            and trade.get("status") == "OPEN"
            and trade.get("trade_role") == "MAIN"
        ):
            return position_id
    return None


def register_executed_trade(symbol, signal, trade_plan, result):
    trades = load_trades()

    position_id = str(result.order if result.order else result.deal)

    existing_main_id = _find_open_main_trade_id(trades, symbol, signal)

    if existing_main_id is None:
        trade_role = "MAIN"
        main_position_id = position_id
    else:
        trade_role = "EXTRA"
        main_position_id = existing_main_id

    trades[position_id] = _build_trade_record(
        position_id=position_id,
        main_position_id=main_position_id,
        trade_role=trade_role,
        symbol=symbol,
        signal=signal,
        entry_price=trade_plan["entry_price"],
        stop_loss=trade_plan["stop_loss"],
        take_profit=trade_plan["take_profit"],
        initial_volume=trade_plan["lot"],
        remaining_volume=trade_plan["lot"],
        deal_id=result.deal,
        order_id=result.order,
        imported_manually=False,
    )

    save_trades(trades)

    logger.info(f"[TRACKER] Registered trade {position_id} as {trade_role}")

    send_telegram_message(
        f"Trade Opened\n"
        f"Position: {position_id}\n"
        f"Role: {trade_role}\n"
        f"Main Position: {main_position_id}\n"
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

    changed = False

    for position_id, trade in list(trades.items()):
        if trade.get("symbol") != symbol:
            continue

        if trade.get("status") == "CLOSED":
            continue

        tracked_remaining = float(trade.get("remaining_volume", 0.0))
        current_position = open_positions_map.get(position_id)

        # Fully closed
        if current_position is None:
            if tracked_remaining > 0:
                closed_now = tracked_remaining
                trade["closed_volume"] = round(float(trade.get("closed_volume", 0.0)) + closed_now, 2)
                trade["remaining_volume"] = 0.0
                trade["status"] = "CLOSED"
                trade["close_time"] = datetime.now().isoformat()
                changed = True

                logger.info(f"[TRACKER] Trade fully closed {position_id}")

                send_telegram_message(
                    f"Trade Fully Closed\n"
                    f"Position: {position_id}\n"
                    f"Role: {trade.get('trade_role', 'UNKNOWN')}\n"
                    f"Symbol: {trade['symbol']}\n"
                    f"Side: {trade['signal']}\n"
                    f"Initial Volume: {trade['initial_volume']}\n"
                    f"Closed Volume: {trade['closed_volume']}\n"
                    f"Remaining Volume: 0.0"
                )
            continue

        # Partial close
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

            trade["closed_volume"] = round(float(trade.get("closed_volume", 0.0)) + closed_now, 2)
            trade["remaining_volume"] = current_volume
            changed = True

            logger.info(
                f"[TRACKER] Partial close detected | "
                f"position={position_id} closed_now={closed_now} remaining={current_volume}"
            )

            send_telegram_message(
                f"Partial Close\n"
                f"Position: {position_id}\n"
                f"Role: {trade.get('trade_role', 'UNKNOWN')}\n"
                f"Symbol: {trade['symbol']}\n"
                f"Closed Volume: {closed_now}\n"
                f"Remaining Volume: {current_volume}"
            )

    if changed:
        save_trades(trades)


def sync_open_positions(symbol: str):
    trades = load_trades()

    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        logger.info(f"[TRACKER] No positions returned for sync on {symbol}")
        return

    changed = False

    for position in positions:
        position_id = str(position.ticket)

        if position_id in trades:
            continue

        signal = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"

        trades[position_id] = _build_trade_record(
            position_id=position_id,
            main_position_id=position_id,
            trade_role="MAIN",
            symbol=position.symbol,
            signal=signal,
            entry_price=position.price_open,
            stop_loss=position.sl,
            take_profit=position.tp,
            initial_volume=float(position.volume),
            remaining_volume=float(position.volume),
            deal_id=None,
            order_id=None,
            imported_manually=True,
        )

        logger.info(f"[TRACKER] Imported manual/open position {position_id}")
        changed = True

    if changed:
        save_trades(trades)