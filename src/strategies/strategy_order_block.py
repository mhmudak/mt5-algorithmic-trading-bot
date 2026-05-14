from config.settings import ATR_MIN, ATR_MAX


ORDER_BLOCK_SL_ATR_MULTIPLIER = 0.20
ORDER_BLOCK_MIN_SL_BUFFER = 2.0
ORDER_BLOCK_MAX_SL_BUFFER = 5.0

ORDER_BLOCK_MAX_EXTENSION_ATR = 0.65
ORDER_BLOCK_RETEST_BUFFER_ATR = 0.25
ORDER_BLOCK_MIN_BODY_ATR = 0.20


def _sl_buffer(atr):
    return min(
        max(atr * ORDER_BLOCK_SL_ATR_MULTIPLIER, ORDER_BLOCK_MIN_SL_BUFFER),
        ORDER_BLOCK_MAX_SL_BUFFER,
    )


def _score_setup(base_score, trigger_body, entry_body, atr, close_aligned, entry_model):
    score = base_score

    if trigger_body > atr * 0.60:
        score += 2

    if trigger_body > atr * 0.80:
        score += 2

    if entry_body > atr * 0.30:
        score += 2

    if close_aligned:
        score += 2

    if entry_model == "OB_RETEST_PRECISION":
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 30:
        return None

    entry = df.iloc[-2]
    trigger = df.iloc[-3]
    ob_candle = df.iloc[-4]
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    trigger_body = abs(trigger["close"] - trigger["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if trigger_body <= 0 or entry_body <= 0:
        return None

    if entry_body < atr * ORDER_BLOCK_MIN_BODY_ATR:
        return None

    ob_high = ob_candle["high"]
    ob_low = ob_candle["low"]
    zone_height = ob_high - ob_low

    if zone_height <= 0:
        return None

    structure = df.iloc[-24:-4]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)
    retest_buffer = atr * ORDER_BLOCK_RETEST_BUFFER_ATR

    # =========================
    # Bullish Order Block
    # Last bearish candle before strong bullish displacement
    # =========================
    bearish_ob = ob_candle["close"] < ob_candle["open"]

    bullish_displacement = (
        trigger["close"] > trigger["open"]
        and trigger_body > atr * 0.50
        and trigger["close"] > ob_high
    )

    revisited_bullish_ob = (
        entry["low"] <= ob_high + retest_buffer
        and entry["close"] >= ob_low
    )

    bullish_confirmation = (
        entry["close"] > entry["open"]
        and price > ema
        and entry_body > atr * 0.20
    )

    extension_from_ob = entry["close"] - ob_high
    not_late = (
        extension_from_ob >= 0
        and extension_from_ob <= atr * ORDER_BLOCK_MAX_EXTENSION_ATR
    )

    precise_retest = (
        entry["low"] <= ob_high + retest_buffer
        and entry["close"] > ob_high
    )

    if (
        bearish_ob
        and bullish_displacement
        and revisited_bullish_ob
        and bullish_confirmation
        and not_late
    ):
        entry_model = "OB_RETEST_PRECISION" if precise_retest else "OB_RETEST_CONTINUATION"

        sl_reference = round(ob_low - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(zone_height * 2, atr * 1.2)
            target_model = "MEASURED_ORDER_BLOCK_MOVE"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=89,
            trigger_body=trigger_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
            entry_model=entry_model,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "ORDER_BLOCK",
            "entry_model": entry_model,
            "pattern_height": zone_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_displacement_retest",
            "direction_context": "price_above_ema",
            "entry_extension": round(extension_from_ob, 2),
            "reason": (
                f"Bullish order block -> bearish base candle zone "
                f"{round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bullish displacement confirmed -> {entry_model} -> "
                f"entry extension {round(extension_from_ob, 2)} -> "
                f"SL below OB low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # Bearish Order Block
    # Last bullish candle before strong bearish displacement
    # =========================
    bullish_ob = ob_candle["close"] > ob_candle["open"]

    bearish_displacement = (
        trigger["close"] < trigger["open"]
        and trigger_body > atr * 0.50
        and trigger["close"] < ob_low
    )

    revisited_bearish_ob = (
        entry["high"] >= ob_low - retest_buffer
        and entry["close"] <= ob_high
    )

    bearish_confirmation = (
        entry["close"] < entry["open"]
        and price < ema
        and entry_body > atr * 0.20
    )

    extension_from_ob = ob_low - entry["close"]
    not_late = (
        extension_from_ob >= 0
        and extension_from_ob <= atr * ORDER_BLOCK_MAX_EXTENSION_ATR
    )

    precise_retest = (
        entry["high"] >= ob_low - retest_buffer
        and entry["close"] < ob_low
    )

    if (
        bullish_ob
        and bearish_displacement
        and revisited_bearish_ob
        and bearish_confirmation
        and not_late
    ):
        entry_model = "OB_RETEST_PRECISION" if precise_retest else "OB_RETEST_CONTINUATION"

        sl_reference = round(ob_high + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(zone_height * 2, atr * 1.2)
            target_model = "MEASURED_ORDER_BLOCK_MOVE"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=89,
            trigger_body=trigger_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
            entry_model=entry_model,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "ORDER_BLOCK",
            "entry_model": entry_model,
            "pattern_height": zone_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_displacement_retest",
            "direction_context": "price_below_ema",
            "entry_extension": round(extension_from_ob, 2),
            "reason": (
                f"Bearish order block -> bullish base candle zone "
                f"{round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bearish displacement confirmed -> {entry_model} -> "
                f"entry extension {round(extension_from_ob, 2)} -> "
                f"SL above OB high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    return None