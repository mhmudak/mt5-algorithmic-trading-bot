import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL
from src.indicators import calculate_ema, calculate_atr


def get_htf_context(timeframe=mt5.TIMEFRAME_M15, bars=120):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) < 50:
        return None

    df = pd.DataFrame(rates)
    df["ema_20"] = calculate_ema(df, 20)
    df["atr_14"] = calculate_atr(df, 14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = last["close"]
    ema = last["ema_20"]

    if price > ema and last["ema_20"] >= prev["ema_20"]:
        bias = "BUY"
    elif price < ema and last["ema_20"] <= prev["ema_20"]:
        bias = "SELL"
    else:
        bias = "NEUTRAL"

    return {
        "bias": bias,
        "price": round(price, 2),
        "ema": round(ema, 2),
        "atr": round(last["atr_14"], 2),
    }


def htf_allows_signal(signal, htf_context, allow_neutral=True):
    if htf_context is None:
        return True

    bias = htf_context.get("bias")

    if bias == "NEUTRAL":
        return allow_neutral

    return signal == bias