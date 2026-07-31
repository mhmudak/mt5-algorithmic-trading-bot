
import hashlib

import pandas as pd

from config.settings import (
    HRCM_HTF_AGGREGATION_BARS,
    HRCM_LOOKBACK_HTF_BARS,
    HRCM_EXTENSION_HTF_BARS,
    HRCM_REQUIRE_LOCATION,
    HRCM_REQUIRE_EXTENSION,
    HRCM_REQUIRE_MTF_CONFIRMATION,
    HRCM_MTF_CONFIRMATION_BARS,
    HRCM_LEVEL_PROXIMITY_PRICE,
    HRCM_SWEEP_BUFFER_PRICE,
    HRCM_MIN_EXTENSION_PRICE,
    HRCM_MIN_WICK_RATIO,
    HRCM_MAX_BODY_RATIO,
    HRCM_CLOSE_LOCATION_RATIO,
    HRCM_ENGULFING_MIN_BODY_RATIO,
    HRCM_SL_BUFFER_PRICE,
    HRCM_TARGET_RR,
    HRCM_MIN_RR,
    HRCM_MIN_SCORE,
    HRCM_ENABLE_SHOOTING_STAR,
    HRCM_ENABLE_HAMMER,
    HRCM_ENABLE_BEARISH_ENGULFING,
    HRCM_ENABLE_BULLISH_ENGULFING,
)


STRATEGY_NAME = "HTF_REJECTION_CANDLE_MTF_ENTRY"
PHASE_NAME = "PHASE_6K_HTF_REJECTION_CANDLE_MTF_ENTRY"


def _round(value, digits=2):
    try:
        return round(float(value), digits)
    except Exception:
        return value


def _candle_parts(row):
    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])

    candle_range = high - low
    body = abs(close - open_price)

    if candle_range <= 0:
        return None

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "range": candle_range,
        "body": body,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "body_ratio": body / candle_range,
        "upper_wick_ratio": upper_wick / candle_range,
        "lower_wick_ratio": lower_wick / candle_range,
        "close_position_from_low": (close - low) / candle_range,
        "close_position_from_high": (high - close) / candle_range,
    }


def _aggregate_m15_to_htf(df):
    if df is None or len(df) < HRCM_HTF_AGGREGATION_BARS * 6:
        return None

    work = df.copy()

    if "time" in work.columns:
        work = work.sort_values("time").reset_index(drop=True)

    rows = []
    group_size = int(HRCM_HTF_AGGREGATION_BARS)

    for start in range(0, len(work), group_size):
        chunk = work.iloc[start:start + group_size]

        if len(chunk) < group_size:
            continue

        rows.append(
            {
                "time": chunk.iloc[-1].get("time") if "time" in chunk.columns else start,
                "open": float(chunk.iloc[0]["open"]),
                "high": float(chunk["high"].max()),
                "low": float(chunk["low"].min()),
                "close": float(chunk.iloc[-1]["close"]),
            }
        )

    minimum_htf_rows = max(8, HRCM_EXTENSION_HTF_BARS + 4)

    if len(rows) < minimum_htf_rows:
        return None

    return pd.DataFrame(rows)


def _recent_structure_levels(htf_before_pattern):
    lookback = htf_before_pattern.tail(HRCM_LOOKBACK_HTF_BARS)

    if len(lookback) < max(6, HRCM_EXTENSION_HTF_BARS + 2):
        return None

    resistance = float(lookback["high"].max())
    support = float(lookback["low"].min())

    return {
        "resistance": resistance,
        "support": support,
    }


def _has_extension(htf_before_pattern, direction):
    bars = htf_before_pattern.tail(HRCM_EXTENSION_HTF_BARS)

    if len(bars) < HRCM_EXTENSION_HTF_BARS:
        return False, "not_enough_extension_bars"

    first_close = float(bars.iloc[0]["close"])
    last_close = float(bars.iloc[-1]["close"])
    move = last_close - first_close

    if direction == "SELL":
        if move >= HRCM_MIN_EXTENSION_PRICE:
            return True, f"bullish_extension_before_bearish_rejection move={_round(move)}"
        return False, f"missing_bullish_extension move={_round(move)}"

    if direction == "BUY":
        if -move >= HRCM_MIN_EXTENSION_PRICE:
            return True, f"bearish_extension_before_bullish_rejection move={_round(move)}"
        return False, f"missing_bearish_extension move={_round(move)}"

    return False, "invalid_direction"


