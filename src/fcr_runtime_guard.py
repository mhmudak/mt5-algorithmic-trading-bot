from __future__ import annotations

from typing import Any


FCR_STRATEGY = "FCR_M1_FVG"


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return number


def resolve_fcr_signal_entry(
    strategy_name: str | None,
    signal_data: dict[str, Any] | None,
    fallback_entry: Any,
) -> float | Any:
    """Use FCR's detection-time entry reference; preserve existing behavior otherwise."""
    if str(strategy_name or "").upper() != FCR_STRATEGY:
        return fallback_entry

    data = signal_data if isinstance(signal_data, dict) else {}
    entry_reference = _safe_float(data.get("entry_reference"))

    if entry_reference is None:
        return fallback_entry

    return entry_reference


def validate_fcr_runtime_geometry(
    *,
    strategy_name: str | None,
    signal: str | None,
    signal_data: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    executable_price: Any,
    min_rr_required: Any,
) -> dict[str, Any]:
    """
    Revalidate FCR immediately before market execution.

    Never manufactures/moves SL or TP. It checks fresh executable geometry,
    recomputes RR, and records chase / RR degradation telemetry.
    """
    strategy = str(strategy_name or "").upper()
    side = str(signal or "").upper()

    if strategy != FCR_STRATEGY:
        return {
            "applies": False,
            "allowed": True,
            "reason": "not_fcr",
            "trade_plan": (
                dict(trade_plan)
                if isinstance(trade_plan, dict)
                else trade_plan
            ),
        }

    data = signal_data if isinstance(signal_data, dict) else {}
    plan = dict(trade_plan) if isinstance(trade_plan, dict) else {}

    signal_entry = _safe_float(data.get("entry_reference"))
    if signal_entry is None:
        signal_entry = _safe_float(plan.get("entry_price"))

    price = _safe_float(executable_price)
    sl = _safe_float(plan.get("stop_loss"))
    tp = _safe_float(plan.get("take_profit"))
    required_rr = _safe_float(min_rr_required)

    result = {
        "applies": True,
        "allowed": False,
        "strategy": strategy,
        "signal": side,
        "signal_entry": signal_entry,
        "executable_price": price,
        "stop_loss": sl,
        "take_profit": tp,
        "required_rr": required_rr,
        "runtime_rr": None,
        "signal_rr": None,
        "rr_degradation": None,
        "chase_distance": None,
        "trade_plan": plan,
    }

    if side not in {"BUY", "SELL"}:
        result["reason"] = "invalid_signal"
        return result

    if any(value is None for value in (signal_entry, price, sl, tp)):
        result["reason"] = "missing_runtime_geometry"
        return result

    if side == "BUY":
        stop_side_valid = sl < price
        target_side_valid = tp > price
        runtime_risk = price - sl
        runtime_reward = tp - price
        signal_risk = signal_entry - sl
        signal_reward = tp - signal_entry
        chase_distance = price - signal_entry
    else:
        stop_side_valid = sl > price
        target_side_valid = tp < price
        runtime_risk = sl - price
        runtime_reward = price - tp
        signal_risk = sl - signal_entry
        signal_reward = signal_entry - tp
        chase_distance = signal_entry - price

    result["chase_distance"] = round(float(chase_distance), 6)

    if not stop_side_valid:
        result["reason"] = "invalid_stop_side"
        return result

    if not target_side_valid:
        result["reason"] = "invalid_target_side"
        return result

    if runtime_risk <= 0 or runtime_reward <= 0:
        result["reason"] = "non_positive_runtime_geometry"
        return result

    runtime_rr = runtime_reward / runtime_risk
    result["runtime_rr"] = round(float(runtime_rr), 6)

    if signal_risk > 0 and signal_reward > 0:
        signal_rr = signal_reward / signal_risk
        result["signal_rr"] = round(float(signal_rr), 6)
        result["rr_degradation"] = round(
            float(runtime_rr - signal_rr),
            6,
        )

    if required_rr is not None and runtime_rr < required_rr:
        result["reason"] = "runtime_rr_below_required"
        return result

    runtime_plan = dict(plan)
    runtime_plan["entry_price"] = round(float(price), 2)
    runtime_plan["fcr_signal_entry"] = round(float(signal_entry), 2)
    runtime_plan["fcr_runtime_rr"] = round(float(runtime_rr), 4)
    runtime_plan["fcr_chase_distance"] = round(float(chase_distance), 2)

    result["allowed"] = True
    result["reason"] = "runtime_geometry_valid"
    result["trade_plan"] = runtime_plan

    return result
