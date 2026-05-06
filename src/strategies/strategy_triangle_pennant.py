from config.settings import ATR_MIN, ATR_MAX


TRIANGLE_MIN_POLE_ATR = 0.80
TRIANGLE_MIN_BODY_ATR = 0.30
TRIANGLE_MAX_EXTENSION_ATR = 0.80

TRIANGLE_SL_ATR_MULTIPLIER = 0.20
TRIANGLE_MIN_SL_BUFFER = 2.0
TRIANGLE_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * TRIANGLE_SL_ATR_MULTIPLIER, TRIANGLE_MIN_SL_BUFFER),
        TRIANGLE_MAX_SL_BUFFER,
    )


def _score_setup(base_score, pole_body, entry_body, atr, close_aligned):
    score = base_score

    if pole_body > atr * 1.0:
        score += 2

    if pole_body > atr * 1.3:
        score += 2

    if entry_body > atr * 0.45:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 25:
        return None

    # We use:
    # - pole around -8
    # - consolidation from -7 to -3
    # - confirmation candle at -2
    pole = df.iloc[-8]
    consolidation = df.iloc[-7:-2]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    pole_body = abs(pole["close"] - pole["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if pole_body < atr * TRIANGLE_MIN_POLE_ATR:
        return None

    if entry_body < atr * TRIANGLE_MIN_BODY_ATR:
        return None

    highs = consolidation["high"].tolist()
    lows = consolidation["low"].tolist()

    if len(highs) < 4 or len(lows) < 4:
        return None

    # =========================
    # Compression structure
    # =========================
    descending_highs = all(highs[i] >= highs[i + 1] for i in range(len(highs) - 1))
    ascending_lows = all(lows[i] <= lows[i + 1] for i in range(len(lows) - 1))

    if not (descending_highs and ascending_lows):
        return None

    triangle_high = max(highs)
    triangle_low = min(lows)
    triangle_height = triangle_high - triangle_low

    if triangle_height <= atr * 0.50:
        return None

    sl_buffer = _sl_buffer(atr)

    # Recent structure for target selection
    recent = df.iloc[-24:-8]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    # =========================
    # Bullish pennant / triangle continuation
    # =========================
    bullish_pole = pole["close"] > pole["open"]

    bullish_breakout_distance = entry["close"] - triangle_high

    bullish_breakout = (
        entry["close"] > entry["open"]
        and entry["close"] > triangle_high
        and price > ema
        and entry_body > atr * TRIANGLE_MIN_BODY_ATR
        and bullish_breakout_distance >= 0
        and bullish_breakout_distance <= atr * TRIANGLE_MAX_EXTENSION_ATR
    )

    if bullish_pole and bullish_breakout:
        sl_reference = round(triangle_low - sl_buffer, 2)

        measured_target = entry["close"] + max(triangle_height, atr * 1.5)

        if recent_high > entry["close"]:
            tp_reference = max(recent_high, measured_target)
            target_model = "RECENT_HIGH_OR_MEASURED_MOVE"
        else:
            tp_reference = measured_target
            target_model = "MEASURED_TRIANGLE_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=88,
            pole_body=pole_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "TRIANGLE_PENNANT",
            "entry_model": "TRIANGLE_BREAKOUT_CONTINUATION",
            "pattern_height": triangle_height,
            "triangle_high": triangle_high,
            "triangle_low": triangle_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_triangle_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish triangle/pennant -> strong pole near {round(pole['close'], 2)} -> "
                f"compression range {round(triangle_low, 2)} to {round(triangle_high, 2)} -> "
                f"breakout above {round(triangle_high, 2)} -> "
                f"SL below triangle low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # Bearish pennant / triangle continuation
    # =========================
    bearish_pole = pole["close"] < pole["open"]

    bearish_breakout_distance = triangle_low - entry["close"]

    bearish_breakout = (
        entry["close"] < entry["open"]
        and entry["close"] < triangle_low
        and price < ema
        and entry_body > atr * TRIANGLE_MIN_BODY_ATR
        and bearish_breakout_distance >= 0
        and bearish_breakout_distance <= atr * TRIANGLE_MAX_EXTENSION_ATR
    )

    if bearish_pole and bearish_breakout:
        sl_reference = round(triangle_high + sl_buffer, 2)

        measured_target = entry["close"] - max(triangle_height, atr * 1.5)

        if recent_low < entry["close"]:
            tp_reference = min(recent_low, measured_target)
            target_model = "RECENT_LOW_OR_MEASURED_MOVE"
        else:
            tp_reference = measured_target
            target_model = "MEASURED_TRIANGLE_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=88,
            pole_body=pole_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "TRIANGLE_PENNANT",
            "entry_model": "TRIANGLE_BREAKDOWN_CONTINUATION",
            "pattern_height": triangle_height,
            "triangle_high": triangle_high,
            "triangle_low": triangle_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_triangle_breakdown",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish triangle/pennant -> strong pole near {round(pole['close'], 2)} -> "
                f"compression range {round(triangle_low, 2)} to {round(triangle_high, 2)} -> "
                f"breakdown below {round(triangle_low, 2)} -> "
                f"SL above triangle high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    return None