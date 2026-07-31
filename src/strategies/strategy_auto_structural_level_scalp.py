from __future__ import annotations

import math
from typing import Any


STRATEGY_NAME = "AUTO_STRUCTURAL_LEVEL_SCALP"
PHASE = "PHASE_6G_AUTO_STRUCTURAL_LEVEL_SCALP"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value):
            return default
        return value
    except Exception:
        return default


def _atr(rows: list[dict[str, Any]], period: int) -> float:
    if len(rows) < period + 1:
        return 0.0

    trs = []
    sample = rows[-(period + 1):]

    for idx in range(1, len(sample)):
        current = sample[idx]
        previous = sample[idx - 1]

        high = safe_float(current.get("high"))
        low = safe_float(current.get("low"))
        prev_close = safe_float(previous.get("close"))

        if high <= 0 or low <= 0 or prev_close <= 0:
            continue

        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    return sum(trs) / len(trs) if trs else 0.0


def _is_round_confluence(level: float) -> bool:
    from config.settings import ASLS_ROUND_CONFLUENCE_STEPS

    for step in ASLS_ROUND_CONFLUENCE_STEPS:
        step = float(step)

        if step <= 0:
            continue

        if abs((level / step) - round(level / step)) <= 0.03:
            return True

    return False


def _extract_hour(row: dict[str, Any]) -> int | None:
    value = row.get("time")

    if value is None:
        return None

    try:
        if hasattr(value, "hour"):
            return int(value.hour)

        text = str(value)

        if "T" in text:
            text = text.split("T", 1)[1]

        if " " in text:
            text = text.split(" ", 1)[1]

        return int(text[:2])
    except Exception:
        return None


def _is_ny_window(row: dict[str, Any]) -> bool:
    from config.settings import ASLS_NY_END_HOUR, ASLS_NY_START_HOUR

    hour = _extract_hour(row)

    if hour is None:
        return False

    if ASLS_NY_START_HOUR <= ASLS_NY_END_HOUR:
        return ASLS_NY_START_HOUR <= hour <= ASLS_NY_END_HOUR

    return hour >= ASLS_NY_START_HOUR or hour <= ASLS_NY_END_HOUR


def _add_level(levels: list[dict[str, Any]], price: float, kind: str, source: str, strength: int) -> None:
    if price <= 0:
        return

    levels.append(
        {
            "level": round(price, 2),
            "kind": kind,
            "sources": [source],
            "strength": int(strength),
            "raw_levels": [round(price, 2)],
        }
    )


def _merge_levels(levels: list[dict[str, Any]], merge_distance: float) -> list[dict[str, Any]]:
    if not levels:
        return []

    ordered = sorted(levels, key=lambda item: item["level"])
    clusters: list[dict[str, Any]] = []

    for item in ordered:
        if not clusters or abs(item["level"] - clusters[-1]["level"]) > merge_distance:
            clusters.append(dict(item))
            continue

        cluster = clusters[-1]
        cluster["raw_levels"].extend(item.get("raw_levels", [item["level"]]))
        cluster["sources"].extend(item.get("sources", []))
        cluster["strength"] += item.get("strength", 0)

        # Keep support/resistance identity when mixed; structural side wins.
        if item.get("kind") != "ROUND":
            cluster["kind"] = item.get("kind")

        cluster["level"] = round(
            sum(cluster["raw_levels"]) / len(cluster["raw_levels"]),
            2,
        )

    return clusters


