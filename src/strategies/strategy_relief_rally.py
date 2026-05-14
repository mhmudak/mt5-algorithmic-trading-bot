from config.settings import ATR_MIN, ATR_MAX


RELIEF_SL_ATR_MULTIPLIER = 0.20
RELIEF_MIN_SL_BUFFER = 2.0
RELIEF_MAX_SL_BUFFER = 5.0

RELIEF_MAX_EXTENSION_ATR = 0.65
RELIEF_RETEST_BUFFER_ATR = 0.25
RELIEF_MIN_BODY_ATR = 0.25


def _sl_buffer(atr):
    return min(
        max(atr * RELIEF_SL_ATR_MULTIPLIER, RELIEF_MIN_SL_BUFFER),
        RELIEF_MAX_SL_BUFFER,
    )


def _score_setup(base_score, entry_body, atr, continuation_strength, close_aligned, entry_model):
    score = base_score

    if entry_body > atr * 0.35:
        score += 2

    if entry_body > atr * 0.50:
        score += 2

    if continuation_strength:
        score += 2

    if close_aligned:
        score += 2

    if entry_model.endswith("RETEST"):
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 35:
        return None

    trend_anchor = df.iloc[-8]
    relief_1 = df.iloc[-5]
    relief_2 = df.iloc[-4]
    relief_3 = df.iloc[-3]
    entry = df.iloc[-2]
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    entry_body = abs(entry["close"] - entry["open"])
    entry_range = entry["high"] - entry["low"]

    if entry_range <= 0:
        return None

    if entry_body < atr * RELIEF_MIN_BODY_ATR:
        return None

    structure = df.iloc[-24:-8]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)
    retest_buffer = atr * RELIEF_RETEST_BUFFER_ATR

    relief_high = max(relief_1["high"], relief_2["high"], relief_3["high"])
    relief_low = min(relief_1["low"], relief_2["low"], relief_3["low"])

    # =========================================================
    # Bearish relief rally
    # =========================================================
    bearish_trend_context = trend_anchor["close"] < trend_anchor["ema_20"]

    relief_up = (
        relief_1["close"] > relief_1["open"]
        and relief_2["close"] > relief_2["open"]
    )

    stalled_relief = relief_3["high"] <= max(relief_1["high"], relief_2["high"]) + atr * 0.15

    bearish_reaction = (
        entry["close"] < entry["open"]
        and price < ema
        and entry_body > atr * RELIEF_MIN_BODY_ATR
    )

    if bearish_trend_context and relief_up and stalled_relief and bearish_reaction:
        break_level = relief_3["low"]

        immediate_break = entry["close"] < break_level
        extension_from_break = break_level - entry["close"]
        immediate_not_late = 0 <= extension_from_break <= atr * RELIEF_MAX_EXTENSION_ATR

        retest_entry = (
            prev["close"] < break_level
            and entry["high"] >= break_level - retest_buffer
            and entry["close"] < break_level
        )

        if immediate_break and immediate_not_late:
            entry_model = "RELIEF_CONTINUATION"
        elif retest_entry:
            entry_model = "RELIEF_CONTINUATION_RETEST"
        else:
            return None

        pattern_height = abs(relief_high - entry["close"])
        sl_reference = round(relief_high + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(pattern_height, atr * 1.5)
            target_model = "MEASURED_CONTINUATION_MOVE"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            entry_body=entry_body,
            atr=atr,
            continuation_strength=entry["close"] < relief_low,
            close_aligned=price < ema,
            entry_model=entry_model,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "RELIEF_RALLY",
            "entry_model": entry_model,
            "pattern_height": pattern_height,
            "relief_high": relief_high,
            "relief_low": relief_low,
            "break_level": break_level,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_continuation_resume",
            "direction_context": "bearish_trend_price_below_ema",
            "reason": (
                f"Relief rally bearish -> rebound stalled near {round(relief_high, 2)} -> "
                f"{entry_model} below {round(break_level, 2)} -> "
                f"SL above relief high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish relief drop
    # =========================================================
    bullish_trend_context = trend_anchor["close"] > trend_anchor["ema_20"]

    relief_down = (
        relief_1["close"] < relief_1["open"]
        and relief_2["close"] < relief_2["open"]
    )

    stalled_drop = relief_3["low"] >= min(relief_1["low"], relief_2["low"]) - atr * 0.15

    bullish_reaction = (
        entry["close"] > entry["open"]
        and price > ema
        and entry_body > atr * RELIEF_MIN_BODY_ATR
    )

    if bullish_trend_context and relief_down and stalled_drop and bullish_reaction:
        break_level = relief_3["high"]

        immediate_break = entry["close"] > break_level
        extension_from_break = entry["close"] - break_level
        immediate_not_late = 0 <= extension_from_break <= atr * RELIEF_MAX_EXTENSION_ATR

        retest_entry = (
            prev["close"] > break_level
            and entry["low"] <= break_level + retest_buffer
            and entry["close"] > break_level
        )

        if immediate_break and immediate_not_late:
            entry_model = "RELIEF_CONTINUATION"
        elif retest_entry:
            entry_model = "RELIEF_CONTINUATION_RETEST"
        else:
            return None

        pattern_height = abs(entry["close"] - relief_low)
        sl_reference = round(relief_low - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(pattern_height, atr * 1.5)
            target_model = "MEASURED_CONTINUATION_MOVE"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            entry_body=entry_body,
            atr=atr,
            continuation_strength=entry["close"] > relief_high,
            close_aligned=price > ema,
            entry_model=entry_model,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "RELIEF_RALLY",
            "entry_model": entry_model,
            "pattern_height": pattern_height,
            "relief_high": relief_high,
            "relief_low": relief_low,
            "break_level": break_level,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_continuation_resume",
            "direction_context": "bullish_trend_price_above_ema",
            "reason": (
                f"Relief drop bullish -> pullback stalled near {round(relief_low, 2)} -> "
                f"{entry_model} above {round(break_level, 2)} -> "
                f"SL below relief low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    return None