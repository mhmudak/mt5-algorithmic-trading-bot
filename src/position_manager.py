import MetaTrader5 as mt5

from src.logger import logger
from src.notifier import send_telegram_message
from src.trade_tracker import load_trades, save_trades
from config.settings import (
    ENABLE_MAIN_STAGE_MANAGEMENT,
    MAIN_STAGE_1_TRIGGER_PRICE,
    MAIN_STAGE_1_CLOSE_PCT,
    MAIN_STAGE_2_TRIGGER_PRICE,
    MAIN_STAGE_2_CLOSE_PCT,
    MAIN_STAGE_2_LOCK_PRICE,
    MAIN_STAGE_3_TRIGGER_PRICE,
    MAIN_STAGE_3_CLOSE_PCT,
    MAIN_STAGE_3_LOCK_PRICE,
    ENABLE_EXTRA_ENTRY_MANAGEMENT,
    EXTRA_ENTRY_TAKE_PROFIT_PRICE,
    ENABLE_WORST_EXTRA_LOCK,
    WORST_EXTRA_LOCK_TRIGGER_PRICE,
    WORST_EXTRA_LOCK_PROFIT_PRICE,
)


def manage_positions(symbol: str):
    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        logger.info("[MANAGER] No positions returned")
        return

    if len(positions) == 0:
        logger.info(f"[MANAGER] No open positions on {symbol}")
        return

    symbol_info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if symbol_info is None:
        logger.error(f"[MANAGER] No symbol info for {symbol}")
        return

    if tick is None:
        logger.error("[MANAGER] No tick data")
        return

    trades = load_trades()
    if not trades:
        logger.info("[MANAGER] No tracked trades found")
        return

    tracked_positions = []
    for position in positions:
        position_id = str(position.ticket)
        trade = trades.get(position_id)

        if trade is None:
            logger.info(f"[MANAGER] Position {position_id} is not tracked")
            continue

        tracked_positions.append((position, trade))

    if not tracked_positions:
        logger.info("[MANAGER] No tracked open positions to manage")
        return

    buy_positions = [(p, t) for p, t in tracked_positions if p.type == mt5.POSITION_TYPE_BUY]
    sell_positions = [(p, t) for p, t in tracked_positions if p.type == mt5.POSITION_TYPE_SELL]

    manage_direction_group(
        symbol=symbol,
        direction="BUY",
        group=buy_positions,
        symbol_info=symbol_info,
        tick=tick,
        trades=trades,
    )

    manage_direction_group(
        symbol=symbol,
        direction="SELL",
        group=sell_positions,
        symbol_info=symbol_info,
        tick=tick,
        trades=trades,
    )

    save_trades(trades)


def manage_direction_group(symbol, direction, group, symbol_info, tick, trades):
    if not group:
        return

    # Main = best entry
    if direction == "SELL":
        main_position, main_trade = max(group, key=lambda item: item[0].price_open)
    else:
        main_position, main_trade = min(group, key=lambda item: item[0].price_open)

    main_position_id = str(main_position.ticket)

    extras = []
    for position, trade in group:
        position_id = str(position.ticket)

        if position_id == main_position_id:
            trade["trade_role"] = "MAIN"
            trade["main_position_id"] = main_position_id
        else:
            trade["trade_role"] = "EXTRA"
            trade["main_position_id"] = main_position_id
            extras.append((position, trade))

    logger.info(
        f"[MANAGER] {direction} group | main={main_position_id} extras={len(extras)}"
    )

    # Worst extra lock when extras >= 2
    if len(extras) >= 2 and ENABLE_WORST_EXTRA_LOCK:
        worst_extra_position, _ = get_worst_extra(direction, extras)
        apply_worst_extra_price_lock(
            position=worst_extra_position,
            direction=direction,
            trigger_price=WORST_EXTRA_LOCK_TRIGGER_PRICE,
            lock_profit_price=WORST_EXTRA_LOCK_PROFIT_PRICE,
            reason="Worst extra lock",
        )

    # Manage extras
    for position, trade in extras:
        manage_extra_entry(position, trade, tick)

    # Refresh main after possible closes
    main_position = get_position_by_ticket(symbol, main_position.ticket)
    if main_position is not None:
        manage_main_trade(main_position, main_trade, tick)


def get_worst_extra(direction, extras):
    # SELL -> lowest entry
    # BUY  -> highest entry
    if direction == "SELL":
        return min(extras, key=lambda item: item[0].price_open)
    return max(extras, key=lambda item: item[0].price_open)


