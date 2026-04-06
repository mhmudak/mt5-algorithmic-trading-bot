from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd

from src.indicators import calculate_ema, calculate_atr
from src.strategy import generate_signal
from src.risk import calculate_trade_plan
from src.execution import check_trade_guard
from src.order_executor import execute_trade
from src.logger import logger
from config.settings import (
    SYMBOL,
    TIMEFRAME,
    BARS_TO_FETCH,
    EMA_PERIOD,
    ATR_PERIOD,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def main() -> None:
    print("Starting MT5 market data test...")

    if not mt5.initialize():
        print("initialize() failed")
        print("Error:", mt5.last_error())
        return

    print("MT5 initialized successfully")

    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        print(f"Symbol {SYMBOL} not found")
        print("Error:", mt5.last_error())
        mt5.shutdown()
        return

    print(f"Symbol found: {SYMBOL}")

    if not symbol_info.visible:
        print(f"{SYMBOL} is not visible, trying to enable it...")
        if not mt5.symbol_select(SYMBOL, True):
            print(f"Failed to select {SYMBOL}")
            print("Error:", mt5.last_error())
            mt5.shutdown()
            return

    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_TO_FETCH)
    if rates is None:
        print("Failed to fetch rates")
        print("Error:", mt5.last_error())
        mt5.shutdown()
        return

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    signal = generate_signal(df)

    last = df.iloc[-1]
    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    recent_resistance = recent_data["high"].max()
    recent_support = recent_data["low"].min()

    print("\nSignal context:")
    print(f"Last close: {last['close']}")
    print(f"EMA: {last['ema_20']}")
    print(f"ATR: {last['atr_14']}")
    print(f"Recent resistance: {recent_resistance}")
    print(f"Recent support: {recent_support}")
    print(f"Breakout buffer: {BREAKOUT_BUFFER}")

    print("\nGenerated signal:")
    print(signal)

    print("\nLast candles:")
    print(df[["time", "open", "high", "low", "close", "tick_volume"]].tail())

    print("\nWith indicators:")
    print(df[["time", "close", "ema_20", "atr_14"]].tail())

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        print("Failed to fetch current tick")
        print("Error:", mt5.last_error())
        mt5.shutdown()
        return

    account_info = mt5.account_info()
    if account_info is None:
        print("Failed to fetch account info")
        print("Error:", mt5.last_error())
        mt5.shutdown()
        return

    trade_plan = calculate_trade_plan(
        df=df,
        signal=signal,
        tick=tick,
        account_balance=account_info.balance,
    )

    trade_allowed, guard_reason = check_trade_guard(signal, tick)

    spread = tick.ask - tick.bid

    print("\nCurrent tick:")
    print(f"Bid: {tick.bid}")
    print(f"Ask: {tick.ask}")
    print(f"Spread: {spread}")
    print(f"Time: {datetime.fromtimestamp(tick.time)}")

    print("\nTrade plan:")
    if trade_plan is None:
        print("No trade plan generated (signal is NO_TRADE)")
    else:
        for key, value in trade_plan.items():
            print(f"{key}: {value}")

    print("\nTrade guard:")
    print(f"Allowed: {trade_allowed}")
    print(f"Reason: {guard_reason}")
    if trade_allowed and trade_plan is not None:
        execute_trade(signal, trade_plan, SYMBOL)

    mt5.shutdown()
    print("\nMT5 data test completed successfully")


if __name__ == "__main__":
    main()