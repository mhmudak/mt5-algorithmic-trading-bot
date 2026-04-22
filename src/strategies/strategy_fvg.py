from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 25:
        return None

    # candles
    c1 = df.iloc[-4]  # origin
    c2 = df.iloc[-3]  # displacement
    c3 = df.iloc[-2]  # entry candle

    atr = c3["atr_14"]
    ema = c3["ema_20"]
    price = c3["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body_c2 = abs(c2["close"] - c2["open"])
    body_c3 = abs(c3["close"] - c3["open"])

    # =========================================================
    # BULLISH FVG
    # =========================================================
    bullish_gap_exists = c1["high"] < c3["low"]
    fvg_top = c3["low"]
    fvg_bottom = c1["high"]
    gap_size = fvg_top - fvg_bottom

    bullish_displacement = (
        c2["close"] > c2["open"]
        and body_c2 > atr * 0.35
    )

    bullish_context = price > ema

    # 🔧 CRITICAL FIX — must retrace INTO FVG (not breakout)
    in_fvg_zone = (
        c3["low"] <= fvg_top and
        c3["high"] >= fvg_bottom
    )

    # 🔧 reaction confirmation (touch + reject)
    reaction = (
        c3["low"] <= fvg_top and
        c3["close"] > c3["open"]
        and body_c3 > atr * 0.2
    )

    # 🔧 anti-late entry
    extension = abs(c3["close"] - fvg_top)
    if extension > atr * 0.5:
        return None

    # 🔧 avoid weak breakout traps
    weak_structure = c3["close"] < fvg_top - atr * 0.05

    if (
        bullish_gap_exists
        and gap_size > atr * 0.15
        and bullish_displacement
        and bullish_context
        and in_fvg_zone
        and reaction
        and not weak_structure
    ):
        return {
            "signal": "BUY",
            "score": 90,
            "strategy": "FVG",
            "pattern_height": gap_size,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "sl_reference": fvg_bottom,  # 🔥 correct SL anchor
            "reason": (
                f"Bullish FVG -> retrace into gap {round(fvg_bottom,2)}-{round(fvg_top,2)} -> "
                f"reaction confirmed -> EMA aligned"
            ),
        }

    # =========================================================
    # BEARISH FVG
    # =========================================================
    bearish_gap_exists = c1["low"] > c3["high"]
    fvg_top = c1["low"]
    fvg_bottom = c3["high"]
    gap_size = fvg_top - fvg_bottom

    bearish_displacement = (
        c2["close"] < c2["open"]
        and body_c2 > atr * 0.35
    )

    bearish_context = price < ema

    in_fvg_zone = (
        c3["high"] >= fvg_bottom and
        c3["low"] <= fvg_top
    )

    reaction = (
        c3["high"] >= fvg_bottom and
        c3["close"] < c3["open"]
        and body_c3 > atr * 0.2
    )

    extension = abs(c3["close"] - fvg_bottom)
    if extension > atr * 0.5:
        return None

    weak_structure = c3["close"] > fvg_bottom + atr * 0.05

    if (
        bearish_gap_exists
        and gap_size > atr * 0.15
        and bearish_displacement
        and bearish_context
        and in_fvg_zone
        and reaction
        and not weak_structure
    ):
        return {
            "signal": "SELL",
            "score": 90,
            "strategy": "FVG",
            "pattern_height": gap_size,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "sl_reference": fvg_top,  # 🔥 correct SL anchor
            "reason": (
                f"Bearish FVG -> retrace into gap {round(fvg_bottom,2)}-{round(fvg_top,2)} -> "
                f"reaction confirmed -> EMA aligned"
            ),
        }

    return None