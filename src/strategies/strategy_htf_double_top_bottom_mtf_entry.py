
import hashlib

import pandas as pd

from config.settings import (
    DTB_HTF_AGGREGATION_BARS,
    DTB_LOOKBACK_HTF_BARS,
    DTB_SWING_WINDOW,
    DTB_MIN_SEPARATION_BARS,
    DTB_MAX_SEPARATION_BARS,
    DTB_PEAK_TOLERANCE_PRICE,
    DTB_TROUGH_TOLERANCE_PRICE,
    DTB_MIN_NECKLINE_DISTANCE,
    DTB_BREAK_BUFFER_PRICE,
    DTB_RETEST_TOLERANCE_PRICE,
    DTB_CLOSE_BACK_BUFFER_PRICE,
    DTB_REQUIRE_MTF_CONFIRMATION,
    DTB_MTF_CONFIRMATION_BARS,
    DTB_MIN_RETEST_BODY_RATIO,
    DTB_SL_BUFFER_PRICE,
    DTB_TARGET_RR,
    DTB_MIN_RR,
    DTB_MIN_SCORE,
)


STRATEGY_NAME = "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"
PHASE_NAME = "PHASE_6M_HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"


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

    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "range": candle_range,
        "body": body,
        "body_ratio": body / candle_range,
    }


def _aggregate_m15_to_htf(df):
    if df is None or len(df) < DTB_HTF_AGGREGATION_BARS * 8:
        return None

    work = df.copy()

    if "time" in work.columns:
        work = work.sort_values("time").reset_index(drop=True)

    rows = []
    group_size = int(DTB_HTF_AGGREGATION_BARS)

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

    if len(rows) < 8:
        return None

    return pd.DataFrame(rows)


def _swing_high_indexes(htf):
    indexes = []
    w = int(DTB_SWING_WINDOW)

    for i in range(w, len(htf) - w):
        current_high = float(htf.iloc[i]["high"])
        left = htf.iloc[i - w:i]["high"].max()
        right = htf.iloc[i + 1:i + w + 1]["high"].max()

        if current_high >= float(left) and current_high >= float(right):
            indexes.append(i)

    # The second top can be the final completed HTF candle before neckline break.
    # In that case there is no right-side candle inside pattern_htf yet.
    edge_index = len(htf) - 1

    if edge_index >= w:
        edge_high = float(htf.iloc[edge_index]["high"])
        edge_left = htf.iloc[edge_index - w:edge_index]["high"].max()

        if edge_high >= float(edge_left) and edge_index not in indexes:
            indexes.append(edge_index)

    return indexes


def _swing_low_indexes(htf):
    indexes = []
    w = int(DTB_SWING_WINDOW)

    for i in range(w, len(htf) - w):
        current_low = float(htf.iloc[i]["low"])
        left = htf.iloc[i - w:i]["low"].min()
        right = htf.iloc[i + 1:i + w + 1]["low"].min()

        if current_low <= float(left) and current_low <= float(right):
            indexes.append(i)

    # The second bottom can be the final completed HTF candle before neckline break.
    # In that case there is no right-side candle inside pattern_htf yet.
    edge_index = len(htf) - 1

    if edge_index >= w:
        edge_low = float(htf.iloc[edge_index]["low"])
        edge_left = htf.iloc[edge_index - w:edge_index]["low"].min()

        if edge_low <= float(edge_left) and edge_index not in indexes:
            indexes.append(edge_index)

    return indexes


def _find_best_double_top(pattern_htf):
    peaks = _swing_high_indexes(pattern_htf)

    best = None

    for a_pos, a in enumerate(peaks):
        for b in peaks[a_pos + 1:]:
            separation = b - a

            if separation < DTB_MIN_SEPARATION_BARS or separation > DTB_MAX_SEPARATION_BARS:
                continue

            high_a = float(pattern_htf.iloc[a]["high"])
            high_b = float(pattern_htf.iloc[b]["high"])

            if abs(high_a - high_b) > DTB_PEAK_TOLERANCE_PRICE:
                continue

            between = pattern_htf.iloc[a:b + 1]
            neckline = float(between["low"].min())
            avg_top = (high_a + high_b) / 2
            pattern_depth = avg_top - neckline

            if pattern_depth < DTB_MIN_NECKLINE_DISTANCE:
                continue

            candidate = {
                "first_index": a,
                "second_index": b,
                "first_price": high_a,
                "second_price": high_b,
                "neckline": neckline,
                "pattern_depth": pattern_depth,
                "quality": pattern_depth - abs(high_a - high_b),
            }

            if best is None or candidate["quality"] > best["quality"]:
                best = candidate

    return best


