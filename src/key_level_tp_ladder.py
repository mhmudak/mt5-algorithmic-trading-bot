from __future__ import annotations

import math
from typing import Any


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value):
            return default
        return value
    except Exception:
        return default


def calculate_rr(signal: str, entry: float, sl: float, tp: float) -> float | None:
    if min(entry, sl, tp) <= 0:
        return None

    if signal == "BUY":
        risk = entry - sl
        reward = tp - entry
    elif signal == "SELL":
        risk = sl - entry
        reward = entry - tp
    else:
        return None

    if risk <= 0 or reward <= 0:
        return None

    return round(reward / risk, 2)


def _normalize_level(level: float, source: str, strength: int) -> dict[str, Any]:
    return {
        "level": round(float(level), 2),
        "source": source,
        "strength": int(strength),
    }


def _add_level(levels: list[dict[str, Any]], level: Any, source: str, strength: int) -> None:
    value = safe_float(level)

    if value is None or value <= 0:
        return

    levels.append(_normalize_level(value, source, strength))


def _row_value(row: Any, key: str) -> float | None:
    try:
        if hasattr(row, "get"):
            return safe_float(row.get(key))
        return safe_float(row[key])
    except Exception:
        return None


def _collect_signal_levels(signal_data: dict[str, Any]) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []

    key_strength = {
        "daily_pivot": 4,
        "pivot": 4,
        "pivot_level": 4,
        "orb_high": 4,
        "orb_low": 4,
        "range_high": 3,
        "range_low": 3,
        "range_mid": 2,
        "breakout_level": 3,
        "session_vwap_proxy": 3,
        "vwap": 3,
        "psych_level": 3,
        "compression_high": 3,
        "compression_low": 3,
    }

    for key, strength in key_strength.items():
        if key in signal_data:
            _add_level(levels, signal_data.get(key), f"signal_data:{key}", strength)

    return levels


def _collect_round_levels(entry: float, tp: float) -> list[dict[str, Any]]:
    from config.settings import KLT_MINOR_ROUND_LEVEL_STEPS, KLT_ROUND_LEVEL_STEPS

    levels: list[dict[str, Any]] = []

    low = min(entry, tp) - 5
    high = max(entry, tp) + 5

    for step in KLT_ROUND_LEVEL_STEPS:
        step = float(step)
        start = math.floor(low / step) * step
        current = start

        while current <= high:
            _add_level(levels, current, f"major_round_{step}", 3)
            current += step

    for step in KLT_MINOR_ROUND_LEVEL_STEPS:
        step = float(step)
        start = math.floor(low / step) * step
        current = start

        while current <= high:
            # Minor round levels are context only unless reinforced by swing/major.
            _add_level(levels, current, f"minor_round_{step}", 1)
            current += step

    return levels


def _collect_swing_levels(df: Any) -> list[dict[str, Any]]:
    from config.settings import KLT_LOOKBACK_BARS, KLT_SWING_WINDOW

    levels: list[dict[str, Any]] = []

    if df is None:
        return levels

    try:
        closed = df.iloc[:-1].reset_index(drop=True)
    except Exception:
        return levels

    if len(closed) < KLT_SWING_WINDOW * 2 + 5:
        return levels

    window = closed.tail(KLT_LOOKBACK_BARS).reset_index(drop=True)
    w = int(KLT_SWING_WINDOW)

    for idx in range(w, len(window) - w):
        row = window.iloc[idx]

        low = _row_value(row, "low")
        high = _row_value(row, "high")

        if low is None or high is None:
            continue

        left = window.iloc[idx - w:idx]
        right = window.iloc[idx + 1:idx + 1 + w]

        left_lows = [safe_float(v) for v in left["low"].tolist()]
        right_lows = [safe_float(v) for v in right["low"].tolist()]
        left_highs = [safe_float(v) for v in left["high"].tolist()]
        right_highs = [safe_float(v) for v in right["high"].tolist()]

        if all(v is not None and low <= v for v in left_lows + right_lows):
            _add_level(levels, low, "recent_swing_low", 3)

        if all(v is not None and high >= v for v in left_highs + right_highs):
            _add_level(levels, high, "recent_swing_high", 3)

    return levels


