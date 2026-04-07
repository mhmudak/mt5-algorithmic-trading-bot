from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from src.execution import check_trade_guard
from src.indicators import calculate_ema, calculate_atr
from src.order_executor import execute_trade
from src.risk import calculate_trade_plan
from src.strategy import generate_signal
from src.logger import logger
from config.settings import FORCE_SIGNAL
from src.position_guard import has_same_direction_position
from src.notifier import send_telegram_message
from src.daily_guard import reached_max_trades_today
from src.cooldown_guard import in_cooldown_period
from src.position_manager import manage_positions

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
    logger.info("🚀 Starting MT5 market data test...")
    send_telegram_message("🚀 MT5 Bot started")

    if not mt5.initialize():
        logger.error("initialize() failed")
        logger.error(f"Error: {mt5.last_error()}")
        return

    logger.info("MT5 initialized successfully")

    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        logger.error(f"Symbol {SYMBOL} not found")
        logger.error(f"Error: {mt5.last_error()}")
        mt5.shutdown()
        return

    logger.info(f"Symbol found: {SYMBOL}")

    if not symbol_info.visible:
        logger.info(f"{SYMBOL} is not visible, trying to enable it...")
        if not mt5.symbol_select(SYMBOL, True):
            logger.error(f"Failed to select {SYMBOL}")
            logger.error(f"Error: {mt5.last_error()}")
            mt5.shutdown()
            return

    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_TO_FETCH)
    if rates is None:
        logger.error("Failed to fetch rates")
        logger.error(f"Error: {mt5.last_error()}")
        mt5.shutdown()
        return

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    signal = generate_signal(df)
    
    

    if FORCE_SIGNAL in ["BUY", "SELL"]:
        logger.warning(f"⚠ FORCE SIGNAL ACTIVE: {FORCE_SIGNAL}")
        signal = FORCE_SIGNAL

    last = df.iloc[-1]
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
    send_telegram_message(f"📊 Signal: {signal}")

    logger.info("Last candles:")
    logger.info(df[["time", "open", "high", "low", "close"]].tail())

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        logger.error("Failed to fetch current tick")
        logger.error(f"Error: {mt5.last_error()}")
        mt5.shutdown()
        return

    account_info = mt5.account_info()
    if account_info is None:
        logger.error("Failed to fetch account info")
        logger.error(f"Error: {mt5.last_error()}")
        mt5.shutdown()
        return

    trade_plan = calculate_trade_plan(
        df=df,
        signal=signal,
        tick=tick,
        account_balance=account_info.balance,
    )

    trade_allowed, guard_reason = check_trade_guard(signal, tick)
    
    if trade_allowed and has_same_direction_position(SYMBOL, signal):
        trade_allowed = False
        guard_reason = f"Same-direction position already exists on {SYMBOL}"
        
    if trade_allowed and reached_max_trades_today(SYMBOL):
        trade_allowed = False
        guard_reason = f"Max trades per day reached for {SYMBOL}"
        
    if trade_allowed and in_cooldown_period(SYMBOL):
        trade_allowed = False
        guard_reason = f"Cooldown active for {SYMBOL}"

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

    if trade_allowed and trade_plan is not None:
        logger.info("🔥 Executing trade...")
        send_telegram_message(
            f"🔥 TRADE EXECUTION\n"
            f"Type: {signal}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"Lot: {trade_plan['lot']}"
        )
        execute_trade(signal, trade_plan, SYMBOL)

    manage_positions(SYMBOL)

    mt5.shutdown()
    logger.info("✅ MT5 data test completed successfully")


if __name__ == "__main__":
    main()