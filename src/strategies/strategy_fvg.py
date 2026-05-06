from config.settings import ATR_MIN, ATR_MAX


FVG_SL_ATR_MULTIPLIER = 0.15
FVG_MIN_SL_BUFFER = 1.0
FVG_MAX_SL_BUFFER = 4.0


def _sl_buffer(atr):
    return min(
        max(atr * FVG_SL_ATR_MULTIPLIER, FVG_MIN_SL_BUFFER),
        FVG_MAX_SL_BUFFER,
    )


def _score_setup(base_score, displacement_body, reaction_body, atr, close_aligned):
    score = base_score

    if displacement_body > atr * 0.50:
        score += 2

    if displacement_body > atr * 0.70:
        score += 2

    if reaction_body > atr * 0.30:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 30:
        return None

    # candles
    c1 = df.iloc[-4]  # origin candle before imbalance
    c2 = df.iloc[-3]  # displacement candle
    c3 = df.iloc[-2]  # reaction / entry candle

    atr = c3["atr_14"]
    ema = c3["ema_20"]
    price = c3["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body_c2 = abs(c2["close"] - c2["open"])
    body_c3 = abs(c3["close"] - c3["open"])

    if body_c2 <= 0 or body_c3 <= 0:
        return None

    structure = df.iloc[-24:-4]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # BULLISH FVG
    # =========================================================
    bullish_gap_exists = c1["high"] < c3["low"]
    fvg_top = c3["low"]
    fvg_bottom = c1["high"]
    gap_size = fvg_top - fvg_bottom

    bullish_displacement = (
        c2["close"] > c2["open"]
        and body_c2 > atr * 0.35
        and c2["close"] > c1["high"]
    )

    bullish_context = price > ema

    in_fvg_zone = (
        c3["low"] <= fvg_top
        and c3["high"] >= fvg_bottom
    )

    reaction = (
        c3["low"] <= fvg_top
        and c3["close"] > c3["open"]
        and body_c3 > atr * 0.20
    )

    extension = abs(c3["close"] - fvg_top)
    if extension > atr * 0.50:
        return None

    weak_structure = c3["close"] < fvg_bottom

    if (
        bullish_gap_exists
        and gap_size > atr * 0.15
        and bullish_displacement
        and bullish_context
        and in_fvg_zone
        and reaction
        and not weak_structure
    ):
        sl_reference = round(fvg_bottom - sl_buffer, 2)

        if recent_high > c3["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = c3["close"] + max(gap_size * 2, atr * 1.2)
            target_model = "MEASURED_FVG_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            displacement_body=body_c2,
            reaction_body=body_c3,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FVG",
            "entry_model": "FVG_RETRACE_REACTION",
            "pattern_height": gap_size,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_displacement_reaction",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish FVG -> retrace into gap "
                f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} -> "
                f"reaction confirmed -> SL below FVG {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    # =========================================================
    # BEARISH FVG
    # =========================================================
    bearish_gap_exists = c1["low"] > c3["high"]
    fvg_top = c1["low"]
    fvg_bottom = c3["high"]
    gap_size = fvg_top - fvg_bottom

    bearish_displacement = (
        c2["close"] < c2["open"]
        and body_c2 > atr * 0.35
        and c2["close"] < c1["low"]
    )

    bearish_context = price < ema

    in_fvg_zone = (
        c3["high"] >= fvg_bottom
        and c3["low"] <= fvg_top
    )

    reaction = (
        c3["high"] >= fvg_bottom
        and c3["close"] < c3["open"]
        and body_c3 > atr * 0.20
    )

    extension = abs(c3["close"] - fvg_bottom)
    if extension > atr * 0.50:
        return None

    weak_structure = c3["close"] > fvg_top

    if (
        bearish_gap_exists
        and gap_size > atr * 0.15
        and bearish_displacement
        and bearish_context
        and in_fvg_zone
        and reaction
        and not weak_structure
    ):
        sl_reference = round(fvg_top + sl_buffer, 2)

        if recent_low < c3["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = c3["close"] - max(gap_size * 2, atr * 1.2)
            target_model = "MEASURED_FVG_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            displacement_body=body_c2,
            reaction_body=body_c3,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FVG",
            "entry_model": "FVG_RETRACE_REACTION",
            "pattern_height": gap_size,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_displacement_reaction",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish FVG -> retrace into gap "
                f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} -> "
                f"reaction confirmed -> SL above FVG {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    return None