def get_price_profit_distance(position, tick):
    entry_price = position.price_open

    if position.type == mt5.POSITION_TYPE_BUY:
        current_price = tick.bid
        return current_price - entry_price

    current_price = tick.ask
    return entry_price - current_price


def manage_extra_entry(position, trade, tick):
    position_id = str(position.ticket)
    current_volume = float(position.volume)
    price_profit_distance = get_price_profit_distance(position, tick)

    logger.info(
        f"[MANAGER] EXTRA | position={position_id} "
        f"price_profit_distance={price_profit_distance} volume={current_volume}"
    )

    if (
        ENABLE_EXTRA_ENTRY_MANAGEMENT
        and price_profit_distance >= EXTRA_ENTRY_TAKE_PROFIT_PRICE
    ):
        if close_position_volume(position, current_volume, tick, reason="Extra entry full close"):
            send_telegram_message(
                f"💰 Extra Entry Closed\n"
                f"Position: {position_id}\n"
                f"Symbol: {position.symbol}\n"
                f"Price Trigger: {EXTRA_ENTRY_TAKE_PROFIT_PRICE}\n"
                f"Closed Volume: {current_volume}"
            )


def manage_main_trade(position, trade, tick):
    if not ENABLE_MAIN_STAGE_MANAGEMENT:
        return

    position_id = str(position.ticket)
    current_volume = float(position.volume)
    initial_volume = float(trade.get("initial_volume", current_volume))
    price_profit_distance = get_price_profit_distance(position, tick)

    logger.info(
        f"[MANAGER] MAIN | position={position_id} "
        f"price_profit_distance={price_profit_distance} "
        f"current_volume={current_volume} initial_volume={initial_volume}"
    )

    # Stage 1
    if (
        not trade.get("stage_1_done", False)
        and price_profit_distance >= MAIN_STAGE_1_TRIGGER_PRICE
    ):
        stage_close_volume = calculate_stage_close_volume(
            initial_volume=initial_volume,
            close_pct=MAIN_STAGE_1_CLOSE_PCT,
            current_volume=current_volume,
            symbol_info=mt5.symbol_info(position.symbol),
        )

        if stage_close_volume > 0:
            if close_position_volume(position, stage_close_volume, tick, reason="Main stage 1 partial close"):
                trade["stage_1_done"] = True

                send_telegram_message(
                    f"📌 Main Trade Stage 1\n"
                    f"Position: {position_id}\n"
                    f"Price Trigger: {MAIN_STAGE_1_TRIGGER_PRICE}\n"
                    f"Closed Volume: {stage_close_volume}"
                )

    position = get_position_by_ticket(position.symbol, position.ticket)
    if position is None:
        return

    current_volume = float(position.volume)
    price_profit_distance = get_price_profit_distance(position, tick)

    # Stage 2
    if (
        not trade.get("stage_2_done", False)
        and price_profit_distance >= MAIN_STAGE_2_TRIGGER_PRICE
    ):
        stage_close_volume = calculate_stage_close_volume(
            initial_volume=initial_volume,
            close_pct=MAIN_STAGE_2_CLOSE_PCT,
            current_volume=current_volume,
            symbol_info=mt5.symbol_info(position.symbol),
        )

        if stage_close_volume > 0:
            if close_position_volume(position, stage_close_volume, tick, reason="Main stage 2 partial close"):
                trade["stage_2_done"] = True

                updated_position = get_position_by_ticket(position.symbol, position.ticket)
                if updated_position is not None:
                    apply_profit_lock_price(
                        updated_position,
                        MAIN_STAGE_2_LOCK_PRICE,
                        reason="Main stage 2 lock",
                    )

                send_telegram_message(
                    f"📌 Main Trade Stage 2\n"
                    f"Position: {position_id}\n"
                    f"Price Trigger: {MAIN_STAGE_2_TRIGGER_PRICE}\n"
                    f"Closed Volume: {stage_close_volume}\n"
                    f"Locked Price Profit: {MAIN_STAGE_2_LOCK_PRICE}"
                )

    position = get_position_by_ticket(position.symbol, position.ticket)
    if position is None:
        return

    current_volume = float(position.volume)
    price_profit_distance = get_price_profit_distance(position, tick)

    # Stage 3
    if (
        not trade.get("stage_3_done", False)
        and price_profit_distance >= MAIN_STAGE_3_TRIGGER_PRICE
    ):
        stage_close_volume = calculate_stage_close_volume(
            initial_volume=initial_volume,
            close_pct=MAIN_STAGE_3_CLOSE_PCT,
            current_volume=current_volume,
            symbol_info=mt5.symbol_info(position.symbol),
        )

        if stage_close_volume > 0:
            if close_position_volume(position, stage_close_volume, tick, reason="Main stage 3 partial close"):
                trade["stage_3_done"] = True

                updated_position = get_position_by_ticket(position.symbol, position.ticket)
                if updated_position is not None:
                    apply_profit_lock_price(
                        updated_position,
                        MAIN_STAGE_3_LOCK_PRICE,
                        reason="Main stage 3 lock",
                    )

                send_telegram_message(
                    f"📌 Main Trade Stage 3\n"
                    f"Position: {position_id}\n"
                    f"Price Trigger: {MAIN_STAGE_3_TRIGGER_PRICE}\n"
                    f"Closed Volume: {stage_close_volume}\n"
                    f"Locked Price Profit: {MAIN_STAGE_3_LOCK_PRICE}"
                )


