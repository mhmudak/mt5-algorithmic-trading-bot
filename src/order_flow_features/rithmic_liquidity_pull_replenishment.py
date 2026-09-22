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


@dataclass(frozen=True)
class LiquidityThresholds:
    pull_ratio: float
    replenishment_ratio: float
    min_persistence_ratio: float
    max_touch_shift_ticks: float


def thresholds_for_session(session: str | None) -> LiquidityThresholds:
    name = str(session or "").upper()

    if any(token in name for token in ("OVERLAP", "NEW_YORK", "NEW YORK", "COMEX")):
        return LiquidityThresholds(
            pull_ratio=0.45,
            replenishment_ratio=0.30,
            min_persistence_ratio=0.45,
            max_touch_shift_ticks=1.5,
        )

    if "LONDON" in name:
        return LiquidityThresholds(
            pull_ratio=0.50,
            replenishment_ratio=0.30,
            min_persistence_ratio=0.40,
            max_touch_shift_ticks=1.5,
        )

    return LiquidityThresholds(
        pull_ratio=0.55,
        replenishment_ratio=0.35,
        min_persistence_ratio=0.35,
        max_touch_shift_ticks=2.0,
    )


def _fingerprint(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("symbol"),
        _safe_float(snapshot.get("updated_at_epoch")),
        _nested(snapshot, "sample", "order_book_count", default=None),
        _safe_float(
            _nested(
                snapshot,
                "order_book",
                "last_received_at_epoch",
                default=None,
            )
        ),
        _safe_float(
            _nested(snapshot, "order_book", "top_bid_price", default=None)
        ),
        _safe_float(
            _nested(snapshot, "order_book", "top_ask_price", default=None)
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
        "order_book",
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
        "phase": "RITHMIC_LIQUIDITY_PULL_REPLENISHMENT_HISTORY_V1",
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


def _price_key(price: float, tick_size: float) -> int:
    return int(round(price / tick_size))


def _levels_by_price(
    snapshot: dict[str, Any],
    side: str,
    *,
    tick_size: float,
    top_n: int,
) -> dict[int, dict[str, Any]]:
    raw = _nested(
        snapshot,
        "order_book",
        f"{side}_levels",
        default=[],
    )
    raw = raw if isinstance(raw, list) else []

    clean: list[dict[str, Any]] = []

    for level in raw:
        if not isinstance(level, dict):
            continue

        price = _safe_float(level.get("price"))
        size = _safe_int(level.get("size"))

        if price is None or price <= 0 or size < 0:
            continue

        clean.append(
            {
                "price": price,
                "size": size,
                "orders": _safe_int(level.get("orders")),
                "implicit_size": _safe_int(
                    level.get("implicit_size")
                ),
            }
        )

    reverse = side == "bid"
    clean.sort(
        key=lambda item: item["price"],
        reverse=reverse,
    )

    result: dict[int, dict[str, Any]] = {}

    for item in clean[:top_n]:
        result[_price_key(item["price"], tick_size)] = item

    return result


def _compare_side(
    previous: dict[str, Any],
    current: dict[str, Any],
    side: str,
    *,
    tick_size: float,
    top_n: int,
    thresholds: LiquidityThresholds,
) -> dict[str, Any]:
    prev = _levels_by_price(
        previous,
        side,
        tick_size=tick_size,
        top_n=top_n,
    )
    cur = _levels_by_price(
        current,
        side,
        tick_size=tick_size,
        top_n=top_n,
    )

    prev_total = sum(item["size"] for item in prev.values())
    cur_total = sum(item["size"] for item in cur.values())

    same_price_added = 0
    same_price_removed = 0
    disappeared_size = 0
    new_price_size = 0
    persistent_size = 0

    for key in set(prev) | set(cur):
        old = prev.get(key)
        new = cur.get(key)

        if old is not None and new is not None:
            old_size = old["size"]
            new_size = new["size"]
            persistent_size += min(old_size, new_size)

            if new_size > old_size:
                same_price_added += new_size - old_size
            elif old_size > new_size:
                same_price_removed += old_size - new_size

        elif old is not None:
            disappeared_size += old["size"]

        elif new is not None:
            new_price_size += new["size"]

    depth_removed_proxy = (
        same_price_removed + disappeared_size
    )
    depth_added_proxy = (
        same_price_added + new_price_size
    )

    pull_ratio = (
        depth_removed_proxy / max(1.0, float(prev_total))
        if prev_total > 0
        else 0.0
    )

    same_price_replenishment_ratio = (
        same_price_added / max(1.0, float(prev_total))
        if prev_total > 0
        else 0.0
    )

    persistence_ratio = (
        persistent_size / max(1.0, float(prev_total))
        if prev_total > 0
        else 0.0
    )

    prev_touch = (
        max(item["price"] for item in prev.values())
        if side == "bid" and prev
        else min(item["price"] for item in prev.values())
        if side == "ask" and prev
        else None
    )
    cur_touch = (
        max(item["price"] for item in cur.values())
        if side == "bid" and cur
        else min(item["price"] for item in cur.values())
        if side == "ask" and cur
        else None
    )

    touch_shift_ticks = None

    if prev_touch is not None and cur_touch is not None:
        touch_shift_ticks = (
            cur_touch - prev_touch
        ) / tick_size

    stable_touch = bool(
        touch_shift_ticks is not None
        and abs(touch_shift_ticks)
        <= thresholds.max_touch_shift_ticks
    )

    pull_risk = bool(
        prev_total > 0
        and stable_touch
        and pull_ratio >= thresholds.pull_ratio
        and persistence_ratio
        < thresholds.min_persistence_ratio
    )

    replenishment = bool(
        prev_total > 0
        and stable_touch
        and same_price_replenishment_ratio
        >= thresholds.replenishment_ratio
    )

    return {
        "previous_depth_top_n": prev_total,
        "current_depth_top_n": cur_total,
        "depth_added_proxy": depth_added_proxy,
        "depth_removed_proxy": depth_removed_proxy,
        "same_price_added_proxy": same_price_added,
        "same_price_removed_proxy": same_price_removed,
        "disappeared_depth_proxy": disappeared_size,
        "new_price_depth_proxy": new_price_size,
        "pull_ratio": round(pull_ratio, 6),
        "same_price_replenishment_ratio": round(
            same_price_replenishment_ratio,
            6,
        ),
        "persistence_ratio": round(
            persistence_ratio,
            6,
        ),
        "previous_touch_price": prev_touch,
        "current_touch_price": cur_touch,
        "touch_shift_ticks": (
            round(touch_shift_ticks, 6)
            if touch_shift_ticks is not None
            else None
        ),
        "touch_stable_for_comparison": stable_touch,
        "pull_risk": pull_risk,
        "replenishment": replenishment,
        "note": (
            "Depth changes are aggregate-book proxies. "
            "They are not exact add/cancel lifecycle events."
        ),
    }


def evaluate_rithmic_liquidity_pull_replenishment(
    snapshot: dict[str, Any] | None,
    *,
    history_path: str | Path,
    feed_integrity: dict[str, Any] | None = None,
    signal: str | None = None,
    session: str | None = None,
    tick_size: float = 0.1,
    top_n: int = 5,
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

    fresh_book = bool(
        _nested(
            current,
            "freshness",
            "has_fresh_order_book",
            default=False,
        )
    )

    thresholds = thresholds_for_session(session)
    tick_size = max(1e-9, float(tick_size))
    top_n = max(1, int(top_n))

    if previous is not None and current:
        bid = _compare_side(
            previous,
            current,
            "bid",
            tick_size=tick_size,
            top_n=top_n,
            thresholds=thresholds,
        )
        ask = _compare_side(
            previous,
            current,
            "ask",
            tick_size=tick_size,
            top_n=top_n,
            thresholds=thresholds,
        )
    else:
        bid = None
        ask = None

    if not current:
        status = "SNAPSHOT_MISSING"
    elif not integrity_ok or not continuity_valid:
        status = "FEED_INTEGRITY_NOT_USABLE"
    elif not fresh_book:
        status = "ORDER_BOOK_STALE"
    elif previous is None:
        status = "INSUFFICIENT_HISTORY"
    elif bid["pull_risk"] and ask["pull_risk"]:
        status = "TWO_SIDED_LIQUIDITY_PULL_RISK"
    elif bid["pull_risk"]:
        status = "BID_LIQUIDITY_PULL_RISK"
    elif ask["pull_risk"]:
        status = "ASK_LIQUIDITY_PULL_RISK"
    elif bid["replenishment"] and ask["replenishment"]:
        status = "TWO_SIDED_REPLENISHMENT"
    elif bid["replenishment"]:
        status = "BID_REPLENISHMENT"
    elif ask["replenishment"]:
        status = "ASK_REPLENISHMENT"
    else:
        status = "STABLE_OR_MIXED"

    signal_name = str(signal or "").upper()

    liquidity_pull_against_signal = bool(
        (signal_name == "BUY" and bid and bid["pull_risk"])
        or (
            signal_name == "SELL"
            and ask
            and ask["pull_risk"]
        )
    )

    liquidity_replenishment_supports_signal = bool(
        (
            signal_name == "BUY"
            and bid
            and bid["replenishment"]
        )
        or (
            signal_name == "SELL"
            and ask
            and ask["replenishment"]
        )
    )

    opposing_liquidity_pull_supports_signal = bool(
        (
            signal_name == "BUY"
            and ask
            and ask["pull_risk"]
        )
        or (
            signal_name == "SELL"
            and bid
            and bid["pull_risk"]
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
        "engine": "RITHMIC_LIQUIDITY_PULL_REPLENISHMENT_V1",
        "status": status,
        "signal": signal_name or None,
        "session": session,
        "top_n_levels": top_n,
        "bid": bid,
        "ask": ask,
        "signal_context": {
            "liquidity_pull_against_signal": (
                liquidity_pull_against_signal
            ),
            "liquidity_replenishment_supports_signal": (
                liquidity_replenishment_supports_signal
            ),
            "opposing_liquidity_pull_supports_signal": (
                opposing_liquidity_pull_supports_signal
            ),
        },
        "history": {
            "history_path": str(history_file),
            "snapshot_count": len(persisted),
            "current_snapshot_was_duplicate": duplicate,
            "deduplication_enabled": True,
        },
        "policy": {
            "aggregate_depth_only": True,
            "exact_cancel_add_available": False,
            "exact_mbo_lifecycle_available": False,
            "dom_is_secondary_context_only": True,
            "can_confirm_setup_alone": False,
            "thresholds_are_research_only": True,
        },
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "trade_action": "NO_AUTO_TRADE",
    }


def format_liquidity_pull_replenishment_text(
    result: dict[str, Any],
) -> str:
    bid = result.get("bid") or {}
    ask = result.get("ask") or {}
    context = result.get("signal_context") or {}
    history = result.get("history") or {}

    lines = [
        "[RITHMIC LIQUIDITY PULL / REPLENISHMENT]",
        f"status = {result.get('status')}",
        f"signal = {result.get('signal')}",
        f"session = {result.get('session')}",
        f"top_n_levels = {result.get('top_n_levels')}",
        f"bid_pull_ratio = {bid.get('pull_ratio')}",
        (
            "bid_replenishment_ratio = "
            f"{bid.get('same_price_replenishment_ratio')}"
        ),
        (
            "bid_persistence_ratio = "
            f"{bid.get('persistence_ratio')}"
        ),
        f"bid_pull_risk = {bid.get('pull_risk')}",
        f"bid_replenishment = {bid.get('replenishment')}",
        f"ask_pull_ratio = {ask.get('pull_ratio')}",
        (
            "ask_replenishment_ratio = "
            f"{ask.get('same_price_replenishment_ratio')}"
        ),
        (
            "ask_persistence_ratio = "
            f"{ask.get('persistence_ratio')}"
        ),
        f"ask_pull_risk = {ask.get('pull_risk')}",
        f"ask_replenishment = {ask.get('replenishment')}",
        (
            "liquidity_pull_against_signal = "
            f"{context.get('liquidity_pull_against_signal')}"
        ),
        (
            "liquidity_replenishment_supports_signal = "
            f"{context.get('liquidity_replenishment_supports_signal')}"
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
