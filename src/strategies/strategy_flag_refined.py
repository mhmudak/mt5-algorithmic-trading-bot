from config.settings import (
    ATR_MIN,
    ATR_MAX,
)


def generate_signal(df):
    if len(df) < 10:
        return None

    # Structure
    # - pole candle around -6
    # - 3-candle flag around -5,-4,-3
    # - confirmation candle at -2

    pole = df.iloc[-6]
    f1 = df.iloc[-5]
    f2 = df.iloc[-4]
    f3 = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    pole_body = abs(pole["close"] - pole["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if pole_body < atr * 0.7:
        return None

    # =========================
    # Descending flag -> bullish continuation
    # strong bullish pole, then 3-candle downward drift, then breakout up
    # =========================
    bullish_pole = pole["close"] > pole["open"]

    descending_flag = (
        f1["high"] >= f2["high"] >= f3["high"]
        and f1["low"] >= f2["low"] >= f3["low"]
    )

    flag_high = max(f1["high"], f2["high"], f3["high"])
    flag_low = min(f1["low"], f2["low"], f3["low"])

    bullish_break = (
        entry["close"] > entry["open"]
        and entry["close"] > flag_high
        and price > ema
        and entry_body > atr * 0.25
    )

    if bullish_pole and descending_flag and bullish_break:
        reason = (
            f"Descending flag bullish continuation -> "
            f"strong pole near {round(pole['close'], 2)} -> "
            f"flag range {round(flag_low, 2)} to {round(flag_high, 2)} -> "
            f"breakout above {round(flag_high, 2)} -> "
            f"price above EMA"
        )

        return {
            "signal": "BUY",
            "score": 84,
            "strategy": "FLAG_REFINED",
            "reason": reason,
        }

    # =========================
    # Ascending flag -> bearish continuation
    # strong bearish pole, then 3-candle upward drift, then breakdown
    # =========================
    bearish_pole = pole["close"] < pole["open"]

    ascending_flag = (
        f1["high"] <= f2["high"] <= f3["high"]
        and f1["low"] <= f2["low"] <= f3["low"]
    )

    bearish_break = (
        entry["close"] < entry["open"]
        and entry["close"] < flag_low
        and price < ema
        and entry_body > atr * 0.25
    )

    if bearish_pole and ascending_flag and bearish_break:
        reason = (
            f"Ascending flag bearish continuation -> "
            f"strong pole near {round(pole['close'], 2)} -> "
            f"flag range {round(flag_low, 2)} to {round(flag_high, 2)} -> "
            f"breakdown below {round(flag_low, 2)} -> "
            f"price below EMA"
        )

        return {
            "signal": "SELL",
            "score": 84,
            "strategy": "FLAG_REFINED",
            "reason": reason,
        }

    return None