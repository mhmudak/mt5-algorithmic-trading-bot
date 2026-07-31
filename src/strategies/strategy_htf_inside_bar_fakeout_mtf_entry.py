
import hashlib

import pandas as pd

from config.settings import (
    IBF_HTF_AGGREGATION_BARS,
    IBF_LOOKBACK_HTF_BARS,
    IBF_EXTENSION_HTF_BARS,
    IBF_REQUIRE_LOCATION,
    IBF_REQUIRE_EXTENSION,
    IBF_REQUIRE_MTF_CONFIRMATION,
    IBF_MTF_CONFIRMATION_BARS,
    IBF_LEVEL_PROXIMITY_PRICE,
    IBF_BREAK_BUFFER_PRICE,
    IBF_CLOSE_BACK_INSIDE_BUFFER,
    IBF_MIN_EXTENSION_PRICE,
    IBF_INSIDE_BAR_MIN_CONTAINMENT,
    IBF_MAX_INSIDE_RANGE_RATIO,
    IBF_MIN_FAKEOUT_BODY_RATIO,
    IBF_SL_BUFFER_PRICE,
    IBF_TARGET_RR,
    IBF_MIN_RR,
    IBF_MIN_SCORE,
)


STRATEGY_NAME = "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY"
PHASE_NAME = "PHASE_6L_HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY"


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
    if df is None or len(df) < IBF_HTF_AGGREGATION_BARS * 6:
        return None

    work = df.copy()

    if "time" in work.columns:
        work = work.sort_values("time").reset_index(drop=True)

    rows = []
    group_size = int(IBF_HTF_AGGREGATION_BARS)

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

    minimum_htf_rows = max(8, IBF_EXTENSION_HTF_BARS + 5)

    if len(rows) < minimum_htf_rows:
        return None

    return pd.DataFrame(rows)


def _recent_structure_levels(htf_before_mother):
    lookback = htf_before_mother.tail(IBF_LOOKBACK_HTF_BARS)

    if len(lookback) < max(5, IBF_EXTENSION_HTF_BARS + 2):
        return None

    return {
        "resistance": float(lookback["high"].max()),
        "support": float(lookback["low"].min()),
    }


def _inside_bar_ok(mother, inside):
    if mother is None or inside is None:
        return False, "missing_mother_or_inside"

    contained = (
        inside["high"] <= mother["high"] - IBF_INSIDE_BAR_MIN_CONTAINMENT
        and inside["low"] >= mother["low"] + IBF_INSIDE_BAR_MIN_CONTAINMENT
    )

    if not contained:
        return False, (
            f"inside_bar_not_contained mother_high={_round(mother['high'])} "
            f"mother_low={_round(mother['low'])} inside_high={_round(inside['high'])} "
            f"inside_low={_round(inside['low'])}"
        )

    range_ratio = inside["range"] / mother["range"] if mother["range"] > 0 else 99

    if range_ratio > IBF_MAX_INSIDE_RANGE_RATIO:
        return False, f"inside_bar_too_large range_ratio={_round(range_ratio, 3)}"

    return True, f"inside_bar_confirmed range_ratio={_round(range_ratio, 3)}"


def _has_extension(htf_before_mother, direction):
    bars = htf_before_mother.tail(IBF_EXTENSION_HTF_BARS)

    if len(bars) < IBF_EXTENSION_HTF_BARS:
        return False, "not_enough_extension_bars"

    first_close = float(bars.iloc[0]["close"])
    last_close = float(bars.iloc[-1]["close"])
    move = last_close - first_close

    if direction == "SELL":
        if move >= IBF_MIN_EXTENSION_PRICE:
            return True, f"bullish_extension_before_bear_trap move={_round(move)}"
        return False, f"missing_bullish_extension move={_round(move)}"

    if direction == "BUY":
        if -move >= IBF_MIN_EXTENSION_PRICE:
            return True, f"bearish_extension_before_bull_trap move={_round(move)}"
        return False, f"missing_bearish_extension move={_round(move)}"

    return False, "invalid_direction"


