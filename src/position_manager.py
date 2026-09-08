import MetaTrader5 as mt5

from src.logger import logger
from src.notifier import send_telegram_message
from src.order_executor import get_supported_filling_modes
from src.trade_tracker import load_trades, save_trades, update_trade_statistics
from src.prop_firm_news_guard import evaluate_runtime_prop_firm_news_action
from src.prop_firm_minimum_hold_guard import (
    evaluate_runtime_prop_firm_minimum_hold,
)
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
    ENABLE_MAIN_RUNNER_MODE,
    MAIN_RUNNER_START_STAGE,
    MAIN_RUNNER_REMOVE_TP,
    MAIN_RUNNER_EMERGENCY_TP_PRICE,
    MAIN_RUNNER_REMAINING_PCT,
    ENABLE_MAIN_TP_LADDER_MANAGEMENT,
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
            logger.info(
                f"[MANAGER] Position {position_id} is manual-imported, updating statistics only"
            )
            update_trade_statistics(position, trade, tick)
            continue

        tracked_positions.append((position, trade))

    if not tracked_positions:
        logger.info("[MANAGER] No tracked open positions to manage")
        return

    buy_positions = [
        (position, trade)
        for position, trade in tracked_positions
        if position.type == mt5.POSITION_TYPE_BUY
    ]

    sell_positions = [
        (position, trade)
        for position, trade in tracked_positions
        if position.type == mt5.POSITION_TYPE_SELL
    ]

    manage_direction_group(
        symbol=symbol,
        direction="BUY",
        group=buy_positions,
        tick=tick,
        trades=trades,
    )

    manage_direction_group(
        symbol=symbol,
        direction="SELL",
        group=sell_positions,
        tick=tick,
        trades=trades,
    )

    save_trades(trades)


def _select_direction_main(
    direction,
    group,
):
    """
    New explicit execution roles are sticky.

    Priority:
      1. role-locked MAIN
      2. managed TP-ladder MAIN
      3. legacy best-entry selection

    A role-locked EXTRA can never be promoted to MAIN.
    If every tracked position is a locked EXTRA, return
    None because the physical MAIN is external/untracked.
    """
    locked_mains = [
        (
            position,
            trade,
        )
        for (
            position,
            trade,
        ) in group
        if trade.get(
            "trade_role_locked",
            False,
        )
        and trade.get(
            "trade_role"
        )
        == "MAIN"
    ]

    if locked_mains:
        if len(locked_mains) > 1:
            logger.warning(
                "[MANAGER ROLE] "
                "multiple locked MAIN positions found; "
                "preserving first tracked MAIN"
            )

        return locked_mains[0]

    managed_mains = [
        (
            position,
            trade,
        )
        for (
            position,
            trade,
        ) in group
        if trade.get(
            "main_tp_ladder_managed",
            False,
        )
        and not (
            trade.get(
                "trade_role_locked",
                False,
            )
            and trade.get(
                "trade_role"
            )
            == "EXTRA"
        )
    ]

    if managed_mains:
        tracked_main = [
            item
            for item in managed_mains
            if item[1].get(
                "trade_role"
            )
            == "MAIN"
        ]

        if tracked_main:
            return tracked_main[0]

        return managed_mains[0]

    eligible = [
        (
            position,
            trade,
        )
        for (
            position,
            trade,
        ) in group
        if not (
            trade.get(
                "trade_role_locked",
                False,
            )
            and trade.get(
                "trade_role"
            )
            == "EXTRA"
        )
    ]

    if not eligible:
        return None

    if direction == "SELL":
        return max(
            eligible,
            key=lambda item: (
                item[0].price_open
            ),
        )

    return min(
        eligible,
        key=lambda item: (
            item[0].price_open
        ),
    )



