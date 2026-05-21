import time

import MetaTrader5 as mt5

from config.settings import (
    TELEGRAM_SIGNAL_MODE,
    TELEGRAM_SIGNAL_SYMBOL,
    TELEGRAM_SIGNAL_DEFAULT_LOT,
    TELEGRAM_SIGNAL_LOW_RISK_LOT,
    TELEGRAM_SIGNAL_MIN_RR,
    TELEGRAM_SIGNAL_MAX_ENTRY_DISTANCE,
    ALLOW_TELEGRAM_PRE_SIGNAL_ENTRY,
    TELEGRAM_PRE_SIGNAL_EMERGENCY_SL_PRICE,
    TELEGRAM_PRE_SIGNAL_EMERGENCY_TP_PRICE,
    TELEGRAM_PRE_SIGNAL_LOT,
    ALLOW_TELEGRAM_SIGNAL_WITHOUT_TP,
    TELEGRAM_NO_TP_LOT,
    ENABLE_TELEGRAM_WAIT_BETTER_ENTRY,
    TELEGRAM_WAIT_BETTER_ENTRY_POLL_SECONDS,
    TELEGRAM_WAIT_BETTER_ENTRY_MAX_PROFIT_MOVE,
    TELEGRAM_WAIT_BETTER_ENTRY_TIMEOUT_SECONDS,
)

from src.execution import check_trade_guard
from src.notifier import send_telegram_message
from src.order_executor import execute_trade
from src.trade_tracker import load_trades, save_trades


def _calculate_rr(signal, entry, sl, tp):
    try:
        if tp in [None, 0, 0.0]:
            return None

        if signal == "BUY":
            risk = entry - sl
            reward = tp - entry
        elif signal == "SELL":
            risk = sl - entry
            reward = entry - tp
        else:
            return None

        if risk <= 0:
            return None

        return round(reward / risk, 2)

    except Exception:
        return None


def _current_price(symbol, signal):
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return None, None

    if signal == "BUY":
        return tick.ask, tick

    if signal == "SELL":
        return tick.bid, tick

    return None, tick


def _is_price_inside_entry_zone(price, low, high):
    return low <= price <= high


def _source_comment(parsed):
    return f"TG-{parsed.get('source_name', 'Trader')}"[:31]


def _source_fields(parsed):
    return {
        "setup_id": parsed.get("telegram_setup_id", "TELEGRAM"),
        "source_name": parsed.get("source_name"),
        "source_chat": parsed.get("source_chat"),
        "source_message_id": parsed.get("source_message_id"),
        "source_event_type": parsed.get("source_event_type"),
        "comment": _source_comment(parsed),
    }


def _build_market_trade_plan(parsed, symbol, price):
    signal = parsed["direction"]
    sl = parsed["sl"]
    tp = parsed["tp1"]

    lot = (
        TELEGRAM_SIGNAL_LOW_RISK_LOT
        if parsed.get("risk_note") == "LOW_RISK"
        else TELEGRAM_SIGNAL_DEFAULT_LOT
    )

    rr = _calculate_rr(signal, price, sl, tp)

    if rr is None:
        return None, "invalid_rr"

    return {
        "signal": signal,
        "entry_price": round(price, 2),
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "lot": lot,
        "risk_mode": "telegram_signal",
        "score": 0,
        "strategy": "TELEGRAM_SIGNAL",
        "market_condition": "EXTERNAL",
        "reason": parsed.get("raw_text", "Telegram external signal"),
        "session": "TELEGRAM",
        "entry_model": "TELEGRAM_MARKET_SIGNAL",
        "rr": rr,
        **_source_fields(parsed),
    }, "ok"