def _location_ok(mother, fakeout, levels, direction):
    if direction == "SELL":
        resistance = levels["resistance"]

        near_resistance = (
            mother["high"] >= resistance - IBF_LEVEL_PROXIMITY_PRICE
            or fakeout["high"] >= resistance + IBF_BREAK_BUFFER_PRICE
        )

        fake_break = fakeout["high"] >= mother["high"] + IBF_BREAK_BUFFER_PRICE
        close_back_inside = fakeout["close"] <= mother["high"] - IBF_CLOSE_BACK_INSIDE_BUFFER
        close_above_mother_low = fakeout["close"] > mother["low"]

        if near_resistance and fake_break and close_back_inside and close_above_mother_low:
            return True, resistance, (
                f"mother_bar_resistance_fakeout level={_round(resistance)} "
                f"mother_high={_round(mother['high'])} fakeout_high={_round(fakeout['high'])} "
                f"close={_round(fakeout['close'])}"
            )

        return False, resistance, (
            f"no_valid_resistance_fakeout level={_round(resistance)} "
            f"mother_high={_round(mother['high'])} fakeout_high={_round(fakeout['high'])} "
            f"close={_round(fakeout['close'])}"
        )

    if direction == "BUY":
        support = levels["support"]

        near_support = (
            mother["low"] <= support + IBF_LEVEL_PROXIMITY_PRICE
            or fakeout["low"] <= support - IBF_BREAK_BUFFER_PRICE
        )

        fake_break = fakeout["low"] <= mother["low"] - IBF_BREAK_BUFFER_PRICE
        close_back_inside = fakeout["close"] >= mother["low"] + IBF_CLOSE_BACK_INSIDE_BUFFER
        close_below_mother_high = fakeout["close"] < mother["high"]

        if near_support and fake_break and close_back_inside and close_below_mother_high:
            return True, support, (
                f"mother_bar_support_fakeout level={_round(support)} "
                f"mother_low={_round(mother['low'])} fakeout_low={_round(fakeout['low'])} "
                f"close={_round(fakeout['close'])}"
            )

        return False, support, (
            f"no_valid_support_fakeout level={_round(support)} "
            f"mother_low={_round(mother['low'])} fakeout_low={_round(fakeout['low'])} "
            f"close={_round(fakeout['close'])}"
        )

    return False, None, "invalid_direction"


def _fakeout_body_ok(fakeout):
    if fakeout is None:
        return False, "missing_fakeout_candle"

    if fakeout["body_ratio"] >= IBF_MIN_FAKEOUT_BODY_RATIO:
        return True, f"fakeout_body_confirmed body_ratio={_round(fakeout['body_ratio'], 3)}"

    return False, f"fakeout_body_too_small body_ratio={_round(fakeout['body_ratio'], 3)}"


def _mtf_confirmation_ok(df, direction):
    if not IBF_REQUIRE_MTF_CONFIRMATION:
        return True, "mtf_confirmation_disabled"

    if df is None or len(df) < IBF_MTF_CONFIRMATION_BARS + 2:
        return False, "not_enough_mtf_bars"

    recent = df.tail(IBF_MTF_CONFIRMATION_BARS)
    last = recent.iloc[-1]
    prev = recent.iloc[-2]

    if direction == "SELL":
        bearish_last = float(last["close"]) < float(last["open"])
        continuation = float(last["close"]) < float(prev["close"])

        if bearish_last and continuation:
            return True, "m15_bearish_confirmation_after_upside_trap"

        return False, "m15_bearish_confirmation_missing"

    if direction == "BUY":
        bullish_last = float(last["close"]) > float(last["open"])
        continuation = float(last["close"]) > float(prev["close"])

        if bullish_last and continuation:
            return True, "m15_bullish_confirmation_after_downside_trap"

        return False, "m15_bullish_confirmation_missing"

    return False, "invalid_direction"


def _score(inside_ok, location_ok, extension_ok, fakeout_body_ok, mtf_ok):
    score = 88

    if inside_ok:
        score += 2

    if location_ok:
        score += 3

    if extension_ok:
        score += 2

    if fakeout_body_ok:
        score += 2

    if mtf_ok:
        score += 3

    return min(score, 100)


