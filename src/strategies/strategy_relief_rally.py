from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 35:
        return None

    # trend leg, relief leg, continuation confirm
    trend_anchor = df.iloc[-8]
    relief_1 = df.iloc[-5]
    relief_2 = df.iloc[-4]
    relief_3 = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    entry_body = abs(entry["close"] - entry["open"])

    # =========================================================
    # Bearish relief rally
    # overall bearish trend, short-term rebound, then continuation down
    # =========================================================
    bearish_trend_context = trend_anchor["close"] < trend_anchor["ema_20"]

    relief_up = (
        relief_1["close"] > relief_1["open"]
        and relief_2["close"] > relief_2["open"]
    )

    stalled_relief = relief_3["high"] <= max(relief_1["high"], relief_2["high"]) + atr * 0.15

    bearish_resume = (
        entry["close"] < entry["open"]
        and entry["close"] < relief_3["low"]
        and price < ema
        and entry_body > atr * 0.25
    )

    if bearish_trend_context and relief_up and stalled_relief and bearish_resume:
        pattern_height = abs(max(relief_1["high"], relief_2["high"], relief_3["high"]) - entry["close"])

        return {
            "signal": "SELL",
            "score": 92,
            "strategy": "RELIEF_RALLY",
            "pattern_height": pattern_height,
            "relief_high": max(relief_1["high"], relief_2["high"], relief_3["high"]),
            "relief_low": min(relief_1["low"], relief_2["low"], relief_3["low"]),
            "sl_reference": max(relief_1["high"], relief_2["high"], relief_3["high"]),
            "reason": (
                f"Relief rally bearish -> temporary rebound stalled near {round(max(relief_1['high'], relief_2['high'], relief_3['high']),2)} -> "
                f"trend resumed down -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish relief drop
    # overall bullish trend, short-term drop, then continuation up
    # =========================================================
    bullish_trend_context = trend_anchor["close"] > trend_anchor["ema_20"]

    relief_down = (
        relief_1["close"] < relief_1["open"]
        and relief_2["close"] < relief_2["open"]
    )

    stalled_drop = relief_3["low"] >= min(relief_1["low"], relief_2["low"]) - atr * 0.15

    bullish_resume = (
        entry["close"] > entry["open"]
        and entry["close"] > relief_3["high"]
        and price > ema
        and entry_body > atr * 0.25
    )

    if bullish_trend_context and relief_down and stalled_drop and bullish_resume:
        pattern_height = abs(entry["close"] - min(relief_1["low"], relief_2["low"], relief_3["low"]))

        return {
            "signal": "BUY",
            "score": 92,
            "strategy": "RELIEF_RALLY",
            "pattern_height": pattern_height,
            "relief_high": max(relief_1["high"], relief_2["high"], relief_3["high"]),
            "relief_low": min(relief_1["low"], relief_2["low"], relief_3["low"]),
            "sl_reference": min(relief_1["low"], relief_2["low"], relief_3["low"]),
            "reason": (
                f"Relief drop bullish -> temporary pullback stalled near {round(min(relief_1['low'], relief_2['low'], relief_3['low']),2)} -> "
                f"trend resumed up -> price above EMA"
            ),
        }

    return None