def _build_no_tp_trade_plan(parsed, symbol, price):
    signal = parsed["direction"]
    sl = parsed["sl"]
    lot = TELEGRAM_NO_TP_LOT

    if signal == "BUY" and sl >= price:
        return None, "invalid_buy_sl"

    if signal == "SELL" and sl <= price:
        return None, "invalid_sell_sl"

    return {
        "signal": signal,
        "entry_price": round(price, 2),
        "stop_loss": round(sl, 2),
        "take_profit": 0.0,
        "lot": lot,
        "risk_mode": "telegram_signal_no_tp",
        "score": 0,
        "strategy": "TELEGRAM_SIGNAL_NO_TP",
        "market_condition": "EXTERNAL",
        "reason": parsed.get("raw_text", "Telegram signal without TP"),
        "session": "TELEGRAM",
        "entry_model": "TELEGRAM_SIGNAL_NO_TP",
        "rr": None,
        **_source_fields(parsed),
    }, "ok"


def _build_pre_signal_trade_plan(parsed, symbol, price):
    signal = parsed["direction"]
    lot = TELEGRAM_PRE_SIGNAL_LOT

    if signal == "BUY":
        sl = price - TELEGRAM_PRE_SIGNAL_EMERGENCY_SL_PRICE
        tp = price + TELEGRAM_PRE_SIGNAL_EMERGENCY_TP_PRICE
    else:
        sl = price + TELEGRAM_PRE_SIGNAL_EMERGENCY_SL_PRICE
        tp = price - TELEGRAM_PRE_SIGNAL_EMERGENCY_TP_PRICE

    rr = _calculate_rr(signal, price, sl, tp)

    return {
        "signal": signal,
        "entry_price": round(price, 2),
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "lot": lot,
        "risk_mode": "telegram_pre_signal",
        "score": 0,
        "strategy": "TELEGRAM_PRE_SIGNAL",
        "market_condition": "EXTERNAL",
        "reason": parsed.get("raw_text", "Telegram pre-signal"),
        "session": "TELEGRAM",
        "entry_model": "TELEGRAM_PRE_SIGNAL_EMERGENCY",
        "rr": rr,
        **_source_fields(parsed),
    }, "ok"


def _profit_move_exceeded(signal, current_price, original_entry):
    if signal == "BUY":
        return current_price >= original_entry + TELEGRAM_WAIT_BETTER_ENTRY_MAX_PROFIT_MOVE

    if signal == "SELL":
        return current_price <= original_entry - TELEGRAM_WAIT_BETTER_ENTRY_MAX_PROFIT_MOVE

    return True


def _price_hit_stop_zone(signal, current_price, stop_loss):
    if signal == "BUY":
        return current_price <= stop_loss

    if signal == "SELL":
        return current_price >= stop_loss

    return True


