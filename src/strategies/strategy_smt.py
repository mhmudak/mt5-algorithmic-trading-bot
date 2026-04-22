from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 40:
        return None

    data = df.iloc[-40:].reset_index(drop=True)

    atr = data.iloc[-2]["atr_14"]
    ema = data.iloc[-2]["ema_20"]
    price = data.iloc[-2]["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    # =========================
    # Find recent highs/lows
    # =========================
    highs = data["high"]
    lows = data["low"]

    recent_high_1 = highs.iloc[-10:-5].max()
    recent_high_2 = highs.iloc[-5:].max()

    recent_low_1 = lows.iloc[-10:-5].min()
    recent_low_2 = lows.iloc[-5:].min()

    entry = data.iloc[-2]
    body = abs(entry["close"] - entry["open"])

    # =========================================================
    # Bearish SMT (fake breakout up)
    # Higher high BUT weak continuation
    # =========================================================
    higher_high = recent_high_2 > recent_high_1

    weak_close = entry["close"] < recent_high_2 - atr * 0.2

    rejection = entry["high"] >= recent_high_2 and entry["close"] < entry["open"]

    if higher_high and weak_close and rejection and price < ema and body > atr * 0.2:
        return {
            "signal": "SELL",
            "score": 91,
            "strategy": "SMT",
            "pattern_height": abs(recent_high_2 - recent_low_2),
            "reason": (
                f"SMT bearish divergence -> higher high {round(recent_high_2,2)} not sustained -> "
                f"rejection confirmed -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish SMT (fake breakout down)
    # Lower low BUT weak continuation
    # =========================================================
    lower_low = recent_low_2 < recent_low_1

    weak_close = entry["close"] > recent_low_2 + atr * 0.2

    rejection = entry["low"] <= recent_low_2 and entry["close"] > entry["open"]

    if lower_low and weak_close and rejection and price > ema and body > atr * 0.2:
        return {
            "signal": "BUY",
            "score": 91,
            "strategy": "SMT",
            "pattern_height": abs(recent_high_2 - recent_low_2),
            "reason": (
                f"SMT bullish divergence -> lower low {round(recent_low_2,2)} not sustained -> "
                f"rejection confirmed -> price above EMA"
            ),
        }

    return None