def _merge_levels(levels: list[dict[str, Any]], merge_distance: float = 1.25) -> list[dict[str, Any]]:
    if not levels:
        return []

    ordered = sorted(levels, key=lambda item: item["level"])
    clusters: list[dict[str, Any]] = []

    for item in ordered:
        if not clusters or abs(item["level"] - clusters[-1]["level"]) > merge_distance:
            clusters.append(
                {
                    "level": item["level"],
                    "strength": item["strength"],
                    "sources": [item["source"]],
                    "raw_levels": [item["level"]],
                }
            )
            continue

        cluster = clusters[-1]
        cluster["raw_levels"].append(item["level"])
        cluster["sources"].append(item["source"])
        cluster["strength"] += item["strength"]
        cluster["level"] = round(sum(cluster["raw_levels"]) / len(cluster["raw_levels"]), 2)

    return clusters


def _has_structural_confirmation(level: dict[str, Any]) -> bool:
    sources = [str(item).lower() for item in level.get("sources", [])]

    structural_keywords = [
        "recent_swing_low",
        "recent_swing_high",
        "signal_data:orb_low",
        "signal_data:orb_high",
        "signal_data:range_low",
        "signal_data:range_high",
        "signal_data:daily_pivot",
        "signal_data:pivot",
        "signal_data:pivot_level",
        "signal_data:session_vwap_proxy",
        "signal_data:vwap",
        "signal_data:compression_low",
        "signal_data:compression_high",
    ]

    return any(
        any(keyword in source for keyword in structural_keywords)
        for source in sources
    )


