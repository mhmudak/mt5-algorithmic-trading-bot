import MetaTrader5 as mt5

from src.logger import logger
from config.settings import (
    ENABLE_BREAK_EVEN,
    BREAK_EVEN_TRIGGER,
    ENABLE_TRAILING_STOP,
    TRAILING_STOP_DISTANCE,
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

    for position in positions:
        logger.info(f"[MANAGER] Checking position {position.ticket}")

        entry_price = position.price_open
        current_sl = position.sl
        current_tp = position.tp

        if position.type == mt5.POSITION_TYPE_BUY:
            current_price = tick.bid
            profit_distance = current_price - entry_price

            if ENABLE_BREAK_EVEN and profit_distance >= BREAK_EVEN_TRIGGER:
                breakeven_sl = entry_price
                if current_sl == 0 or current_sl < breakeven_sl:
                    modify_sl(position, breakeven_sl, current_tp, reason="Break-even")

            if ENABLE_TRAILING_STOP and profit_distance >= BREAK_EVEN_TRIGGER:
                trailing_sl = current_price - TRAILING_STOP_DISTANCE
                if trailing_sl > entry_price and trailing_sl > current_sl:
                    modify_sl(position, trailing_sl, current_tp, reason="Trailing stop")

        elif position.type == mt5.POSITION_TYPE_SELL:
            current_price = tick.ask
            profit_distance = entry_price - current_price

            if ENABLE_BREAK_EVEN and profit_distance >= BREAK_EVEN_TRIGGER:
                breakeven_sl = entry_price
                if current_sl == 0 or current_sl > breakeven_sl:
                    modify_sl(position, breakeven_sl, current_tp, reason="Break-even")

            if ENABLE_TRAILING_STOP and profit_distance >= BREAK_EVEN_TRIGGER:
                trailing_sl = current_price + TRAILING_STOP_DISTANCE
                if trailing_sl < entry_price and (current_sl == 0 or trailing_sl < current_sl):
                    modify_sl(position, trailing_sl, current_tp, reason="Trailing stop")


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
        return

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(
            f"[MANAGER] {reason} applied | "
            f"ticket={position.ticket} new_sl={round(new_sl, 2)}"
        )
    else:
        logger.error(f"[MANAGER] Failed to modify SL: {result}")