def _collect_structural_levels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from config.settings import (
        ASLS_LEVEL_MERGE_DISTANCE,
        ASLS_LOOKBACK_BARS,
        ASLS_MIN_LEVEL_STRENGTH,
        ASLS_SWING_WINDOW,
        ASLS_TOUCH_DISTANCE,
    )

    window = rows[-ASLS_LOOKBACK_BARS:]

    if len(window) < ASLS_SWING_WINDOW * 2 + 10:
        return []

    levels: list[dict[str, Any]] = []
    w = int(ASLS_SWING_WINDOW)

    for idx in range(w, len(window) - w):
        row = window[idx]
        low = safe_float(row.get("low"))
        high = safe_float(row.get("high"))

        left = window[idx - w:idx]
        right = window[idx + 1:idx + 1 + w]

        left_lows = [safe_float(item.get("low")) for item in left]
        right_lows = [safe_float(item.get("low")) for item in right]
        left_highs = [safe_float(item.get("high")) for item in left]
        right_highs = [safe_float(item.get("high")) for item in right]

        if all(low <= value for value in left_lows + right_lows):
            _add_level(levels, low, "SUPPORT", "recent_swing_low", 3)

        if all(high >= value for value in left_highs + right_highs):
            _add_level(levels, high, "RESISTANCE", "recent_swing_high", 3)

    # Repeated touch levels from lows/highs.
    for row in window:
        _add_level(levels, safe_float(row.get("low")), "SUPPORT", "low_touch_candidate", 1)
        _add_level(levels, safe_float(row.get("high")), "RESISTANCE", "high_touch_candidate", 1)

    # Round levels are confluence only. They do not become valid without structure.
    if window:
        min_price = min(safe_float(row.get("low")) for row in window)
        max_price = max(safe_float(row.get("high")) for row in window)

        for step in [5.0, 25.0, 50.0, 100.0]:
            current = math.floor((min_price - 2) / step) * step

            while current <= max_price + 2:
                _add_level(levels, current, "ROUND", f"round_{step}", 1)
                current += step

    merged = _merge_levels(levels, ASLS_LEVEL_MERGE_DISTANCE)
    confirmed: list[dict[str, Any]] = []

    for level in merged:
        sources = [str(source) for source in level.get("sources", [])]

        has_round = any(source.startswith("round_") for source in sources)

        support_evidence = [
            source for source in sources
            if source in {"recent_swing_low", "low_touch_candidate"}
        ]
        resistance_evidence = [
            source for source in sources
            if source in {"recent_swing_high", "high_touch_candidate"}
        ]

        support_structural = "recent_swing_low" in support_evidence
        resistance_structural = "recent_swing_high" in resistance_evidence

        candidates: list[tuple[str, str, int]] = []

        if support_structural:
            candidates.append(("SUPPORT", "STRUCTURAL_SWING_CONFIRMED", len(support_evidence)))
        elif len(support_evidence) >= 3:
            candidates.append(("SUPPORT", "REPEATED_TOUCH_CONFIRMED", len(support_evidence)))

        if resistance_structural:
            candidates.append(("RESISTANCE", "STRUCTURAL_SWING_CONFIRMED", len(resistance_evidence)))
        elif len(resistance_evidence) >= 3:
            candidates.append(("RESISTANCE", "REPEATED_TOUCH_CONFIRMED", len(resistance_evidence)))

        for kind, confirmation, evidence_count in candidates:
            item = dict(level)
            item["kind"] = kind
            item["confirmation"] = confirmation
            item["evidence_count"] = evidence_count
            item["round_confluence"] = bool(has_round)

            if has_round:
                item["strength"] = int(item.get("strength", 0)) + 1

            if int(item.get("strength", 0)) < ASLS_MIN_LEVEL_STRENGTH:
                continue

            confirmed.append(item)

    return confirmed


def _nearest_level(levels: list[dict[str, Any]], kind: str, price: float) -> dict[str, Any] | None:
    candidates = [item for item in levels if item.get("kind") == kind]

    if not candidates:
        return None

    return min(candidates, key=lambda item: abs(float(item["level"]) - price))


def _levels_by_distance(
    levels: list[dict[str, Any]],
    kind: str,
    price: float,
    side: str | None = None,
) -> list[dict[str, Any]]:
    candidates = [item for item in levels if item.get("kind") == kind]

    if side == "below_or_equal":
        candidates = [item for item in candidates if float(item["level"]) <= price]

    elif side == "above_or_equal":
        candidates = [item for item in candidates if float(item["level"]) >= price]

    return sorted(candidates, key=lambda item: abs(float(item["level"]) - price))