def _find_best_double_bottom(pattern_htf):
    lows = _swing_low_indexes(pattern_htf)

    best = None

    for a_pos, a in enumerate(lows):
        for b in lows[a_pos + 1:]:
            separation = b - a

            if separation < DTB_MIN_SEPARATION_BARS or separation > DTB_MAX_SEPARATION_BARS:
                continue

            low_a = float(pattern_htf.iloc[a]["low"])
            low_b = float(pattern_htf.iloc[b]["low"])

            if abs(low_a - low_b) > DTB_TROUGH_TOLERANCE_PRICE:
                continue

            between = pattern_htf.iloc[a:b + 1]
            neckline = float(between["high"].max())
            avg_bottom = (low_a + low_b) / 2
            pattern_depth = neckline - avg_bottom

            if pattern_depth < DTB_MIN_NECKLINE_DISTANCE:
                continue

            candidate = {
                "first_index": a,
                "second_index": b,
                "first_price": low_a,
                "second_price": low_b,
                "neckline": neckline,
                "pattern_depth": pattern_depth,
                "quality": pattern_depth - abs(low_a - low_b),
            }

            if best is None or candidate["quality"] > best["quality"]:
                best = candidate

    return best


def _break_retest_ok(pattern, break_candle, retest, direction):
    if pattern is None or break_candle is None or retest is None:
        return False, "missing_pattern_break_or_retest"

    neckline = float(pattern["neckline"])

    if direction == "SELL":
        broke_neckline = break_candle["close"] <= neckline - DTB_BREAK_BUFFER_PRICE
        retested_neckline = retest["high"] >= neckline - DTB_RETEST_TOLERANCE_PRICE
        closed_back_below = retest["close"] <= neckline - DTB_CLOSE_BACK_BUFFER_PRICE

        if broke_neckline and retested_neckline and closed_back_below:
            return True, (
                f"double_top_neckline_break_retest neckline={_round(neckline)} "
                f"break_close={_round(break_candle['close'])} retest_high={_round(retest['high'])} "
                f"retest_close={_round(retest['close'])}"
            )

        return False, (
            f"no_double_top_break_retest neckline={_round(neckline)} "
            f"break_close={_round(break_candle['close'])} retest_high={_round(retest['high'])} "
            f"retest_close={_round(retest['close'])}"
        )

    if direction == "BUY":
        broke_neckline = break_candle["close"] >= neckline + DTB_BREAK_BUFFER_PRICE
        retested_neckline = retest["low"] <= neckline + DTB_RETEST_TOLERANCE_PRICE
        closed_back_above = retest["close"] >= neckline + DTB_CLOSE_BACK_BUFFER_PRICE

        if broke_neckline and retested_neckline and closed_back_above:
            return True, (
                f"double_bottom_neckline_break_retest neckline={_round(neckline)} "
                f"break_close={_round(break_candle['close'])} retest_low={_round(retest['low'])} "
                f"retest_close={_round(retest['close'])}"
            )

        return False, (
            f"no_double_bottom_break_retest neckline={_round(neckline)} "
            f"break_close={_round(break_candle['close'])} retest_low={_round(retest['low'])} "
            f"retest_close={_round(retest['close'])}"
        )

    return False, "invalid_direction"


def _retest_body_ok(retest):
    if retest is None:
        return False, "missing_retest_candle"

    if retest["body_ratio"] >= DTB_MIN_RETEST_BODY_RATIO:
        return True, f"retest_body_confirmed body_ratio={_round(retest['body_ratio'], 3)}"

    return False, f"retest_body_too_small body_ratio={_round(retest['body_ratio'], 3)}"


def _mtf_confirmation_ok(df, direction):
    if not DTB_REQUIRE_MTF_CONFIRMATION:
        return True, "mtf_confirmation_disabled"

    if df is None or len(df) < DTB_MTF_CONFIRMATION_BARS + 2:
        return False, "not_enough_mtf_bars"

    recent = df.tail(DTB_MTF_CONFIRMATION_BARS)
    last = recent.iloc[-1]
    prev = recent.iloc[-2]

    if direction == "SELL":
        bearish_last = float(last["close"]) < float(last["open"])
        continuation = float(last["close"]) < float(prev["close"])

        if bearish_last and continuation:
            return True, "m15_bearish_confirmation_after_double_top_retest"

        return False, "m15_bearish_confirmation_missing"

    if direction == "BUY":
        bullish_last = float(last["close"]) > float(last["open"])
        continuation = float(last["close"]) > float(prev["close"])

        if bullish_last and continuation:
            return True, "m15_bullish_confirmation_after_double_bottom_retest"

        return False, "m15_bullish_confirmation_missing"

    return False, "invalid_direction"


def _score(pattern, break_retest_ok, retest_body_ok, mtf_ok):
    score = 88

    if pattern is not None:
        score += 4

        if pattern.get("pattern_depth", 0) >= DTB_MIN_NECKLINE_DISTANCE * 1.5:
            score += 2

    if break_retest_ok:
        score += 3

    if retest_body_ok:
        score += 1

    if mtf_ok:
        score += 3

    return min(score, 100)


