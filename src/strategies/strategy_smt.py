from config.settings import ATR_MIN, ATR_MAX


SMT_SL_ATR_MULTIPLIER = 0.20
SMT_MIN_SL_BUFFER = 2.0
SMT_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * SMT_SL_ATR_MULTIPLIER, SMT_MIN_SL_BUFFER),
        SMT_MAX_SL_BUFFER,
    )


def _score_setup(base_score, body, atr, wick_strength, close_aligned):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if wick_strength:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 45:
        return None

    closed = df.iloc[:-1].reset_index(drop=True)
    data = closed.iloc[-40:].reset_index(drop=True)

    entry = data.iloc[-1]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    highs = data["high"]
    lows = data["low"]

    recent_high_1 = highs.iloc[-12:-6].max()
    recent_high_2 = highs.iloc[-6:].max()

    recent_low_1 = lows.iloc[-12:-6].min()
    recent_low_2 = lows.iloc[-6:].min()

    structure_high = highs.iloc[-20:].max()
    structure_low = lows.iloc[-20:].min()

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if body <= 0 or candle_range <= 0:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # Bearish SMT
    # Fake higher high / failed continuation
    # =========================================================
    higher_high = recent_high_2 > recent_high_1

    weak_close = entry["close"] < recent_high_2 - atr * 0.20

    rejection = (
        entry["high"] >= recent_high_2
        and entry["close"] < entry["open"]
        and upper_wick > body * 1.0
    )

    bearish_context = price < ema
    bearish_momentum = body > atr * 0.20

    if higher_high and weak_close and rejection and bearish_context and bearish_momentum:
        pattern_height = abs(recent_high_2 - recent_low_2)

        if pattern_height <= 0:
            return None

        sl_reference = round(recent_high_2 + sl_buffer, 2)

        if structure_low < entry["close"]:
            tp_reference = structure_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(pattern_height, atr * 1.5)
            target_model = "MEASURED_SMT_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=91,
            body=body,
            atr=atr,
            wick_strength=upper_wick > body * 1.5,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "SMT",
            "entry_model": "SMT_INTERNAL_DIVERGENCE_REVERSAL",
            "pattern_height": pattern_height,
            "recent_high_1": recent_high_1,
            "recent_high_2": recent_high_2,
            "recent_low_1": recent_low_1,
            "recent_low_2": recent_low_2,
            "structure_high": structure_high,
            "structure_low": structure_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_rejection_after_higher_high",
            "direction_context": "price_below_ema",
            "reason": (
                f"SMT bearish divergence -> higher high {round(recent_high_2, 2)} not sustained -> "
                f"SL above failed high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish SMT
    # Fake lower low / failed continuation
    # =========================================================
    lower_low = recent_low_2 < recent_low_1

    weak_close = entry["close"] > recent_low_2 + atr * 0.20

    rejection = (
        entry["low"] <= recent_low_2
        and entry["close"] > entry["open"]
        and lower_wick > body * 1.0
    )

    bullish_context = price > ema
    bullish_momentum = body > atr * 0.20

    if lower_low and weak_close and rejection and bullish_context and bullish_momentum:
        pattern_height = abs(recent_high_2 - recent_low_2)

        if pattern_height <= 0:
            return None

        sl_reference = round(recent_low_2 - sl_buffer, 2)

        if structure_high > entry["close"]:
            tp_reference = structure_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(pattern_height, atr * 1.5)
            target_model = "MEASURED_SMT_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=91,
            body=body,
            atr=atr,
            wick_strength=lower_wick > body * 1.5,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "SMT",
            "entry_model": "SMT_INTERNAL_DIVERGENCE_REVERSAL",
            "pattern_height": pattern_height,
            "recent_high_1": recent_high_1,
            "recent_high_2": recent_high_2,
            "recent_low_1": recent_low_1,
            "recent_low_2": recent_low_2,
            "structure_high": structure_high,
            "structure_low": structure_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_rejection_after_lower_low",
            "direction_context": "price_above_ema",
            "reason": (
                f"SMT bullish divergence -> lower low {round(recent_low_2, 2)} not sustained -> "
                f"SL below failed low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    return None