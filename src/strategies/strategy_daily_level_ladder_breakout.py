from __future__ import annotations

import hashlib
import math
from typing import Any

from config.settings import DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT
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
    candle_time: str | None,
) -> str:
    raw = (
        f"{STRATEGY_NAME}|"
        f"{approved_ladder.broker_date.isoformat()}|"
        f"{approved_ladder.source}|"
        f"{signal}|"
        f"{broken_boundary:.5f}|"
        f"{target_price:.5f}|"
        f"{candle_time or 'UNKNOWN_M5'}"
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"DLLB-{signal}-{digest}"


def evaluate_daily_level_ladder_breakout(
    *,
    m5_df: Any,
    approved_ladder: DailyLadder,
) -> dict[str, Any] | None:
    """
    Evaluate the authoritative DLLB contract from completed M5 closes only.

    Pivot is the directional anchor:
    - above Pivot: BUY ladder only;
    - below Pivot: SELL ladder only.

    A completed-M5 close through the active approved rung is the DLLB signal.
    Legacy body, candle-colour, close-location, ATR-break and strategy-RR
    thresholds do not define DLLB candidate validity.
    """
    if not isinstance(approved_ladder, DailyLadder):
        return None

    rows = _closed_m5_rows(m5_df)
    if rows is None:
        return None

    previous, candle = rows

    previous_close = _safe_float(previous.get("close"))
    candle_close = _safe_float(candle.get("close"))

    if previous_close is None or candle_close is None:
        return None

    try:
        candle_time = str(candle.get("time"))
    except Exception:
        candle_time = None

    candle_open = _safe_float(candle.get("open"))
    candle_high = _safe_float(candle.get("high"))
    candle_low = _safe_float(candle.get("low"))
    atr = _safe_float(candle.get("atr_14"))

    body = (
        abs(candle_close - candle_open)
        if candle_open is not None
        else 0.0
    )

    pivot = float(approved_ladder.pivot)

    if candle_close > pivot:
        signal = "BUY"
    elif candle_close < pivot:
        signal = "SELL"
    else:
        return None

    close_location = 0.0
    if (
        candle_high is not None
        and candle_low is not None
        and candle_high > candle_low
    ):
        if signal == "BUY":
            close_location = (
                candle_close - candle_low
            ) / (candle_high - candle_low)
        else:
            close_location = (
                candle_high - candle_close
            ) / (candle_high - candle_low)

    levels = _approved_execution_levels(approved_ladder)
    crossed: list[dict[str, Any]] = []

    if signal == "BUY":
        # Pivot + approved upper rungs only.
        for item in levels:
            boundary = float(item["price"])
            if boundary < pivot:
                continue
            if previous_close <= boundary < candle_close:
                crossed.append(item)

        if not crossed:
            return None

        # Multi-rung close: the deepest crossed rung is the broken rung.
        broken = max(
            crossed,
            key=lambda item: float(item["price"]),
        )
        broken_boundary = float(broken["price"])
        break_distance = candle_close - broken_boundary

        # Target must still be ahead of the completed close.
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
        # Pivot + approved lower rungs only.
        for item in levels:
            boundary = float(item["price"])
            if boundary > pivot:
                continue
            if previous_close >= boundary > candle_close:
                crossed.append(item)

        if not crossed:
            return None

        # Multi-rung close: the deepest crossed rung is the broken rung.
        broken = min(
            crossed,
            key=lambda item: float(item["price"]),
        )
        broken_boundary = float(broken["price"])
        break_distance = broken_boundary - candle_close

        # Target must still be ahead of the completed close.
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
    gap = abs(broken_boundary - target_price)

    if gap <= 0:
        return None

    raw_sl_distance = (
        gap * float(DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT)
    )
    practical_sl_distance = float(math.ceil(raw_sl_distance))

    if practical_sl_distance <= 0:
        return None

    if signal == "BUY":
        sl_reference = broken_boundary - practical_sl_distance
    else:
        sl_reference = broken_boundary + practical_sl_distance

    setup_id = _setup_id(
        approved_ladder=approved_ladder,
        signal=signal,
        broken_boundary=broken_boundary,
        target_price=target_price,
        candle_time=candle_time,
    )

    broken_name = str(broken["name"])
    target_name = str(target["name"])
    broker_date = approved_ladder.broker_date.isoformat()

    reason = (
        f"{STRATEGY_NAME} {signal} -> "
        f"completed M5 close freshly broke approved {broken_name} "
        f"level={round(broken_boundary, 2)} -> "
        f"next still-unreached approved {target_name} "
        f"target={round(target_price, 2)} -> "
        f"SL distance=ceil({round(gap, 4)}*"
        f"{float(DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT)})="
        f"{round(practical_sl_distance, 2)} -> "
        f"SL={round(sl_reference, 2)}"
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
        "zone_distance": round(gap, 2),
        "raw_sl_distance": round(raw_sl_distance, 4),
        "practical_sl_distance": round(practical_sl_distance, 2),
        # Legacy filter telemetry retained as diagnostics only.
        "break_buffer": 0.0,
        "break_distance": round(break_distance, 4),
        "m5_body": round(body, 4),
        "m5_atr": round(atr, 4) if atr is not None else None,
        "m5_close_location": round(close_location, 4),
        "m5_closed_time": candle_time,
        "strategy_geometry_authoritative": True,
        "tp_authority": "DLLB_NEXT_APPROVED_RUNG",
        "position_management_mode": "DLLB_FIXED_RUNG_EXIT",
        "reason": reason,
        "duplicate_policy": (
            "broker_date_approved_source_closed_m5_broken_target"
        ),
    }