def manage_direction_group(symbol, direction, group, tick, trades):
    if not group:
        return

    selection = (
        _select_direction_main(
            direction,
            group,
        )
    )

    # All tracked positions can legitimately be EXTRAs
    # when the physical MAIN is manual/untracked.
    if selection is None:
        extras = list(group)

        for position, trade in extras:
            trade[
                "trade_role"
            ] = "EXTRA"

            if not trade.get(
                "main_position_id"
            ):
                trade[
                    "main_position_id"
                ] = (
                    "UNTRACKED_PHYSICAL_MAIN"
                )

        logger.info(
            f"[MANAGER] {direction} group | "
            "main=UNTRACKED_PHYSICAL_MAIN "
            f"extras={len(extras)}"
        )

        if (
            len(extras) >= 2
            and ENABLE_WORST_EXTRA_LOCK
        ):
            (
                worst_extra_position,
                _,
            ) = get_worst_extra(
                direction,
                extras,
            )

            apply_price_lock(
                position=(
                    worst_extra_position
                ),
                direction=direction,
                trigger_price=(
                    WORST_EXTRA_LOCK_TRIGGER_PRICE
                ),
                lock_profit_price=(
                    WORST_EXTRA_LOCK_PROFIT_PRICE
                ),
                reason=(
                    "Worst extra lock"
                ),
            )

        for position, trade in extras:
            update_trade_statistics(
                position,
                trade,
                tick,
            )

            manage_extra_entry(
                position,
                trade,
                tick,
            )

        return

    main_position, main_trade = (
        selection
    )

    main_position_id = str(
        main_position.ticket
    )

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

    main_position = get_position_by_ticket(
        symbol,
        main_position.ticket,
    )

    if main_position is not None:
        update_trade_statistics(
            main_position,
            main_trade,
            tick,
        )

        if (
            ENABLE_MAIN_TP_LADDER_MANAGEMENT
            and main_trade.get(
                "main_tp_ladder_managed",
                False,
            )
        ):
            manage_main_tp_ladder_trade(
                main_position,
                main_trade,
                tick,
            )

        else:
            manage_main_trade(
                main_position,
                main_trade,
                tick,
            )


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
    direction = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"

    logger.info(
        f"[MANAGER] EXTRA | position={position_id} "
        f"price_profit_distance={price_profit_distance} volume={current_volume}"
    )

    if not ENABLE_EXTRA_ENTRY_MANAGEMENT:
        return

    if price_profit_distance >= EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE:
        apply_price_lock(
            position=position,
            direction=direction,
            trigger_price=EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE,
            lock_profit_price=0.0,
            reason="Extra BE lock",
        )

    if price_profit_distance >= EXTRA_ENTRY_LOCK_TRIGGER_PRICE:
        apply_price_lock(
            position=position,
            direction=direction,
            trigger_price=EXTRA_ENTRY_LOCK_TRIGGER_PRICE,
            lock_profit_price=EXTRA_ENTRY_LOCK_PRICE,
            reason="Extra +2 lock",
        )

    if price_profit_distance >= EXTRA_ENTRY_TAKE_PROFIT_PRICE:
        if close_position_volume(
            position,
            current_volume,
            tick,
            reason="Extra entry full close",
        ):
            send_telegram_message(
                f"Extra Entry Closed\n"
                f"Position: {position_id}\n"
                f"Symbol: {position.symbol}\n"
                f"Price Trigger: {EXTRA_ENTRY_TAKE_PROFIT_PRICE}\n"
                f"Closed Volume: {current_volume}"
            )


def calculate_runner_tp(position, direction):
    if not ENABLE_MAIN_RUNNER_MODE:
        return position.tp

    if MAIN_RUNNER_REMOVE_TP:
        return 0.0

    if direction == "BUY":
        return round(position.price_open + MAIN_RUNNER_EMERGENCY_TP_PRICE, 2)

    return round(position.price_open - MAIN_RUNNER_EMERGENCY_TP_PRICE, 2)