def _wait_for_better_telegram_entry(direction, symbol, trade_plan):
    if not ENABLE_TELEGRAM_WAIT_BETTER_ENTRY:
        return None, "wait_better_entry_disabled"

    original_entry = trade_plan["entry_price"]
    stop_loss = trade_plan["stop_loss"]
    take_profit = trade_plan["take_profit"]

    if take_profit in [None, 0, 0.0]:
        return None, "missing_tp_for_better_entry"

    send_telegram_message(
        f"⏳ Telegram Waiting for Better Entry\n"
        f"Signal: {direction}\n"
        f"Symbol: {symbol}\n"
        f"Current Entry: {original_entry}\n"
        f"SL: {stop_loss}\n"
        f"TP: {take_profit}\n"
        f"Current RR: {trade_plan.get('rr')}\n"
        f"Required RR: {TELEGRAM_SIGNAL_MIN_RR}\n\n"
        f"Checking every {TELEGRAM_WAIT_BETTER_ENTRY_POLL_SECONDS} seconds.\n"
        f"Cancel if price moves {TELEGRAM_WAIT_BETTER_ENTRY_MAX_PROFIT_MOVE} USD in profit direction."
    )

    start_time = time.time()

    while time.time() - start_time <= TELEGRAM_WAIT_BETTER_ENTRY_TIMEOUT_SECONDS:
        time.sleep(TELEGRAM_WAIT_BETTER_ENTRY_POLL_SECONDS)

        current_price, tick = _current_price(symbol, direction)

        if current_price is None or tick is None:
            continue

        if _profit_move_exceeded(direction, current_price, original_entry):
            send_telegram_message(
                f"⌛ Telegram Better Entry Cancelled\n"
                f"Reason: Price already moved in profit direction\n"
                f"Signal: {direction}\n"
                f"Symbol: {symbol}\n"
                f"Original Entry: {original_entry}\n"
                f"Current Price: {round(current_price, 2)}\n"
                f"Max Profit Move: {TELEGRAM_WAIT_BETTER_ENTRY_MAX_PROFIT_MOVE}"
            )
            return None, "profit_move_exceeded_before_entry"

        if _price_hit_stop_zone(direction, current_price, stop_loss):
            send_telegram_message(
                f"🚫 Telegram Better Entry Cancelled\n"
                f"Reason: Price reached stop zone before entry\n"
                f"Signal: {direction}\n"
                f"Symbol: {symbol}\n"
                f"Current Price: {round(current_price, 2)}\n"
                f"SL: {stop_loss}"
            )
            return None, "price_reached_stop_zone"

        rr = _calculate_rr(direction, current_price, stop_loss, take_profit)

        if rr is None:
            continue

        if rr >= TELEGRAM_SIGNAL_MIN_RR:
            adjusted_plan = trade_plan.copy()
            adjusted_plan["entry_price"] = round(current_price, 2)
            adjusted_plan["rr"] = rr
            adjusted_plan["reason"] = (
                f"{trade_plan.get('reason', '')} | TELEGRAM_BETTER_ENTRY"
            )
            adjusted_plan["comment"] = trade_plan.get("comment", "TG-BetterEntry")[:31]

            send_telegram_message(
                f"✅ Telegram Better Entry Found\n"
                f"Signal: {direction}\n"
                f"Symbol: {symbol}\n"
                f"Old Entry: {original_entry}\n"
                f"New Entry: {adjusted_plan['entry_price']}\n"
                f"SL: {stop_loss}\n"
                f"TP: {take_profit}\n"
                f"RR: {rr}"
            )

            return adjusted_plan, "better_entry_found"

    send_telegram_message(
        f"⌛ Telegram Better Entry Expired\n"
        f"Signal: {direction}\n"
        f"Symbol: {symbol}\n"
        f"Original Entry: {original_entry}\n"
        f"Required RR: {TELEGRAM_SIGNAL_MIN_RR}\n"
        f"No trade executed."
    )

    return None, "better_entry_timeout"


def _prepare_auto_execute_trade_plan(direction, symbol, trade_plan):
    rr = trade_plan.get("rr")

    if rr is None:
        rr = _calculate_rr(
            direction,
            trade_plan["entry_price"],
            trade_plan["stop_loss"],
            trade_plan["take_profit"],
        )

    if rr is not None and rr >= TELEGRAM_SIGNAL_MIN_RR:
        trade_plan["rr"] = rr
        return trade_plan, "rr_ok"

    better_plan, reason = _wait_for_better_telegram_entry(
        direction,
        symbol,
        trade_plan,
    )

    if better_plan is None:
        return None, reason

    return better_plan, reason


def _find_open_trade_by_message(parsed):
    trades = load_trades()
    source_name = parsed.get("source_name")
    source_message_id = parsed.get("source_message_id")
    direction = parsed.get("direction")

    for position_id, trade in trades.items():
        if trade.get("status") != "OPEN":
            continue

        if trade.get("source_name") != source_name:
            continue

        if str(trade.get("source_message_id")) != str(source_message_id):
            continue

        if trade.get("signal") != direction:
            continue

        return position_id, trade

    return None, None


