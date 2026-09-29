from __future__ import annotations

from typing import Any

STRATEGY = "INTRABAR_MICRO_MOMENTUM"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def build_authoritative_micro_momentum_geometry(
    *,
    signal: str,
    trade_plan: dict[str, Any],
    execution_price: float,
) -> dict[str, float] | None:
    if not isinstance(trade_plan, dict):
        return None

    strategy = str(trade_plan.get("strategy") or "").upper()
    authority = str(
        trade_plan.get("execution_geometry_authority") or ""
    ).upper()

    if strategy != STRATEGY or authority != STRATEGY:
        return None

    signal = str(signal or "").upper()
    if signal not in {"BUY", "SELL"}:
        return None

    price = _safe_float(execution_price)
    if price is None or price <= 0:
        return None

    reversal_mode = bool(trade_plan.get("micro_momentum_execution_reversal"))
    if reversal_mode:
        reversed_signal = str(trade_plan.get("micro_momentum_reversed_signal") or "").upper()
        sl = _safe_float(trade_plan.get("micro_momentum_reversed_stop_loss"))
        tp = _safe_float(trade_plan.get("micro_momentum_reversed_take_profit"))
        if reversed_signal != signal or sl is None or tp is None:
            return None
        valid = sl < price < tp if signal == "BUY" else tp < price < sl
        if not valid:
            return None
        sl_distance = abs(price - sl)
        tp_distance = abs(tp - price)
    else:
        sl_distance = _safe_float(trade_plan.get("micro_momentum_execution_sl_distance"))
        tp_distance = _safe_float(trade_plan.get("micro_momentum_execution_tp_distance"))
        if sl_distance is None or tp_distance is None:
            return None
        if not (0.30 - 1e-9 <= sl_distance <= 0.50 + 1e-9):
            return None
        if not (0.60 - 1e-9 <= tp_distance <= 2.00 + 1e-9):
            return None
        if signal == "BUY":
            sl, tp = price - sl_distance, price + tp_distance
        else:
            sl, tp = price + sl_distance, price - tp_distance

    return {
        "entry_price": round(price, 2),
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "sl_distance": round(sl_distance, 6),
        "tp_distance": round(tp_distance, 6),
    }


def apply_authoritative_micro_momentum_geometry(
    *,
    signal: str,
    trade_plan: dict[str, Any],
    request: dict[str, Any],
    execution_price: float,
) -> dict[str, Any] | None:
    geometry = build_authoritative_micro_momentum_geometry(
        signal=signal,
        trade_plan=trade_plan,
        execution_price=execution_price,
    )
    if geometry is None:
        return None

    request["price"] = geometry["entry_price"]
    request["sl"] = geometry["stop_loss"]
    request["tp"] = geometry["take_profit"]

    trade_plan["entry_price"] = geometry["entry_price"]
    trade_plan["stop_loss"] = geometry["stop_loss"]
    trade_plan["take_profit"] = geometry["take_profit"]
    trade_plan["stop_distance"] = geometry["sl_distance"]
    trade_plan["micro_momentum_execution_sl_distance"] = geometry["sl_distance"]
    trade_plan["micro_momentum_execution_tp_distance"] = geometry["tp_distance"]
    final_execution_rr = round(geometry["tp_distance"] / geometry["sl_distance"], 6)
    trade_plan["micro_momentum_execution_rr"] = final_execution_rr
    trade_plan["rr"] = final_execution_rr
    trade_plan["risk_reward"] = final_execution_rr
    trade_plan["micro_momentum_final_geometry_reversal_absolute"] = bool(
        trade_plan.get("micro_momentum_execution_reversal")
    )
    trade_plan["micro_momentum_final_geometry_applied"] = True
    trade_plan["micro_momentum_final_geometry_price"] = geometry[
        "entry_price"
    ]

    return geometry