def activate_main_runner_mode(position, trade, direction, lock_profit_price, reason):
    if not ENABLE_MAIN_RUNNER_MODE:
        return False

    entry_price = position.price_open

    if direction == "SELL":
        new_sl = entry_price - lock_profit_price
    else:
        new_sl = entry_price + lock_profit_price

    runner_tp = calculate_runner_tp(position, direction)

    if modify_sl(position, new_sl, runner_tp, reason):
        trade["runner_mode_active"] = True
        trade["runner_tp_removed"] = MAIN_RUNNER_REMOVE_TP
        trade["runner_started_at"] = reason

        send_telegram_message(
            f"Main Runner Mode Activated\n"
            f"Position: {position.ticket}\n"
            f"Direction: {direction}\n"
            f"Locked Profit: {lock_profit_price}\n"
            f"TP: {'Removed' if runner_tp == 0.0 else runner_tp}\n"
            f"Reason: {reason}"
        )
        return True

    return False


def _volume_decimals_from_step(
    step,
):
    try:
        text = (
            f"{float(step):.10f}"
            .rstrip("0")
        )

        if "." not in text:
            return 0

        return len(
            text.split(".")[1]
        )

    except Exception:
        return 2


def _floor_broker_volume(
    volume,
    symbol_info,
):
    try:
        step = float(
            symbol_info.volume_step
        )

        minimum = float(
            symbol_info.volume_min
        )

        if step <= 0:
            return 0.0

        units = int(
            (
                float(volume)
                + 1e-10
            )
            / step
        )

        result = (
            units * step
        )

        if result + 1e-9 < minimum:
            return 0.0

        return round(
            result,
            _volume_decimals_from_step(
                step
            ),
        )

    except Exception:
        return 0.0


def _ceil_broker_volume(
    volume,
    symbol_info,
):
    try:
        step = float(
            symbol_info.volume_step
        )

        minimum = float(
            symbol_info.volume_min
        )

        if step <= 0:
            return 0.0

        value = max(
            float(volume),
            minimum,
        )

        units = int(
            value / step
        )

        if (
            units * step
            + 1e-10
            < value
        ):
            units += 1

        return round(
            units * step,
            _volume_decimals_from_step(
                step
            ),
        )

    except Exception:
        return 0.0


def _main_ladder_stage_close_volume(
    *,
    initial_volume,
    close_pct,
    current_volume,
    symbol_info,
):
    """
    Allocate each TP partial while preserving at least
    MAIN_RUNNER_REMAINING_PCT for the final runner.
    """
    try:
        initial_volume = float(
            initial_volume
        )

        current_volume = float(
            current_volume
        )

        close_pct = float(
            close_pct
        )

    except Exception:
        return 0.0

    desired = (
        _floor_broker_volume(
            initial_volume
            * close_pct,
            symbol_info,
        )
    )

    runner_floor = (
        _ceil_broker_volume(
            initial_volume
            * float(
                MAIN_RUNNER_REMAINING_PCT
            ),
            symbol_info,
        )
    )

    max_close = (
        _floor_broker_volume(
            current_volume
            - runner_floor,
            symbol_info,
        )
    )

    if (
        desired <= 0
        or max_close <= 0
    ):
        return 0.0

    close_volume = min(
        desired,
        max_close,
    )

    if (
        current_volume
        - close_volume
        < runner_floor - 1e-9
    ):
        return 0.0

    return close_volume


def _main_ladder_current_price(
    direction,
    tick,
):
    if direction == "BUY":
        return float(
            tick.bid
        )

    return float(
        tick.ask
    )


def _main_ladder_target_reached(
    direction,
    current_price,
    target,
):
    try:
        current_price = float(
            current_price
        )

        target = float(
            target
        )

    except Exception:
        return False

    if direction == "BUY":
        return (
            current_price
            >= target
        )

    return (
        current_price
        <= target
    )


def _protect_main_ladder(
    position,
    direction,
    lock_price,
    tick,
    *,
    remove_tp,
    reason,
):
    """
    Never weaken an already-better SL.
    At TP3 the runner TP may be removed.
    """
    try:
        lock_price = float(
            lock_price
        )

        current_price = (
            float(tick.bid)
            if direction == "BUY"
            else float(tick.ask)
        )

        current_sl = float(
            position.sl
            or 0.0
        )

        current_tp = float(
            position.tp
            or 0.0
        )

    except Exception:
        return False

    if direction == "BUY":
        desired_sl = (
            max(
                current_sl,
                lock_price,
            )
            if current_sl > 0
            else lock_price
        )

        if desired_sl >= current_price:
            return False

    else:
        desired_sl = (
            min(
                current_sl,
                lock_price,
            )
            if current_sl > 0
            else lock_price
        )

        if desired_sl <= current_price:
            return False

    desired_tp = (
        0.0
        if remove_tp
        else current_tp
    )

    if (
        abs(
            desired_sl
            - current_sl
        ) < 0.005
        and abs(
            desired_tp
            - current_tp
        ) < 0.005
    ):
        return True

    return modify_sl(
        position,
        desired_sl,
        desired_tp,
        reason,
    )


