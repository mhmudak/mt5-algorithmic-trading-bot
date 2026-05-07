from src.logger import logger


def detect_market_condition(df):
    if len(df) < 20:
        logger.info("[MARKET] Not enough data, defaulting to RANGING")
        return "RANGING"

    # Use closed candles only
    last = df.iloc[-2]
    prev = df.iloc[-3]

    atr = last["atr_14"]
    prev_atr = prev["atr_14"]

    ema = last["ema_20"]
    price = last["close"]

    if atr <= 0:
        logger.info("[MARKET] Invalid ATR, defaulting to RANGING")
        return "RANGING"

    # =========================
    # VOLATILITY DETECTION
    # =========================
    if prev_atr > 0 and atr > prev_atr * 1.7:
        logger.info("[MARKET] VOLATILE detected")
        return "VOLATILE"

    # =========================
    # EMA SLOPE / TREND CONTEXT
    # =========================
    ema_now = df["ema_20"].iloc[-2]
    ema_past = df["ema_20"].iloc[-8]
    ema_slope = ema_now - ema_past

    distance_from_ema = abs(price - ema)

    # =========================
    # STRONG TREND
    # Price is away from EMA and EMA has slope
    # =========================
    if distance_from_ema > atr * 1.2 and abs(ema_slope) > atr * 0.25:
        logger.info("[MARKET] TRENDING detected")
        return "TRENDING"

    # =========================
    # PULLBACK TREND
    # Trend exists, but price is near value/EMA
    # =========================
    if abs(ema_slope) > atr * 0.20 and distance_from_ema <= atr * 0.90:
        logger.info("[MARKET] PULLBACK_TREND detected")
        return "PULLBACK_TREND"

    # =========================
    # DEFAULT
    # =========================
    logger.info("[MARKET] RANGING detected")
    return "RANGING"