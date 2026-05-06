from config.settings import ATR_MIN, ATR_MAX


FLAG_SL_ATR_MULTIPLIER = 0.20
FLAG_MIN_SL_BUFFER = 2.0
FLAG_MAX_SL_BUFFER = 5.0

FLAG_MIN_POLE_ATR = 0.60
FLAG_MIN_ENTRY_BODY_ATR = 0.25
FLAG_MAX_EXTENSION_ATR = 0.80


def _sl_buffer(atr):
    return min(
        max(atr * FLAG_SL_ATR_MULTIPLIER, FLAG_MIN_SL_BUFFER),
        FLAG_MAX_SL_BUFFER,
    )


def _score_setup(base_score, pole_body, entry_body, atr, close_aligned):
    score = base_score

    if pole_body > atr * 0.80:
        score += 2

    if pole_body > atr * 1.10:
        score += 2

    if entry_body > atr * 0.35:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 20:
        return None

    # Structure:
    # pole = older impulse
    # pullback candles = short opposite drift
    # entry candle = latest closed candle
    entry = df.iloc[-2]
    pullback_1 = df.iloc[-3]
    pullback_2 = df.iloc[-4]
    pole = df.iloc[-5]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    pole_body = abs(pole["close"] - pole["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if pole_body < atr * FLAG_MIN_POLE_ATR:
        return None

    if entry_body < atr * FLAG_MIN_ENTRY_BODY_ATR:
        return None

    pullback_high = max(pullback_1["high"], pullback_2["high"])
    pullback_low = min(pullback_1["low"], pullback_2["low"])
    pullback_height = pullback_high - pullback_low

    if pullback_height <= 0:
        return None

    sl_buffer = _sl_buffer(atr)

    recent = df.iloc[-20:-5]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    # =========================
    # Bullish flag
    # =========================
    bullish_pole = (
        pole["close"] > pole["open"]
        and pole_body > atr * FLAG_MIN_POLE_ATR
    )

    bearish_pullback = (
        pullback_2["close"] < pullback_2["open"]
        and pullback_1["close"] < pullback_1["open"]
    )

    breakout_distance = entry["close"] - pullback_high

    bullish_break = (
        entry["close"] > entry["open"]
        and entry["close"] > pullback_high
        and price > ema
        and breakout_distance >= 0
        and breakout_distance <= atr * FLAG_MAX_EXTENSION_ATR
    )

    if bullish_pole and bearish_pullback and bullish_break:
        measured_move = entry["close"] + max(pole_body, pullback_height * 2, atr * 1.5)

        if recent_high > entry["close"]:
            tp_reference = max(recent_high, measured_move)
            target_model = "RECENT_HIGH_OR_MEASURED_FLAG_MOVE"
        else:
            tp_reference = measured_move
            target_model = "MEASURED_FLAG_MOVE"

        sl_reference = round(pullback_low - sl_buffer, 2)
        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=78,
            pole_body=pole_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FLAG",
            "entry_model": "FLAG_BREAKOUT_CONTINUATION",
            "pattern_height": max(pole_body, pullback_height),
            "flag_high": pullback_high,
            "flag_low": pullback_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_flag_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish flag -> strong pole near {round(pole['close'], 2)} -> "
                f"2-candle pullback range {round(pullback_low, 2)} to {round(pullback_high, 2)} -> "
                f"breakout above {round(pullback_high, 2)} -> "
                f"SL below pullback low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # Bearish flag
    # =========================
    bearish_pole = (
        pole["close"] < pole["open"]
        and pole_body > atr * FLAG_MIN_POLE_ATR
    )

    bullish_pullback = (
        pullback_2["close"] > pullback_2["open"]
        and pullback_1["close"] > pullback_1["open"]
    )

    breakdown_distance = pullback_low - entry["close"]

    bearish_break = (
        entry["close"] < entry["open"]
        and entry["close"] < pullback_low
        and price < ema
        and breakdown_distance >= 0
        and breakdown_distance <= atr * FLAG_MAX_EXTENSION_ATR
    )

    if bearish_pole and bullish_pullback and bearish_break:
        measured_move = entry["close"] - max(pole_body, pullback_height * 2, atr * 1.5)

        if recent_low < entry["close"]:
            tp_reference = min(recent_low, measured_move)
            target_model = "RECENT_LOW_OR_MEASURED_FLAG_MOVE"
        else:
            tp_reference = measured_move
            target_model = "MEASURED_FLAG_MOVE"

        sl_reference = round(pullback_high + sl_buffer, 2)
        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=78,
            pole_body=pole_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FLAG",
            "entry_model": "FLAG_BREAKDOWN_CONTINUATION",
            "pattern_height": max(pole_body, pullback_height),
            "flag_high": pullback_high,
            "flag_low": pullback_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_flag_breakdown",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish flag -> strong pole near {round(pole['close'], 2)} -> "
                f"2-candle pullback range {round(pullback_low, 2)} to {round(pullback_high, 2)} -> "
                f"breakdown below {round(pullback_low, 2)} -> "
                f"SL above pullback high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    return None