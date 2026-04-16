from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 5:
        return None

    entry = df.iloc[-2]
    breakout = df.iloc[-3]

    price = entry["close"]
    ema = entry["ema_20"]
    atr = entry["atr_14"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if abs(price - ema) > atr * 1.8:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    breakout_up = breakout["close"] > resistance + BREAKOUT_BUFFER
    breakout_down = breakout["close"] < support - BREAKOUT_BUFFER

    bullish = entry["close"] > entry["open"]
    bearish = entry["close"] < entry["open"]

    if price > ema and breakout_up and bullish:
        reason = (
            f"Breakout above resistance {round(resistance, 2)} -> "
            f"retest near {round(entry['low'], 2)} -> "
            f"bullish confirmation -> "
            f"price above EMA"
        )

        return {
            "signal": "BUY",
            "score": 75,
            "strategy": "SNIPER_V2",
            "reason": reason,
        }

    if price < ema and breakout_down and bearish:
        reason = (
            f"Breakout below support {round(support, 2)} -> "
            f"retest near {round(entry['high'], 2)} -> "
            f"bearish confirmation -> "
            f"price below EMA"
        )
    
        return {
            "signal": "SELL",
            "score": 75,
            "strategy": "SNIPER_V2",
            "reason": reason,
        }

    return None