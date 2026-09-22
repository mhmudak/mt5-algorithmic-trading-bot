from __future__ import annotations

import json
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


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _fingerprint(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("symbol"),
        _safe_float(snapshot.get("updated_at_epoch")),
        _nested(snapshot, "sample", "last_trade_count_total_session", default=None),
        _nested(snapshot, "sample", "bbo_count", default=None),
        _nested(snapshot, "sample", "order_book_count", default=None),
        _safe_float(
            _nested(snapshot, "latest_trade", "received_at_epoch", default=None)
        ),
        _safe_float(
            _nested(snapshot, "order_book", "last_received_at_epoch", default=None)
        ),
    )


def _market_fingerprint(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _nested(snapshot, "sample", "last_trade_count_total_session", default=None),
        _nested(snapshot, "sample", "bbo_count", default=None),
        _nested(snapshot, "sample", "order_book_count", default=None),
        _safe_float(_nested(snapshot, "latest_trade", "price", default=None)),
        _safe_float(_nested(snapshot, "order_book", "top_bid_price", default=None)),
        _safe_float(_nested(snapshot, "order_book", "top_ask_price", default=None)),
        _safe_float(_nested(snapshot, "order_book", "bid_depth", default=None)),
        _safe_float(_nested(snapshot, "order_book", "ask_depth", default=None)),
    )


