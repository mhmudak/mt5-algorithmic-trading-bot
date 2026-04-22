from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 35:
        return None

    trap = df.iloc[-3]
    confirm = df.iloc[-2]

    atr = confirm["atr_14"]
    ema = confirm["ema_20"]
    price = confirm["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    recent = df.iloc[-18:-3]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    trap_body = abs(trap["close"] - trap["open"])
    trap_range = trap["high"] - trap["low"]
    confirm_body = abs(confirm["close"] - confirm["open"])

    if trap_range <= 0:
        return None

    upper_wick = trap["high"] - max(trap["open"], trap["close"])
    lower_wick = min(trap["open"], trap["close"]) - trap["low"]

    # =========================================================
    # Bearish liquidity trap
    # take highs -> fail -> confirm down
    # =========================================================
    took_highs = trap["high"] > recent_high
    failed_breakout = trap["close"] < recent_high
    upper_rejection = upper_wick > trap_body * 1.2

    bearish_confirmation = (
        confirm["close"] < confirm["open"]
        and confirm["close"] < trap["low"]
        and confirm_body > atr * 0.25
        and price < ema
    )

    if (
        took_highs
        and failed_breakout
        and upper_rejection
        and bearish_confirmation
    ):
        pattern_height = abs(recent_high - recent_low)

        return {
            "signal": "SELL",
            "score": 94,
            "strategy": "LIQUIDITY_TRAP",
            "pattern_height": pattern_height,
            "trap_high": trap["high"],
            "trap_low": trap["low"],
            "range_high": recent_high,
            "range_low": recent_low,
            "sl_reference": trap["high"],
            "reason": (
                f"Liquidity trap bearish -> highs above {round(recent_high,2)} taken -> "
                f"failed breakout -> bearish confirmation below {round(trap['low'],2)} -> "
                f"price below EMA"
            ),
        }

    # =========================================================
    # Bullish liquidity trap
    # take lows -> fail -> confirm up
    # =========================================================
    took_lows = trap["low"] < recent_low
    failed_breakdown = trap["close"] > recent_low
    lower_rejection = lower_wick > trap_body * 1.2

    bullish_confirmation = (
        confirm["close"] > confirm["open"]
        and confirm["close"] > trap["high"]
        and confirm_body > atr * 0.25
        and price > ema
    )

    if (
        took_lows
        and failed_breakdown
        and lower_rejection
        and bullish_confirmation
    ):
        pattern_height = abs(recent_high - recent_low)

        return {
            "signal": "BUY",
            "score": 94,
            "strategy": "LIQUIDITY_TRAP",
            "pattern_height": pattern_height,
            "trap_high": trap["high"],
            "trap_low": trap["low"],
            "range_high": recent_high,
            "range_low": recent_low,
            "sl_reference": trap["low"],
            "reason": (
                f"Liquidity trap bullish -> lows below {round(recent_low,2)} taken -> "
                f"failed breakdown -> bullish confirmation above {round(trap['high'],2)} -> "
                f"price above EMA"
            ),
        }

    return None