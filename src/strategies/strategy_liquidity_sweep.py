from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    confirmation = df.iloc[-2]
    sweep = df.iloc[-3]

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

    displacement = conf_body > atr * 0.30

    # =========================
    # 🔴 SELL (sweep highs)
    # =========================
    if (
        sweep["high"] > resistance + BREAKOUT_BUFFER
        and sweep["close"] < resistance
        and upper_wick > sweep_body * 1.2
        and bearish_confirmation
        and displacement
        and confirmation["close"] < (sweep["open"] + sweep["close"]) / 2
        and price < ema
    ):
        return {
            "signal": "SELL",
            "score": 90,
            "strategy": "LIQUIDITY_SWEEP",
            "sweep_high": sweep["high"],
            "pattern_height": sweep_range,
            "reason": (
                f"ICT bearish liquidity sweep -> took highs above {round(resistance, 2)} -> "
                f"sweep high {round(sweep['high'], 2)} -> rejection confirmed"
            ),
        }

    # =========================
    # 🟢 BUY (sweep lows)
    # =========================
    if (
        sweep["low"] < support - BREAKOUT_BUFFER
        and sweep["close"] > support
        and lower_wick > sweep_body * 1.2
        and bullish_confirmation
        and displacement
        and confirmation["close"] > (sweep["open"] + sweep["close"]) / 2
        and price > ema
    ):
        return {
            "signal": "BUY",
            "score": 90,
            "strategy": "LIQUIDITY_SWEEP",
            "sweep_low": sweep["low"],
            "pattern_height": sweep_range,
            "reason": (
                f"ICT bullish liquidity sweep -> took lows below {round(support, 2)} -> "
                f"sweep low {round(sweep['low'], 2)} -> rejection confirmed"
            ),
        }

    return None