def _target_against_opposite_level(
    *,
    signal: str,
    entry: float,
    levels: list[dict[str, Any]],
) -> tuple[float, str]:
    from config.settings import ASLS_MAX_TARGET_PRICE, ASLS_MIN_TARGET_PRICE, ASLS_TARGET_PRICE

    base_target = float(ASLS_TARGET_PRICE)
    min_target = float(ASLS_MIN_TARGET_PRICE)
    max_target = float(ASLS_MAX_TARGET_PRICE)

    if signal == "BUY":
        raw_tp = entry + base_target
        resistance_candidates = [
            item for item in levels
            if item.get("kind") == "RESISTANCE" and float(item["level"]) > entry + min_target
        ]

        if resistance_candidates:
            nearest = min(resistance_candidates, key=lambda item: float(item["level"]) - entry)
            capped = min(raw_tp, float(nearest["level"]) - 0.55)
            return round(max(entry + min_target, capped), 2), "SCALP_TARGET_CAPPED_BEFORE_RESISTANCE"

        return round(min(entry + max_target, raw_tp), 2), "FIXED_SCALP_TARGET"

    raw_tp = entry - base_target
    support_candidates = [
        item for item in levels
        if item.get("kind") == "SUPPORT" and float(item["level"]) < entry - min_target
    ]

    if support_candidates:
        nearest = max(support_candidates, key=lambda item: float(item["level"]))
        capped = max(raw_tp, float(nearest["level"]) + 0.55)
        return round(min(entry - min_target, capped), 2), "SCALP_TARGET_CAPPED_BEFORE_SUPPORT"

    return round(max(entry - max_target, raw_tp), 2), "FIXED_SCALP_TARGET"


def _rr(signal: str, entry: float, sl: float, tp: float) -> float:
    if signal == "BUY":
        risk = entry - sl
        reward = tp - entry
    else:
        risk = sl - entry
        reward = entry - tp

    if risk <= 0 or reward <= 0:
        return 0.0

    return round(reward / risk, 2)


def _score(
    *,
    base: int,
    level: dict[str, Any],
    rr: float,
    is_ny: bool,
    mode: str,
) -> int:
    from config.settings import ASLS_NY_SESSION_BOOST_ENABLED

    score = int(base)

    if level.get("round_confluence"):
        score += 1

    if rr >= 1.2:
        score += 1

    if ASLS_NY_SESSION_BOOST_ENABLED and is_ny:
        score += 2

    if mode == "BREAK_HOLD_SCALP":
        score += 1

    return min(score, 99)


def _build_signal(
    *,
    signal: str,
    mode: str,
    level: dict[str, Any],
    entry: float,
    sl: float,
    tp: float,
    rr: float,
    score: int,
    atr: float,
    target_model: str,
    trigger_reason: str,
) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "signal": signal,
        "score": score,
        "strategy": STRATEGY_NAME,
        "family": "AUTO_STRUCTURAL_LEVEL_SCALP",
        "entry_model": mode,
        "setup_source_bucket": "AUTO_STRUCTURAL_LEVEL_SCALP",
        "execution_mode": "GLOBAL_RUNTIME_CONTROLLED",
        "entry_reference": round(entry, 2),
        "sl_reference": round(sl, 2),
        "tp_reference": round(tp, 2),
        "pattern_height": round(abs(tp - entry), 2),
        "rr": rr,
        "atr": round(atr, 2),
        "structural_level": round(float(level["level"]), 2),
        "structural_level_type": level.get("kind"),
        "structural_level_strength": level.get("strength"),
        "structural_level_confirmation": level.get("confirmation"),
        "structural_level_sources": level.get("sources"),
        "round_confluence": bool(level.get("round_confluence")),
        "target_model": target_model,
        "orderflow_status": "NOT_CONNECTED_MT5_ONLY",
        "funded_suitable": True,
        "demo_execution_suitable": True,
        "auto_trade_allowed": True,
        "decision_impact": "MAIN_BOT_RUNTIME_CONTROLLED",
        "reason": (
            f"Auto structural level scalp {signal} {mode} -> "
            f"level={round(float(level['level']), 2)} "
            f"type={level.get('kind')} confirmation={level.get('confirmation')} "
            f"entry={round(entry, 2)} sl={round(sl, 2)} tp={round(tp, 2)} "
            f"rr={rr} | {trigger_reason}"
        ),
    }


