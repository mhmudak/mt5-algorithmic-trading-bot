import MetaTrader5 as mt5

from src.logger import logger


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

    for position in positions:
        logger.info(f"[MANAGER] Checking position {position.ticket}")

        entry_price = position.price_open
        current_sl = position.sl

        if position.type == mt5.POSITION_TYPE_BUY:
            current_price = tick.bid
        else:
            current_price = tick.ask

        # Example: move to breakeven after small profit
        profit_distance = abs(current_price - entry_price)

        if profit_distance > 5:  # adjust later
            new_sl = entry_price

            if position.type == mt5.POSITION_TYPE_BUY:
                if current_sl < new_sl:
                    modify_sl(position, new_sl)

            elif position.type == mt5.POSITION_TYPE_SELL:
                if current_sl == 0 or current_sl > new_sl:
                    modify_sl(position, new_sl)


def modify_sl(position, new_sl):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position.ticket,
        "sl": round(new_sl, 2),
        "tp": position.tp,
    }

    result = mt5.order_send(request)

    if result is None:
        logger.error(f"[MANAGER] Failed to modify SL: {mt5.last_error()}")
        return

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[MANAGER] SL moved to BE for {position.ticket}")
    else:
        logger.error(f"[MANAGER] Failed to modify SL: {result}")