import MetaTrader5 as mt5


def get_execution_price(signal, tick):
    if tick is None:
        return None

    if signal == "BUY":
        return float(tick.ask)

    if signal == "SELL":
        return float(tick.bid)

    return None


def get_current_execution_price(symbol, signal):
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return None

    return get_execution_price(signal, tick)