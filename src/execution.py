from config.settings import MAX_ALLOWED_SPREAD, ALLOW_LIVE_TRADING
from config.settings import EXECUTION_MODE
from config.settings import MAX_SPREAD

def check_trade_guard(signal, tick):
    if signal not in ["BUY", "SELL"]:
        return False, "Signal is not tradable"

    spread = tick.ask - tick.bid
    if spread > MAX_ALLOWED_SPREAD:
        return False, f"Spread too high: {spread:.2f}"

    if EXECUTION_MODE == "LIVE" and not ALLOW_LIVE_TRADING:
        return False, "Live trading is disabled in settings"
    
    if spread > MAX_SPREAD:
        return False, f"Spread too high: {spread}"

    return True, "Trade allowed"