def generate_signal(df):
    from config.settings import (
        ASLS_ATR_PERIOD,
        ASLS_BOUNCE_ENTRY_OFFSET,
        ASLS_BREAK_BODY_ATR_RATIO,
        ASLS_BREAK_CONFIRM_DISTANCE,
        ASLS_BREAK_CONFIRM_TOLERANCE,
        ASLS_BREAK_ENTRY_OFFSET,
        ASLS_ENTRY_PROXIMITY,
        ASLS_LOOKBACK_BARS,
        ASLS_MAX_BREAK_ENTRY_LATE_DISTANCE,
        ASLS_MAX_ENTRY_DISTANCE_FROM_LEVEL,
        ASLS_MIN_BODY_ATR_RATIO,
        ASLS_MIN_BODY_PRICE,
        ASLS_MIN_RECLAIM_DISTANCE,
        ASLS_MIN_RR,
        ASLS_MIN_WICK_PRICE,
        ASLS_MIN_SCORE,
        ASLS_MIN_WICK_ATR_RATIO,
        ASLS_SL_BUFFER,
        ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP,
    )

    if not ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP:
        return None

    if df is None or len(df) < max(ASLS_LOOKBACK_BARS // 3, ASLS_ATR_PERIOD + 10):
        return None

    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < ASLS_ATR_PERIOD + 10:
        return None

    rows = [row.to_dict() for _, row in closed.iterrows()]
    entry_bar = rows[-1]
    previous_bar = rows[-2]
    atr = _atr(rows, ASLS_ATR_PERIOD)

    if atr <= 0:
        return None

    levels = _collect_structural_levels(rows)

    if not levels:
        return None

    open_price = safe_float(entry_bar.get("open"))
    high = safe_float(entry_bar.get("high"))
    low = safe_float(entry_bar.get("low"))
    close = safe_float(entry_bar.get("close"))
    prev_close = safe_float(previous_bar.get("close"))

    if min(open_price, high, low, close, prev_close) <= 0:
        return None

    candle_range = high - low

    if candle_range <= 0:
        return None

    body = abs(close - open_price)
    body_atr_ratio = body / atr
    body_confirmed = (
        body_atr_ratio >= ASLS_MIN_BODY_ATR_RATIO
        or body >= ASLS_MIN_BODY_PRICE
    )
    close_position = (close - low) / candle_range
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    upper_wick_atr_ratio = upper_wick / atr
    lower_wick_atr_ratio = lower_wick / atr
    upper_wick_confirmed = (
        upper_wick_atr_ratio >= ASLS_MIN_WICK_ATR_RATIO
        or upper_wick >= ASLS_MIN_WICK_PRICE
    )
    lower_wick_confirmed = (
        lower_wick_atr_ratio >= ASLS_MIN_WICK_ATR_RATIO
        or lower_wick >= ASLS_MIN_WICK_PRICE
    )
    is_ny = _is_ny_window(entry_bar)

    support_bounce_candidates = _levels_by_distance(
        levels, "SUPPORT", close, "below_or_equal"
    )
    resistance_bounce_candidates = _levels_by_distance(
        levels, "RESISTANCE", close, "above_or_equal"
    )
    support_break_candidates = _levels_by_distance(
        levels, "SUPPORT", close, "above_or_equal"
    )
    resistance_break_candidates = _levels_by_distance(
        levels, "RESISTANCE", close, "below_or_equal"
    )

    # 1) Support bounce BUY scalp.
    for nearest_support in support_bounce_candidates:
        level_price = float(nearest_support["level"])

        support_touched = low <= level_price + ASLS_ENTRY_PROXIMITY
        support_reclaimed = close >= level_price + ASLS_MIN_RECLAIM_DISTANCE
        entry_distance_from_level = abs(close - level_price)

        if (
            support_touched
            and support_reclaimed
            and entry_distance_from_level <= ASLS_MAX_ENTRY_DISTANCE_FROM_LEVEL
            and lower_wick_confirmed
            and body_confirmed
            and close_position >= 0.55
        ):
            entry = round(level_price + ASLS_BOUNCE_ENTRY_OFFSET, 2)
            sl = round(level_price - ASLS_SL_BUFFER, 2)
            tp, target_model = _target_against_opposite_level(
                signal="BUY",
                entry=entry,
                levels=levels,
            )
            rr = _rr("BUY", entry, sl, tp)

            if rr >= ASLS_MIN_RR:
                score = _score(
                    base=ASLS_MIN_SCORE,
                    level=nearest_support,
                    rr=rr,
                    is_ny=is_ny,
                    mode="BOUNCE_SCALP",
                )
                return _build_signal(
                    signal="BUY",
                    mode="SUPPORT_BOUNCE_SCALP",
                    level=nearest_support,
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    rr=rr,
                    score=score,
                    atr=atr,
                    target_model=target_model,
                    trigger_reason=(
                        f"support_touched={support_touched} "
                        f"reclaimed={support_reclaimed} "
                        f"entry_distance={round(entry_distance_from_level, 2)} "
                        f"body={round(body, 2)} "
                        f"lower_wick={round(lower_wick, 2)} "
                        f"lower_wick_atr={round(lower_wick_atr_ratio, 3)}"
                    ),
                )

    # 2) Resistance bounce SELL scalp.
    for nearest_resistance in resistance_bounce_candidates:
        level_price = float(nearest_resistance["level"])

        resistance_touched = high >= level_price - ASLS_ENTRY_PROXIMITY
        resistance_rejected = close <= level_price - ASLS_MIN_RECLAIM_DISTANCE
        entry_distance_from_level = abs(close - level_price)

        if (
            resistance_touched
            and resistance_rejected
            and entry_distance_from_level <= ASLS_MAX_ENTRY_DISTANCE_FROM_LEVEL
            and upper_wick_confirmed
            and body_confirmed
            and close_position <= 0.45
        ):
            entry = round(level_price - ASLS_BOUNCE_ENTRY_OFFSET, 2)
            sl = round(level_price + ASLS_SL_BUFFER, 2)
            tp, target_model = _target_against_opposite_level(
                signal="SELL",
                entry=entry,
                levels=levels,
            )
            rr = _rr("SELL", entry, sl, tp)

            if rr >= ASLS_MIN_RR:
                score = _score(
                    base=ASLS_MIN_SCORE,
                    level=nearest_resistance,
                    rr=rr,
                    is_ny=is_ny,
                    mode="BOUNCE_SCALP",
                )
                return _build_signal(
                    signal="SELL",
                    mode="RESISTANCE_BOUNCE_SCALP",
                    level=nearest_resistance,
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    rr=rr,
                    score=score,
                    atr=atr,
                    target_model=target_model,
                    trigger_reason=(
                        f"resistance_touched={resistance_touched} "
                        f"rejected={resistance_rejected} "
                        f"entry_distance={round(entry_distance_from_level, 2)} "
                        f"body={round(body, 2)} "
                        f"upper_wick={round(upper_wick, 2)} "
                        f"upper_wick_atr={round(upper_wick_atr_ratio, 3)}"
                    ),
                )

    # 3) Support break-hold SELL scalp.
    for nearest_support in support_break_candidates:
        level_price = float(nearest_support["level"])

        target_break_entry = round(level_price - ASLS_BREAK_ENTRY_OFFSET, 2)
        was_above_or_touching = prev_close >= level_price - ASLS_ENTRY_PROXIMITY
        broke_below = close <= target_break_entry + ASLS_BREAK_CONFIRM_TOLERANCE
        not_late_break_entry = (
            abs(close - target_break_entry)
            <= ASLS_MAX_BREAK_ENTRY_LATE_DISTANCE + ASLS_BREAK_CONFIRM_TOLERANCE
        )

        if (
            was_above_or_touching
            and broke_below
            and not_late_break_entry
            and close < open_price
            and body_atr_ratio >= ASLS_BREAK_BODY_ATR_RATIO
        ):
            entry = target_break_entry
            sl = round(level_price + ASLS_SL_BUFFER, 2)
            tp, target_model = _target_against_opposite_level(
                signal="SELL",
                entry=entry,
                levels=levels,
            )
            rr = _rr("SELL", entry, sl, tp)

            if rr >= ASLS_MIN_RR:
                score = _score(
                    base=ASLS_MIN_SCORE,
                    level=nearest_support,
                    rr=rr,
                    is_ny=is_ny,
                    mode="BREAK_HOLD_SCALP",
                )
                return _build_signal(
                    signal="SELL",
                    mode="SUPPORT_BREAK_HOLD_SCALP",
                    level=nearest_support,
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    rr=rr,
                    score=score,
                    atr=atr,
                    target_model=target_model,
                    trigger_reason=(
                        f"line_break_scalp was_above_or_touching={was_above_or_touching} "
                        f"break_entry={target_break_entry} "
                        f"not_late={not_late_break_entry} "
                        f"broke_below={broke_below} body_atr={round(body_atr_ratio, 3)}"
                    ),
                )

    # 4) Resistance break-hold BUY scalp.
    for nearest_resistance in resistance_break_candidates:
        level_price = float(nearest_resistance["level"])

        target_break_entry = round(level_price + ASLS_BREAK_ENTRY_OFFSET, 2)
        was_below_or_touching = prev_close <= level_price + ASLS_ENTRY_PROXIMITY
        broke_above = close >= target_break_entry - ASLS_BREAK_CONFIRM_TOLERANCE
        not_late_break_entry = (
            abs(close - target_break_entry)
            <= ASLS_MAX_BREAK_ENTRY_LATE_DISTANCE + ASLS_BREAK_CONFIRM_TOLERANCE
        )

        if (
            was_below_or_touching
            and broke_above
            and not_late_break_entry
            and close > open_price
            and body_atr_ratio >= ASLS_BREAK_BODY_ATR_RATIO
        ):
            entry = target_break_entry
            sl = round(level_price - ASLS_SL_BUFFER, 2)
            tp, target_model = _target_against_opposite_level(
                signal="BUY",
                entry=entry,
                levels=levels,
            )
            rr = _rr("BUY", entry, sl, tp)

            if rr >= ASLS_MIN_RR:
                score = _score(
                    base=ASLS_MIN_SCORE,
                    level=nearest_resistance,
                    rr=rr,
                    is_ny=is_ny,
                    mode="BREAK_HOLD_SCALP",
                )
                return _build_signal(
                    signal="BUY",
                    mode="RESISTANCE_BREAK_HOLD_SCALP",
                    level=nearest_resistance,
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    rr=rr,
                    score=score,
                    atr=atr,
                    target_model=target_model,
                    trigger_reason=(
                        f"line_break_scalp was_below_or_touching={was_below_or_touching} "
                        f"break_entry={target_break_entry} "
                        f"not_late={not_late_break_entry} "
                        f"broke_above={broke_above} body_atr={round(body_atr_ratio, 3)}"
                    ),
                )

    return None
