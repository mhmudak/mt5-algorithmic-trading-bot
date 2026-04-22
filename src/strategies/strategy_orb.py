from config.settings import ATR_MIN, ATR_MAX


ORB_WINDOW = 15  # 15 candles = approx 15 min if M1


def generate_signal(df):
    if len(df) < ORB_WINDOW + 5:
        return None

    data = df.iloc[-(ORB_WINDOW + 5):-2]

    orb_high = data["high"].max()
    orb_low = data["low"].min()

    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])

    # =========================
    # BUY breakout
    # =========================
    bullish_break = entry["close"] > orb_high

    bullish_momentum = (
        entry["close"] > entry["open"]
        and body > atr * 0.3
        and price > ema
    )

    if bullish_break and bullish_momentum:
        range_size = orb_high - orb_low

        return {
            "signal": "BUY",
            "score": 90,
            "strategy": "ORB",
            "pattern_height": range_size,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "reason": (
                f"ORB breakout BUY -> range {round(orb_low,2)} to {round(orb_high,2)} -> "
                f"strong close above range -> price above EMA"
            ),
        }

    # =========================
    # SELL breakout
    # =========================
    bearish_break = entry["close"] < orb_low

    bearish_momentum = (
        entry["close"] < entry["open"]
        and body > atr * 0.3
        and price < ema
    )

    if bearish_break and bearish_momentum:
        range_size = orb_high - orb_low

        return {
            "signal": "SELL",
            "score": 90,
            "strategy": "ORB",
            "pattern_height": range_size,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "reason": (
                f"ORB breakout SELL -> range {round(orb_low,2)} to {round(orb_high,2)} -> "
                f"strong close below range -> price below EMA"
            ),
        }

    return None