from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DECISION_IMPACT = "NONE"
CAN_INFLUENCE_DECISION = False
SAFE_FOR_EXECUTION = False

def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number

def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def _nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current

def _sign(value: float | None, deadband: float = 0.0) -> int:
    if value is None:
        return 0
    if value > deadband:
        return 1
    if value < -deadband:
        return -1
    return 0

@dataclass(frozen=True)
class AbsorptionThresholds:
    min_trade_count: int
    min_total_volume: float
    min_flow_imbalance: float
    effective_response_ticks: float
    absorption_max_response_ticks: float
    exhaustion_volume_ratio: float
    exhaustion_imbalance_ratio: float

def thresholds_for_session(session: str | None) -> AbsorptionThresholds:
    name = str(session or "").upper()
    if any(token in name for token in ("OVERLAP", "NEW_YORK", "NEW YORK", "COMEX")):
        return AbsorptionThresholds(20, 20.0, 0.18, 2.0, 1.0, 0.55, 0.50)
    if "LONDON" in name:
        return AbsorptionThresholds(14, 14.0, 0.16, 1.5, 0.8, 0.55, 0.50)
    return AbsorptionThresholds(10, 10.0, 0.14, 1.0, 0.6, 0.50, 0.45)

def _fingerprint(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("symbol"),
        _safe_float(snapshot.get("updated_at_epoch")),
        _nested(snapshot, "sample", "rolling_trade_count", default=None),
        _safe_float(_nested(snapshot, "trade_flow", "rolling_delta", default=None)),
        _safe_float(_nested(snapshot, "trade_flow", "rolling_total_volume", default=None)),
        _safe_float(_nested(snapshot, "trade_flow", "last_trade_price", default=None)),
    )

def _compact(snapshot: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "symbol", "exchange", "system_name", "is_test_environment",
        "updated_at_epoch", "freshness", "sample", "trade_flow",
        "adapter_compatible_metrics", "footprint", "quality",
    )
    return {key: snapshot.get(key) for key in keep if key in snapshot}

def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, dict):
        payload = payload.get("snapshots")
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]

