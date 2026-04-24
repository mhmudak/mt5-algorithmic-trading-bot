import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL
from src.indicators import calculate_ema, calculate_atr


def get_liquidity_context(timeframe=mt5.TIMEFRAME_M15, bars=120):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) < 50:
        return None

    df = pd.DataFrame(rates)
    df["ema_20"] = calculate_ema(df, 20)
    df["atr_14"] = calculate_atr(df, 14)

    recent = df.iloc[-25:-1]
    last = df.iloc[-1]

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    swept_high = last["high"] > recent_high and last["close"] < recent_high
    swept_low = last["low"] < recent_low and last["close"] > recent_low

    if swept_low:
        bias = "BUY"
        reason = "HTF swept lows and closed back inside"
    elif swept_high:
        bias = "SELL"
        reason = "HTF swept highs and closed back inside"
    else:
        bias = "NEUTRAL"
        reason = "No clear HTF liquidity sweep"

    return {
        "bias": bias,
        "recent_high": round(recent_high, 2),
        "recent_low": round(recent_low, 2),
        "last_high": round(last["high"], 2),
        "last_low": round(last["low"], 2),
        "last_close": round(last["close"], 2),
        "reason": reason,
    }


def liquidity_allows_signal(signal, context, allow_neutral=True):
    if context is None:
        return True

    bias = context.get("bias")

    if bias == "NEUTRAL":
        return allow_neutral

    return signal == bias