def _build_signal(direction, mother, inside, fakeout, level, score, reasons, pattern_time):
    entry = fakeout["close"]

    if direction == "SELL":
        sl = fakeout["high"] + IBF_SL_BUFFER_PRICE
        risk = sl - entry
        tp = entry - (risk * IBF_TARGET_RR)
        entry_model = "MOTHER_BAR_UPSIDE_FAKEOUT_SELL"

    else:
        sl = fakeout["low"] - IBF_SL_BUFFER_PRICE
        risk = entry - sl
        tp = entry + (risk * IBF_TARGET_RR)
        entry_model = "MOTHER_BAR_DOWNSIDE_FAKEOUT_BUY"

    if risk <= 0:
        return None

    rr = round(abs(entry - tp) / risk, 2)

    if rr < IBF_MIN_RR:
        return None

    setup_seed = f"{STRATEGY_NAME}:{direction}:{entry_model}:{pattern_time}:{round(entry, 2)}"
    setup_hash = hashlib.md5(setup_seed.encode("utf-8")).hexdigest()[:10]

    return {
        "phase": PHASE_NAME,
        "strategy": STRATEGY_NAME,
        "signal": direction,
        "entry_model": entry_model,
        "setup_id": f"IBF-{direction}-{setup_hash}",
        "score": score,
        "min_required_score": IBF_MIN_SCORE,
        "entry_reference": _round(entry),
        "sl_reference": _round(sl),
        "tp_reference": _round(tp),
        "rr": rr,
        "risk_reward": rr,
        "sl_model": "FAKEOUT_EXTREME_SL",
        "target_model": "FIXED_RR_TARGET_KEY_LEVEL_LADDER_ELIGIBLE",
        "structural_level": _round(level),
        "mother_high": _round(mother["high"]),
        "mother_low": _round(mother["low"]),
        "inside_high": _round(inside["high"]),
        "inside_low": _round(inside["low"]),
        "fakeout_high": _round(fakeout["high"]),
        "fakeout_low": _round(fakeout["low"]),
        "fakeout_close": _round(fakeout["close"]),
        "reason": " | ".join(reasons),
        "auto_trade_allowed": True,
        "decision_impact": "MAIN_BOT_RUNTIME_CONTROLLED",
        "orderflow_status": "NOT_REQUIRED_FOR_PHASE6L_INSIDE_BAR_TRAP",
        "duplicate_policy": "setup_id_by_mother_bar_fakeout_time_entry",
    }


def generate_signal(df, htf_df=None):
    if df is None or len(df) < IBF_HTF_AGGREGATION_BARS * 8:
        return None

    if htf_df is None:
        htf_df = _aggregate_m15_to_htf(df)

    if htf_df is None or len(htf_df) < max(8, IBF_EXTENSION_HTF_BARS + 5):
        return None

    htf_df = htf_df.reset_index(drop=True)

    mother_candle = htf_df.iloc[-3]
    inside_candle = htf_df.iloc[-2]
    fakeout_candle = htf_df.iloc[-1]
    htf_before_mother = htf_df.iloc[:-3]

    mother = _candle_parts(mother_candle)
    inside = _candle_parts(inside_candle)
    fakeout = _candle_parts(fakeout_candle)

    if mother is None or inside is None or fakeout is None:
        return None

    levels = _recent_structure_levels(htf_before_mother)

    if not levels:
        return None

    inside_pass, inside_reason = _inside_bar_ok(mother, inside)

    if not inside_pass:
        return None

    fakeout_body_pass, fakeout_body_reason = _fakeout_body_ok(fakeout)

    if not fakeout_body_pass:
        return None

    candidates = []

    sell_fakeout = (
        fakeout["high"] >= mother["high"] + IBF_BREAK_BUFFER_PRICE
        and fakeout["close"] <= mother["high"] - IBF_CLOSE_BACK_INSIDE_BUFFER
    )

    buy_fakeout = (
        fakeout["low"] <= mother["low"] - IBF_BREAK_BUFFER_PRICE
        and fakeout["close"] >= mother["low"] + IBF_CLOSE_BACK_INSIDE_BUFFER
    )

    if sell_fakeout:
        candidates.append("SELL")

    if buy_fakeout:
        candidates.append("BUY")

    if not candidates:
        return None

    best_signal = None

    for direction in candidates:
        reasons = [inside_reason, fakeout_body_reason]

        location_pass, level, location_reason = _location_ok(mother, fakeout, levels, direction)
        reasons.append(location_reason)

        if IBF_REQUIRE_LOCATION and not location_pass:
            continue

        extension_pass, extension_reason = _has_extension(htf_before_mother, direction)
        reasons.append(extension_reason)

        if IBF_REQUIRE_EXTENSION and not extension_pass:
            continue

        mtf_pass, mtf_reason = _mtf_confirmation_ok(df, direction)
        reasons.append(mtf_reason)

        if IBF_REQUIRE_MTF_CONFIRMATION and not mtf_pass:
            continue

        score = _score(
            inside_ok=inside_pass,
            location_ok=location_pass,
            extension_ok=extension_pass,
            fakeout_body_ok=fakeout_body_pass,
            mtf_ok=mtf_pass,
        )

        if score < IBF_MIN_SCORE:
            continue

        signal = _build_signal(
            direction=direction,
            mother=mother,
            inside=inside,
            fakeout=fakeout,
            level=level,
            score=score,
            reasons=reasons,
            pattern_time=fakeout_candle.get("time", len(htf_df)),
        )

        if signal is None:
            continue

        if best_signal is None or signal["score"] > best_signal["score"]:
            best_signal = signal

    return best_signal
