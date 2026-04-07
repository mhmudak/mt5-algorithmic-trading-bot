from datetime import datetime
import MetaTrader5 as mt5
from config.settings import MAX_TRADES_PER_DAY


def reached_max_trades_today(symbol: str) -> bool:
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        print("[DAILY GUARD] No tick data")
        return False

    now = datetime.fromtimestamp(tick.time)
    start_of_day = datetime(now.year, now.month, now.day)

    deals = mt5.history_deals_get(start_of_day, now)
    if deals is None:
        print("[DAILY GUARD] No deals returned")
        return False

    count = 0

    for deal in deals:
        if deal.symbol != symbol:
            continue

        if deal.entry == mt5.DEAL_ENTRY_IN:
            count += 1
            print(
                f"[DAILY GUARD] Counted entry deal | "
                f"ticket={deal.ticket} symbol={deal.symbol} entry={deal.entry} volume={deal.volume}"
            )

    print(f"[DAILY GUARD] Total entry deals today for {symbol}: {count}")
    return count >= MAX_TRADES_PER_DAY