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


def _nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


@dataclass(frozen=True)
class DivergenceThresholds:
    min_abs_cum_delta_change: float
    min_price_progress_ticks: float
    flat_price_ticks: float


def thresholds_for_session(session: str | None) -> DivergenceThresholds:
    name = str(session or "").upper()

    if any(token in name for token in ("OVERLAP", "NEW_YORK", "NEW YORK", "COMEX")):
        return DivergenceThresholds(
            min_abs_cum_delta_change=20.0,
            min_price_progress_ticks=2.0,
            flat_price_ticks=1.0,
        )

    if "LONDON" in name:
        return DivergenceThresholds(
            min_abs_cum_delta_change=14.0,
            min_price_progress_ticks=1.5,
            flat_price_ticks=0.8,
        )

    return DivergenceThresholds(
        min_abs_cum_delta_change=10.0,
        min_price_progress_ticks=1.0,
        flat_price_ticks=0.6,
    )


def _fingerprint(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("symbol"),
        _safe_float(snapshot.get("updated_at_epoch")),
        _safe_float(
            _nested(
                snapshot,
                "adapter_compatible_metrics",
                "cumulative_delta",
                default=None,
            )
        ),
        _safe_float(
            _nested(
                snapshot,
                "latest_trade",
                "price",
                default=None,
            )
        ),
        _nested(
            snapshot,
            "sample",
            "last_trade_count_total_session",
            default=None,
        ),
    )