def _build_signal(direction, pattern, break_candle, retest, score, reasons, pattern_time):
    entry = retest["close"]
    neckline = float(pattern["neckline"])

    if direction == "SELL":
        sl_base = max(retest["high"], neckline + DTB_BREAK_BUFFER_PRICE)
        sl = sl_base + DTB_SL_BUFFER_PRICE
        risk = sl - entry
        tp = entry - (risk * DTB_TARGET_RR)
        entry_model = "DOUBLE_TOP_NECKLINE_RETEST_SELL"

    else:
        sl_base = min(retest["low"], neckline - DTB_BREAK_BUFFER_PRICE)
        sl = sl_base - DTB_SL_BUFFER_PRICE
        risk = entry - sl
        tp = entry + (risk * DTB_TARGET_RR)
        entry_model = "DOUBLE_BOTTOM_NECKLINE_RETEST_BUY"

    if risk <= 0:
        return None

    rr = round(abs(entry - tp) / risk, 2)

    if rr < DTB_MIN_RR:
        return None

    setup_seed = f"{STRATEGY_NAME}:{direction}:{entry_model}:{pattern_time}:{round(entry, 2)}"
    setup_hash = hashlib.md5(setup_seed.encode("utf-8")).hexdigest()[:10]

    return {
        "phase": PHASE_NAME,
        "strategy": STRATEGY_NAME,
        "signal": direction,
        "entry_model": entry_model,
        "setup_id": f"DTB-{direction}-{setup_hash}",
        "score": score,
        "min_required_score": DTB_MIN_SCORE,
        "entry_reference": _round(entry),
        "sl_reference": _round(sl),
        "tp_reference": _round(tp),
        "rr": rr,
        "risk_reward": rr,
        "sl_model": "NECKLINE_RETEST_EXTREME_SL",
        "target_model": "FIXED_RR_TARGET_KEY_LEVEL_LADDER_ELIGIBLE",
        "neckline": _round(neckline),
        "pattern_depth": _round(pattern["pattern_depth"]),
        "first_extreme_price": _round(pattern["first_price"]),
        "second_extreme_price": _round(pattern["second_price"]),
        "break_close": _round(break_candle["close"]),
        "retest_high": _round(retest["high"]),
        "retest_low": _round(retest["low"]),
        "retest_close": _round(retest["close"]),
        "reason": " | ".join(reasons),
        "auto_trade_allowed": True,
        "decision_impact": "MAIN_BOT_RUNTIME_CONTROLLED",
        "orderflow_status": "NOT_REQUIRED_FOR_PHASE6M_DOUBLE_TOP_BOTTOM",
        "duplicate_policy": "setup_id_by_pattern_time_entry",
    }


def generate_signal(df, htf_df=None):
    if df is None or len(df) < DTB_HTF_AGGREGATION_BARS * 8:
        return None

    if htf_df is None:
        htf_df = _aggregate_m15_to_htf(df)

    if htf_df is None or len(htf_df) < 8:
        return None

    htf_df = htf_df.reset_index(drop=True).tail(DTB_LOOKBACK_HTF_BARS).reset_index(drop=True)

    pattern_htf = htf_df.iloc[:-2]
    break_candle = _candle_parts(htf_df.iloc[-2])
    retest = _candle_parts(htf_df.iloc[-1])

    if len(pattern_htf) < 6 or break_candle is None or retest is None:
        return None

    retest_body_pass, retest_body_reason = _retest_body_ok(retest)

    if not retest_body_pass:
        return None

    candidates = []

    double_top = _find_best_double_top(pattern_htf)

    if double_top is not None:
        ok, reason = _break_retest_ok(double_top, break_candle, retest, "SELL")

        if ok:
            candidates.append(("SELL", double_top, reason))

    double_bottom = _find_best_double_bottom(pattern_htf)

    if double_bottom is not None:
        ok, reason = _break_retest_ok(double_bottom, break_candle, retest, "BUY")

        if ok:
            candidates.append(("BUY", double_bottom, reason))

    if not candidates:
        return None

    best_signal = None

    for direction, pattern, break_retest_reason in candidates:
        reasons = [
            "pattern_geometry=double_top_bottom_confirmed",
            retest_body_reason,
            break_retest_reason,
        ]

        mtf_pass, mtf_reason = _mtf_confirmation_ok(df, direction)
        reasons.append(mtf_reason)

        if DTB_REQUIRE_MTF_CONFIRMATION and not mtf_pass:
            continue

        score = _score(
            pattern=pattern,
            break_retest_ok=True,
            retest_body_ok=retest_body_pass,
            mtf_ok=mtf_pass,
        )

        if score < DTB_MIN_SCORE:
            continue

        signal = _build_signal(
            direction=direction,
            pattern=pattern,
            break_candle=break_candle,
            retest=retest,
            score=score,
            reasons=reasons,
            pattern_time=htf_df.iloc[-1].get("time", len(htf_df)),
        )

        if signal is None:
            continue

        if best_signal is None or signal["score"] > best_signal["score"]:
            best_signal = signal

    return best_signal
