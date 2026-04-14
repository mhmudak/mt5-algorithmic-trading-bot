import MetaTrader5 as mt5


def close_all_positions(symbol):
    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        return

    for pos in positions:
        ticket = pos.ticket
        volume = pos.volume
        symbol = pos.symbol

        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY

        price = (
            mt5.symbol_info_tick(symbol).bid
            if pos.type == 0
            else mt5.symbol_info_tick(symbol).ask
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "EMERGENCY_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        mt5.order_send(request)