def _compact(snapshot: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "symbol",
        "exchange",
        "system_name",
        "is_test_environment",
        "updated_at_epoch",
        "state_status",
        "connection",
        "freshness",
        "sample",
        "latest_trade",
        "bbo",
        "order_book",
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

    return [item for item in payload if isinstance(item, dict)]


def _write_history(path: Path, snapshots: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "RITHMIC_FEED_INTEGRITY_HISTORY_V1",
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "snapshots": snapshots,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _counter_state(snapshot: dict[str, Any]) -> dict[str, int | None]:
    return {
        "trade_count": _safe_int(
            _nested(
                snapshot,
                "sample",
                "last_trade_count_total_session",
                default=None,
            )
        ),
        "bbo_count": _safe_int(
            _nested(snapshot, "sample", "bbo_count", default=None)
        ),
        "order_book_count": _safe_int(
            _nested(snapshot, "sample", "order_book_count", default=None)
        ),
        "login_event_count": _safe_int(
            _nested(
                snapshot,
                "connection",
                "login_event_count",
                default=None,
            )
        ),
        "market_data_response_count": _safe_int(
            _nested(
                snapshot,
                "connection",
                "market_data_response_count",
                default=None,
            )
        ),
    }


def _counter_reset(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> tuple[bool, list[str]]:
    if not previous:
        return False, []

    before = _counter_state(previous)
    after = _counter_state(current)
    reset_fields: list[str] = []

    for key in ("trade_count", "bbo_count", "order_book_count"):
        old = before.get(key)
        new = after.get(key)

        if old is None or new is None:
            continue

        if new < old:
            reset_fields.append(key)

    return bool(reset_fields), reset_fields


def _book_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    available = bool(
        _nested(snapshot, "order_book", "available", default=False)
    )
    bid = _safe_float(
        _nested(snapshot, "order_book", "top_bid_price", default=None)
    )
    ask = _safe_float(
        _nested(snapshot, "order_book", "top_ask_price", default=None)
    )
    bid_depth = _safe_float(
        _nested(snapshot, "order_book", "bid_depth", default=0)
    ) or 0.0
    ask_depth = _safe_float(
        _nested(snapshot, "order_book", "ask_depth", default=0)
    ) or 0.0
    bid_levels = _safe_int(
        _nested(snapshot, "order_book", "bid_level_count", default=0)
    ) or 0
    ask_levels = _safe_int(
        _nested(snapshot, "order_book", "ask_level_count", default=0)
    ) or 0

    crossed = bool(
        bid is not None
        and ask is not None
        and bid > ask
    )
    locked = bool(
        bid is not None
        and ask is not None
        and bid == ask
    )
    one_sided = bool(
        available
        and (
            bid is None
            or ask is None
            or bid_depth <= 0
            or ask_depth <= 0
            or bid_levels <= 0
            or ask_levels <= 0
        )
    )

    return {
        "available": available,
        "top_bid_price": bid,
        "top_ask_price": ask,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "bid_level_count": bid_levels,
        "ask_level_count": ask_levels,
        "crossed": crossed,
        "locked": locked,
        "one_sided": one_sided,
    }


def evaluate_rithmic_feed_integrity(
    snapshot: dict[str, Any] | None,
    *,
    history_path: str | Path,
    max_history: int = 12,
) -> dict[str, Any]:
    history_file = Path(history_path)
    history = _load_history(history_file)

    current = _compact(snapshot) if isinstance(snapshot, dict) else {}
    duplicate_current = bool(
        current
        and history
        and _fingerprint(history[-1]) == _fingerprint(current)
    )

    previous = history[-1] if history else None

    login_ok = bool(
        _nested(current, "connection", "login_ok", default=False)
    )
    market_data_ok = bool(
        _nested(current, "connection", "market_data_ok", default=False)
    )

    freshness = current.get("freshness")
    freshness = freshness if isinstance(freshness, dict) else {}

    fresh_trade = bool(freshness.get("has_fresh_trade"))
    fresh_bbo = bool(freshness.get("has_fresh_bbo"))
    fresh_book = bool(freshness.get("has_fresh_order_book"))

    book = _book_state(current)

    reset_detected, reset_fields = _counter_reset(previous, current)

    current_time = _safe_float(current.get("updated_at_epoch"))
    previous_time = (
        _safe_float(previous.get("updated_at_epoch"))
        if isinstance(previous, dict)
        else None
    )
    time_regression = bool(
        current_time is not None
        and previous_time is not None
        and current_time < previous_time
    )

    recent = list(history[-2:])
    if current and not duplicate_current:
        recent.append(current)
    elif current and duplicate_current and not recent:
        recent.append(current)

    frozen_signature = bool(
        len(recent) >= 3
        and len({_market_fingerprint(item) for item in recent}) == 1
    )

    both_quote_channels_stale = bool(
        not fresh_bbo and not fresh_book
    )

    warnings: list[str] = []
    hard_failures: list[str] = []

    if not current:
        hard_failures.append("SNAPSHOT_MISSING")
    if current and not login_ok:
        hard_failures.append("LOGIN_NOT_OK")
    if current and not market_data_ok:
        hard_failures.append("MARKET_DATA_NOT_OK")
    if time_regression:
        hard_failures.append("SNAPSHOT_TIME_REGRESSION")
    if book["crossed"]:
        hard_failures.append("CROSSED_BOOK")
    if current and not book["available"]:
        hard_failures.append("ORDER_BOOK_UNAVAILABLE")
    if current and both_quote_channels_stale:
        hard_failures.append("BBO_AND_ORDER_BOOK_STALE")

    if reset_detected:
        warnings.append("COUNTER_RESET_OR_RECONNECT_SIGNATURE")
    if book["locked"]:
        warnings.append("LOCKED_BOOK")
    if book["one_sided"]:
        warnings.append("ONE_SIDED_BOOK")
    if current and not fresh_trade:
        warnings.append("TRADE_CHANNEL_STALE_OR_QUIET")
    if current and not fresh_bbo:
        warnings.append("BBO_CHANNEL_STALE")
    if current and not fresh_book:
        warnings.append("ORDER_BOOK_CHANNEL_STALE")
    if frozen_signature:
        warnings.append("FROZEN_OR_QUIET_MARKET_SIGNATURE")
    if duplicate_current:
        warnings.append("UNCHANGED_SNAPSHOT_REEVALUATED")

    continuity_valid = bool(
        current
        and not reset_detected
        and not time_regression
    )

    if hard_failures:
        status = hard_failures[0]
        integrity_ok = False
    elif reset_detected:
        status = "RESET_REPRIME_REQUIRED"
        integrity_ok = False
    elif book["locked"] or book["one_sided"]:
        status = "DEGRADED_BOOK"
        integrity_ok = False
    elif not fresh_trade:
        status = "TRADE_STALE_OR_QUIET"
        integrity_ok = True
    elif not fresh_bbo or not fresh_book:
        status = "PARTIAL_CHANNEL_STALENESS"
        integrity_ok = False
    elif frozen_signature:
        status = "FROZEN_OR_QUIET_SIGNATURE"
        integrity_ok = False
    else:
        status = "HEALTHY"
        integrity_ok = True

    is_test_environment = bool(current.get("is_test_environment"))
    environment_grade = (
        "TEST_ENVIRONMENT"
        if is_test_environment
        else "NON_TEST_ENVIRONMENT"
    )

    production_data_eligible = bool(
        integrity_ok
        and continuity_valid
        and not is_test_environment
        and login_ok
        and market_data_ok
        and book["available"]
        and fresh_bbo
        and fresh_book
    )

    if current and not duplicate_current:
        persisted = (history + [current])[-max_history:]
        _write_history(history_file, persisted)
    else:
        persisted = history[-max_history:]

    return {
        "engine": "RITHMIC_FEED_INTEGRITY_GUARD_V1",
        "status": status,
        "integrity_ok": integrity_ok,
        "continuity_valid": continuity_valid,
        "production_data_eligible": production_data_eligible,
        "environment_grade": environment_grade,
        "connection": {
            "login_ok": login_ok,
            "market_data_ok": market_data_ok,
        },
        "freshness": {
            "has_fresh_trade": fresh_trade,
            "has_fresh_bbo": fresh_bbo,
            "has_fresh_order_book": fresh_book,
            "last_trade_age_seconds": freshness.get("last_trade_age_seconds"),
            "last_bbo_age_seconds": freshness.get("last_bbo_age_seconds"),
            "last_order_book_age_seconds": freshness.get(
                "last_order_book_age_seconds"
            ),
        },
        "book": book,
        "continuity": {
            "counter_reset_detected": reset_detected,
            "reset_fields": reset_fields,
            "snapshot_time_regression": time_regression,
            "frozen_or_quiet_signature": frozen_signature,
            "duplicate_snapshot": duplicate_current,
            "history_snapshot_count": len(persisted),
        },
        "sequence_gap_check": {
            "status": "UNAVAILABLE",
            "reason": (
                "No exchange sequence-number field is proven in the current "
                "Phase 5C cached snapshot schema."
            ),
        },
        "warnings": warnings,
        "hard_failures": hard_failures,
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "trade_action": "NO_AUTO_TRADE",
    }


def format_feed_integrity_text(result: dict[str, Any]) -> str:
    connection = result.get("connection") or {}
    freshness = result.get("freshness") or {}
    continuity = result.get("continuity") or {}
    book = result.get("book") or {}

    lines = [
        "[RITHMIC FEED INTEGRITY]",
        f"status = {result.get('status')}",
        f"integrity_ok = {result.get('integrity_ok')}",
        f"continuity_valid = {result.get('continuity_valid')}",
        (
            "production_data_eligible = "
            f"{result.get('production_data_eligible')}"
        ),
        f"environment_grade = {result.get('environment_grade')}",
        f"login_ok = {connection.get('login_ok')}",
        f"market_data_ok = {connection.get('market_data_ok')}",
        f"fresh_trade = {freshness.get('has_fresh_trade')}",
        f"fresh_bbo = {freshness.get('has_fresh_bbo')}",
        f"fresh_order_book = {freshness.get('has_fresh_order_book')}",
        f"book_available = {book.get('available')}",
        f"book_crossed = {book.get('crossed')}",
        f"book_locked = {book.get('locked')}",
        f"book_one_sided = {book.get('one_sided')}",
        (
            "counter_reset_detected = "
            f"{continuity.get('counter_reset_detected')}"
        ),
        (
            "frozen_or_quiet_signature = "
            f"{continuity.get('frozen_or_quiet_signature')}"
        ),
        (
            "sequence_gap_check = "
            f"{(result.get('sequence_gap_check') or {}).get('status')}"
        ),
        f"warnings = {', '.join(result.get('warnings') or [])}",
        f"hard_failures = {', '.join(result.get('hard_failures') or [])}",
        f"decision_impact = {result.get('decision_impact')}",
        (
            "can_influence_decision = "
            f"{result.get('can_influence_decision')}"
        ),
        f"safe_for_execution = {result.get('safe_for_execution')}",
    ]
    return "\n".join(lines)
