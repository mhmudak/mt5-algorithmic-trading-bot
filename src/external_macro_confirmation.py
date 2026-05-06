import MetaTrader5 as mt5
import pandas as pd

from config.settings import (
    EMA_PERIOD,
    ATR_PERIOD,
    TIMEFRAME,
    ENABLE_EXTERNAL_MACRO_CONFIRMATION,
    EXTERNAL_MACRO_CONFIRMATIONS,
)
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger


MACRO_BARS = 120


def _fetch_symbol_df(symbol: str):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, MACRO_BARS)

    if rates is None or len(rates) < 50:
        logger.info(f"[MACRO CONFIRMATION] Symbol unavailable or insufficient data: {symbol}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _detect_symbol_bias(df):
    """
    Returns BUY if symbol is bullish, SELL if bearish, otherwise NEUTRAL.
    Uses closed candles only.
    """
    if df is None or len(df) < 10:
        return "NEUTRAL"

    last = df.iloc[-2]
    prev = df.iloc[-5]

    close = last["close"]
    ema = last["ema_20"]
    ema_slope = last["ema_20"] - prev["ema_20"]

    if close > ema and ema_slope > 0:
        return "BUY"

    if close < ema and ema_slope < 0:
        return "SELL"

    return "NEUTRAL"


def apply_external_macro_confirmation(signal_data):
    """
    Soft external confirmation layer for XAUUSD.

    It adjusts score only.
    It does not block trades by itself.
    """

    if not ENABLE_EXTERNAL_MACRO_CONFIRMATION:
        return 0, []

    if not signal_data:
        return 0, []

    xau_signal = signal_data.get("signal")
    strategy = signal_data.get("strategy")

    if xau_signal not in ["BUY", "SELL"]:
        return 0, []

    score_adjustment = 0
    reasons = []

    for item in EXTERNAL_MACRO_CONFIRMATIONS:
        symbol = item.get("symbol")
        mode = item.get("mode", "INVERSE")
        weight = item.get("weight", 1)

        if not symbol:
            continue

        df = _fetch_symbol_df(symbol)
        symbol_bias = _detect_symbol_bias(df)

        if symbol_bias == "NEUTRAL":
            continue

        # For inverse confirmations:
        # XAU BUY likes DXY/USDJPY SELL.
        # XAU SELL likes DXY/USDJPY BUY.
        if mode == "INVERSE":
            confirms = (
                (xau_signal == "BUY" and symbol_bias == "SELL")
                or (xau_signal == "SELL" and symbol_bias == "BUY")
            )

            conflicts = (
                (xau_signal == "BUY" and symbol_bias == "BUY")
                or (xau_signal == "SELL" and symbol_bias == "SELL")
            )

            if confirms:
                score_adjustment += weight
                reasons.append(f"{symbol.lower()}_inverse_confirms_{symbol_bias.lower()}")

            elif conflicts:
                score_adjustment -= weight
                reasons.append(f"{symbol.lower()}_inverse_conflict_{symbol_bias.lower()}")

        logger.info(
            f"[MACRO CONFIRMATION] strategy={strategy} "
            f"xau_signal={xau_signal} symbol={symbol} "
            f"symbol_bias={symbol_bias} adjustment={score_adjustment}"
        )

    return score_adjustment, reasons