def _location_ok(parts, levels, direction):
    if direction == "SELL":
        resistance = levels["resistance"]

        swept_or_touched = (
            parts["high"] >= resistance - HRCM_LEVEL_PROXIMITY_PRICE
            or parts["high"] >= resistance + HRCM_SWEEP_BUFFER_PRICE
        )
        closed_back_below = parts["close"] < resistance

        if swept_or_touched and closed_back_below:
            return True, resistance, (
                f"htf_resistance_rejection level={_round(resistance)} "
                f"high={_round(parts['high'])} close={_round(parts['close'])}"
            )

        return False, resistance, (
            f"no_resistance_rejection level={_round(resistance)} "
            f"high={_round(parts['high'])} close={_round(parts['close'])}"
        )

    if direction == "BUY":
        support = levels["support"]

        swept_or_touched = (
            parts["low"] <= support + HRCM_LEVEL_PROXIMITY_PRICE
            or parts["low"] <= support - HRCM_SWEEP_BUFFER_PRICE
        )
        closed_back_above = parts["close"] > support

        if swept_or_touched and closed_back_above:
            return True, support, (
                f"htf_support_rejection level={_round(support)} "
                f"low={_round(parts['low'])} close={_round(parts['close'])}"
            )

        return False, support, (
            f"no_support_rejection level={_round(support)} "
            f"low={_round(parts['low'])} close={_round(parts['close'])}"
        )

    return False, None, "invalid_direction"


def _mtf_confirmation_ok(df, direction):
    if not HRCM_REQUIRE_MTF_CONFIRMATION:
        return True, "mtf_confirmation_disabled"

    if df is None or len(df) < HRCM_MTF_CONFIRMATION_BARS + 2:
        return False, "not_enough_mtf_bars"

    recent = df.tail(HRCM_MTF_CONFIRMATION_BARS)
    last = recent.iloc[-1]
    prev = recent.iloc[-2]

    if direction == "SELL":
        bearish_last = float(last["close"]) < float(last["open"])
        continuation = float(last["close"]) < float(prev["close"])

        if bearish_last and continuation:
            return True, "m15_bearish_confirmation"

        return False, "m15_bearish_confirmation_missing"

    if direction == "BUY":
        bullish_last = float(last["close"]) > float(last["open"])
        continuation = float(last["close"]) > float(prev["close"])

        if bullish_last and continuation:
            return True, "m15_bullish_confirmation"

        return False, "m15_bullish_confirmation_missing"

    return False, "invalid_direction"


def _detect_shooting_star(parts):
    return (
        HRCM_ENABLE_SHOOTING_STAR
        and parts["upper_wick_ratio"] >= HRCM_MIN_WICK_RATIO
        and parts["body_ratio"] <= HRCM_MAX_BODY_RATIO
        and parts["close_position_from_high"] >= HRCM_CLOSE_LOCATION_RATIO
    )


def _detect_hammer(parts):
    return (
        HRCM_ENABLE_HAMMER
        and parts["lower_wick_ratio"] >= HRCM_MIN_WICK_RATIO
        and parts["body_ratio"] <= HRCM_MAX_BODY_RATIO
        and parts["close_position_from_low"] >= HRCM_CLOSE_LOCATION_RATIO
    )


def _detect_bearish_engulfing(parts, prev_parts):
    if not HRCM_ENABLE_BEARISH_ENGULFING or prev_parts is None:
        return False

    current_bearish = parts["close"] < parts["open"]
    previous_bullish = prev_parts["close"] > prev_parts["open"]

    body_large_enough = parts["body_ratio"] >= HRCM_ENGULFING_MIN_BODY_RATIO

    engulfs_body = (
        parts["open"] >= prev_parts["close"]
        and parts["close"] <= prev_parts["open"]
    )

    return current_bearish and previous_bullish and body_large_enough and engulfs_body


def _detect_bullish_engulfing(parts, prev_parts):
    if not HRCM_ENABLE_BULLISH_ENGULFING or prev_parts is None:
        return False

    current_bullish = parts["close"] > parts["open"]
    previous_bearish = prev_parts["close"] < prev_parts["open"]

    body_large_enough = parts["body_ratio"] >= HRCM_ENGULFING_MIN_BODY_RATIO

    engulfs_body = (
        parts["open"] <= prev_parts["close"]
        and parts["close"] >= prev_parts["open"]
    )

    return current_bullish and previous_bearish and body_large_enough and engulfs_body


def _score(parts, pattern_type, location_ok, extension_ok, mtf_ok):
    score = 88

    if pattern_type in ["SHOOTING_STAR", "HAMMER"]:
        score += 3

        if max(parts["upper_wick_ratio"], parts["lower_wick_ratio"]) >= 0.65:
            score += 2

    if pattern_type in ["BEARISH_ENGULFING", "BULLISH_ENGULFING"]:
        score += 4

    if location_ok:
        score += 3

    if extension_ok:
        score += 2

    if mtf_ok:
        score += 2

    return min(score, 100)


