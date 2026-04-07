# import MetaTrader5 as mt5

# from src.logger import logger
# from config.settings import (
#     ENABLE_BREAK_EVEN,
#     BREAK_EVEN_TRIGGER,
#     ENABLE_TRAILING_STOP,
#     TRAILING_STOP_DISTANCE,
# )


# def manage_positions(symbol: str):
#     positions = mt5.positions_get(symbol=symbol)

#     if positions is None:
#         logger.info("[MANAGER] No positions returned")
#         return

#     if len(positions) == 0:
#         logger.info(f"[MANAGER] No open positions on {symbol}")
#         return

#     tick = mt5.symbol_info_tick(symbol)
#     if tick is None:
#         logger.error("[MANAGER] No tick data")
#         return

#     for position in positions:
#         logger.info(f"[MANAGER] Checking position {position.ticket}")

#         entry_price = position.price_open
#         current_sl = position.sl
#         current_tp = position.tp

#         if position.type == mt5.POSITION_TYPE_BUY:
#             current_price = tick.bid
#             profit_distance = current_price - entry_price

#             if ENABLE_BREAK_EVEN and profit_distance >= BREAK_EVEN_TRIGGER:
#                 breakeven_sl = entry_price
#                 if current_sl == 0 or current_sl < breakeven_sl:
#                     modify_sl(position, breakeven_sl, current_tp, reason="Break-even")

#             if ENABLE_TRAILING_STOP and profit_distance >= BREAK_EVEN_TRIGGER:
#                 trailing_sl = current_price - TRAILING_STOP_DISTANCE
#                 if trailing_sl > entry_price and trailing_sl > current_sl:
#                     modify_sl(position, trailing_sl, current_tp, reason="Trailing stop")

#         elif position.type == mt5.POSITION_TYPE_SELL:
#             current_price = tick.ask
#             profit_distance = entry_price - current_price

#             if ENABLE_BREAK_EVEN and profit_distance >= BREAK_EVEN_TRIGGER:
#                 breakeven_sl = entry_price
#                 if current_sl == 0 or current_sl > breakeven_sl:
#                     modify_sl(position, breakeven_sl, current_tp, reason="Break-even")

#             if ENABLE_TRAILING_STOP and profit_distance >= BREAK_EVEN_TRIGGER:
#                 trailing_sl = current_price + TRAILING_STOP_DISTANCE
#                 if trailing_sl < entry_price and (current_sl == 0 or trailing_sl < current_sl):
#                     modify_sl(position, trailing_sl, current_tp, reason="Trailing stop")


# def modify_sl(position, new_sl, tp, reason="SL update"):
#     request = {
#         "action": mt5.TRADE_ACTION_SLTP,
#         "position": position.ticket,
#         "sl": round(new_sl, 2),
#         "tp": tp,
#     }

#     result = mt5.order_send(request)

#     if result is None:
#         logger.error(f"[MANAGER] Failed to modify SL: {mt5.last_error()}")
#         return

#     if result.retcode == mt5.TRADE_RETCODE_DONE:
#         logger.info(
#             f"[MANAGER] {reason} applied | "
#             f"ticket={position.ticket} new_sl={round(new_sl, 2)}"
#         )
#     else:
#         logger.error(f"[MANAGER] Failed to modify SL: {result}")


import MetaTrader5 as mt5

from src.logger import logger
from config.settings import (
    ENABLE_BREAK_EVEN,
    BREAK_EVEN_R,
    ENABLE_TRAILING_STOP,
    TRAILING_START_R,
    TRAILING_STOP_R,
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
            initial_risk = entry_price - current_sl
            profit_distance = current_price - entry_price
        else:
            current_price = tick.ask
            initial_risk = current_sl - entry_price
            profit_distance = entry_price - current_price

        if initial_risk <= 0:
            logger.warning(
                f"[MANAGER] Invalid initial risk for position {position.ticket} | "
                f"entry={entry_price} sl={current_sl}"
            )
            continue

        logger.info(
            f"[MANAGER] entry={entry_price} current_price={current_price} "
            f"profit_distance={profit_distance} initial_risk={initial_risk}"
        )

        # Break-even logic
        if ENABLE_BREAK_EVEN and profit_distance >= (initial_risk * BREAK_EVEN_R):
            breakeven_sl = entry_price

            if position.type == mt5.POSITION_TYPE_BUY:
                if current_sl < breakeven_sl:
                    modify_sl(position, breakeven_sl, current_tp, reason="Break-even")

            elif position.type == mt5.POSITION_TYPE_SELL:
                if current_sl > breakeven_sl:
                    modify_sl(position, breakeven_sl, current_tp, reason="Break-even")

        # Trailing stop logic
        if ENABLE_TRAILING_STOP and profit_distance >= (initial_risk * TRAILING_START_R):
            trailing_distance = initial_risk * TRAILING_STOP_R

            if position.type == mt5.POSITION_TYPE_BUY:
                trailing_sl = current_price - trailing_distance
                if trailing_sl > entry_price and trailing_sl > current_sl:
                    modify_sl(position, trailing_sl, current_tp, reason="Trailing stop")

            elif position.type == mt5.POSITION_TYPE_SELL:
                trailing_sl = current_price + trailing_distance
                if trailing_sl < entry_price and trailing_sl < current_sl:
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