def _update_existing_trade_tp(parsed, symbol):
    if parsed.get("type") != "SIGNAL":
        return False, "not_full_signal"

    tp1 = parsed.get("tp1")

    if tp1 is None:
        return False, "no_tp1"

    position_id, trade = _find_open_trade_by_message(parsed)

    if position_id is None:
        return False, "no_matching_open_trade"

    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        return False, "no_positions"

    target_position = None

    for pos in positions:
        if str(pos.ticket) == str(position_id):
            target_position = pos
            break

    if target_position is None:
        return False, "position_not_found"

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": target_position.ticket,
        "sl": target_position.sl,
        "tp": round(tp1, 2),
    }

    result = mt5.order_send(request)

    if result is None:
        return False, f"mt5_error {mt5.last_error()}"

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"modify_tp_rejected {result}"

    trades = load_trades()
    if position_id in trades:
        trades[position_id]["take_profit"] = round(tp1, 2)
        trades[position_id]["tp_updated_from_telegram"] = True
        save_trades(trades)

    send_telegram_message(
        f"✅ Telegram TP Updated\n"
        f"Source: {parsed.get('source_name')}\n"
        f"Position: {position_id}\n"
        f"TP1: {round(tp1, 2)}"
    )

    return True, "tp_updated"


def handle_parsed_telegram_signal(parsed):
    signal_type = parsed.get("type")

    if signal_type == "IGNORE":
        return False, parsed.get("reason", "ignored")

    if signal_type == "UPDATE":
        return True, "informational_update_ignored"

    if signal_type == "MANAGEMENT":
        send_telegram_message(
            f"📩 Telegram Management Message\n"
            f"Source: {parsed.get('source_name')}\n"
            f"Action: {parsed.get('action')}\n"
            f"Details: {parsed}"
        )
        return True, "management_message"

    if signal_type == "INCOMPLETE_SIGNAL":
        send_telegram_message(
            f"⚠️ Incomplete Telegram Signal\n"
            f"Direction: {parsed.get('direction')}\n"
            f"Missing: {', '.join(parsed.get('missing', []))}\n\n"
            f"Raw:\n{parsed.get('raw_text')}"
        )
        return False, "incomplete_signal"

    symbol = TELEGRAM_SIGNAL_SYMBOL
    direction = parsed.get("direction")

    price, tick = _current_price(symbol, direction)

    if price is None or tick is None:
        send_telegram_message(
            f"❌ Telegram Signal Error\n"
            f"Reason: No tick data for {symbol}"
        )
        return False, "no_tick_data"

    if signal_type == "SIGNAL" and TELEGRAM_SIGNAL_MODE == "AUTO_EXECUTE":
        updated, update_reason = _update_existing_trade_tp(parsed, symbol)

        if updated:
            return True, update_reason

    if signal_type == "PRE_SIGNAL":
        if not ALLOW_TELEGRAM_PRE_SIGNAL_ENTRY:
            send_telegram_message(
                f"📩 Telegram Pre-Signal Detected\n"
                f"Direction: {direction}\n"
                f"Symbol: {symbol}\n"
                f"Mode: ALERT ONLY\n\n"
                f"Waiting for edited message with entry / SL / TP."
            )
            return True, "pre_signal_alert_only"

        trade_plan, reason = _build_pre_signal_trade_plan(parsed, symbol, price)

    elif signal_type == "SIGNAL_NO_TP":
        if not ALLOW_TELEGRAM_SIGNAL_WITHOUT_TP:
            send_telegram_message(
                f"⚠️ Telegram Signal Missing TP\n"
                f"Direction: {direction}\n"
                f"SL exists, but TP missing.\n"
                f"Mode: not allowed."
            )
            return False, "tp_missing_not_allowed"

        entry_low = parsed.get("entry_low")
        entry_high = parsed.get("entry_high")

        if not _is_price_inside_entry_zone(price, entry_low, entry_high):
            distance = min(abs(price - entry_low), abs(price - entry_high))

            send_telegram_message(
                f"🚫 Telegram No-TP Signal Skipped\n"
                f"Reason: Price outside entry zone\n"
                f"Signal: {direction}\n"
                f"Current: {round(price, 2)}\n"
                f"Zone: {entry_low}-{entry_high}\n"
                f"Distance: {round(distance, 2)}"
            )
            return False, "price_outside_entry_zone"

        trade_plan, reason = _build_no_tp_trade_plan(parsed, symbol, price)

    elif signal_type == "SIGNAL":
        entry_low = parsed.get("entry_low")
        entry_high = parsed.get("entry_high")

        if not _is_price_inside_entry_zone(price, entry_low, entry_high):
            distance = min(abs(price - entry_low), abs(price - entry_high))

            if distance > TELEGRAM_SIGNAL_MAX_ENTRY_DISTANCE:
                send_telegram_message(
                    f"🚫 Telegram Signal Skipped\n"
                    f"Reason: Price outside entry zone\n"
                    f"Signal: {direction}\n"
                    f"Current: {round(price, 2)}\n"
                    f"Zone: {entry_low}-{entry_high}\n"
                    f"Distance: {round(distance, 2)}"
                )
                return False, "price_outside_entry_zone"

        trade_plan, reason = _build_market_trade_plan(parsed, symbol, price)

    else:
        return False, "unsupported_signal_type"

    if trade_plan is None:
        send_telegram_message(
            f"🚫 Telegram Signal Rejected\n"
            f"Reason: {reason}\n"
            f"Parsed: {parsed}"
        )
        return False, reason

    trade_allowed, guard_reason = check_trade_guard(direction, tick)

    if not trade_allowed:
        send_telegram_message(
            f"🚫 Telegram Signal Blocked\n"
            f"Reason: {guard_reason}\n"
            f"Signal: {direction}\n"
            f"Symbol: {symbol}"
        )
        return False, guard_reason

    if TELEGRAM_SIGNAL_MODE == "ALERT_ONLY":
        send_telegram_message(
            f"📩 Telegram Signal Parsed\n"
            f"Mode: ALERT ONLY\n"
            f"Signal: {direction}\n"
            f"Symbol: {symbol}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"RR: {trade_plan.get('rr')}\n"
            f"Lot: {trade_plan['lot']}"
        )
        return True, "alert_only"

    if TELEGRAM_SIGNAL_MODE == "CONFIRMATION":
        send_telegram_message(
            f"🟡 Telegram Signal Awaiting Confirmation\n"
            f"Signal: {direction}\n"
            f"Symbol: {symbol}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"RR: {trade_plan.get('rr')}\n"
            f"Lot: {trade_plan['lot']}"
        )
        return True, "awaiting_confirmation"

    if TELEGRAM_SIGNAL_MODE == "AUTO_EXECUTE":
        trade_plan, prepare_reason = _prepare_auto_execute_trade_plan(
            direction,
            symbol,
            trade_plan,
        )

        if trade_plan is None:
            return False, prepare_reason

        latest_price, latest_tick = _current_price(symbol, direction)

        if latest_price is None or latest_tick is None:
            return False, "no_tick_data_before_execution"

        trade_allowed, guard_reason = check_trade_guard(direction, latest_tick)

        if not trade_allowed:
            send_telegram_message(
                f"🚫 Telegram Signal Blocked Before Execution\n"
                f"Reason: {guard_reason}\n"
                f"Signal: {direction}\n"
                f"Symbol: {symbol}"
            )
            return False, guard_reason

        send_telegram_message(
            f"🔥 Executing Telegram Signal\n"
            f"Signal: {direction}\n"
            f"Symbol: {symbol}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"RR: {trade_plan.get('rr')}\n"
            f"Lot: {trade_plan['lot']}"
        )

        execution_result = execute_trade(direction, trade_plan, symbol)

        return execution_result, "executed" if execution_result else "execution_failed"

    return False, f"unknown_mode {TELEGRAM_SIGNAL_MODE}"