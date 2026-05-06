from config.settings import ATR_MIN, ATR_MAX


BREAKER_LOOKBACK = 35

BREAKER_MIN_DISPLACEMENT_ATR = 0.35
BREAKER_MIN_REACTION_BODY_ATR = 0.20

BREAKER_RETEST_ATR_BUFFER = 0.30
BREAKER_MIN_RETEST_BUFFER = 1.0

BREAKER_SL_ATR_MULTIPLIER = 0.20
BREAKER_MIN_SL_BUFFER = 2.0
BREAKER_MAX_SL_BUFFER = 5.0

BREAKER_TARGET_ATR_MIN = 1.5
BREAKER_TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(
        max(atr * BREAKER_SL_ATR_MULTIPLIER, BREAKER_MIN_SL_BUFFER),
        BREAKER_MAX_SL_BUFFER,
    )


def _target_distance(atr, zone_height, structure_range):
    return min(
        max(zone_height * 2, structure_range * 0.50, atr * BREAKER_TARGET_ATR_MIN),
        atr * BREAKER_TARGET_ATR_MAX,
    )


def _score_setup(base_score, displacement_body, reaction_body, atr, clean_retest, close_aligned):
    score = base_score

    if displacement_body > atr * 0.50:
        score += 2

    if displacement_body > atr * 0.75:
        score += 2

    if reaction_body > atr * 0.30:
        score += 2

    if clean_retest:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < BREAKER_LOOKBACK + 5:
        return None

    # Closed candles only
    zone_candle = df.iloc[-5]     # former zone / block candle
    break_candle = df.iloc[-4]    # displacement candle breaking the zone
    retest_candle = df.iloc[-3]   # first return toward zone
    entry = df.iloc[-2]           # rejection / confirmation candle

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    displacement_body = abs(break_candle["close"] - break_candle["open"])
    reaction_body = abs(entry["close"] - entry["open"])
    entry_range = entry["high"] - entry["low"]

    if displacement_body <= 0 or reaction_body <= 0 or entry_range <= 0:
        return None

    if displacement_body < atr * BREAKER_MIN_DISPLACEMENT_ATR:
        return None

    if reaction_body < atr * BREAKER_MIN_REACTION_BODY_ATR:
        return None

    zone_high = max(zone_candle["open"], zone_candle["close"], zone_candle["high"])
    zone_low = min(zone_candle["open"], zone_candle["close"], zone_candle["low"])
    zone_height = zone_high - zone_low

    if zone_height <= 0:
        return None

    recent = df.iloc[-BREAKER_LOOKBACK:-5]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    structure_range = recent_high - recent_low

    if structure_range <= 0:
        return None

    retest_buffer = max(atr * BREAKER_RETEST_ATR_BUFFER, BREAKER_MIN_RETEST_BUFFER)
    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, zone_height, structure_range)

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    # =========================
    # BUY breaker block
    # Former resistance / supply zone breaks upward, then acts as support
    # =========================
    bullish_break = (
        break_candle["close"] > zone_high
        and break_candle["close"] > break_candle["open"]
    )

    retest_zone_from_above = (
        retest_candle["low"] <= zone_high + retest_buffer
        or entry["low"] <= zone_high + retest_buffer
    )

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and entry["close"] > zone_high
        and price > ema
        and entry["close"] >= entry["low"] + entry_range * 0.60
    )

    if bullish_break and retest_zone_from_above and bullish_reclaim:
        sl_reference = round(min(entry["low"], retest_candle["low"], zone_low) - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "BREAKER_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=93,
            displacement_body=displacement_body,
            reaction_body=reaction_body,
            atr=atr,
            clean_retest=retest_zone_from_above,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "BREAKER_BLOCK",
            "entry_model": "BULLISH_BREAKER_RETEST",
            "pattern_height": target_distance,
            "zone_high": zone_high,
            "zone_low": zone_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_breaker_retest_reclaim",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish breaker block -> zone {round(zone_low, 2)}-{round(zone_high, 2)} "
                f"broken upward then retested -> SL below breaker {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL breaker block
    # Former support / demand zone breaks downward, then acts as resistance
    # =========================
    bearish_break = (
        break_candle["close"] < zone_low
        and break_candle["close"] < break_candle["open"]
    )

    retest_zone_from_below = (
        retest_candle["high"] >= zone_low - retest_buffer
        or entry["high"] >= zone_low - retest_buffer
    )

    bearish_reject = (
        entry["close"] < entry["open"]
        and entry["close"] < zone_low
        and price < ema
        and entry["close"] <= entry["high"] - entry_range * 0.60
    )

    if bearish_break and retest_zone_from_below and bearish_reject:
        sl_reference = round(max(entry["high"], retest_candle["high"], zone_high) + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "BREAKER_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=93,
            displacement_body=displacement_body,
            reaction_body=reaction_body,
            atr=atr,
            clean_retest=retest_zone_from_below,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "BREAKER_BLOCK",
            "entry_model": "BEARISH_BREAKER_RETEST",
            "pattern_height": target_distance,
            "zone_high": zone_high,
            "zone_low": zone_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_breaker_retest_rejection",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish breaker block -> zone {round(zone_low, 2)}-{round(zone_high, 2)} "
                f"broken downward then retested -> SL above breaker {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    return None