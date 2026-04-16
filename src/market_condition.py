from src.logger import logger


def detect_market_condition(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    atr = last["atr_14"]
    prev_atr = prev["atr_14"]

    ema = last["ema_20"]
    price = last["close"]

    # =========================
    # VOLATILITY DETECTION
    # =========================
    if prev_atr > 0 and atr > prev_atr * 1.7:
        logger.info("[MARKET] VOLATILE detected")
        return "VOLATILE"

    # =========================
    # TREND DETECTION
    # =========================
    distance = abs(price - ema)

    if distance > atr * 1.2:
        logger.info("[MARKET] TRENDING detected")
        return "TRENDING"

    # =========================
    # DEFAULT
    # =========================
    logger.info("[MARKET] RANGING detected")
    return "RANGING"