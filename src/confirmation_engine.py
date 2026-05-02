def confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
    if len(df) < 3:
        return False

    candle = df.iloc[-2]

    body = abs(candle["close"] - candle["open"])
    candle_range = candle["high"] - candle["low"]

    if candle_range <= 0:
        return False

    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]

    touched_zone = candle["high"] >= zone_low and candle["low"] <= zone_high

    if not touched_zone:
        return False

    if signal == "BUY":
        return (
            candle["close"] > candle["open"]
            and lower_wick > body * 1.2
            and candle["close"] >= candle["low"] + candle_range * 0.6
            and body > atr * 0.15
        )

    if signal == "SELL":
        return (
            candle["close"] < candle["open"]
            and upper_wick > body * 1.2
            and candle["close"] <= candle["high"] - candle_range * 0.6
            and body > atr * 0.15
        )

    return False


def confirm_breakout_hold(df, signal, level, atr):
    if len(df) < 3:
        return False

    candle = df.iloc[-2]

    body = abs(candle["close"] - candle["open"])
    candle_range = candle["high"] - candle["low"]

    if candle_range <= 0:
        return False

    if signal == "BUY":
        return (
            candle["close"] > level
            and candle["low"] >= level - atr * 0.10
            and candle["close"] >= candle["low"] + candle_range * 0.7
            and body > atr * 0.20
        )

    if signal == "SELL":
        return (
            candle["close"] < level
            and candle["high"] <= level + atr * 0.10
            and candle["close"] <= candle["high"] - candle_range * 0.7
            and body > atr * 0.20
        )

    return False

def confirm_entry(df, signal):
    """
    Generic confirmation for strategies that do not already have
    strategy-specific execution confirmation.

    Uses closed candles only:
    - last = last closed candle
    - prev = candle before it
    """

    try:
        if len(df) < 4:
            return False

        last = df.iloc[-2]
        prev = df.iloc[-3]

        if signal == "BUY":
            return last["close"] > prev["high"]

        if signal == "SELL":
            return last["close"] < prev["low"]

        return False

    except Exception:
        return False