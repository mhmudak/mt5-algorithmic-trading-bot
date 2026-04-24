def detect_liquidity_sweep(df, signal, lookback=6):
    if len(df) < lookback + 2:
        return False

    last = df.iloc[-1]
    prev_data = df.iloc[-(lookback + 1):-1]

    recent_high = prev_data["high"].max()
    recent_low = prev_data["low"].min()

    if signal == "BUY":
        # swept sell-side liquidity then closed back up
        return last["low"] < recent_low and last["close"] > recent_low

    if signal == "SELL":
        # swept buy-side liquidity then closed back down
        return last["high"] > recent_high and last["close"] < recent_high

    return False


def detect_displacement(df, signal, atr_multiplier=0.6):
    if len(df) < 2:
        return False

    last = df.iloc[-1]
    atr = last["atr_14"]

    body = abs(last["close"] - last["open"])

    if body < atr * atr_multiplier:
        return False

    if signal == "BUY":
        return last["close"] > last["open"]

    if signal == "SELL":
        return last["close"] < last["open"]

    return False


def detect_inducement_break(df, signal, lookback=4):
    if len(df) < lookback + 2:
        return False

    last = df.iloc[-1]
    recent = df.iloc[-(lookback + 1):-1]

    local_high = recent["high"].max()
    local_low = recent["low"].min()

    if signal == "BUY":
        return last["low"] < local_low and last["close"] > last["open"]

    if signal == "SELL":
        return last["high"] > local_high and last["close"] < last["open"]

    return False


def smart_money_confirm(df, signal):
    sweep = detect_liquidity_sweep(df, signal)
    displacement = detect_displacement(df, signal)
    inducement = detect_inducement_break(df, signal)

    score = 0
    reasons = []

    if sweep:
        score += 1
        reasons.append("liquidity_sweep")

    if displacement:
        score += 1
        reasons.append("displacement")

    if inducement:
        score += 1
        reasons.append("inducement_break")

    return {
        "confirmed": score >= 2,
        "score": score,
        "reasons": reasons,
    }