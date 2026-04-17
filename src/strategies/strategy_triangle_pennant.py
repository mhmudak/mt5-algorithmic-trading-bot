from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 18:
        return None

    # We use:
    # - pole around -8
    # - consolidation from -7 to -3
    # - confirmation candle at -2

    pole = df.iloc[-8]
    consolidation = df.iloc[-7:-2]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    pole_body = abs(pole["close"] - pole["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if pole_body < atr * 0.8:
        return None

    highs = consolidation["high"].tolist()
    lows = consolidation["low"].tolist()

    if len(highs) < 4 or len(lows) < 4:
        return None

    # =========================
    # Descending highs / ascending lows = triangle compression
    # =========================
    descending_highs = all(highs[i] >= highs[i + 1] for i in range(len(highs) - 1))
    ascending_lows = all(lows[i] <= lows[i + 1] for i in range(len(lows) - 1))

    triangle_high = max(highs)
    triangle_low = min(lows)
    triangle_height = triangle_high - triangle_low

    if triangle_height <= atr * 0.5:
        return None

    # =========================
    # Bullish pennant / triangle continuation
    # =========================
    bullish_pole = pole["close"] > pole["open"]

    bullish_breakout = (
        entry["close"] > entry["open"]
        and entry["close"] > triangle_high
        and price > ema
        and entry_body > atr * 0.30
    )

    if bullish_pole and descending_highs and ascending_lows and bullish_breakout:
        return {
            "signal": "BUY",
            "score": 88,
            "strategy": "TRIANGLE_PENNANT",
            "pattern_height": triangle_height,
            "triangle_high": triangle_high,
            "triangle_low": triangle_low,
            "reason": (
                f"Bullish triangle/pennant -> strong pole near {round(pole['close'], 2)} -> "
                f"compression range {round(triangle_low, 2)} to {round(triangle_high, 2)} -> "
                f"breakout above {round(triangle_high, 2)} -> price above EMA"
            ),
        }

    # =========================
    # Bearish pennant / triangle continuation
    # =========================
    bearish_pole = pole["close"] < pole["open"]

    bearish_breakout = (
        entry["close"] < entry["open"]
        and entry["close"] < triangle_low
        and price < ema
        and entry_body > atr * 0.30
    )

    if bearish_pole and descending_highs and ascending_lows and bearish_breakout:
        return {
            "signal": "SELL",
            "score": 88,
            "strategy": "TRIANGLE_PENNANT",
            "pattern_height": triangle_height,
            "triangle_high": triangle_high,
            "triangle_low": triangle_low,
            "reason": (
                f"Bearish triangle/pennant -> strong pole near {round(pole['close'], 2)} -> "
                f"compression range {round(triangle_low, 2)} to {round(triangle_high, 2)} -> "
                f"breakdown below {round(triangle_low, 2)} -> price below EMA"
            ),
        }

    return None