def _build_signal(direction, pattern_type, parts, level, score, reasons, pattern_time):
    entry = parts["close"]

    if direction == "SELL":
        sl = parts["high"] + HRCM_SL_BUFFER_PRICE
        risk = sl - entry
        tp = entry - (risk * HRCM_TARGET_RR)

    else:
        sl = parts["low"] - HRCM_SL_BUFFER_PRICE
        risk = entry - sl
        tp = entry + (risk * HRCM_TARGET_RR)

    if risk <= 0:
        return None

    rr = round(abs(entry - tp) / risk, 2)

    if rr < HRCM_MIN_RR:
        return None

    setup_seed = f"{STRATEGY_NAME}:{direction}:{pattern_type}:{pattern_time}:{round(entry, 2)}"
    setup_hash = hashlib.md5(setup_seed.encode("utf-8")).hexdigest()[:10]

    return {
        "phase": PHASE_NAME,
        "strategy": STRATEGY_NAME,
        "signal": direction,
        "entry_model": pattern_type,
        "setup_id": f"HRCM-{direction}-{setup_hash}",
        "score": score,
        "min_required_score": HRCM_MIN_SCORE,
        "entry_reference": _round(entry),
        "sl_reference": _round(sl),
        "tp_reference": _round(tp),
        "rr": rr,
        "risk_reward": rr,
        "sl_model": "HTF_REJECTION_WICK_SL",
        "target_model": "FIXED_RR_TARGET_KEY_LEVEL_LADDER_ELIGIBLE",
        "htf_rejection_pattern": pattern_type,
        "structural_level": _round(level),
        "htf_open": _round(parts["open"]),
        "htf_high": _round(parts["high"]),
        "htf_low": _round(parts["low"]),
        "htf_close": _round(parts["close"]),
        "wick_ratio": _round(
            parts["upper_wick_ratio"] if direction == "SELL" else parts["lower_wick_ratio"],
            3,
        ),
        "body_ratio": _round(parts["body_ratio"], 3),
        "reason": " | ".join(reasons),
        "auto_trade_allowed": True,
        "decision_impact": "MAIN_BOT_RUNTIME_CONTROLLED",
        "orderflow_status": "NOT_REQUIRED_FOR_PHASE6K_CANDLE_REJECTION",
        "duplicate_policy": "setup_id_by_pattern_time_entry",
    }


def generate_signal(df, htf_df=None):
    if df is None or len(df) < HRCM_HTF_AGGREGATION_BARS * 8:
        return None

    if htf_df is None:
        htf_df = _aggregate_m15_to_htf(df)

    if htf_df is None or len(htf_df) < max(8, HRCM_EXTENSION_HTF_BARS + 4):
        return None

    htf_df = htf_df.reset_index(drop=True)
    pattern_candle = htf_df.iloc[-1]
    previous_candle = htf_df.iloc[-2]
    htf_before_pattern = htf_df.iloc[:-1]

    parts = _candle_parts(pattern_candle)
    prev_parts = _candle_parts(previous_candle)

    if parts is None:
        return None

    levels = _recent_structure_levels(htf_before_pattern)

    if not levels:
        return None

    candidates = []

    if _detect_shooting_star(parts):
        candidates.append(("SELL", "SHOOTING_STAR"))

    if _detect_bearish_engulfing(parts, prev_parts):
        candidates.append(("SELL", "BEARISH_ENGULFING"))

    if _detect_hammer(parts):
        candidates.append(("BUY", "HAMMER"))

    if _detect_bullish_engulfing(parts, prev_parts):
        candidates.append(("BUY", "BULLISH_ENGULFING"))

    if not candidates:
        return None

    best_signal = None

    for direction, pattern_type in candidates:
        reasons = [f"pattern={pattern_type}"]

        location_pass, level, location_reason = _location_ok(parts, levels, direction)
        reasons.append(location_reason)

        if HRCM_REQUIRE_LOCATION and not location_pass:
            continue

        extension_pass, extension_reason = _has_extension(htf_before_pattern, direction)
        reasons.append(extension_reason)

        if HRCM_REQUIRE_EXTENSION and not extension_pass:
            continue

        mtf_pass, mtf_reason = _mtf_confirmation_ok(df, direction)
        reasons.append(mtf_reason)

        if HRCM_REQUIRE_MTF_CONFIRMATION and not mtf_pass:
            continue

        score = _score(parts, pattern_type, location_pass, extension_pass, mtf_pass)

        if score < HRCM_MIN_SCORE:
            continue

        signal = _build_signal(
            direction=direction,
            pattern_type=pattern_type,
            parts=parts,
            level=level,
            score=score,
            reasons=reasons,
            pattern_time=pattern_candle.get("time", len(htf_df)),
        )

        if signal is None:
            continue

        if best_signal is None or signal["score"] > best_signal["score"]:
            best_signal = signal

    return best_signal
