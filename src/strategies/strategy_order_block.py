from config.settings import ATR_MIN, ATR_MAX


ORDER_BLOCK_SL_ATR_MULTIPLIER = 0.20
ORDER_BLOCK_MIN_SL_BUFFER = 2.0
ORDER_BLOCK_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * ORDER_BLOCK_SL_ATR_MULTIPLIER, ORDER_BLOCK_MIN_SL_BUFFER),
        ORDER_BLOCK_MAX_SL_BUFFER,
    )


def _score_setup(base_score, trigger_body, entry_body, atr, close_aligned):
    score = base_score

    if trigger_body > atr * 0.60:
        score += 2

    if trigger_body > atr * 0.80:
        score += 2

    if entry_body > atr * 0.30:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 30:
        return None

    # Logic:
    # - detect displacement candle
    # - take the last opposite candle before displacement as order block
    # - require revisit / respect of zone
    # - confirmation on latest closed candle

    entry = df.iloc[-2]
    trigger = df.iloc[-3]
    ob_candle = df.iloc[-4]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    trigger_body = abs(trigger["close"] - trigger["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if trigger_body <= 0 or entry_body <= 0:
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
        entry["low"] <= ob_high
        and entry["close"] >= ob_low
    )

    bullish_confirmation = (
        entry["close"] > entry["open"]
        and price > ema
        and entry_body > atr * 0.20
    )

    if (
        bearish_ob
        and bullish_displacement
        and revisited_bullish_ob
        and bullish_confirmation
    ):
        sl_reference = round(ob_low - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(zone_height * 2, atr * 1.2)
            target_model = "MEASURED_ORDER_BLOCK_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=89,
            trigger_body=trigger_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "ORDER_BLOCK",
            "entry_model": "OB_RETEST_CONTINUATION",
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
            "reason": (
                f"Bullish order block -> bearish base candle zone "
                f"{round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bullish displacement confirmed -> revisit respected -> "
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
        entry["high"] >= ob_low
        and entry["close"] <= ob_high
    )

    bearish_confirmation = (
        entry["close"] < entry["open"]
        and price < ema
        and entry_body > atr * 0.20
    )

    if (
        bullish_ob
        and bearish_displacement
        and revisited_bearish_ob
        and bearish_confirmation
    ):
        sl_reference = round(ob_high + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(zone_height * 2, atr * 1.2)
            target_model = "MEASURED_ORDER_BLOCK_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=89,
            trigger_body=trigger_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "ORDER_BLOCK",
            "entry_model": "OB_RETEST_CONTINUATION",
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
            "reason": (
                f"Bearish order block -> bullish base candle zone "
                f"{round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bearish displacement confirmed -> revisit respected -> "
                f"SL above OB high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    return None