def _compact(snapshot: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "symbol",
        "exchange",
        "system_name",
        "is_test_environment",
        "updated_at_epoch",
        "freshness",
        "sample",
        "latest_trade",
        "adapter_compatible_metrics",
        "trade_flow",
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
        payload = json.loads(path.read_text(encoding="utf-8"))
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
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "phase": "RITHMIC_DELTA_PRICE_DIVERGENCE_HISTORY_V1",
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


def _cum_delta(snapshot: dict[str, Any]) -> float | None:
    value = _safe_float(
        _nested(
            snapshot,
            "adapter_compatible_metrics",
            "cumulative_delta",
            default=None,
        )
    )

    if value is not None:
        return value

    return _safe_float(
        _nested(
            snapshot,
            "trade_flow",
            "session_cumulative_delta",
            default=None,
        )
    )


def _price(snapshot: dict[str, Any]) -> float | None:
    value = _safe_float(
        _nested(
            snapshot,
            "latest_trade",
            "price",
            default=None,
        )
    )

    if value is not None:
        return value

    return _safe_float(
        _nested(
            snapshot,
            "trade_flow",
            "last_trade_price",
            default=None,
        )
    )


def evaluate_rithmic_delta_price_divergence(
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

    current = (
        _compact(snapshot)
        if isinstance(snapshot, dict)
        else {}
    )

    duplicate = bool(
        current
        and history
        and _fingerprint(history[-1])
        == _fingerprint(current)
    )

    previous = history[-1] if history else None

    feed_integrity = (
        feed_integrity
        if isinstance(feed_integrity, dict)
        else {}
    )
    integrity_ok = bool(
        feed_integrity.get("integrity_ok")
    )
    continuity_valid = bool(
        feed_integrity.get("continuity_valid")
    )

    fresh_trade = bool(
        _nested(
            current,
            "freshness",
            "has_fresh_trade",
            default=False,
        )
    )

    thresholds = thresholds_for_session(session)
    tick_size = max(1e-9, float(tick_size))

    current_delta = _cum_delta(current)
    current_price = _price(current)

    previous_delta = (
        _cum_delta(previous)
        if isinstance(previous, dict)
        else None
    )
    previous_price = (
        _price(previous)
        if isinstance(previous, dict)
        else None
    )

    delta_change = None
    price_change = None
    price_change_ticks = None

    if (
        current_delta is not None
        and previous_delta is not None
    ):
        delta_change = current_delta - previous_delta

    if (
        current_price is not None
        and previous_price is not None
    ):
        price_change = current_price - previous_price
        price_change_ticks = price_change / tick_size

    enough_delta_move = bool(
        delta_change is not None
        and abs(delta_change)
        >= thresholds.min_abs_cum_delta_change
    )

    buyers_aggressive = bool(
        enough_delta_move
        and delta_change is not None
        and delta_change > 0
    )

    sellers_aggressive = bool(
        enough_delta_move
        and delta_change is not None
        and delta_change < 0
    )

    price_up_effective = bool(
        price_change_ticks is not None
        and price_change_ticks
        >= thresholds.min_price_progress_ticks
    )
    price_down_effective = bool(
        price_change_ticks is not None
        and price_change_ticks
        <= -thresholds.min_price_progress_ticks
    )

    price_flat = bool(
        price_change_ticks is not None
        and abs(price_change_ticks)
        <= thresholds.flat_price_ticks
    )

    potential_trapped_buyers = bool(
        buyers_aggressive
        and price_change_ticks is not None
        and (
            price_flat
            or price_change_ticks < 0
        )
    )

    potential_trapped_sellers = bool(
        sellers_aggressive
        and price_change_ticks is not None
        and (
            price_flat
            or price_change_ticks > 0
        )
    )

    buyer_flow_effective = bool(
        buyers_aggressive
        and price_up_effective
    )

    seller_flow_effective = bool(
        sellers_aggressive
        and price_down_effective
    )

    bullish_price_without_delta = bool(
        price_up_effective
        and delta_change is not None
        and delta_change <= 0
    )

    bearish_price_without_delta = bool(
        price_down_effective
        and delta_change is not None
        and delta_change >= 0
    )

    if not current:
        status = "SNAPSHOT_MISSING"
    elif not integrity_ok or not continuity_valid:
        status = "FEED_INTEGRITY_NOT_USABLE"
    elif not fresh_trade:
        status = "TRADE_FLOW_STALE"
    elif previous is None:
        status = "INSUFFICIENT_HISTORY"
    elif (
        current_delta is None
        or previous_delta is None
        or current_price is None
        or previous_price is None
    ):
        status = "INSUFFICIENT_DELTA_PRICE_DATA"
    elif potential_trapped_buyers:
        status = "POTENTIAL_TRAPPED_BUYERS"
    elif potential_trapped_sellers:
        status = "POTENTIAL_TRAPPED_SELLERS"
    elif buyer_flow_effective:
        status = "BUY_FLOW_PRICE_CONFIRMED"
    elif seller_flow_effective:
        status = "SELL_FLOW_PRICE_CONFIRMED"
    elif bullish_price_without_delta:
        status = "BULLISH_PRICE_DELTA_DIVERGENCE"
    elif bearish_price_without_delta:
        status = "BEARISH_PRICE_DELTA_DIVERGENCE"
    elif not enough_delta_move:
        status = "DELTA_CHANGE_TOO_SMALL"
    else:
        status = "NEUTRAL_OR_TRANSITIONAL"

    signal_name = str(signal or "").upper()

    trapped_against_signal = bool(
        (
            signal_name == "BUY"
            and potential_trapped_buyers
        )
        or (
            signal_name == "SELL"
            and potential_trapped_sellers
        )
    )

    trapped_supports_signal = bool(
        (
            signal_name == "BUY"
            and potential_trapped_sellers
        )
        or (
            signal_name == "SELL"
            and potential_trapped_buyers
        )
    )

    flow_confirms_signal = bool(
        (
            signal_name == "BUY"
            and buyer_flow_effective
        )
        or (
            signal_name == "SELL"
            and seller_flow_effective
        )
    )

    if current and not duplicate:
        persisted = (
            history + [current]
        )[-max_history:]

        _write_history(
            history_file,
            persisted,
        )
    else:
        persisted = history[-max_history:]

    return {
        "engine": "RITHMIC_DELTA_PRICE_DIVERGENCE_V1",
        "status": status,
        "signal": signal_name or None,
        "session": session,
        "delta": {
            "previous_cumulative_delta": previous_delta,
            "current_cumulative_delta": current_delta,
            "change": (
                round(delta_change, 6)
                if delta_change is not None
                else None
            ),
            "enough_change": enough_delta_move,
        },
        "price": {
            "previous_price": previous_price,
            "current_price": current_price,
            "change": (
                round(price_change, 6)
                if price_change is not None
                else None
            ),
            "change_ticks": (
                round(price_change_ticks, 6)
                if price_change_ticks is not None
                else None
            ),
            "flat": price_flat,
        },
        "classification": {
            "potential_trapped_buyers": (
                potential_trapped_buyers
            ),
            "potential_trapped_sellers": (
                potential_trapped_sellers
            ),
            "buyer_flow_effective": (
                buyer_flow_effective
            ),
            "seller_flow_effective": (
                seller_flow_effective
            ),
            "bullish_price_without_delta": (
                bullish_price_without_delta
            ),
            "bearish_price_without_delta": (
                bearish_price_without_delta
            ),
            "trapped_against_signal": (
                trapped_against_signal
            ),
            "trapped_supports_signal": (
                trapped_supports_signal
            ),
            "flow_confirms_signal": (
                flow_confirms_signal
            ),
        },
        "history": {
            "history_path": str(history_file),
            "snapshot_count": len(persisted),
            "current_snapshot_was_duplicate": duplicate,
            "deduplication_enabled": True,
        },
        "policy": {
            "uses_cumulative_delta_change_not_absolute_level": True,
            "requires_price_response": True,
            "trapped_label_is_potential_not_certain": True,
            "feed_continuity_required": True,
            "thresholds_are_research_only": True,
        },
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "trade_action": "NO_AUTO_TRADE",
    }


def format_delta_price_divergence_text(
    result: dict[str, Any],
) -> str:
    delta = result.get("delta") or {}
    price = result.get("price") or {}
    cls = result.get("classification") or {}
    history = result.get("history") or {}

    lines = [
        "[RITHMIC DELTA / PRICE DIVERGENCE]",
        f"status = {result.get('status')}",
        f"signal = {result.get('signal')}",
        f"session = {result.get('session')}",
        (
            "previous_cumulative_delta = "
            f"{delta.get('previous_cumulative_delta')}"
        ),
        (
            "current_cumulative_delta = "
            f"{delta.get('current_cumulative_delta')}"
        ),
        f"cumulative_delta_change = {delta.get('change')}",
        f"price_change_ticks = {price.get('change_ticks')}",
        (
            "potential_trapped_buyers = "
            f"{cls.get('potential_trapped_buyers')}"
        ),
        (
            "potential_trapped_sellers = "
            f"{cls.get('potential_trapped_sellers')}"
        ),
        (
            "buyer_flow_effective = "
            f"{cls.get('buyer_flow_effective')}"
        ),
        (
            "seller_flow_effective = "
            f"{cls.get('seller_flow_effective')}"
        ),
        (
            "trapped_against_signal = "
            f"{cls.get('trapped_against_signal')}"
        ),
        (
            "trapped_supports_signal = "
            f"{cls.get('trapped_supports_signal')}"
        ),
        (
            "history_snapshot_count = "
            f"{history.get('snapshot_count')}"
        ),
        f"decision_impact = {result.get('decision_impact')}",
        (
            "can_influence_decision = "
            f"{result.get('can_influence_decision')}"
        ),
        f"safe_for_execution = {result.get('safe_for_execution')}",
    ]

    return "\n".join(lines)
