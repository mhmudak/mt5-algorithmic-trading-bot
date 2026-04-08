from src.position_guard import count_same_direction_positions
from src.daily_guard import reached_max_trades_today
from src.cooldown_guard import in_cooldown_period
from config.settings import (
    SYMBOL,
    MAX_SPREAD,
    EXECUTION_MODE,
    ALLOW_LIVE_TRADING,
    ALLOW_SAME_DIRECTION_ENTRIES,
    MAX_SAME_DIRECTION_TRADES,
)


def check_trade_guard(signal, tick):
    if signal not in ["BUY", "SELL"]:
        return False, "Signal is not tradable"

    spread = tick.ask - tick.bid
    if spread > MAX_SPREAD:
        return False, f"Spread too high: {spread}"

    if EXECUTION_MODE == "LIVE" and not ALLOW_LIVE_TRADING:
        return False, "Live trading is disabled in settings"

    same_direction_count = count_same_direction_positions(SYMBOL, signal)

    if ALLOW_SAME_DIRECTION_ENTRIES:
        if same_direction_count >= MAX_SAME_DIRECTION_TRADES:
            return (
                False,
                f"Max same-direction open trades reached on {SYMBOL}: {same_direction_count}/{MAX_SAME_DIRECTION_TRADES}",
            )
    else:
        if same_direction_count >= 1:
            return False, f"Same-direction position already exists on {SYMBOL}"

    if reached_max_trades_today(SYMBOL):
        return False, f"Max trades per day reached for {SYMBOL}"

    if in_cooldown_period(SYMBOL):
        return False, f"Cooldown active for {SYMBOL}"

    return True, "Trade allowed"