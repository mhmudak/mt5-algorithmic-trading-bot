from datetime import datetime

import MetaTrader5 as mt5

from config.settings import (
    ENABLE_TELEGRAM_PARTIAL_TP_MANAGER,
    TELEGRAM_RUNNER_REMAINING_PCT,
)

from src.notifier import send_telegram_message
from src.order_executor import get_supported_filling_modes
from src.trade_tracker import load_trades, save_trades


def _round_volume(symbol, volume):
    symbol_info = mt5.symbol_info(symbol)

    if symbol_info is None:
        return round(volume, 2)

    step = symbol_info.volume_step
    min_volume = symbol_info.volume_min

    rounded = round(round(volume / step) * step, 2)

    if rounded < min_volume:
        return 0.0

    return rounded


def _tp_reached(signal, current_price, tp):
    if signal == "BUY":
        return current_price >= tp

    if signal == "SELL":
        return current_price <= tp

    return False


def _close_partial_position(symbol, position, signal, close_volume):
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return False, f"no_tick_data {mt5.last_error()}"

    if signal == "BUY":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    elif signal == "SELL":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        return False, "invalid_signal"

    base_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "position": position.ticket,
        "volume": close_volume,
        "type": order_type,
        "price": price,
        "deviation": 10,
        "magic": 123456,
        "comment": "TGPartialTP",
        "type_time": mt5.ORDER_TIME_GTC,
    }

    last_error = None

    for filling_mode in get_supported_filling_modes(symbol):
        request = base_request.copy()
        request["type_filling"] = filling_mode

        result = mt5.order_send(request)

        if result is None:
            last_error = mt5.last_error()
            continue

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return True, "closed"

        last_error = result

        if result.retcode == 10030:
            continue

        break

    return False, f"partial_close_failed {last_error}"


def manage_telegram_partial_tps(symbol):
    if not ENABLE_TELEGRAM_PARTIAL_TP_MANAGER:
        return False

    trades = load_trades()

    if not trades:
        return False

    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        return False

    positions_map = {str(position.ticket): position for position in positions}
    changed = False

    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return False

    for position_id, trade in trades.items():
        if trade.get("status") != "OPEN":
            continue

        if trade.get("symbol") != symbol:
            continue

        if not trade.get("telegram_partial_tp_enabled"):
            continue

        position = positions_map.get(str(position_id))

        if position is None:
            continue

        signal = trade.get("signal")

        if signal == "BUY":
            current_price = tick.bid
        elif signal == "SELL":
            current_price = tick.ask
        else:
            continue

        initial_volume = float(trade.get("initial_volume", 0.0))
        current_volume = float(position.volume)

        if initial_volume <= 0 or current_volume <= 0:
            continue

        runner_volume = _round_volume(
            symbol,
            initial_volume * float(
                trade.get("telegram_runner_remaining_pct", TELEGRAM_RUNNER_REMAINING_PCT)
            ),
        )

        stages = trade.get("telegram_tp_stages", [])

        for stage in stages:
            if stage.get("done"):
                continue

            tp = float(stage.get("tp", 0.0))

            if tp <= 0:
                continue

            if not _tp_reached(signal, current_price, tp):
                continue

            target_close_volume = _round_volume(
                symbol,
                initial_volume * float(stage.get("close_pct", 0.0)),
            )

            max_close_allowed = _round_volume(
                symbol,
                max(current_volume - runner_volume, 0.0),
            )

            close_volume = min(target_close_volume, max_close_allowed)

            close_volume = _round_volume(symbol, close_volume)

            if close_volume <= 0:
                stage["done"] = True
                stage["skipped_reason"] = "no_volume_available_after_runner_reserve"
                changed = True
                continue

            success, reason = _close_partial_position(
                symbol=symbol,
                position=position,
                signal=signal,
                close_volume=close_volume,
            )

            if not success:
                send_telegram_message(
                    f"❌ Telegram Partial TP Failed\n"
                    f"Position: {position_id}\n"
                    f"Stage: TP{stage.get('index')}\n"
                    f"TP: {tp}\n"
                    f"Close Volume: {close_volume}\n"
                    f"Reason: {reason}"
                )
                continue

            stage["done"] = True
            stage["closed_volume"] = close_volume
            stage["closed_at"] = datetime.now().isoformat()
            stage["closed_price"] = round(current_price, 2)

            trade["closed_volume"] = round(
                float(trade.get("closed_volume", 0.0)) + close_volume,
                2,
            )
            trade["remaining_volume"] = round(
                max(current_volume - close_volume, 0.0),
                2,
            )

            trade.setdefault("partial_closes", [])
            trade["partial_closes"].append(
                {
                    "time": datetime.now().isoformat(),
                    "reason": f"TELEGRAM_TP{stage.get('index')}",
                    "tp": tp,
                    "closed_volume": close_volume,
                    "remaining_volume": trade["remaining_volume"],
                    "current_price": round(current_price, 2),
                }
            )

            changed = True

            send_telegram_message(
                f"✅ Telegram Partial TP Closed\n"
                f"Position: {position_id}\n"
                f"Stage: TP{stage.get('index')}\n"
                f"TP: {tp}\n"
                f"Closed: {close_volume}\n"
                f"Remaining: {trade['remaining_volume']}\n"
                f"Runner Reserved: {runner_volume}"
            )

            # One partial close per loop is safer.
            break

        if stages and all(stage.get("done") for stage in stages):
            trade["runner_mode_active"] = True
            trade["runner_started_at"] = trade.get("runner_started_at") or datetime.now().isoformat()
            changed = True

    if changed:
        save_trades(trades)

    return changed