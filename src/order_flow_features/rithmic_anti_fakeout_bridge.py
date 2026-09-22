from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.order_flow_features.rithmic_anti_fakeout import (
    RithmicAntiFakeoutEngine,
)


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


def _nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _snapshot_fingerprint(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("symbol"),
        _safe_float(snapshot.get("updated_at_epoch")),
        _nested(snapshot, "sample", "order_book_count", default=None),
        _nested(snapshot, "sample", "rolling_trade_count", default=None),
        _safe_float(
            _nested(
                snapshot,
                "order_book",
                "last_received_at_epoch",
                default=None,
            )
        ),
        _safe_float(
            _nested(
                snapshot,
                "latest_trade",
                "received_at_epoch",
                default=None,
            )
        ),
    )


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Keep only fields needed by the anti-fakeout engine.

    Full Phase 5C snapshots can contain large DOM/footprint payloads. The bridge
    needs only a short rolling history for persistence/churn analysis.
    """
    keep = (
        "symbol",
        "exchange",
        "system_name",
        "is_test_environment",
        "updated_at_epoch",
        "freshness",
        "sample",
        "latest_trade",
        "order_book",
        "trade_flow",
        "volume_profile",
        "footprint",
        "adapter_compatible_metrics",
        "quality",
    )
    return {
        key: snapshot.get(key)
        for key in keep
        if key in snapshot
    }


def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return []

    if isinstance(payload, dict):
        payload = payload.get("snapshots")

    if not isinstance(payload, list):
        return []

    return [
        item
        for item in payload
        if isinstance(item, dict)
    ]


def _write_history(
    path: Path,
    snapshots: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    payload = {
        "phase": "RITHMIC_ANTI_FAKEOUT_BRIDGE_HISTORY_V1",
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "snapshots": snapshots,
    }
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def build_bridge_anti_fakeout(
    snapshot: dict[str, Any] | None,
    *,
    history_path: str | Path,
    signal: str | None = None,
    session: str | None = None,
    tick_size: float = 0.1,
    max_history: int = 12,
    basis_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history_file = Path(history_path)
    history = _load_history(history_file)

    current = (
        _compact_snapshot(snapshot)
        if isinstance(snapshot, dict)
        else {}
    )
    current_fp = _snapshot_fingerprint(current)

    duplicate_current = bool(
        current
        and history
        and _snapshot_fingerprint(history[-1]) == current_fp
    )

    prior_history = (
        history[:-1]
        if duplicate_current
        else history
    )

    engine = RithmicAntiFakeoutEngine(
        tick_size=tick_size,
        history_size=max_history,
    )

    for item in prior_history[-max_history:]:
        engine.update(
            item,
            signal=None,
            session=session,
            basis_state=None,
        )

    result = engine.update(
        current,
        signal=signal,
        session=session,
        basis_state=basis_state,
    )

    if current:
        persisted = list(prior_history)

        if (
            not persisted
            or _snapshot_fingerprint(persisted[-1]) != current_fp
        ):
            persisted.append(current)

        persisted = persisted[-max_history:]
        _write_history(
            history_file,
            persisted,
        )
    else:
        persisted = prior_history[-max_history:]

    quality = (
        current.get("quality")
        if isinstance(current.get("quality"), dict)
        else {}
    )
    is_test_environment = bool(
        current.get("is_test_environment")
    )
    cache_safe_for_live_decision = bool(
        quality.get("safe_for_live_decision")
    )

    if is_test_environment:
        data_grade = "TEST_ENVIRONMENT_OBSERVATION_ONLY"
    elif not cache_safe_for_live_decision:
        data_grade = "CACHE_NOT_LIVE_DECISION_GRADE"
    else:
        data_grade = "PRODUCTION_FEED_VALIDATION_PENDING"

    result["bridge_history"] = {
        "history_path": str(history_file),
        "history_snapshot_count": len(persisted),
        "current_snapshot_was_duplicate": duplicate_current,
        "deduplication_enabled": True,
        "max_history": max_history,
    }
    result["data_grade"] = data_grade
    result["production_data_eligible"] = bool(
        current
        and not is_test_environment
        and cache_safe_for_live_decision
    )

    # Phase-2 integration is telemetry only even if the underlying data later
    # becomes production-quality.
    result["decision_impact"] = DECISION_IMPACT
    result["can_influence_decision"] = CAN_INFLUENCE_DECISION
    result["safe_for_execution"] = SAFE_FOR_EXECUTION
    result["bridge_integration_mode"] = "OBSERVE_ONLY"

    return result


def format_bridge_anti_fakeout_text(
    result: dict[str, Any],
) -> str:
    history = result.get("bridge_history") or {}
    freshness = result.get("freshness_gate") or {}
    dom = result.get("dom") or {}
    flow = result.get("executed_flow") or {}
    response = result.get("price_response") or {}

    lines = [
        "[RITHMIC ANTI-FAKEOUT]",
        f"status = {result.get('status')}",
        f"data_grade = {result.get('data_grade')}",
        (
            "production_data_eligible = "
            f"{result.get('production_data_eligible')}"
        ),
        f"signal = {result.get('signal')}",
        f"session = {result.get('session')}",
        (
            "freshness_all_fresh = "
            f"{freshness.get('all_fresh')}"
        ),
        (
            "executed_flow_sufficient = "
            f"{flow.get('sufficient')}"
        ),
        (
            "flow_imbalance = "
            f"{flow.get('flow_imbalance')}"
        ),
        (
            "price_response_confirms_flow = "
            f"{response.get('confirms_executed_flow')}"
        ),
        (
            "absorption_against_signal = "
            f"{result.get('absorption_against_signal')}"
        ),
        (
            "dom_persistence_ratio = "
            f"{dom.get('persistence_ratio')}"
        ),
        (
            "dom_flip_ratio = "
            f"{dom.get('dom_flip_ratio')}"
        ),
        (
            "depth_churn_ratio_proxy = "
            f"{dom.get('depth_churn_ratio_proxy')}"
        ),
        (
            "quote_flicker_score = "
            f"{dom.get('quote_flicker_score')}"
        ),
        f"spoof_risk = {result.get('spoof_risk')}",
        (
            "history_snapshot_count = "
            f"{history.get('history_snapshot_count')}"
        ),
        (
            "current_snapshot_was_duplicate = "
            f"{history.get('current_snapshot_was_duplicate')}"
        ),
        f"decision_impact = {result.get('decision_impact')}",
        (
            "can_influence_decision = "
            f"{result.get('can_influence_decision')}"
        ),
        (
            "safe_for_execution = "
            f"{result.get('safe_for_execution')}"
        ),
    ]

    return "\n".join(lines)
