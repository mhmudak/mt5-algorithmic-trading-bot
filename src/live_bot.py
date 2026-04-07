import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from src.execution import check_trade_guard
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger
from src.notifier import send_telegram_message
from src.order_executor import execute_trade
from src.position_manager import manage_positions
from src.risk import calculate_trade_plan
from src.strategy import generate_signal
from src.trade_tracker import update_trade_lifecycle

from config.settings import (
    SYMBOL,
    TIMEFRAME,
    BARS_TO_FETCH,
    EMA_PERIOD,
    ATR_PERIOD,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
    FORCE_SIGNAL,
)


def fetch_market_data():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_TO_FETCH)
    if rates is None:
        logger.error(f"Failed to fetch rates: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)
    return df


def process_cycle(last_processed_candle_time):
    df = fetch_market_data()
    if df is None:
        return last_processed_candle_time

    last = df.iloc[-1]
    current_candle_time = last["time"]

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        logger.error(f"Failed to fetch current tick: {mt5.last_error()}")
        return last_processed_candle_time

    account_info = mt5.account_info()
    if account_info is None:
        logger.error(f"Failed to fetch account info: {mt5.last_error()}")
        return last_processed_candle_time

    # Always manage existing positions and update lifecycle every cycle
    manage_positions(SYMBOL)
    update_trade_lifecycle(SYMBOL)

    # Only evaluate new entries once per new candle
    if (
        last_processed_candle_time is not None
        and current_candle_time == last_processed_candle_time
    ):
        logger.info(f"No new candle yet. Current candle: {current_candle_time}")
        return last_processed_candle_time

    logger.info(f"New candle detected: {current_candle_time}")

    signal = generate_signal(df)

    if FORCE_SIGNAL in ["BUY", "SELL"]:
        logger.warning(f"⚠ FORCE SIGNAL ACTIVE: {FORCE_SIGNAL}")
        signal = FORCE_SIGNAL

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1): -1]
    recent_resistance = recent_data["high"].max()
    recent_support = recent_data["low"].min()

    logger.info("Signal context:")
    logger.info(f"Last close: {last['close']}")
    logger.info(f"EMA: {last['ema_20']}")
    logger.info(f"ATR: {last['atr_14']}")
    logger.info(f"Resistance: {recent_resistance}")
    logger.info(f"Support: {recent_support}")
    logger.info(f"Buffer: {BREAKOUT_BUFFER}")
    logger.info(f"Generated signal: {signal}")

    trade_plan = calculate_trade_plan(
        df=df,
        signal=signal,
        tick=tick,
        account_balance=account_info.balance,
    )

    trade_allowed, guard_reason = check_trade_guard(signal, tick)

    spread = tick.ask - tick.bid
    logger.info("Current tick:")
    logger.info(f"Bid: {tick.bid}")
    logger.info(f"Ask: {tick.ask}")
    logger.info(f"Spread: {spread}")
    logger.info(f"Time: {datetime.fromtimestamp(tick.time)}")

    if trade_plan is None:
        logger.info("No trade plan generated (NO_TRADE)")
    else:
        logger.info("Trade plan:")
        for key, value in trade_plan.items():
            logger.info(f"{key}: {value}")

    logger.info(f"Trade allowed: {trade_allowed}")
    logger.info(f"Guard reason: {guard_reason}")

    if not trade_allowed:
        send_telegram_message(
            f"⛔ Trade Blocked\n"
            f"Symbol: {SYMBOL}\n"
            f"Signal: {signal}\n"
            f"Reason: {guard_reason}"
        )
        return current_candle_time

    if trade_plan is not None:
        logger.info("🔥 Executing trade...")
        execute_trade(signal, trade_plan, SYMBOL)

    return current_candle_time


def main():
    logger.info("🚀 Starting live bot loop...")
    send_telegram_message(f"🚀 Live bot started on {SYMBOL}")

    if not mt5.initialize():
        logger.error(f"initialize() failed: {mt5.last_error()}")
        return

    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        logger.error(f"Symbol {SYMBOL} not found")
        mt5.shutdown()
        return

    if not symbol_info.visible:
        logger.info(f"{SYMBOL} is not visible, trying to enable it...")
        if not mt5.symbol_select(SYMBOL, True):
            logger.error(f"Failed to select {SYMBOL}: {mt5.last_error()}")
            mt5.shutdown()
            return

    last_processed_candle_time = None

    try:
        while True:
            try:
                last_processed_candle_time = process_cycle(last_processed_candle_time)
            except Exception as e:
                logger.exception(f"Loop cycle failed: {e}")
                send_telegram_message(f"❌ Loop cycle failed: {e}")

            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped manually by user")

    finally:
        mt5.shutdown()
        logger.info("MT5 shutdown completed")


if __name__ == "__main__":
    main()