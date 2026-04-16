from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 3:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = last["close"]
    ema = last["ema_20"]
    atr = last["atr_14"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if abs(price - ema) > atr * 1.2:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    breakout_up = prev["close"] > (resistance + BREAKOUT_BUFFER)
    breakout_down = prev["close"] < (support - BREAKOUT_BUFFER)

    bullish = last["close"] > last["open"]
    bearish = last["close"] < last["open"]

    if price > ema and breakout_up and bullish:
        reason = (
            f"Fast breakout above resistance {round(resistance, 2)} -> "
            f"current bullish continuation near {round(last['close'], 2)} -> "
            f"price above EMA"
        )

        return {
            "signal": "BUY",
            "score": 55,
            "strategy": "FAST",
            "reason": reason,
        }

    if price < ema and breakout_down and bearish:
        reason = (
            f"Fast breakout below support {round(support, 2)} -> "
            f"current bearish continuation near {round(last['close'], 2)} -> "
            f"price below EMA"
        )

        return {
            "signal": "SELL",
            "score": 55,
            "strategy": "FAST",
            "reason": reason,
        }

    return None