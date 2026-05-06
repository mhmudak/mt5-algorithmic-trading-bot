from config.settings import ATR_MIN, ATR_MAX

ORB_WINDOW = 15

ORB_MIN_BODY_ATR = 0.30
ORB_CLOSE_STRENGTH = 0.65

ORB_SL_ATR_MULTIPLIER = 0.25
ORB_MIN_SL_BUFFER = 1.5
ORB_MAX_SL_BUFFER = 5.0

ORB_TP_EXTENSION_MULTIPLIER = 0.75
ORB_MIN_TP_ATR_MULTIPLIER = 1.2
ORB_MAX_TP_ATR_MULTIPLIER = 3.0


def _sl_buffer(atr, orb_width):
    return min(
        max(atr * ORB_SL_ATR_MULTIPLIER, orb_width * 0.08, ORB_MIN_SL_BUFFER),
        ORB_MAX_SL_BUFFER,
    )


def _target_distance(atr, orb_width):
    return min(
        max(orb_width * ORB_TP_EXTENSION_MULTIPLIER, atr * ORB_MIN_TP_ATR_MULTIPLIER),
        atr * ORB_MAX_TP_ATR_MULTIPLIER,
    )


def _score_setup(base_score, body, atr, close_strength, ema_aligned, entry_model):
    score = base_score

    if body > atr * 0.40:
        score += 2

    if body > atr * 0.60:
        score += 2

    if close_strength >= 0.75:
        score += 2

    if ema_aligned:
        score += 2

    if entry_model == "WAIT_RETEST":
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < ORB_WINDOW + 5:
        return None

    data = df.iloc[-(ORB_WINDOW + 5):-2]

    orb_high = data["high"].max()
    orb_low = data["low"].min()
    orb_width = orb_high - orb_low

    if orb_width <= 0:
        return None

    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * ORB_MIN_BODY_ATR:
        return None

    close_from_low = (entry["close"] - entry["low"]) / candle_range
    close_from_high = (entry["high"] - entry["close"]) / candle_range

    sl_buffer = _sl_buffer(atr, orb_width)
    target_distance = _target_distance(atr, orb_width)

    max_immediate = min(atr * 0.35, orb_width * 0.20)
    max_retest = min(atr * 0.80, orb_width * 0.45)

    # =========================
    # BUY ORB
    # =========================
    if price > orb_high and price > ema:
        breakout_distance = price - orb_high

        if breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        elif breakout_distance <= max_retest:
            entry_model = "WAIT_RETEST"
        else:
            return None

        bullish_momentum = (
            entry["close"] > entry["open"]
            and close_from_low >= ORB_CLOSE_STRENGTH
        )

        if not bullish_momentum:
            return None

        # Tight invalidation near the breakout level.
        # If price fully returns inside the ORB, the breakout thesis is weakened.
        sl_reference = round(orb_high - sl_buffer, 2)
        tp_reference = round(orb_high + target_distance, 2)

        if sl_reference >= price:
            return None

        if tp_reference <= price:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_strength=close_from_low,
            ema_aligned=price > ema,
            entry_model=entry_model,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "ORB",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "ORB_RANGE_EXTENSION",
            "momentum": "bullish_orb_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"ORB BUY ({entry_model}) -> range {round(orb_low, 2)}-{round(orb_high, 2)} -> "
                f"breakout distance {round(breakout_distance, 2)} -> "
                f"SL below breakout level {sl_reference} -> "
                f"TP ORB extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL ORB
    # =========================
    if price < orb_low and price < ema:
        breakout_distance = orb_low - price

        if breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        elif breakout_distance <= max_retest:
            entry_model = "WAIT_RETEST"
        else:
            return None

        bearish_momentum = (
            entry["close"] < entry["open"]
            and close_from_high >= ORB_CLOSE_STRENGTH
        )

        if not bearish_momentum:
            return None

        # Tight invalidation near the breakout level.
        # If price fully returns inside the ORB, the breakout thesis is weakened.
        sl_reference = round(orb_low + sl_buffer, 2)
        tp_reference = round(orb_low - target_distance, 2)

        if sl_reference <= price:
            return None

        if tp_reference >= price:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_strength=close_from_high,
            ema_aligned=price < ema,
            entry_model=entry_model,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "ORB",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "ORB_RANGE_EXTENSION",
            "momentum": "bearish_orb_breakout",
            "direction_context": "price_below_ema",
            "reason": (
                f"ORB SELL ({entry_model}) -> range {round(orb_low, 2)}-{round(orb_high, 2)} -> "
                f"breakout distance {round(breakout_distance, 2)} -> "
                f"SL above breakout level {sl_reference} -> "
                f"TP ORB extension {tp_reference} -> price below EMA"
            ),
        }

    return None