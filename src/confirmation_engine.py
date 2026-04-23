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
        bullish_close = candle["close"] > candle["open"]
        strong_close = candle["close"] >= candle["low"] + candle_range * 0.6
        rejection = lower_wick > body * 1.2
        body_ok = body > atr * 0.15
        return bullish_close and strong_close and rejection and body_ok

    if signal == "SELL":
        bearish_close = candle["close"] < candle["open"]
        strong_close = candle["close"] <= candle["high"] - candle_range * 0.6
        rejection = upper_wick > body * 1.2
        body_ok = body > atr * 0.15
        return bearish_close and strong_close and rejection and body_ok

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
        broke = candle["close"] > level
        held = candle["low"] >= level - atr * 0.10
        strong_close = candle["close"] >= candle["low"] + candle_range * 0.7
        body_ok = body > atr * 0.20
        return broke and held and strong_close and body_ok

    if signal == "SELL":
        broke = candle["close"] < level
        held = candle["high"] <= level + atr * 0.10
        strong_close = candle["close"] <= candle["high"] - candle_range * 0.7
        body_ok = body > atr * 0.20
        return broke and held and strong_close and body_ok

    return False