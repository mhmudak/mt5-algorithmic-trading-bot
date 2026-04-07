import MetaTrader5 as mt5


def manage_positions(symbol: str):
    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        print("[MANAGER] No positions")
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print("[MANAGER] No tick data")
        return

    for position in positions:
        print(f"[MANAGER] Checking position {position.ticket}")

        entry = position.price_open
        sl = position.sl

        if position.type == mt5.POSITION_TYPE_BUY:
            price_current = tick.bid
        else:
            price_current = tick.ask

        # Example: move to breakeven after small profit
        profit_distance = abs(price_current - entry)

        if profit_distance > 5:  # adjust later
            new_sl = entry

            if position.type == mt5.POSITION_TYPE_BUY:
                if sl < new_sl:
                    modify_sl(position, new_sl)

            elif position.type == mt5.POSITION_TYPE_SELL:
                if sl == 0 or sl > new_sl:
                    modify_sl(position, new_sl)


def modify_sl(position, new_sl):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position.ticket,
        "sl": new_sl,
        "tp": position.tp,
    }

    result = mt5.order_send(request)

    if result is None:
        print(f"[MANAGER] Failed to modify SL: {mt5.last_error()}")
        return

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[MANAGER] SL moved to BE for {position.ticket}")
    else:
        print(f"[MANAGER] Failed to modify SL: {result}")