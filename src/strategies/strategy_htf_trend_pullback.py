from config.settings import ATR_MIN, ATR_MAX


PULLBACK_LOOKBACK = 30

PULLBACK_VALUE_ATR_BUFFER = 0.35
PULLBACK_MIN_BODY_ATR = 0.20

PULLBACK_SL_ATR_MULTIPLIER = 0.25
PULLBACK_MIN_SL_BUFFER = 2.0
PULLBACK_MAX_SL_BUFFER = 6.0

PULLBACK_TARGET_ATR_MIN = 1.5
PULLBACK_TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(
        max(atr * PULLBACK_SL_ATR_MULTIPLIER, PULLBACK_MIN_SL_BUFFER),
        PULLBACK_MAX_SL_BUFFER,
    )


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * 0.70, atr * PULLBACK_TARGET_ATR_MIN),
        atr * PULLBACK_TARGET_ATR_MAX,
    )


def _score_setup(base_score, body, atr, close_aligned, rejection_strength):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if close_aligned:
        score += 2

    if rejection_strength:
        score += 3

    return min(score, 99)


def generate_signal(df):
    if len(df) < PULLBACK_LOOKBACK + 5:
        return None

    entry = df.iloc[-2]
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * PULLBACK_MIN_BODY_ATR:
        return None

    recent = df.iloc[-PULLBACK_LOOKBACK:-2]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    structure_range = recent_high - recent_low

    if structure_range <= 0:
        return None

    ema_slope = df["ema_20"].iloc[-2] - df["ema_20"].iloc[-8]

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================
    # BUY: HTF/EMA bullish pullback continuation
    # =========================
    bullish_context = (
        price > ema
        and ema_slope > 0
    )

    pulled_back_to_value = (
        entry["low"] <= ema + atr * PULLBACK_VALUE_ATR_BUFFER
        or prev["low"] <= ema + atr * PULLBACK_VALUE_ATR_BUFFER
    )

    bullish_rejection = (
        entry["close"] > entry["open"]
        and entry["close"] > ema
        and lower_wick > body * 0.80
        and entry["close"] >= entry["low"] + candle_range * 0.60
    )

    if bullish_context and pulled_back_to_value and bullish_rejection:
        sl_reference = round(min(entry["low"], prev["low"]) - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "TREND_CONTINUATION_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_aligned=price > ema,
            rejection_strength=lower_wick > body * 1.2,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "HTF_TREND_PULLBACK",
            "entry_model": "BULLISH_VALUE_PULLBACK_RECLAIM",
            "pattern_height": target_distance,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "ema_value": ema,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_pullback_reclaim",
            "direction_context": "ema_uptrend_price_above_ema",
            "reason": (
                f"HTF trend pullback BUY -> price pulled back near EMA {round(ema, 2)} -> "
                f"bullish reclaim confirmed -> SL below pullback {sl_reference} -> "
                f"TP {target_model} {tp_reference}"
            ),
        }

    # =========================
    # SELL: HTF/EMA bearish pullback continuation
    # =========================
    bearish_context = (
        price < ema
        and ema_slope < 0
    )

    pulled_back_to_value = (
        entry["high"] >= ema - atr * PULLBACK_VALUE_ATR_BUFFER
        or prev["high"] >= ema - atr * PULLBACK_VALUE_ATR_BUFFER
    )

    bearish_rejection = (
        entry["close"] < entry["open"]
        and entry["close"] < ema
        and upper_wick > body * 0.80
        and entry["close"] <= entry["high"] - candle_range * 0.60
    )

    if bearish_context and pulled_back_to_value and bearish_rejection:
        sl_reference = round(max(entry["high"], prev["high"]) + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "TREND_CONTINUATION_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_aligned=price < ema,
            rejection_strength=upper_wick > body * 1.2,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "HTF_TREND_PULLBACK",
            "entry_model": "BEARISH_VALUE_PULLBACK_REJECT",
            "pattern_height": target_distance,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "ema_value": ema,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_pullback_rejection",
            "direction_context": "ema_downtrend_price_below_ema",
            "reason": (
                f"HTF trend pullback SELL -> price pulled back near EMA {round(ema, 2)} -> "
                f"bearish rejection confirmed -> SL above pullback {sl_reference} -> "
                f"TP {target_model} {tp_reference}"
            ),
        }

    return None