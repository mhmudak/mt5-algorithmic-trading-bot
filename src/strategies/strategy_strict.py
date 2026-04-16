from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 6:
        return None

    entry = df.iloc[-2]
    breakout = df.iloc[-3]

    price = entry["close"]
    ema = entry["ema_20"]
    atr = entry["atr_14"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if abs(price - ema) > atr * 1.5:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    breakout_body = abs(breakout["close"] - breakout["open"])

    if breakout_body < atr * 0.5:
        return None

    breakout_up = breakout["close"] > resistance + BREAKOUT_BUFFER
    breakout_down = breakout["close"] < support - BREAKOUT_BUFFER

    bullish = entry["close"] > entry["open"]
    bearish = entry["close"] < entry["open"]

    if price > ema and breakout_up and bullish:
        reason = (
            f"Strict breakout above resistance {round(resistance, 2)} -> "
            f"strong breakout body {round(breakout_body, 2)} -> "
            f"confirmed bullish close near {round(entry['close'], 2)} -> "
            f"price above EMA"
        )

        return {
            "signal": "BUY",
            "score": 90,
            "strategy": "STRICT",
            "reason": reason,
        }

    if price < ema and breakout_down and bearish:
        reason = (
            f"Strict breakout below support {round(support, 2)} -> "
            f"strong breakout body {round(breakout_body, 2)} -> "
            f"confirmed bearish close near {round(entry['close'], 2)} -> "
            f"price below EMA"
        )

        return {
            "signal": "SELL",
            "score": 90,
            "strategy": "STRICT",
            "reason": reason,
        }

    return None