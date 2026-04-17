import MetaTrader5 as mt5
import pandas as pd

from src.indicators import calculate_ema
from src.logger import logger
from config.settings import SYMBOL, MTF_TIMEFRAME, MTF_BARS_TO_FETCH, EMA_PERIOD


def get_mtf_bias():
    rates = mt5.copy_rates_from_pos(SYMBOL, MTF_TIMEFRAME, 0, MTF_BARS_TO_FETCH)
    if rates is None:
        logger.error(f"[MTF] Failed to fetch MTF rates: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    if df.empty:
        return None

    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)

    last_closed = df.iloc[-2]
    close = last_closed["close"]
    ema = last_closed["ema_20"]

    if close > ema:
        return "BUY"
    elif close < ema:
        return "SELL"
    return None