from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    # candles
    confirmation = df.iloc[-2]   # last closed candle
    sweep = df.iloc[-3]          # liquidity sweep candle
    pre_sweep = df.iloc[-4]      # candle before sweep

    atr = confirmation["atr_14"]
    price = confirmation["close"]
    ema = confirmation["ema_20"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 5):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    sweep_body = abs(sweep["close"] - sweep["open"])
    sweep_range = sweep["high"] - sweep["low"]
    conf_body = abs(confirmation["close"] - confirmation["open"])

    if sweep_range <= 0:
        return None

    upper_wick = sweep["high"] - max(sweep["open"], sweep["close"])
    lower_wick = min(sweep["open"], sweep["close"]) - sweep["low"]

    bullish_confirmation = confirmation["close"] > confirmation["open"]
    bearish_confirmation = confirmation["close"] < confirmation["open"]

    bearish_displacement = conf_body > atr * 0.30
    bullish_displacement = conf_body > atr * 0.30

    # =========================================================
    # Bearish ICT-style sweep
    # Sweep above highs -> reject -> close back below resistance
    # then confirmation closes below sweep midpoint / low pressure
    # =========================================================
    swept_high = sweep["high"] > (resistance + BREAKOUT_BUFFER)
    close_back_inside = sweep["close"] < resistance
    strong_rejection = upper_wick > sweep_body * 1.2
    confirmation_bearish = bearish_confirmation and bearish_displacement
    follow_through_down = confirmation["close"] < (sweep["open"] + sweep["close"]) / 2
    bearish_context = price <= ema * 1.002  # light context, not too strict

    if (
        swept_high
        and close_back_inside
        and strong_rejection
        and confirmation_bearish
        and follow_through_down
        and bearish_context
    ):
        reason = (
            f"ICT bearish liquidity sweep -> took highs above {round(resistance, 2)} -> "
            f"sweep high {round(sweep['high'], 2)} -> "
            f"closed back inside range -> "
            f"bearish confirmation at {round(confirmation['close'], 2)}"
        )

        return {
            "signal": "SELL",
            "score": 86,
            "strategy": "LIQUIDITY_SWEEP",
            "reason": reason,
        }

    # =========================================================
    # Bullish ICT-style sweep
    # Sweep below lows -> reject -> close back above support
    # then confirmation closes above sweep midpoint / high pressure
    # =========================================================
    swept_low = sweep["low"] < (support - BREAKOUT_BUFFER)
    close_back_inside = sweep["close"] > support
    strong_rejection = lower_wick > sweep_body * 1.2
    confirmation_bullish = bullish_confirmation and bullish_displacement
    follow_through_up = confirmation["close"] > (sweep["open"] + sweep["close"]) / 2
    bullish_context = price >= ema * 0.998  # light context, not too strict

    if (
        swept_low
        and close_back_inside
        and strong_rejection
        and confirmation_bullish
        and follow_through_up
        and bullish_context
    ):
        reason = (
            f"ICT bullish liquidity sweep -> took lows below {round(support, 2)} -> "
            f"sweep low {round(sweep['low'], 2)} -> "
            f"closed back inside range -> "
            f"bullish confirmation at {round(confirmation['close'], 2)}"
        )

        return {
            "signal": "BUY",
            "score": 86,
            "strategy": "LIQUIDITY_SWEEP",
            "reason": reason,
        }

    return None