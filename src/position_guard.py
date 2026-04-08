import MetaTrader5 as mt5

from src.logger import logger


def count_same_direction_positions(symbol: str, signal: str) -> int:
    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        logger.info(f"[POSITION GUARD] No positions returned for {symbol}")
        return 0

    if len(positions) == 0:
        logger.info(f"[POSITION GUARD] No open positions on {symbol}")
        return 0

    count = 0

    for position in positions:
        direction = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"

        logger.info(
            f"[POSITION GUARD] ticket={position.ticket} "
            f"direction={direction} volume={position.volume} open_price={position.price_open}"
        )

        if direction == signal:
            count += 1

    logger.info(
        f"[POSITION GUARD] Same-direction count for {signal} on {symbol}: {count}"
    )
    return count


def has_same_direction_position(symbol: str, signal: str) -> bool:
    return count_same_direction_positions(symbol, signal) > 0