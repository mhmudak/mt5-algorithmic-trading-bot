from config.settings import (
    FRACTAL_LOOKBACK,
    FRACTAL_SWEEP_DISTANCE_MIN,
    FRACTAL_SWEEP_DISTANCE_MAX,
    FRACTAL_SL_DISTANCE,
    FRACTAL_TP_DISTANCE,
    FRACTAL_TP_EXTENDED_DISTANCE,
)


MIN_BODY_ATR_RATIO = 0.10
MIN_WICK_BODY_RATIO = 1.2
MIN_CLOSE_POSITION = 0.60
MAX_CLOSE_DISTANCE_FROM_LEVEL = 3.0


def _find_last_fractal_low(df, lookback=FRACTAL_LOOKBACK):
    """
    Confirmed fractal low:
    middle candle low is lower than two candles before and two candles after.
    Uses only closed candles.
    """
    closed = df.iloc[:-1]

    if len(closed) < 7:
        return None

    start = max(2, len(closed) - lookback)

    for i in range(len(closed) - 3, start - 1, -1):
        low = closed.iloc[i]["low"]

        if (
            low < closed.iloc[i - 1]["low"]
            and low < closed.iloc[i - 2]["low"]
            and low < closed.iloc[i + 1]["low"]
            and low < closed.iloc[i + 2]["low"]
        ):
            return {
                "level": low,
                "index": i,
                "time": closed.iloc[i].get("time"),
            }

    return None


def _find_last_fractal_high(df, lookback=FRACTAL_LOOKBACK):
    """
    Confirmed fractal high:
    middle candle high is higher than two candles before and two candles after.
    Uses only closed candles.
    """
    closed = df.iloc[:-1]

    if len(closed) < 7:
        return None

    start = max(2, len(closed) - lookback)

    for i in range(len(closed) - 3, start - 1, -1):
        high = closed.iloc[i]["high"]

        if (
            high > closed.iloc[i - 1]["high"]
            and high > closed.iloc[i - 2]["high"]
            and high > closed.iloc[i + 1]["high"]
            and high > closed.iloc[i + 2]["high"]
        ):
            return {
                "level": high,
                "index": i,
                "time": closed.iloc[i].get("time"),
            }

    return None


def _score_sweep(base_score, sweep_distance, wick_ratio, close_strength, ema_aligned):
    score = base_score

    if FRACTAL_SWEEP_DISTANCE_MIN <= sweep_distance <= 5.0:
        score += 3

    if wick_ratio >= 1.8:
        score += 3
    elif wick_ratio >= 1.5:
        score += 2

    if close_strength >= 0.75:
        score += 2
    elif close_strength >= 0.65:
        score += 1

    if ema_aligned:
        score += 2

    return min(score, 99)


def _get_structure_targets(df):
    closed = df.iloc[:-1]
    structure = closed.iloc[-FRACTAL_LOOKBACK:]

    return {
        "recent_high": structure["high"].max(),
        "recent_low": structure["low"].min(),
    }


