from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def calculate_setup_score(df):
    entry_candle = df.iloc[-2]
    breakout_candle = df.iloc[-3]

    score = 0

    # 1. Breakout strength
    breakout_size = abs(breakout_candle["close"] - breakout_candle["open"])
    if breakout_size > entry_candle["atr_14"] * 0.8:
        score += 25
    elif breakout_size > entry_candle["atr_14"] * 0.5:
        score += 15

    # 2. Retest quality
    wick_range = abs(entry_candle["high"] - entry_candle["low"])
    body = abs(entry_candle["close"] - entry_candle["open"])
    if wick_range > body:
        score += 20
    else:
        score += 10

    # 3. EMA alignment
    if abs(entry_candle["close"] - entry_candle["ema_20"]) < entry_candle["atr_14"] * 2:
        score += 15

    # 4. ATR quality
    if ATR_MIN <= entry_candle["atr_14"] <= ATR_MAX:
        score += 15

    # 5. Candle strength
    if abs(entry_candle["close"] - entry_candle["open"]) > entry_candle["atr_14"] * 0.3:
        score += 15

    # 6. Spread placeholder
    score += 10

    return min(score, 100)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 4:
        return "NO_TRADE"

    entry_candle = df.iloc[-2]       # last closed candle
    breakout_candle = df.iloc[-3]    # candle before it

    price = entry_candle["close"]
    ema = entry_candle["ema_20"]
    atr = entry_candle["atr_14"]

    # 1. Volatility filter
    if atr < ATR_MIN or atr > ATR_MAX:
        return "NO_TRADE"

    # 2. Distance from EMA
    distance = abs(price - ema)
    if distance > atr * 2:
        return "NO_TRADE"

    # 3. Recent levels (exclude breakout and entry candles)
    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    # 4. Breakout detection with candle direction confirmation
    breakout_up = (
        breakout_candle["close"] > (resistance + BREAKOUT_BUFFER)
        and breakout_candle["close"] > breakout_candle["open"]
    )

    breakout_down = (
        breakout_candle["close"] < (support - BREAKOUT_BUFFER)
        and breakout_candle["close"] < breakout_candle["open"]
    )

    # 5. Optional soft retest
    retest_up = entry_candle["low"] <= resistance + BREAKOUT_BUFFER
    retest_down = entry_candle["high"] >= support - BREAKOUT_BUFFER

    # 6. Candle confirmation
    bullish = entry_candle["close"] > entry_candle["open"]
    bearish = entry_candle["close"] < entry_candle["open"]

    # 7. Strong breakout override
    strong_breakout_up = abs(breakout_candle["close"] - breakout_candle["open"]) > atr * 0.5
    strong_breakout_down = abs(breakout_candle["close"] - breakout_candle["open"]) > atr * 0.5

    # 8. Dead-zone filter
    candle_range = entry_candle["high"] - entry_candle["low"]
    if candle_range < atr * 0.3:
        return "NO_TRADE"

    # 9. Final decision
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