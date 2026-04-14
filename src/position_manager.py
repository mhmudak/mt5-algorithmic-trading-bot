import MetaTrader5 as mt5

from src.logger import logger
from src.notifier import send_telegram_message
from src.trade_tracker import load_trades, save_trades, update_trade_statistics
from config.settings import (
    ENABLE_MAIN_STAGE_MANAGEMENT,
    MAIN_STAGE_1_TRIGGER_PRICE,
    MAIN_STAGE_1_CLOSE_PCT,
    MAIN_EARLY_LOCK_TRIGGER_PRICE,
    MAIN_EARLY_LOCK_PRICE,
    MAIN_STAGE_2_TRIGGER_PRICE,
    MAIN_STAGE_2_CLOSE_PCT,
    MAIN_STAGE_2_LOCK_PRICE,
    MAIN_STAGE_3_TRIGGER_PRICE,
    MAIN_STAGE_3_CLOSE_PCT,
    MAIN_STAGE_3_LOCK_PRICE,
    ENABLE_EXTRA_ENTRY_MANAGEMENT,
    EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE,
    EXTRA_ENTRY_LOCK_TRIGGER_PRICE,
    EXTRA_ENTRY_LOCK_PRICE,
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

    tick = mt5.symbol_info_tick(symbol)
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

        if trade.get("imported_manually", False):
            logger.info(f"[MANAGER] Position {position_id} is manual-imported, skipping normal manager")
            continue

        tracked_positions.append((position, trade))

    if not tracked_positions:
        logger.info("[MANAGER] No tracked open positions to manage")
        return

    buy_positions = [(p, t) for p, t in tracked_positions if p.type == mt5.POSITION_TYPE_BUY]
    sell_positions = [(p, t) for p, t in tracked_positions if p.type == mt5.POSITION_TYPE_SELL]

    manage_direction_group(symbol=symbol, direction="BUY", group=buy_positions, tick=tick, trades=trades)
    manage_direction_group(symbol=symbol, direction="SELL", group=sell_positions, tick=tick, trades=trades)

    save_trades(trades)


def manage_direction_group(symbol, direction, group, tick, trades):
    if not group:
        return

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

    logger.info(f"[MANAGER] {direction} group | main={main_position_id} extras={len(extras)}")

    if len(extras) >= 2 and ENABLE_WORST_EXTRA_LOCK:
        worst_extra_position, _ = get_worst_extra(direction, extras)
        apply_price_lock(
            position=worst_extra_position,
            direction=direction,
            trigger_price=WORST_EXTRA_LOCK_TRIGGER_PRICE,
            lock_profit_price=WORST_EXTRA_LOCK_PROFIT_PRICE,
            reason="Worst extra lock",
        )

    for position, trade in extras:
        update_trade_statistics(position, trade, tick)
        manage_extra_entry(position, trade, tick)

    main_position = get_position_by_ticket(symbol, main_position.ticket)
    if main_position is not None:
        update_trade_statistics(main_position, main_trade, tick)
        manage_main_trade(main_position, main_trade, tick)


def get_worst_extra(direction, extras):
    if direction == "SELL":
        return min(extras, key=lambda item: item[0].price_open)
    return max(extras, key=lambda item: item[0].price_open)


def get_price_profit_distance(position, tick):
    entry_price = position.price_open

    if position.type == mt5.POSITION_TYPE_BUY:
        return tick.bid - entry_price

    return entry_price - tick.ask


def manage_extra_entry(position, trade, tick):
    position_id = str(position.ticket)
    current_volume = float(position.volume)
    price_profit_distance = get_price_profit_distance(position, tick)

    logger.info(
        f"[MANAGER] EXTRA | position={position_id} "
        f"price_profit_distance={price_profit_distance} volume={current_volume}"
    )

    if not ENABLE_EXTRA_ENTRY_MANAGEMENT:
        return

    # +3 -> BE
    if price_profit_distance >= EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE:
        apply_price_lock(
            position=position,
            direction="BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL",
            trigger_price=EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE,
            lock_profit_price=0.0,
            reason="Extra BE lock",
        )

    # +5 -> lock +2
    if price_profit_distance >= EXTRA_ENTRY_LOCK_TRIGGER_PRICE:
        apply_price_lock(
            position=position,
            direction="BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL",
            trigger_price=EXTRA_ENTRY_LOCK_TRIGGER_PRICE,
            lock_profit_price=EXTRA_ENTRY_LOCK_PRICE,
            reason="Extra +2 lock",
        )

    # +8 -> full close
    if price_profit_distance >= EXTRA_ENTRY_TAKE_PROFIT_PRICE:
        if close_position_volume(position, current_volume, tick, reason="Extra entry full close"):
            send_telegram_message(
                f"Extra Entry Closed\n"
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
    direction = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"

    logger.info(
        f"[MANAGER] MAIN | position={position_id} "
        f"price_profit_distance={price_profit_distance} "
        f"current_volume={current_volume} initial_volume={initial_volume}"
    )

    # Stage 1: +7.5 -> close 25%
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
                    f"Main Trade Stage 1\n"
                    f"Position: {position_id}\n"
                    f"Price Trigger: {MAIN_STAGE_1_TRIGGER_PRICE}\n"
                    f"Closed Volume: {stage_close_volume}"
                )

    position = get_position_by_ticket(position.symbol, position.ticket)
    if position is None:
        return

    price_profit_distance = get_price_profit_distance(position, tick)

    # Early lock: +12 -> lock +2.5
    if price_profit_distance >= MAIN_EARLY_LOCK_TRIGGER_PRICE:
        apply_price_lock(
            position=position,
            direction=direction,
            trigger_price=MAIN_EARLY_LOCK_TRIGGER_PRICE,
            lock_profit_price=MAIN_EARLY_LOCK_PRICE,
            reason="Main early +2.5 lock",
        )

    position = get_position_by_ticket(position.symbol, position.ticket)
    if position is None:
        return

    current_volume = float(position.volume)
    price_profit_distance = get_price_profit_distance(position, tick)

    # Stage 2: +18 -> close 25% + lock +12.5
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
                    apply_price_lock(
                        position=updated_position,
                        direction=direction,
                        trigger_price=MAIN_STAGE_2_TRIGGER_PRICE,
                        lock_profit_price=MAIN_STAGE_2_LOCK_PRICE,
                        reason="Main stage 2 lock",
                    )

                send_telegram_message(
                    f"Main Trade Stage 2\n"
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

    # Stage 3: +28 -> close 25% + lock +16
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
                    apply_price_lock(
                        position=updated_position,
                        direction=direction,
                        trigger_price=MAIN_STAGE_3_TRIGGER_PRICE,
                        lock_profit_price=MAIN_STAGE_3_LOCK_PRICE,
                        reason="Main stage 3 lock",
                    )

                send_telegram_message(
                    f"Main Trade Stage 3\n"
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


def apply_price_lock(position, direction, trigger_price, lock_profit_price, reason="Price lock"):
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