def generate_signal(df):
    if len(df) < FRACTAL_LOOKBACK:
        return None

    candle = df.iloc[-2]  # last closed candle
    atr = candle["atr_14"]
    ema = candle["ema_20"]

    open_price = candle["open"]
    close_price = candle["close"]
    high = candle["high"]
    low = candle["low"]

    body = abs(close_price - open_price)
    candle_range = high - low

    if candle_range <= 0 or atr <= 0:
        return None

    if body < atr * MIN_BODY_ATR_RATIO:
        return None

    lower_wick = min(open_price, close_price) - low
    upper_wick = high - max(open_price, close_price)

    close_position_from_low = (close_price - low) / candle_range
    close_position_from_high = (high - close_price) / candle_range

    fractal_low = _find_last_fractal_low(df)
    fractal_high = _find_last_fractal_high(df)

    targets = _get_structure_targets(df)
    recent_high = targets["recent_high"]
    recent_low = targets["recent_low"]

    candidates = []

    # =========================
    # BUY: sweep below fractal low then bullish rejection
    # =========================
    if fractal_low is not None:
        fractal_level = fractal_low["level"]
        sweep_distance = fractal_level - low
        close_distance = abs(close_price - fractal_level)
        wick_ratio = lower_wick / body if body > 0 else 0

        if (
            FRACTAL_SWEEP_DISTANCE_MIN <= sweep_distance <= FRACTAL_SWEEP_DISTANCE_MAX
            and close_price > fractal_level
            and close_price > open_price
            and lower_wick > body * MIN_WICK_BODY_RATIO
            and close_position_from_low >= MIN_CLOSE_POSITION
            and close_distance <= MAX_CLOSE_DISTANCE_FROM_LEVEL
        ):
            sl_reference = round(low - FRACTAL_SL_DISTANCE, 2)

            if recent_high > close_price:
                tp_reference = recent_high
                target_model = "RECENT_STRUCTURE_HIGH"
            else:
                tp_reference = close_price + FRACTAL_TP_DISTANCE
                target_model = "FIXED_FRACTAL_TARGET"

            # Do not target beyond the extended target in the first version.
            max_allowed_tp = close_price + FRACTAL_TP_EXTENDED_DISTANCE
            tp_reference = round(min(tp_reference, max_allowed_tp), 2)

            score = _score_sweep(
                base_score=90,
                sweep_distance=sweep_distance,
                wick_ratio=wick_ratio,
                close_strength=close_position_from_low,
                ema_aligned=close_price > ema,
            )

            candidates.append(
                {
                    "signal": "BUY",
                    "strategy": "FRACTAL_SWEEP",
                    "entry_model": "SWEEP_REJECTION",
                    "score": score,
                    "fractal_level": fractal_level,
                    "fractal_time": fractal_low["time"],
                    "sweep_low": low,
                    "sweep_distance": round(sweep_distance, 2),
                    "recent_high": recent_high,
                    "recent_low": recent_low,
                    "sl_reference": sl_reference,
                    "tp_reference": tp_reference,
                    "pattern_height": FRACTAL_TP_DISTANCE,
                    "extended_target": FRACTAL_TP_EXTENDED_DISTANCE,
                    "target_model": target_model,
                    "momentum": "bullish_sweep_rejection",
                    "direction_context": (
                        "price_above_ema"
                        if close_price > ema
                        else "counter_ema_reversal"
                    ),
                    "reason": (
                        f"Fractal sweep BUY -> swept below fractal low "
                        f"{round(fractal_level, 2)} by ${round(sweep_distance, 2)} -> "
                        f"closed back above with bullish rejection -> "
                        f"SL below sweep low {sl_reference} -> "
                        f"TP {target_model} {tp_reference}"
                    ),
                }
            )

    # =========================
    # SELL: sweep above fractal high then bearish rejection
    # =========================
    if fractal_high is not None:
        fractal_level = fractal_high["level"]
        sweep_distance = high - fractal_level
        close_distance = abs(close_price - fractal_level)
        wick_ratio = upper_wick / body if body > 0 else 0

        if (
            FRACTAL_SWEEP_DISTANCE_MIN <= sweep_distance <= FRACTAL_SWEEP_DISTANCE_MAX
            and close_price < fractal_level
            and close_price < open_price
            and upper_wick > body * MIN_WICK_BODY_RATIO
            and close_position_from_high >= MIN_CLOSE_POSITION
            and close_distance <= MAX_CLOSE_DISTANCE_FROM_LEVEL
        ):
            sl_reference = round(high + FRACTAL_SL_DISTANCE, 2)

            if recent_low < close_price:
                tp_reference = recent_low
                target_model = "RECENT_STRUCTURE_LOW"
            else:
                tp_reference = close_price - FRACTAL_TP_DISTANCE
                target_model = "FIXED_FRACTAL_TARGET"

            # Do not target beyond the extended target in the first version.
            min_allowed_tp = close_price - FRACTAL_TP_EXTENDED_DISTANCE
            tp_reference = round(max(tp_reference, min_allowed_tp), 2)

            score = _score_sweep(
                base_score=90,
                sweep_distance=sweep_distance,
                wick_ratio=wick_ratio,
                close_strength=close_position_from_high,
                ema_aligned=close_price < ema,
            )

            candidates.append(
                {
                    "signal": "SELL",
                    "strategy": "FRACTAL_SWEEP",
                    "entry_model": "SWEEP_REJECTION",
                    "score": score,
                    "fractal_level": fractal_level,
                    "fractal_time": fractal_high["time"],
                    "sweep_high": high,
                    "sweep_distance": round(sweep_distance, 2),
                    "recent_high": recent_high,
                    "recent_low": recent_low,
                    "sl_reference": sl_reference,
                    "tp_reference": tp_reference,
                    "pattern_height": FRACTAL_TP_DISTANCE,
                    "extended_target": FRACTAL_TP_EXTENDED_DISTANCE,
                    "target_model": target_model,
                    "momentum": "bearish_sweep_rejection",
                    "direction_context": (
                        "price_below_ema"
                        if close_price < ema
                        else "counter_ema_reversal"
                    ),
                    "reason": (
                        f"Fractal sweep SELL -> swept above fractal high "
                        f"{round(fractal_level, 2)} by ${round(sweep_distance, 2)} -> "
                        f"closed back below with bearish rejection -> "
                        f"SL above sweep high {sl_reference} -> "
                        f"TP {target_model} {tp_reference}"
                    ),
                }
            )

    if not candidates:
        return None

    return max(candidates, key=lambda item: item["score"])