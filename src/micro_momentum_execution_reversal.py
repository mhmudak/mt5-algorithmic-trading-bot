from __future__ import annotations

from typing import Any

STRATEGY = "INTRABAR_MICRO_MOMENTUM"


def _f(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except Exception:
        return None


def _valid(signal: str, entry: float, sl: float, tp: float) -> bool:
    if signal == "BUY":
        return sl < entry < tp
    if signal == "SELL":
        return tp < entry < sl
    return False


def _rr(entry: float, sl: float, tp: float) -> float | None:
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    return round(abs(tp - entry) / risk, 6)


def resolve_micro_momentum_execution_signal(signal: str, *, enabled: bool) -> str | None:
    side = str(signal or "").upper()
    if side not in {"BUY", "SELL"}:
        return None
    if not enabled:
        return side
    return "SELL" if side == "BUY" else "BUY"


def apply_micro_momentum_execution_reversal(
    *, signal: str, trade_plan: dict[str, Any], enabled: bool,
) -> dict[str, Any] | None:
    if not isinstance(trade_plan, dict):
        return None
    if str(trade_plan.get("strategy") or "").upper() != STRATEGY:
        return None

    original_signal = str(signal or "").upper()
    execution_signal = resolve_micro_momentum_execution_signal(
        original_signal, enabled=bool(enabled)
    )
    entry = _f(trade_plan.get("entry_price"))
    old_sl = _f(trade_plan.get("stop_loss"))
    old_tp = _f(trade_plan.get("take_profit"))
    if execution_signal is None or entry is None or old_sl is None or old_tp is None:
        return None
    if not _valid(original_signal, entry, old_sl, old_tp):
        return None

    old_rr = _rr(entry, old_sl, old_tp)
    if old_rr is None:
        return None

    new_sl, new_tp = (old_tp, old_sl) if enabled else (old_sl, old_tp)
    if not _valid(execution_signal, entry, new_sl, new_tp):
        return None
    new_rr = _rr(entry, new_sl, new_tp)
    if new_rr is None:
        return None

    plan = dict(trade_plan)
    plan["stop_loss"] = new_sl
    plan["take_profit"] = new_tp
    plan["stop_distance"] = round(abs(entry - new_sl), 6)
    plan["micro_momentum_execution_sl_distance"] = round(abs(entry - new_sl), 6)
    plan["micro_momentum_execution_tp_distance"] = round(abs(new_tp - entry), 6)
    plan["rr"] = new_rr
    plan["risk_reward"] = new_rr

    telemetry = {
        "micro_momentum_execution_reversal": bool(enabled),
        "micro_momentum_original_signal": original_signal,
        "micro_momentum_original_entry_price": entry,
        "micro_momentum_original_stop_loss": old_sl,
        "micro_momentum_original_take_profit": old_tp,
        "micro_momentum_original_rr": old_rr,
        "micro_momentum_reversed_signal": execution_signal,
        "micro_momentum_reversed_stop_loss": new_sl,
        "micro_momentum_reversed_take_profit": new_tp,
        "micro_momentum_reversed_rr": new_rr,
        "micro_momentum_execution_signal": execution_signal,
        "micro_momentum_execution_rr": new_rr,
    }
    plan.update(telemetry)
    return {
        "execution_signal": execution_signal,
        "execution_rr": new_rr,
        "trade_plan": plan,
        "telemetry": telemetry,
    }
