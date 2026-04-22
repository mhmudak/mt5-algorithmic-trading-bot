from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 25:
        return None

    # candles
    entry = df.iloc[-2]
    liquidity = df.iloc[-3]
    prev = df.iloc[-4]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    # basic measures
    liquidity_range = liquidity["high"] - liquidity["low"]
    liquidity_body = abs(liquidity["close"] - liquidity["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if liquidity_range <= 0:
        return None

    upper_wick = liquidity["high"] - max(liquidity["open"], liquidity["close"])
    lower_wick = min(liquidity["open"], liquidity["close"]) - liquidity["low"]

    # =========================================================
    # ANTI LATE ENTRY FILTER (CRITICAL)
    # =========================================================
    extension_up = abs(entry["close"] - liquidity["high"])
    extension_down = abs(entry["close"] - liquidity["low"])

    if extension_up > atr * 0.6 or extension_down > atr * 0.6:
        return None

    # =========================================================
    # BREAKOUT STRENGTH FILTER
    # =========================================================
    breakout_up_strength = entry["close"] - liquidity["high"]
    breakout_down_strength = liquidity["low"] - entry["close"]

    # =========================================================
    # SMT-LIKE BEHAVIOR (internal divergence)
    # idea: liquidity taken but structure not strongly continuing
    # =========================================================
    failed_continuation_up = (
        prev["high"] < liquidity["high"]
        and entry["close"] < liquidity["high"] + atr * 0.05
    )

    failed_continuation_down = (
        prev["low"] > liquidity["low"]
        and entry["close"] > liquidity["low"] - atr * 0.05
    )

    # =========================================================
    # BULLISH SETUP
    # =========================================================
    bullish_liquidity = (
        lower_wick > liquidity_body * 1.5
        and liquidity_range > atr * 0.6
    )

    bullish_confirmation = (
        entry["close"] > entry["open"]
        and entry["close"] > liquidity["high"]
        and price > ema
        and entry_body > atr * 0.20
        and breakout_up_strength > atr * 0.1
        and not failed_continuation_up
    )

    if bullish_liquidity and bullish_confirmation:
        risk_height = entry["close"] - liquidity["low"]

        if risk_height > 0:
            return {
                "signal": "BUY",
                "score": 90,
                "strategy": "LIQUIDITY_CANDLE",
                "pattern_height": risk_height,
                "liquidity_high": liquidity["high"],
                "liquidity_low": liquidity["low"],
                "entry_model": "R_BASED",
                "sl_reference": liquidity["low"],
                "reason": (
                    f"Bullish liquidity candle -> strong rejection from {round(liquidity['low'], 2)} -> "
                    f"validated breakout above {round(liquidity['high'], 2)} -> "
                    f"EMA aligned -> breakout strength OK"
                ),
            }

    # =========================================================
    # BEARISH SETUP
    # =========================================================
    bearish_liquidity = (
        upper_wick > liquidity_body * 1.5
        and liquidity_range > atr * 0.6
    )

    bearish_confirmation = (
        entry["close"] < entry["open"]
        and entry["close"] < liquidity["low"]
        and price < ema
        and entry_body > atr * 0.20
        and breakout_down_strength > atr * 0.1
        and not failed_continuation_down
    )

    if bearish_liquidity and bearish_confirmation:
        risk_height = liquidity["high"] - entry["close"]

        if risk_height > 0:
            return {
                "signal": "SELL",
                "score": 90,
                "strategy": "LIQUIDITY_CANDLE",
                "pattern_height": risk_height,
                "liquidity_high": liquidity["high"],
                "liquidity_low": liquidity["low"],
                "entry_model": "R_BASED",
                "sl_reference": liquidity["high"],
                "reason": (
                    f"Bearish liquidity candle -> strong rejection from {round(liquidity['high'], 2)} -> "
                    f"validated breakout below {round(liquidity['low'], 2)} -> "
                    f"EMA aligned -> breakout strength OK"
                ),
            }

    return None