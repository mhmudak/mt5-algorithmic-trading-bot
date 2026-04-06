from config.settings import MAX_ALLOWED_SPREAD, ALLOW_LIVE_TRADING


def check_trade_guard(signal, tick):
    if signal not in ["BUY", "SELL"]:
        return False, "Signal is not tradable"

    spread = tick.ask - tick.bid
    if spread > MAX_ALLOWED_SPREAD:
        return False, f"Spread too high: {spread:.2f}"

    if not ALLOW_LIVE_TRADING:
        return False, "Live trading is disabled in settings"

    return True, "Trade allowed"