def _write_history(path: Path, snapshots: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "RITHMIC_ABSORPTION_EXHAUSTION_HISTORY_V1",
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "snapshots": snapshots,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

def _flow(snapshot: dict[str, Any]) -> dict[str, Any]:
    total_volume = _safe_float(_nested(snapshot, "trade_flow", "rolling_total_volume", default=0)) or 0.0
    delta = _safe_float(_nested(snapshot, "trade_flow", "rolling_delta", default=0)) or 0.0
    imbalance = _safe_float(_nested(snapshot, "trade_flow", "rolling_imbalance_ratio", default=None))
    if imbalance is None and total_volume > 0:
        imbalance = delta / total_volume
    imbalance = imbalance or 0.0
    return {
        "trade_count": _safe_int(_nested(snapshot, "sample", "rolling_trade_count", default=0)),
        "total_volume": total_volume,
        "delta": delta,
        "imbalance": imbalance,
        "direction": _sign(imbalance),
        "first_price": _safe_float(_nested(snapshot, "trade_flow", "first_trade_price", default=None)),
        "last_price": _safe_float(_nested(snapshot, "trade_flow", "last_trade_price", default=None)),
        "high_price": _safe_float(_nested(snapshot, "trade_flow", "high_trade_price", default=None)),
        "low_price": _safe_float(_nested(snapshot, "trade_flow", "low_trade_price", default=None)),
    }

def evaluate_rithmic_absorption_exhaustion(
    snapshot: dict[str, Any] | None,
    *,
    history_path: str | Path,
    feed_integrity: dict[str, Any] | None = None,
    signal: str | None = None,
    session: str | None = None,
    tick_size: float = 0.1,
    max_history: int = 12,
) -> dict[str, Any]:
    history_file = Path(history_path)
    history = _load_history(history_file)
    current = _compact(snapshot) if isinstance(snapshot, dict) else {}
    duplicate = bool(current and history and _fingerprint(history[-1]) == _fingerprint(current))
    thresholds = thresholds_for_session(session)
    tick_size = max(1e-9, float(tick_size))
    flow = _flow(current)
    feed_integrity = feed_integrity if isinstance(feed_integrity, dict) else {}
    integrity_ok = bool(feed_integrity.get("integrity_ok"))
    continuity_valid = bool(feed_integrity.get("continuity_valid"))
    fresh_trade = bool(_nested(current, "freshness", "has_fresh_trade", default=False))

    first_price = flow["first_price"]
    last_price = flow["last_price"]
    if first_price is not None and last_price is not None:
        price_change = last_price - first_price
        response_ticks = price_change / tick_size
    else:
        price_change = None
        response_ticks = None

    direction = int(flow["direction"])
    signed_response_ticks = response_ticks * direction if response_ticks is not None and direction != 0 else None

    sufficient_flow = bool(
        fresh_trade
        and flow["trade_count"] >= thresholds.min_trade_count
        and flow["total_volume"] >= thresholds.min_total_volume
        and abs(flow["imbalance"]) >= thresholds.min_flow_imbalance
    )

    aggression_effective = bool(
        sufficient_flow
        and signed_response_ticks is not None
        and signed_response_ticks >= thresholds.effective_response_ticks
    )
    absorbed = bool(
        sufficient_flow
        and signed_response_ticks is not None
        and signed_response_ticks <= thresholds.absorption_max_response_ticks
    )
    adverse_response = bool(
        sufficient_flow
        and signed_response_ticks is not None
        and signed_response_ticks < 0
    )

    prior = _flow(history[-1]) if history else None
    exhaustion = False
    exhaustion_direction = 0
    volume_ratio = None
    imbalance_ratio = None

    if (
        sufficient_flow
        and prior is not None
        and prior["direction"] == direction
        and direction != 0
        and prior["total_volume"] > 0
        and abs(prior["imbalance"]) > 0
    ):
        volume_ratio = flow["total_volume"] / prior["total_volume"]
        imbalance_ratio = abs(flow["imbalance"]) / abs(prior["imbalance"])
        if (
            volume_ratio <= thresholds.exhaustion_volume_ratio
            and imbalance_ratio <= thresholds.exhaustion_imbalance_ratio
            and not aggression_effective
        ):
            exhaustion = True
            exhaustion_direction = direction

    if not current:
        status = "SNAPSHOT_MISSING"
    elif not integrity_ok or not continuity_valid:
        status = "FEED_INTEGRITY_NOT_USABLE"
    elif not fresh_trade:
        status = "TRADE_FLOW_STALE"
    elif not sufficient_flow:
        status = "INSUFFICIENT_EXECUTED_FLOW"
    elif adverse_response and direction > 0:
        status = "BUY_AGGRESSION_ABSORBED_ADVERSE"
    elif adverse_response and direction < 0:
        status = "SELL_AGGRESSION_ABSORBED_ADVERSE"
    elif absorbed and direction > 0:
        status = "BUY_AGGRESSION_ABSORBED"
    elif absorbed and direction < 0:
        status = "SELL_AGGRESSION_ABSORBED"
    elif exhaustion and exhaustion_direction > 0:
        status = "BUY_AGGRESSION_EXHAUSTING"
    elif exhaustion and exhaustion_direction < 0:
        status = "SELL_AGGRESSION_EXHAUSTING"
    elif aggression_effective and direction > 0:
        status = "BUY_AGGRESSION_EFFECTIVE"
    elif aggression_effective and direction < 0:
        status = "SELL_AGGRESSION_EFFECTIVE"
    else:
        status = "BALANCED_OR_TRANSITIONAL"

    signal_name = str(signal or "").upper()
    signal_direction = 1 if signal_name == "BUY" else -1 if signal_name == "SELL" else 0

    absorption_against_signal = bool(signal_direction != 0 and direction == signal_direction and absorbed)
    absorption_supports_signal = bool(signal_direction != 0 and direction == -signal_direction and absorbed)
    exhaustion_against_signal = bool(signal_direction != 0 and exhaustion and exhaustion_direction == signal_direction)
    exhaustion_supports_signal = bool(signal_direction != 0 and exhaustion and exhaustion_direction == -signal_direction)

    directional_efficiency = None
    if sufficient_flow and signed_response_ticks is not None:
        directional_efficiency = signed_response_ticks / max(1e-9, abs(flow["delta"]))

    if current and not duplicate:
        persisted = (history + [current])[-max_history:]
        _write_history(history_file, persisted)
    else:
        persisted = history[-max_history:]

    return {
        "engine": "RITHMIC_ABSORPTION_EXHAUSTION_V1",
        "status": status,
        "signal": signal_name or None,
        "session": session,
        "flow": {
            "trade_count": flow["trade_count"],
            "total_volume": round(flow["total_volume"], 6),
            "delta": round(flow["delta"], 6),
            "imbalance": round(flow["imbalance"], 6),
            "direction": direction,
            "sufficient": sufficient_flow,
        },
        "price_response": {
            "first_price": first_price,
            "last_price": last_price,
            "price_change": round(price_change, 6) if price_change is not None else None,
            "response_ticks": round(response_ticks, 6) if response_ticks is not None else None,
            "signed_response_ticks": round(signed_response_ticks, 6) if signed_response_ticks is not None else None,
            "directional_efficiency_ticks_per_abs_delta": round(directional_efficiency, 8) if directional_efficiency is not None else None,
        },
        "classification": {
            "aggression_effective": aggression_effective,
            "absorbed": absorbed,
            "adverse_response": adverse_response,
            "exhaustion": exhaustion,
            "absorption_against_signal": absorption_against_signal,
            "absorption_supports_signal": absorption_supports_signal,
            "exhaustion_against_signal": exhaustion_against_signal,
            "exhaustion_supports_signal": exhaustion_supports_signal,
        },
        "exhaustion_comparison": {
            "prior_available": prior is not None,
            "volume_ratio_vs_prior": round(volume_ratio, 6) if volume_ratio is not None else None,
            "imbalance_ratio_vs_prior": round(imbalance_ratio, 6) if imbalance_ratio is not None else None,
        },
        "history": {
            "history_path": str(history_file),
            "snapshot_count": len(persisted),
            "current_snapshot_was_duplicate": duplicate,
            "deduplication_enabled": True,
        },
        "policy": {
            "executed_flow_primary": True,
            "price_response_required": True,
            "dom_used_for_classification": False,
            "thresholds_are_research_only": True,
        },
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "trade_action": "NO_AUTO_TRADE",
    }

def format_absorption_exhaustion_text(result: dict[str, Any]) -> str:
    flow = result.get("flow") or {}
    response = result.get("price_response") or {}
    cls = result.get("classification") or {}
    history = result.get("history") or {}
    lines = [
        "[RITHMIC ABSORPTION / EXHAUSTION]",
        f"status = {result.get('status')}",
        f"signal = {result.get('signal')}",
        f"session = {result.get('session')}",
        f"flow_direction = {flow.get('direction')}",
        f"flow_sufficient = {flow.get('sufficient')}",
        f"delta = {flow.get('delta')}",
        f"imbalance = {flow.get('imbalance')}",
        f"response_ticks = {response.get('response_ticks')}",
        f"signed_response_ticks = {response.get('signed_response_ticks')}",
        f"directional_efficiency = {response.get('directional_efficiency_ticks_per_abs_delta')}",
        f"aggression_effective = {cls.get('aggression_effective')}",
        f"absorbed = {cls.get('absorbed')}",
        f"adverse_response = {cls.get('adverse_response')}",
        f"exhaustion = {cls.get('exhaustion')}",
        f"absorption_against_signal = {cls.get('absorption_against_signal')}",
        f"absorption_supports_signal = {cls.get('absorption_supports_signal')}",
        f"exhaustion_against_signal = {cls.get('exhaustion_against_signal')}",
        f"history_snapshot_count = {history.get('snapshot_count')}",
        f"decision_impact = {result.get('decision_impact')}",
        f"can_influence_decision = {result.get('can_influence_decision')}",
        f"safe_for_execution = {result.get('safe_for_execution')}",
    ]
    return "\n".join(lines)