def _find_barriers(
    *,
    signal: str,
    entry: float,
    original_tp: float,
    levels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from config.settings import (
        KLT_MAX_BARRIER_DISTANCE_PRICE,
        KLT_MIN_BARRIER_STRENGTH,
    )

    barriers: list[dict[str, Any]] = []

    for level in levels:
        price = safe_float(level.get("level"))

        if price is None:
            continue

        strength = int(level.get("strength", 0))

        if strength < KLT_MIN_BARRIER_STRENGTH:
            continue

        if not _has_structural_confirmation(level):
            continue

        if abs(entry - price) > KLT_MAX_BARRIER_DISTANCE_PRICE:
            continue

        if signal == "SELL" and original_tp < price < entry:
            item = dict(level)
            item["barrier_type"] = "SUPPORT"
            item["distance_from_entry"] = round(entry - price, 2)
            item["barrier_confirmation"] = "STRUCTURAL_LEVEL_CONFIRMED"
            barriers.append(item)

        elif signal == "BUY" and entry < price < original_tp:
            item = dict(level)
            item["barrier_type"] = "RESISTANCE"
            item["distance_from_entry"] = round(price - entry, 2)
            item["barrier_confirmation"] = "STRUCTURAL_LEVEL_CONFIRMED"
            barriers.append(item)

    if signal == "SELL":
        return sorted(barriers, key=lambda item: item["level"], reverse=True)

    return sorted(barriers, key=lambda item: item["level"])


def build_tp_ladder(
    *,
    df: Any,
    signal: str,
    trade_plan: dict[str, Any],
    signal_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from config.settings import (
        KLT_LEVEL_BUFFER_PRICE,
        KLT_MIN_TP1_RR,
    )

    signal_data = signal_data or {}

    entry = safe_float(trade_plan.get("entry_price"))
    sl = safe_float(trade_plan.get("stop_loss"))
    original_tp = safe_float(trade_plan.get("take_profit"))

    if entry is None or sl is None or original_tp is None:
        return {"applied": False, "reason": "missing_trade_plan_prices"}

    if signal not in {"BUY", "SELL"}:
        return {"applied": False, "reason": "invalid_signal"}

    original_rr = calculate_rr(signal, entry, sl, original_tp)

    if original_rr is None:
        return {"applied": False, "reason": "invalid_original_rr"}

    raw_levels = []
    raw_levels.extend(_collect_signal_levels(signal_data))
    raw_levels.extend(_collect_round_levels(entry, original_tp))
    raw_levels.extend(_collect_swing_levels(df))

    merged_levels = _merge_levels(raw_levels)
    barriers = _find_barriers(
        signal=signal,
        entry=entry,
        original_tp=original_tp,
        levels=merged_levels,
    )

    if not barriers:
        return {
            "applied": False,
            "reason": "no_strong_barrier_in_target_path",
            "original_rr": original_rr,
        }

    first_barrier = barriers[0]
    barrier_price = safe_float(first_barrier.get("level"))

    if barrier_price is None:
        return {"applied": False, "reason": "invalid_barrier_price"}

    buffer = float(KLT_LEVEL_BUFFER_PRICE)

    if signal == "SELL":
        tp1 = round(barrier_price + buffer, 2)
        if not (original_tp < tp1 < entry):
            return {"applied": False, "reason": "invalid_sell_tp1_after_buffer"}
    else:
        tp1 = round(barrier_price - buffer, 2)
        if not (entry < tp1 < original_tp):
            return {"applied": False, "reason": "invalid_buy_tp1_after_buffer"}

    tp1_rr = calculate_rr(signal, entry, sl, tp1)

    if tp1_rr is None or tp1_rr < KLT_MIN_TP1_RR:
        return {
            "applied": False,
            "reason": f"tp1_rr_too_low {tp1_rr}/{KLT_MIN_TP1_RR}",
            "barrier": first_barrier,
            "original_rr": original_rr,
        }

    ladder = [
        {
            "name": "TP1_BEFORE_KEY_BARRIER",
            "price": tp1,
            "rr": tp1_rr,
            "barrier": first_barrier,
            "action": "safe_first_target_before_support_resistance",
        },
        {
            "name": "TP2_AFTER_BARRIER_BREAK",
            "price": round((tp1 + original_tp) / 2, 2),
            "rr": calculate_rr(signal, entry, sl, round((tp1 + original_tp) / 2, 2)),
            "action": "only_valid_if_barrier_breaks_and_holds",
        },
        {
            "name": "TP3_ORIGINAL_EXTENSION",
            "price": round(original_tp, 2),
            "rr": original_rr,
            "action": "original_strategy_extension_target",
        },
    ]

    return {
        "applied": True,
        "reason": "strong_key_level_barrier_in_target_path",
        "original_tp": round(original_tp, 2),
        "original_rr": original_rr,
        "execution_tp": tp1,
        "execution_rr": tp1_rr,
        "barrier": first_barrier,
        "tp_ladder": ladder,
        "summary": (
            f"TP1 {tp1} before {first_barrier.get('barrier_type')} "
            f"{first_barrier.get('level')} | TP2 {ladder[1]['price']} | "
            f"TP3 {round(original_tp, 2)}"
        ),
    }


def apply_key_level_tp_ladder(
    *,
    df: Any,
    signal: str,
    trade_plan: dict[str, Any],
    signal_data: dict[str, Any] | None = None,
    strategy_name: str | None = None,
    session_name: str | None = None,
    market_condition: str | None = None,
) -> dict[str, Any]:
    from config.settings import (
        ENABLE_KEY_LEVEL_TP_LADDER,
        KEY_LEVEL_TP_LADDER_STRATEGIES,
        KLT_SET_EXECUTION_TP_TO_TP1,
    )

    if not ENABLE_KEY_LEVEL_TP_LADDER:
        return trade_plan

    strategy_key = str(strategy_name or trade_plan.get("strategy") or "").upper()

    if strategy_key not in {str(item).upper() for item in KEY_LEVEL_TP_LADDER_STRATEGIES}:
        return trade_plan

    result = build_tp_ladder(
        df=df,
        signal=signal,
        trade_plan=trade_plan,
        signal_data=signal_data or {},
    )

    if not result.get("applied"):
        trade_plan["key_level_tp_ladder_checked"] = True
        trade_plan["key_level_tp_ladder_reason"] = result.get("reason")
        return trade_plan

    adjusted = dict(trade_plan)
    adjusted["key_level_tp_ladder_applied"] = True
    adjusted["original_take_profit"] = result.get("original_tp")
    adjusted["original_rr"] = result.get("original_rr")
    adjusted["tp_ladder"] = result.get("tp_ladder")
    adjusted["tp_plan_summary"] = result.get("summary")
    adjusted["tp_barrier"] = result.get("barrier")
    adjusted["tp_management_mode"] = "TP1_EXECUTION_WITH_TP2_TP3_METADATA"
    adjusted["session"] = session_name or adjusted.get("session")
    adjusted["market_condition"] = market_condition or adjusted.get("market_condition")

    if KLT_SET_EXECUTION_TP_TO_TP1:
        adjusted["take_profit"] = result.get("execution_tp")
        adjusted["tp_clamped_from"] = result.get("original_tp")
        adjusted["tp_clamped_reason"] = result.get("reason")

    adjusted["reason"] = (
        f"{adjusted.get('reason', '')} | KEY_LEVEL_TP_LADDER: "
        f"{result.get('summary')}"
    )

    return adjusted
