import MetaTrader5 as mt5

from src.logger import logger
from src.trade_tracker import load_trades


def manage_manual_trailing_positions(symbol: str, start_price: float, trail_distance: float):
    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        logger.info("[MANUAL TRAIL] No positions returned")
        return

    if len(positions) == 0:
        logger.info(f"[MANUAL TRAIL] No open positions on {symbol}")
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error("[MANUAL TRAIL] No tick data")
        return

    trades = load_trades()
    if not trades:
        logger.info("[MANUAL TRAIL] No tracked trades found")
        return

    for position in positions:
        position_id = str(position.ticket)
        trade = trades.get(position_id)

        if trade is None:
            continue

        if not trade.get("imported_manually", False):
            continue

        entry_price = position.price_open
        current_sl = position.sl
        current_tp = position.tp

        if position.type == mt5.POSITION_TYPE_BUY:
            current_price = tick.bid
            profit_distance = current_price - entry_price

            if profit_distance < start_price:
                continue

            new_sl = current_price - trail_distance

            # never trail below entry after trigger
            if new_sl < entry_price:
                new_sl = entry_price

            if current_sl == 0 or new_sl > current_sl:
                modify_sl(position, new_sl, current_tp, reason="Manual trailing BUY")

        else:
            current_price = tick.ask
            profit_distance = entry_price - current_price

            if profit_distance < start_price:
                continue

            new_sl = current_price + trail_distance

            # never trail above entry after trigger
            if new_sl > entry_price:
                new_sl = entry_price

            if current_sl == 0 or new_sl < current_sl:
                modify_sl(position, new_sl, current_tp, reason="Manual trailing SELL")


def modify_sl(position, new_sl, tp, reason="SL update"):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position.ticket,
        "sl": round(new_sl, 2),
        "tp": tp,
    }

    result = mt5.order_send(request)

    if result is None:
        logger.error(f"[MANUAL TRAIL] Failed to modify SL: {mt5.last_error()}")
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(
            f"[MANUAL TRAIL] {reason} applied | "
            f"ticket={position.ticket} new_sl={round(new_sl, 2)}"
        )
        return True

    logger.error(f"[MANUAL TRAIL] Failed to modify SL: {result}")
    return False