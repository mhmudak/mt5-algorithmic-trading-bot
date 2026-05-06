from config.settings import ATR_MIN, ATR_MAX


SESSION_ORB_LOOKBACK = 18

SESSION_ORB_MIN_RANGE_ATR = 0.80
SESSION_ORB_MAX_RANGE_ATR = 5.00

SESSION_ORB_RETEST_ATR_BUFFER = 0.30
SESSION_ORB_MIN_RETEST_BUFFER = 1.0

SESSION_ORB_SL_ATR_MULTIPLIER = 0.25
SESSION_ORB_MIN_SL_BUFFER = 2.0
SESSION_ORB_MAX_SL_BUFFER = 6.0

SESSION_ORB_TARGET_RANGE_MULTIPLIER = 1.0
SESSION_ORB_MIN_TARGET_ATR = 1.5
SESSION_ORB_MAX_TARGET_ATR = 3.5


def _sl_buffer(atr):
    return min(
        max(atr * SESSION_ORB_SL_ATR_MULTIPLIER, SESSION_ORB_MIN_SL_BUFFER),
        SESSION_ORB_MAX_SL_BUFFER,
    )


def _target_distance(atr, orb_range):
    return min(
        max(orb_range * SESSION_ORB_TARGET_RANGE_MULTIPLIER, atr * SESSION_ORB_MIN_TARGET_ATR),
        atr * SESSION_ORB_MAX_TARGET_ATR,
    )


def _score_setup(base_score, body, atr, close_quality, clean_retest):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if close_quality:
        score += 2

    if clean_retest:
        score += 3

    return min(score, 99)


def generate_signal(df):
    if len(df) < SESSION_ORB_LOOKBACK + 8:
        return None

    # Closed candles only
    range_data = df.iloc[-(SESSION_ORB_LOOKBACK + 4):-4]
    breakout = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    orb_high = range_data["high"].max()
    orb_low = range_data["low"].min()
    orb_range = orb_high - orb_low

    if orb_range <= 0:
        return None

    if orb_range < atr * SESSION_ORB_MIN_RANGE_ATR:
        return None

    if orb_range > atr * SESSION_ORB_MAX_RANGE_ATR:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if body <= 0 or candle_range <= 0:
        return None

    retest_buffer = max(atr * SESSION_ORB_RETEST_ATR_BUFFER, SESSION_ORB_MIN_RETEST_BUFFER)
    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, orb_range)

    close_from_low = (entry["close"] - entry["low"]) / candle_range
    close_from_high = (entry["high"] - entry["close"]) / candle_range

    # =========================
    # BUY: breakout above ORB high, then retest/reclaim
    # =========================
    breakout_up = (
        breakout["close"] > orb_high
        and breakout["close"] > breakout["open"]
    )

    retest_high = (
        entry["low"] <= orb_high + retest_buffer
        and entry["close"] > orb_high
    )

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and price > ema
        and close_from_low >= 0.60
    )

    if breakout_up and retest_high and bullish_reclaim:
        sl_reference = round(min(entry["low"], orb_high) - sl_buffer, 2)
        tp_reference = round(orb_high + target_distance, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_quality=close_from_low >= 0.70,
            clean_retest=entry["low"] <= orb_high + retest_buffer,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "SESSION_ORB_RETEST",
            "entry_model": "ORB_RETEST_RECLAIM",
            "pattern_height": target_distance,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "orb_range": orb_range,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "SESSION_ORB_RANGE_EXTENSION",
            "momentum": "bullish_orb_retest_reclaim",
            "direction_context": "price_above_ema",
            "reason": (
                f"Session ORB BUY retest -> range {round(orb_low, 2)}-{round(orb_high, 2)} -> "
                f"breakout then retest/reclaim confirmed -> "
                f"SL below retest {sl_reference} -> "
                f"TP ORB extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL: breakout below ORB low, then retest/rejection
    # =========================
    breakout_down = (
        breakout["close"] < orb_low
        and breakout["close"] < breakout["open"]
    )

    retest_low = (
        entry["high"] >= orb_low - retest_buffer
        and entry["close"] < orb_low
    )

    bearish_reclaim = (
        entry["close"] < entry["open"]
        and price < ema
        and close_from_high >= 0.60
    )

    if breakout_down and retest_low and bearish_reclaim:
        sl_reference = round(max(entry["high"], orb_low) + sl_buffer, 2)
        tp_reference = round(orb_low - target_distance, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_quality=close_from_high >= 0.70,
            clean_retest=entry["high"] >= orb_low - retest_buffer,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "SESSION_ORB_RETEST",
            "entry_model": "ORB_RETEST_REJECTION",
            "pattern_height": target_distance,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "orb_range": orb_range,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "SESSION_ORB_RANGE_EXTENSION",
            "momentum": "bearish_orb_retest_rejection",
            "direction_context": "price_below_ema",
            "reason": (
                f"Session ORB SELL retest -> range {round(orb_low, 2)}-{round(orb_high, 2)} -> "
                f"breakdown then retest/rejection confirmed -> "
                f"SL above retest {sl_reference} -> "
                f"TP ORB extension {tp_reference} -> price below EMA"
            ),
        }

    return None