def manage_main_tp_ladder_trade(
    position,
    trade,
    tick,
):
    """
    One physical MAIN:

      TP1 -> partial
      TP2 -> partial, protect remaining at TP1
      TP3 -> partial, protect runner at TP2
      RUNNER -> remains open

    TP3 is never a full-position liquidation.
    """
    if not ENABLE_MAIN_STAGE_MANAGEMENT:
        return

    position_id = str(
        position.ticket
    )

    direction = (
        "BUY"
        if position.type
        == mt5.POSITION_TYPE_BUY
        else "SELL"
    )

    try:
        tp1 = float(
            trade["main_tp1"]
        )

        tp2 = float(
            trade["main_tp2"]
        )

        tp3 = float(
            trade["main_tp3"]
        )

    except Exception:
        logger.warning(
            "[MAIN TP LADDER] "
            "invalid persisted ladder; "
            "falling back to legacy MAIN manager "
            f"| position={position_id}"
        )

        return manage_main_trade(
            position,
            trade,
            tick,
        )

    symbol_info = mt5.symbol_info(
        position.symbol
    )

    if symbol_info is None:
        return

    initial_volume = float(
        trade.get(
            "initial_volume",
            position.volume,
        )
    )

    # Retry TP2 protection if a runtime news/minimum-hold
    # protection guard previously prevented modification.
    if (
        trade.get(
            "stage_2_done",
            False,
        )
        and not trade.get(
            "stage_3_done",
            False,
        )
        and not trade.get(
            "runner_tp2_lock_done",
            False,
        )
    ):
        fresh_position = (
            get_position_by_ticket(
                position.symbol,
                position.ticket,
            )
        )

        if (
            fresh_position
            is not None
            and _protect_main_ladder(
                fresh_position,
                direction,
                tp1,
                tick,
                remove_tp=False,
                reason=(
                    "Main TP2 protection "
                    "retry -> TP1"
                ),
            )
        ):
            trade[
                "runner_tp2_lock_done"
            ] = True

    # Once TP3 has been partially realized, only the
    # runner remains. Retry its protection if needed.
    if trade.get(
        "stage_3_done",
        False,
    ):
        trade[
            "runner_mode_active"
        ] = True

        if not trade.get(
            "runner_tp3_lock_done",
            False,
        ):
            fresh_position = (
                get_position_by_ticket(
                    position.symbol,
                    position.ticket,
                )
            )

            if (
                fresh_position
                is not None
                and _protect_main_ladder(
                    fresh_position,
                    direction,
                    tp2,
                    tick,
                    remove_tp=bool(
                        MAIN_RUNNER_REMOVE_TP
                    ),
                    reason=(
                        "Main TP3 runner "
                        "protection retry -> TP2"
                    ),
                )
            ):
                trade[
                    "runner_tp3_lock_done"
                ] = True

                trade[
                    "runner_tp_removed"
                ] = bool(
                    MAIN_RUNNER_REMOVE_TP
                )

        return

    stages = (
        (
            1,
            tp1,
            MAIN_STAGE_1_CLOSE_PCT,
        ),
        (
            2,
            tp2,
            MAIN_STAGE_2_CLOSE_PCT,
        ),
        (
            3,
            tp3,
            MAIN_STAGE_3_CLOSE_PCT,
        ),
    )

    for (
        stage_no,
        target,
        close_pct,
    ) in stages:
        done_key = (
            f"stage_{stage_no}_done"
        )

        if trade.get(
            done_key,
            False,
        ):
            continue

        position = (
            get_position_by_ticket(
                position.symbol,
                position.ticket,
            )
        )

        if position is None:
            return

        current_price = (
            _main_ladder_current_price(
                direction,
                tick,
            )
        )

        if not (
            _main_ladder_target_reached(
                direction,
                current_price,
                target,
            )
        ):
            # Targets must be reached sequentially.
            break

        close_volume = (
            _main_ladder_stage_close_volume(
                initial_volume=(
                    initial_volume
                ),
                close_pct=close_pct,
                current_volume=float(
                    position.volume
                ),
                symbol_info=(
                    symbol_info
                ),
            )
        )

        if close_volume <= 0:
            logger.warning(
                "[MAIN TP LADDER] "
                "stage partial unavailable "
                f"| position={position_id} "
                f"stage=TP{stage_no} "
                f"volume={position.volume}"
            )

            break

        if not close_position_volume(
            position,
            close_volume,
            tick,
            reason=(
                f"Main TP{stage_no} "
                "partial close"
            ),
        ):
            # Existing news/minimum-hold guards remain
            # authoritative. Retry on a later cycle.
            break

        trade[
            done_key
        ] = True

        send_telegram_message(
            f"🎯 MAIN TP{stage_no} Reached\n"
            f"Position: {position_id}\n"
            f"Symbol: {position.symbol}\n"
            f"Target: {target}\n"
            f"Closed Volume: {close_volume}\n"
            f"Runner Preserved: True"
        )

        updated_position = (
            get_position_by_ticket(
                position.symbol,
                position.ticket,
            )
        )

        if updated_position is None:
            return

        if stage_no == 2:
            if _protect_main_ladder(
                updated_position,
                direction,
                tp1,
                tick,
                remove_tp=False,
                reason=(
                    "Main TP2 protection "
                    "-> TP1"
                ),
            ):
                trade[
                    "runner_tp2_lock_done"
                ] = True

        elif stage_no == 3:
            trade[
                "runner_mode_active"
            ] = True

            trade[
                "runner_started_at"
            ] = "TP3_REACHED"

            if _protect_main_ladder(
                updated_position,
                direction,
                tp2,
                tick,
                remove_tp=bool(
                    MAIN_RUNNER_REMOVE_TP
                ),
                reason=(
                    "Main TP3 runner "
                    "protection -> TP2"
                ),
            ):
                trade[
                    "runner_tp3_lock_done"
                ] = True

                trade[
                    "runner_tp_removed"
                ] = bool(
                    MAIN_RUNNER_REMOVE_TP
                )

            send_telegram_message(
                f"🏃 MAIN Runner Active\n"
                f"Position: {position_id}\n"
                f"Symbol: {position.symbol}\n"
                f"TP3: {tp3}\n"
                f"Runner Protection: TP2 {tp2}\n"
                f"TP Removed: "
                f"{bool(MAIN_RUNNER_REMOVE_TP)}"
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
            if close_position_volume(
                position,
                stage_close_volume,
                tick,
                reason="Main stage 1 partial close",
            ):
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

    if price_profit_distance >= MAIN_EARLY_LOCK_TRIGGER_PRICE:
        apply_price_lock(
            position=position,
            direction=direction,
            trigger_price=MAIN_EARLY_LOCK_TRIGGER_PRICE,
            lock_profit_price=MAIN_EARLY_LOCK_PRICE,
            reason="Main early lock",
        )

    position = get_position_by_ticket(position.symbol, position.ticket)

    if position is None:
        return

    current_volume = float(position.volume)
    price_profit_distance = get_price_profit_distance(position, tick)

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
            if close_position_volume(
                position,
                stage_close_volume,
                tick,
                reason="Main stage 2 partial close",
            ):
                trade["stage_2_done"] = True

                updated_position = get_position_by_ticket(position.symbol, position.ticket)

                if updated_position is not None:
                    if ENABLE_MAIN_RUNNER_MODE and MAIN_RUNNER_START_STAGE <= 2:
                        activate_main_runner_mode(
                            position=updated_position,
                            trade=trade,
                            direction=direction,
                            lock_profit_price=MAIN_STAGE_2_LOCK_PRICE,
                            reason="Main stage 2 runner start",
                        )
                    else:
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
            if close_position_volume(
                position,
                stage_close_volume,
                tick,
                reason="Main stage 3 partial close",
            ):
                trade["stage_3_done"] = True

                updated_position = get_position_by_ticket(position.symbol, position.ticket)

                if updated_position is not None:
                    if ENABLE_MAIN_RUNNER_MODE and MAIN_RUNNER_START_STAGE <= 3:
                        activate_main_runner_mode(
                            position=updated_position,
                            trade=trade,
                            direction=direction,
                            lock_profit_price=MAIN_STAGE_3_LOCK_PRICE,
                            reason="Main stage 3 runner protection",
                        )
                    else:
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

    try:
        current_volume = float(position.volume)
        requested_close_volume = float(close_volume)

        if requested_close_volume >= current_volume - 1e-9:
            news_action = "FULL_CLOSE_POSITION"
        else:
            news_action = "PARTIAL_CLOSE_POSITION"

        news_decision = evaluate_runtime_prop_firm_news_action(
            action=news_action,
        )

        if not news_decision.get("allowed", False):
            logger.warning(
                "[PROP FIRM NEWS EXIT GUARD] "
                f"position close blocked | "
                f"ticket={position.ticket} "
                f"symbol={position.symbol} "
                f"action={news_action} "
                f"close_volume={close_volume} "
                f"reason={reason} "
                f"guard_reason={news_decision.get('reason')} "
                f"snapshot={news_decision.get('snapshot')}"
            )
            return False

        hold_decision = evaluate_runtime_prop_firm_minimum_hold(
            position=position,
            action=news_action,
            now_timestamp=getattr(tick, "time", None),
        )

        if not hold_decision.get("allowed", False):
            logger.warning(
                "[PROP FIRM MINIMUM HOLD GUARD] "
                f"position close blocked | "
                f"ticket={position.ticket} "
                f"symbol={position.symbol} "
                f"action={news_action} "
                f"close_volume={close_volume} "
                f"reason={reason} "
                f"guard_reason={hold_decision.get('reason')} "
                f"snapshot={hold_decision.get('snapshot')} "
                f"orders_sent=0"
            )
            return False

    except Exception as exc:
        logger.error(
            "[PROP FIRM NEWS EXIT GUARD] "
            f"close evaluation failed: {exc}"
        )

        try:
            from config import settings as runtime_settings

            if (
                runtime_settings.ENABLE_PROP_FIRM_SAFE_MODE
                and runtime_settings.PROP_FIRM_SAFE_MODE_FAIL_CLOSED
            ):
                return False
        except Exception:
            pass

    if position.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    base_request = {
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
    }

    result = None
    last_error_message = None

    for filling_mode in get_supported_filling_modes(position.symbol):
        request = base_request.copy()
        request["type_filling"] = filling_mode

        result = mt5.order_send(request)

        if result is None:
            last_error_message = (
                f"{reason} failed with filling={filling_mode}: {mt5.last_error()}"
            )
            continue

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(
                f"[MANAGER] {reason} success | "
                f"ticket={position.ticket} "
                f"closed_volume={close_volume} "
                f"filling_mode={filling_mode}"
            )
            return True

        last_error_message = f"{reason} rejected with filling={filling_mode}: {result}"

        if result.retcode == 10030:
            continue

        break

    logger.error(f"[MANAGER] {last_error_message}")
    return False


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
    news_decision = evaluate_runtime_prop_firm_news_action(
        action="MODIFY_PROTECTIVE_SL_TP",
    )

    if not news_decision.get("allowed", False):
        logger.warning(
            "[PROP FIRM NEWS PROTECTION GUARD] "
            f"SL/TP modification frozen | "
            f"ticket={position.ticket} "
            f"symbol={position.symbol} "
            f"requested_sl={round(new_sl, 2)} "
            f"requested_tp={tp} "
            f"reason={reason} "
            f"guard_reason={news_decision.get('reason')} "
            f"existing protection remains active"
        )
        return False

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
