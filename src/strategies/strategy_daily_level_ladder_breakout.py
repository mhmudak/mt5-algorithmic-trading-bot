from __future__ import annotations

import hashlib
from typing import Any

from config.settings import (
    DAILY_LEVEL_LADDER_MIN_BODY_ATR,
    DAILY_LEVEL_LADDER_MIN_BREAK_ATR,
    DAILY_LEVEL_LADDER_MIN_BREAK_PRICE,
    DAILY_LEVEL_LADDER_MIN_CLOSE_LOCATION,
    DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT,
)
from src.daily_ladder_provider import DailyLadder


STRATEGY_NAME = "DAILY_LEVEL_LADDER_BREAKOUT"
ENTRY_MODEL = "M5_DAILY_LEVEL_BREAKOUT"
SL_MODEL = "DAILY_LEVEL_ZONE_40PCT_SL"
TP_MODEL = "NEXT_DAILY_LEVEL"
DECISION_IMPACT = "MAIN_BOT_RUNTIME_CONTROLLED"


def _safe_float(value: Any) -> float | None:
    try:
        value = float(value)
        if value != value:
            return None
        return value
    except Exception:
        return None


def _closed_m5_rows(m5_df: Any):
    try:
        if m5_df is None or len(m5_df) < 3:
            return None
        return m5_df.iloc[-3], m5_df.iloc[-2]
    except Exception:
        return None


def _approved_execution_levels(
    approved_ladder: DailyLadder,
) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = [
        {
            "name": "APPROVED_PIVOT",
            "price": float(approved_ladder.pivot),
            "kind": "PIVOT",
        }
    ]

    levels.extend(
        {
            "name": f"APPROVED_UPPER_{index}",
            "price": float(price),
            "kind": "UPPER",
        }
        for index, price in enumerate(approved_ladder.upper, start=1)
    )
    levels.extend(
        {
            "name": f"APPROVED_LOWER_{index}",
            "price": float(price),
            "kind": "LOWER",
        }
        for index, price in enumerate(approved_ladder.lower, start=1)
    )

    return sorted(levels, key=lambda item: float(item["price"]))


