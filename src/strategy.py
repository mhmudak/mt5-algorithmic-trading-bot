from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 3:
        return "NO_TRADE"

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = last["close"]
    ema = last["ema_20"]
    atr = last["atr_14"]

    # 1. Volatility filter
    if atr < ATR_MIN or atr > ATR_MAX:
        return "NO_TRADE"

    # 2. Distance from EMA
    distance = abs(price - ema)
    if distance > atr:
        return "NO_TRADE"

    # 3. Recent levels
    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    # 4. Breakout detection (previous candle)
    breakout_up = prev["close"] > (resistance + BREAKOUT_BUFFER)
    breakout_down = prev["close"] < (support - BREAKOUT_BUFFER)

    # 5. Retest (current candle)
    retest_up = last["low"] <= resistance + BREAKOUT_BUFFER
    retest_down = last["high"] >= support - BREAKOUT_BUFFER

    # 6. Candle confirmation
    bullish = last["close"] > last["open"]
    bearish = last["close"] < last["open"]

    # 7. Final decision
    if price > ema and breakout_up and retest_up and bullish:
        return "BUY"

    if price < ema and breakout_down and retest_down and bearish:
        return "SELL"

    return "NO_TRADE"