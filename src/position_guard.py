import MetaTrader5 as mt5


def has_same_direction_position(symbol: str, signal: str) -> bool:
    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        print(f"[POSITION GUARD] No positions returned for {symbol}")
        return False

    if len(positions) == 0:
        print(f"[POSITION GUARD] No open positions on {symbol}")
        return False

    print(f"[POSITION GUARD] Found {len(positions)} open position(s) on {symbol}")

    for position in positions:
        direction = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
        print(
            f"[POSITION GUARD] ticket={position.ticket} "
            f"direction={direction} volume={position.volume} open_price={position.price_open}"
        )

        if signal == "BUY" and position.type == mt5.POSITION_TYPE_BUY:
            return True

        if signal == "SELL" and position.type == mt5.POSITION_TYPE_SELL:
            return True

    return False