def _setup_id(
    *,
    approved_ladder: DailyLadder,
    signal: str,
    broken_boundary: float,
    target_price: float,
) -> str:
    raw = (
        f"{STRATEGY_NAME}|"
        f"{approved_ladder.broker_date.isoformat()}|"
        f"{approved_ladder.source}|"
        f"{signal}|"
        f"{broken_boundary:.5f}|"
        f"{target_price:.5f}"
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"DLLB-{signal}-{digest}"


def _strong_close_ok(
    *,
    signal: str,
    candle_open: float,
    candle_high: float,
    candle_low: float,
    candle_close: float,
    atr: float,
) -> tuple[bool, float, float]:
    candle_range = candle_high - candle_low
    if candle_range <= 0:
        return False, 0.0, 0.0

    body = abs(candle_close - candle_open)
    min_body = atr * float(DAILY_LEVEL_LADDER_MIN_BODY_ATR)
    if body < min_body:
        return False, body, 0.0

    if signal == "BUY":
        close_location = (candle_close - candle_low) / candle_range
        passed = (
            candle_close > candle_open
            and close_location >= float(DAILY_LEVEL_LADDER_MIN_CLOSE_LOCATION)
        )
    else:
        close_location = (candle_high - candle_close) / candle_range
        passed = (
            candle_close < candle_open
            and close_location >= float(DAILY_LEVEL_LADDER_MIN_CLOSE_LOCATION)
        )

    return passed, body, close_location


def evaluate_daily_level_ladder_breakout(
    *,
    m5_df: Any,
    approved_ladder: DailyLadder,
) -> dict[str, Any] | None:
    """Evaluate a fresh closed-M5 break of the approved manual ladder only."""
    if not isinstance(approved_ladder, DailyLadder):
        return None

    rows = _closed_m5_rows(m5_df)
    if rows is None:
        return None

    previous, candle = rows

    previous_close = _safe_float(previous.get("close"))
    candle_open = _safe_float(candle.get("open"))
    candle_high = _safe_float(candle.get("high"))
    candle_low = _safe_float(candle.get("low"))
    candle_close = _safe_float(candle.get("close"))
    atr = _safe_float(candle.get("atr_14"))

    if None in {
        previous_close,
        candle_open,
        candle_high,
        candle_low,
        candle_close,
        atr,
    }:
        return None
    if atr <= 0:
        return None

    pivot = float(approved_ladder.pivot)
    if candle_close > pivot:
        signal = "BUY"
    elif candle_close < pivot:
        signal = "SELL"
    else:
        return None

    strong_close, body, close_location = _strong_close_ok(
        signal=signal,
        candle_open=candle_open,
        candle_high=candle_high,
        candle_low=candle_low,
        candle_close=candle_close,
        atr=atr,
    )
    if not strong_close:
        return None

    break_buffer = max(
        float(DAILY_LEVEL_LADDER_MIN_BREAK_PRICE),
        atr * float(DAILY_LEVEL_LADDER_MIN_BREAK_ATR),
    )

    levels = _approved_execution_levels(approved_ladder)
    crossed: list[dict[str, Any]] = []

    if signal == "BUY":
        for item in levels:
            boundary = float(item["price"])
            if boundary < pivot:
                continue
            if previous_close <= boundary < candle_close:
                crossed.append(item)

        if not crossed:
            return None

        broken = max(crossed, key=lambda item: float(item["price"]))
        broken_boundary = float(broken["price"])
        break_distance = candle_close - broken_boundary
        if break_distance < break_buffer:
            return None

        target = next(
            (
                item
                for item in levels
                if float(item["price"]) > broken_boundary
                and float(item["price"]) > candle_close
            ),
            None,
        )
    else:
        for item in levels:
            boundary = float(item["price"])
            if boundary > pivot:
                continue
            if previous_close >= boundary > candle_close:
                crossed.append(item)

        if not crossed:
            return None

        broken = min(crossed, key=lambda item: float(item["price"]))
        broken_boundary = float(broken["price"])
        break_distance = broken_boundary - candle_close
        if break_distance < break_buffer:
            return None

        target = next(
            (
                item
                for item in reversed(levels)
                if float(item["price"]) < broken_boundary
                and float(item["price"]) < candle_close
            ),
            None,
        )

    if target is None:
        return None

    target_price = float(target["price"])

    if signal == "BUY":
        zone_distance = target_price - broken_boundary
        if zone_distance <= 0:
            return None
        sl_reference = (
            broken_boundary
            - zone_distance * float(DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT)
        )
    else:
        zone_distance = broken_boundary - target_price
        if zone_distance <= 0:
            return None
        sl_reference = (
            broken_boundary
            + zone_distance * float(DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT)
        )

    setup_id = _setup_id(
        approved_ladder=approved_ladder,
        signal=signal,
        broken_boundary=broken_boundary,
        target_price=target_price,
    )

    try:
        candle_time = str(candle.get("time"))
    except Exception:
        candle_time = None

    broken_name = str(broken["name"])
    target_name = str(target["name"])
    broker_date = approved_ladder.broker_date.isoformat()

    reason = (
        f"{STRATEGY_NAME} {signal} -> "
        f"closed M5 freshly broke approved {broken_name} "
        f"level={round(broken_boundary, 2)} -> "
        f"next approved {target_name} target={round(target_price, 2)} -> "
        f"SL 40% source-to-target zone={round(sl_reference, 2)}"
    )

    return {
        "signal": signal,
        "score": 95,
        "strategy": STRATEGY_NAME,
        "entry_model": ENTRY_MODEL,
        "sl_model": SL_MODEL,
        "tp_model": TP_MODEL,
        "target_model": TP_MODEL,
        "decision_impact": DECISION_IMPACT,
        "auto_trade_allowed": True,
        "setup_id": setup_id,
        "daily_source_time": broker_date,
        "daily_broker_date": broker_date,
        "daily_approved_source": approved_ladder.source,
        "daily_pivot": round(pivot, 2),
        "daily_cluster_distance": 0.0,
        "broken_level": round(broken_boundary, 2),
        "broken_level_name": broken_name,
        "broken_cluster_names": [broken_name],
        "broken_cluster_low": round(broken_boundary, 2),
        "broken_cluster_high": round(broken_boundary, 2),
        "target_level": round(target_price, 2),
        "target_level_name": target_name,
        "target_cluster_names": [target_name],
        "target_cluster_low": round(target_price, 2),
        "target_cluster_high": round(target_price, 2),
        "sl_reference": round(sl_reference, 2),
        "tp_reference": round(target_price, 2),
        "entry_reference": round(candle_close, 2),
        "zone_distance": round(zone_distance, 2),
        "break_buffer": round(break_buffer, 4),
        "break_distance": round(break_distance, 4),
        "m5_body": round(body, 4),
        "m5_atr": round(atr, 4),
        "m5_close_location": round(close_location, 4),
        "m5_closed_time": candle_time,
        "reason": reason,
        "duplicate_policy": "broker_date_approved_source_target",
    }
