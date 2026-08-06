import MetaTrader5 as mt5

from src.logger import logger
from src.prop_firm_news_guard import (
    evaluate_runtime_prop_firm_news_action,
)


def _close_result(
    *,
    all_closed=False,
    blocked=False,
    reason,
    position_count=0,
    closed_count=0,
    failed_count=0,
    orders_sent=0,
    snapshot=None,
):
    return {
        "all_closed": bool(all_closed),
        "blocked": bool(blocked),
        "reason": reason,
        "position_count": int(position_count),
        "closed_count": int(closed_count),
        "failed_count": int(failed_count),
        "orders_sent": int(orders_sent),
        "snapshot": snapshot or {},
    }


def close_all_positions(symbol):
    """
    Close all positions for a symbol.

    During an active prop-firm restricted-news window, no market
    close request is submitted. The caller must remain active and
    retry after the restriction ends.
    """
    news_decision = evaluate_runtime_prop_firm_news_action(
        action="FULL_CLOSE_POSITION",
    )

    if not news_decision.get("allowed", False):
        logger.critical(
            "[PROP FIRM NEWS EMERGENCY GUARD] "
            f"emergency market close blocked | "
            f"symbol={symbol} "
            f"reason={news_decision.get('reason')} "
            f"snapshot={news_decision.get('snapshot')} "
            f"orders_sent=0"
        )

        return _close_result(
            all_closed=False,
            blocked=True,
            reason=news_decision.get(
                "reason",
                "prop_firm_emergency_close_blocked",
            ),
            orders_sent=0,
            snapshot=news_decision.get("snapshot"),
        )

    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        logger.error(
            "[EMERGENCY CLOSE] positions_get failed | "
            f"symbol={symbol} error={mt5.last_error()}"
        )

        return _close_result(
            reason="positions_get_failed",
        )

    positions = list(positions)
    position_count = len(positions)

    if position_count == 0:
        logger.info(
            f"[EMERGENCY CLOSE] No open positions on {symbol}"
        )

        return _close_result(
            all_closed=True,
            reason="no_open_positions",
        )

    closed_count = 0
    failed_count = 0
    orders_sent = 0

    for position in positions:
        position_symbol = position.symbol
        tick = mt5.symbol_info_tick(position_symbol)

        if tick is None:
            failed_count += 1

            logger.error(
                "[EMERGENCY CLOSE] Missing tick | "
                f"ticket={position.ticket} "
                f"symbol={position_symbol}"
            )
            continue

        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position_symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "EMERGENCY_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        orders_sent += 1

        if (
            result is not None
            and result.retcode == mt5.TRADE_RETCODE_DONE
        ):
            closed_count += 1

            logger.warning(
                "[EMERGENCY CLOSE] Position closed | "
                f"ticket={position.ticket} "
                f"symbol={position_symbol} "
                f"volume={position.volume}"
            )
        else:
            failed_count += 1

            logger.error(
                "[EMERGENCY CLOSE] Position close failed | "
                f"ticket={position.ticket} "
                f"symbol={position_symbol} "
                f"result={result} "
                f"error={mt5.last_error()}"
            )

    all_closed = (
        position_count > 0
        and closed_count == position_count
        and failed_count == 0
    )

    return _close_result(
        all_closed=all_closed,
        blocked=False,
        reason=(
            "emergency_close_complete"
            if all_closed
            else "emergency_close_incomplete"
        ),
        position_count=position_count,
        closed_count=closed_count,
        failed_count=failed_count,
        orders_sent=orders_sent,
    )
