import MetaTrader5 as mt5
from config.settings import SYMBOL, MAX_DRAWDOWN_USD


def get_total_floating_pnl(symbol):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return 0.0

    total = 0.0
    for pos in positions:
        total += pos.profit

    return total


def is_drawdown_exceeded(symbol):
    total_pnl = get_total_floating_pnl(symbol)

    # drawdown = negative pnl
    if total_pnl <= -MAX_DRAWDOWN_USD:
        return True, total_pnl

    return False, total_pnl