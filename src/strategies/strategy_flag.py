from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 8:
        return None

    # Structure:
    # flag_pole = older impulse
    # pullback candles = small opposite drift
    # entry candle = latest closed candle

    entry = df.iloc[-2]
    pullback_1 = df.iloc[-3]
    pullback_2 = df.iloc[-4]
    pole = df.iloc[-5]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    pole_body = abs(pole["close"] - pole["open"])
    entry_body = abs(entry["close"] - entry["open"])

    # =========================
    # Bullish flag
    # =========================
    bullish_pole = (
        pole["close"] > pole["open"]
        and pole_body > atr * 0.6
    )

    bearish_pullback = (
        pullback_2["close"] < pullback_2["open"]
        and pullback_1["close"] < pullback_1["open"]
    )

    bullish_break = (
        entry["close"] > entry["open"]
        and entry["close"] > pullback_1["high"]
        and price > ema
        and entry_body > atr * 0.25
    )

    if bullish_pole and bearish_pullback and bullish_break:
        reason = (
            f"Bullish flag -> strong pole near {round(pole['close'], 2)} -> "
            f"2-candle pullback -> breakout above {round(pullback_1['high'], 2)} -> "
            f"price above EMA"
        )

        return {
            "signal": "BUY",
            "score": 78,
            "strategy": "FLAG",
            "reason": reason,
        }

    # =========================
    # Bearish flag
    # =========================
    bearish_pole = (
        pole["close"] < pole["open"]
        and pole_body > atr * 0.6
    )

    bullish_pullback = (
        pullback_2["close"] > pullback_2["open"]
        and pullback_1["close"] > pullback_1["open"]
    )

    bearish_break = (
        entry["close"] < entry["open"]
        and entry["close"] < pullback_1["low"]
        and price < ema
        and entry_body > atr * 0.25
    )

    if bearish_pole and bullish_pullback and bearish_break:
        reason = (
            f"Bearish flag -> strong pole near {round(pole['close'], 2)} -> "
            f"2-candle pullback -> breakdown below {round(pullback_1['low'], 2)} -> "
            f"price below EMA"
        )

        return {
            "signal": "SELL",
            "score": 78,
            "strategy": "FLAG",
            "reason": reason,
        }

    return None