from datetime import datetime, timedelta
import MetaTrader5 as mt5
from config.settings import COOLDOWN_MINUTES


def in_cooldown_period(symbol: str) -> bool:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print("[COOLDOWN] No tick data")
        return False

    now = datetime.fromtimestamp(tick.time)
    cooldown_start = now - timedelta(minutes=COOLDOWN_MINUTES)

    deals = mt5.history_deals_get(cooldown_start, now)
    if deals is None:
        print("[COOLDOWN] No deals returned")
        return False

    for deal in deals:
        if deal.symbol != symbol:
            continue

        if deal.entry == mt5.DEAL_ENTRY_IN:
            print(
                f"[COOLDOWN] Recent entry found | "
                f"ticket={deal.ticket} symbol={deal.symbol} time={deal.time}"
            )
            return True

    print(f"[COOLDOWN] No recent entry found in last {COOLDOWN_MINUTES} minutes for {symbol}")
    return False