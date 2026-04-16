from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
    ENABLE_SNIPER_V2,
    MIN_BREAKOUT_BODY_ATR,
    MAX_BREAKOUT_WICK_BODY_RATIO,
    ENABLE_VOLATILITY_SPIKE_FILTER,
    MAX_ATR_SPIKE_MULTIPLIER,
    ENABLE_SESSION_FILTER,
    SESSION_START_HOUR,
    SESSION_END_HOUR,
)


def in_session(df):
    if not ENABLE_SESSION_FILTER:
        return True

    entry_candle = df.iloc[-2]
    candle_time = entry_candle["time"]

    hour = candle_time.hour
    return SESSION_START_HOUR <= hour < SESSION_END_HOUR


def calculate_setup_score(df):
    entry_candle = df.iloc[-2]
    breakout_candle = df.iloc[-3]

    score = 0

    breakout_size = abs(breakout_candle["close"] - breakout_candle["open"])
    if breakout_size > entry_candle["atr_14"] * 0.8:
        score += 25
    elif breakout_size > entry_candle["atr_14"] * 0.5:
        score += 15

    wick_range = abs(entry_candle["high"] - entry_candle["low"])
    body = abs(entry_candle["close"] - entry_candle["open"])
    if wick_range > body:
        score += 20
    else:
        score += 10

    if abs(entry_candle["close"] - entry_candle["ema_20"]) < entry_candle["atr_14"] * 2:
        score += 15

    if ATR_MIN <= entry_candle["atr_14"] <= ATR_MAX:
        score += 15

    if abs(entry_candle["close"] - entry_candle["open"]) > entry_candle["atr_14"] * 0.3:
        score += 15

    score += 10

    return min(score, 100)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 6:
        return "NO_TRADE"

    entry_candle = df.iloc[-2]
    breakout_candle = df.iloc[-3]
    prev_atr_candle = df.iloc[-4]

    if not in_session(df):
        return "NO_TRADE"

    price = entry_candle["close"]
    ema = entry_candle["ema_20"]
    atr = entry_candle["atr_14"]
    prev_atr = prev_atr_candle["atr_14"]

    # 1) Volatility filter
    if atr < ATR_MIN or atr > ATR_MAX:
        return "NO_TRADE"

    # 2) Volatility spike filter
    if ENABLE_VOLATILITY_SPIKE_FILTER and prev_atr > 0:
        if atr > prev_atr * MAX_ATR_SPIKE_MULTIPLIER:
            return "NO_TRADE"

    # 3) Distance from EMA
    distance = abs(price - ema)
    if distance > atr * 2:
        return "NO_TRADE"

    # 4) Recent structure
    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    breakout_body = abs(breakout_candle["close"] - breakout_candle["open"])
    breakout_range = breakout_candle["high"] - breakout_candle["low"]

    if breakout_body <= 0:
        return "NO_TRADE"

    upper_wick = breakout_candle["high"] - max(breakout_candle["open"], breakout_candle["close"])
    lower_wick = min(breakout_candle["open"], breakout_candle["close"]) - breakout_candle["low"]

    bullish = entry_candle["close"] > entry_candle["open"]
    bearish = entry_candle["close"] < entry_candle["open"]

    retest_up = entry_candle["low"] <= resistance + BREAKOUT_BUFFER
    retest_down = entry_candle["high"] >= support - BREAKOUT_BUFFER

    breakout_up = (
        breakout_candle["close"] > (resistance + BREAKOUT_BUFFER)
        and breakout_candle["close"] > breakout_candle["open"]
    )

    breakout_down = (
        breakout_candle["close"] < (support - BREAKOUT_BUFFER)
        and breakout_candle["close"] < breakout_candle["open"]
    )

    strong_breakout_up = breakout_body > atr * 0.5
    strong_breakout_down = breakout_body > atr * 0.5

    candle_range = entry_candle["high"] - entry_candle["low"]
    if candle_range < atr * 0.3:
        return "NO_TRADE"

    if ENABLE_SNIPER_V2:
        # breakout body must have some real size
        if breakout_body < atr * MIN_BREAKOUT_BODY_ATR:
            return "NO_TRADE"

        # reject breakout candles with huge rejection wicks
        if upper_wick / breakout_body > MAX_BREAKOUT_WICK_BODY_RATIO and breakout_up:
            return "NO_TRADE"

        if lower_wick / breakout_body > MAX_BREAKOUT_WICK_BODY_RATIO and breakout_down:
            return "NO_TRADE"

    if price > ema and breakout_up and bullish and (retest_up or strong_breakout_up):
        return {
            "signal": "BUY",
            "score": calculate_setup_score(df),
        }

    if price < ema and breakout_down and bearish and (retest_down or strong_breakout_down):
        return {
            "signal": "SELL",
            "score": calculate_setup_score(df),
        }

    return "NO_TRADE"