def calculate_stage_close_volume(initial_volume, close_pct, current_volume, symbol_info):
    target_volume = initial_volume * close_pct
    target_volume = round_to_broker_volume(target_volume, symbol_info)

    min_volume = symbol_info.volume_min

    if target_volume <= 0:
        return 0.0

    if current_volume - target_volume < min_volume:
        adjusted = round(current_volume - min_volume, 2)
        if adjusted <= 0:
            return 0.0
        target_volume = round_to_broker_volume(adjusted, symbol_info)

    if target_volume >= current_volume:
        return 0.0

    return round(target_volume, 2)


def round_to_broker_volume(volume, symbol_info):
    step = symbol_info.volume_step
    min_volume = symbol_info.volume_min

    if volume < min_volume:
        return min_volume

    rounded = round(round(volume / step) * step, 2)
    return max(rounded, min_volume)


def close_position_volume(position, close_volume, tick, reason="Partial close"):
    if close_volume <= 0:
        return False

    if position.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": round(close_volume, 2),
        "type": order_type,
        "position": position.ticket,
        "price": price,
        "deviation": 10,
        "magic": 123456,
        "comment": "MT5BotPC",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is None:
        logger.error(f"[MANAGER] {reason} failed: {mt5.last_error()}")
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"[MANAGER] {reason} rejected: {result}")
        return False

    logger.info(
        f"[MANAGER] {reason} success | ticket={position.ticket} closed_volume={close_volume}"
    )
    return True


def apply_profit_lock_price(position, lock_profit_price, reason="Profit lock"):
    current_sl = position.sl
    entry_price = position.price_open
    current_tp = position.tp

    if position.type == mt5.POSITION_TYPE_BUY:
        new_sl = entry_price + lock_profit_price
        if current_sl != 0 and new_sl <= current_sl:
            return False
    else:
        new_sl = entry_price - lock_profit_price
        if current_sl != 0 and new_sl >= current_sl:
            return False

    return modify_sl(position, new_sl, current_tp, reason)


def apply_worst_extra_price_lock(position, direction, trigger_price, lock_profit_price, reason="Worst extra lock"):
    entry_price = position.price_open
    current_sl = position.sl
    current_tp = position.tp

    tick = mt5.symbol_info_tick(position.symbol)
    if tick is None:
        logger.error(f"[MANAGER] No tick data for {position.ticket}")
        return False

    if direction == "SELL":
        current_price = tick.ask
        profit_distance = entry_price - current_price

        if profit_distance < trigger_price:
            return False

        new_sl = entry_price - lock_profit_price

        if current_sl != 0 and new_sl >= current_sl:
            return False

    else:
        current_price = tick.bid
        profit_distance = current_price - entry_price

        if profit_distance < trigger_price:
            return False

        new_sl = entry_price + lock_profit_price

        if current_sl != 0 and new_sl <= current_sl:
            return False

    return modify_sl(position, new_sl, current_tp, reason)


def modify_sl(position, new_sl, tp, reason="SL update"):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position.ticket,
        "sl": round(new_sl, 2),
        "tp": tp,
    }

    result = mt5.order_send(request)

    if result is None:
        logger.error(f"[MANAGER] Failed to modify SL: {mt5.last_error()}")
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(
            f"[MANAGER] {reason} applied | ticket={position.ticket} new_sl={round(new_sl, 2)}"
        )
        return True

    logger.error(f"[MANAGER] Failed to modify SL: {result}")
    return False


def get_position_by_ticket(symbol, ticket):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return None

    for pos in positions:
        if pos.ticket == ticket:
            return pos

    return None