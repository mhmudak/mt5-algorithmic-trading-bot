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
class ProfileThresholds:
    poc_migration_ticks: float
    acceptance_band_ticks: float
    rejection_distance_ticks: float
    min_acceptance_observations: int


def thresholds_for_session(session: str | None) -> ProfileThresholds:
    name = str(session or "").upper()

    if any(token in name for token in ("OVERLAP", "NEW_YORK", "NEW YORK", "COMEX")):
        return ProfileThresholds(
            poc_migration_ticks=2.0,
            acceptance_band_ticks=1.5,
            rejection_distance_ticks=3.0,
            min_acceptance_observations=2,
        )

    if "LONDON" in name:
        return ProfileThresholds(
            poc_migration_ticks=1.5,
            acceptance_band_ticks=1.5,
            rejection_distance_ticks=2.5,
            min_acceptance_observations=2,
        )

    return ProfileThresholds(
        poc_migration_ticks=1.0,
        acceptance_band_ticks=2.0,
        rejection_distance_ticks=2.0,
        min_acceptance_observations=2,
    )


def _fingerprint(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("symbol"),
        _safe_float(snapshot.get("updated_at_epoch")),
        _safe_float(
            _nested(
                snapshot,
                "volume_profile",
                "rolling_poc_price",
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
        "volume_profile",
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
        "phase": "RITHMIC_VOLUME_PROFILE_MIGRATION_HISTORY_V1",
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


def _poc(snapshot: dict[str, Any]) -> float | None:
    return _safe_float(
        _nested(
            snapshot,
            "volume_profile",
            "rolling_poc_price",
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


def _near_poc(
    snapshot: dict[str, Any],
    *,
    tick_size: float,
    band_ticks: float,
) -> bool:
    poc = _poc(snapshot)
    price = _price(snapshot)

    if poc is None or price is None:
        return False

    return abs(price - poc) / tick_size <= band_ticks


def evaluate_rithmic_volume_profile_migration(
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

    current_poc = _poc(current)
    current_price = _price(current)

    previous_poc = (
        _poc(previous)
        if isinstance(previous, dict)
        else None
    )
    previous_price = (
        _price(previous)
        if isinstance(previous, dict)
        else None
    )

    poc_change = None
    poc_change_ticks = None
    price_vs_poc_ticks = None
    previous_price_vs_poc_ticks = None

    if current_poc is not None and previous_poc is not None:
        poc_change = current_poc - previous_poc
        poc_change_ticks = poc_change / tick_size

    if current_poc is not None and current_price is not None:
        price_vs_poc_ticks = (
            current_price - current_poc
        ) / tick_size

    if previous_poc is not None and previous_price is not None:
        previous_price_vs_poc_ticks = (
            previous_price - previous_poc
        ) / tick_size

    poc_migrating_up = bool(
        poc_change_ticks is not None
        and poc_change_ticks
        >= thresholds.poc_migration_ticks
    )
    poc_migrating_down = bool(
        poc_change_ticks is not None
        and poc_change_ticks
        <= -thresholds.poc_migration_ticks
    )
    poc_stable = bool(
        poc_change_ticks is not None
        and abs(poc_change_ticks)
        < thresholds.poc_migration_ticks
    )

    price_near_poc = bool(
        price_vs_poc_ticks is not None
        and abs(price_vs_poc_ticks)
        <= thresholds.acceptance_band_ticks
    )

    recent_for_acceptance = history[-(
        thresholds.min_acceptance_observations - 1
    ):]

    acceptance_observations = sum(
        1
        for item in recent_for_acceptance
        if _near_poc(
            item,
            tick_size=tick_size,
            band_ticks=thresholds.acceptance_band_ticks,
        )
    )

    if price_near_poc:
        acceptance_observations += 1

    accepting_near_poc = bool(
        acceptance_observations
        >= thresholds.min_acceptance_observations
    )

    previous_near_poc = bool(
        previous_price_vs_poc_ticks is not None
        and abs(previous_price_vs_poc_ticks)
        <= thresholds.acceptance_band_ticks
    )

    rejection_above_poc = bool(
        previous_near_poc
        and price_vs_poc_ticks is not None
        and price_vs_poc_ticks
        >= thresholds.rejection_distance_ticks
    )

    rejection_below_poc = bool(
        previous_near_poc
        and price_vs_poc_ticks is not None
        and price_vs_poc_ticks
        <= -thresholds.rejection_distance_ticks
    )

    price_following_up_migration = bool(
        poc_migrating_up
        and current_price is not None
        and previous_price is not None
        and current_price > previous_price
    )

    price_following_down_migration = bool(
        poc_migrating_down
        and current_price is not None
        and previous_price is not None
        and current_price < previous_price
    )

    migration_price_conflict = bool(
        (
            poc_migrating_up
            and current_price is not None
            and previous_price is not None
            and current_price <= previous_price
        )
        or (
            poc_migrating_down
            and current_price is not None
            and previous_price is not None
            and current_price >= previous_price
        )
    )

    if not current:
        status = "SNAPSHOT_MISSING"
    elif not integrity_ok or not continuity_valid:
        status = "FEED_INTEGRITY_NOT_USABLE"
    elif not fresh_trade:
        status = "TRADE_FLOW_STALE"
    elif current_poc is None or current_price is None:
        status = "POC_OR_PRICE_UNAVAILABLE"
    elif previous is None or previous_poc is None or previous_price is None:
        status = "INSUFFICIENT_HISTORY"
    elif rejection_above_poc:
        status = "PRICE_REJECTED_UP_FROM_POC"
    elif rejection_below_poc:
        status = "PRICE_REJECTED_DOWN_FROM_POC"
    elif poc_migrating_up and price_following_up_migration:
        status = "POC_MIGRATING_UP_WITH_PRICE"
    elif poc_migrating_down and price_following_down_migration:
        status = "POC_MIGRATING_DOWN_WITH_PRICE"
    elif migration_price_conflict:
        status = "POC_PRICE_MIGRATION_CONFLICT"
    elif accepting_near_poc and poc_stable:
        status = "PRICE_ACCEPTING_NEAR_STABLE_POC"
    elif poc_migrating_up:
        status = "POC_MIGRATING_UP"
    elif poc_migrating_down:
        status = "POC_MIGRATING_DOWN"
    else:
        status = "STABLE_OR_TRANSITIONAL"

    signal_name = str(signal or "").upper()

    profile_supports_signal = bool(
        (
            signal_name == "BUY"
            and (
                price_following_up_migration
                or rejection_above_poc
            )
        )
        or (
            signal_name == "SELL"
            and (
                price_following_down_migration
                or rejection_below_poc
            )
        )
    )

    profile_conflicts_signal = bool(
        (
            signal_name == "BUY"
            and (
                price_following_down_migration
                or rejection_below_poc
            )
        )
        or (
            signal_name == "SELL"
            and (
                price_following_up_migration
                or rejection_above_poc
            )
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
        "engine": "RITHMIC_VOLUME_PROFILE_MIGRATION_V1",
        "status": status,
        "signal": signal_name or None,
        "session": session,
        "poc": {
            "previous": previous_poc,
            "current": current_poc,
            "change": (
                round(poc_change, 6)
                if poc_change is not None
                else None
            ),
            "change_ticks": (
                round(poc_change_ticks, 6)
                if poc_change_ticks is not None
                else None
            ),
            "migrating_up": poc_migrating_up,
            "migrating_down": poc_migrating_down,
            "stable": poc_stable,
        },
        "price_context": {
            "previous_price": previous_price,
            "current_price": current_price,
            "price_vs_poc_ticks": (
                round(price_vs_poc_ticks, 6)
                if price_vs_poc_ticks is not None
                else None
            ),
            "accepting_near_poc": accepting_near_poc,
            "acceptance_observations": acceptance_observations,
            "rejection_above_poc": rejection_above_poc,
            "rejection_below_poc": rejection_below_poc,
            "price_following_up_migration": (
                price_following_up_migration
            ),
            "price_following_down_migration": (
                price_following_down_migration
            ),
            "migration_price_conflict": (
                migration_price_conflict
            ),
        },
        "signal_context": {
            "profile_supports_signal": (
                profile_supports_signal
            ),
            "profile_conflicts_signal": (
                profile_conflicts_signal
            ),
        },
        "history": {
            "history_path": str(history_file),
            "snapshot_count": len(persisted),
            "current_snapshot_was_duplicate": duplicate,
            "deduplication_enabled": True,
        },
        "policy": {
            "uses_executed_volume_poc": True,
            "vah_val_available": False,
            "full_volume_at_price_export_required_for_vah_val": True,
            "poc_is_context_not_execution_authority": True,
            "thresholds_are_research_only": True,
        },
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "trade_action": "NO_AUTO_TRADE",
    }


def format_volume_profile_migration_text(
    result: dict[str, Any],
) -> str:
    poc = result.get("poc") or {}
    price_context = result.get("price_context") or {}
    signal_context = result.get("signal_context") or {}
    history = result.get("history") or {}

    lines = [
        "[RITHMIC VOLUME PROFILE MIGRATION]",
        f"status = {result.get('status')}",
        f"signal = {result.get('signal')}",
        f"session = {result.get('session')}",
        f"previous_poc = {poc.get('previous')}",
        f"current_poc = {poc.get('current')}",
        f"poc_change_ticks = {poc.get('change_ticks')}",
        f"poc_migrating_up = {poc.get('migrating_up')}",
        f"poc_migrating_down = {poc.get('migrating_down')}",
        (
            "price_vs_poc_ticks = "
            f"{price_context.get('price_vs_poc_ticks')}"
        ),
        (
            "accepting_near_poc = "
            f"{price_context.get('accepting_near_poc')}"
        ),
        (
            "rejection_above_poc = "
            f"{price_context.get('rejection_above_poc')}"
        ),
        (
            "rejection_below_poc = "
            f"{price_context.get('rejection_below_poc')}"
        ),
        (
            "migration_price_conflict = "
            f"{price_context.get('migration_price_conflict')}"
        ),
        (
            "profile_supports_signal = "
            f"{signal_context.get('profile_supports_signal')}"
        ),
        (
            "profile_conflicts_signal = "
            f"{signal_context.get('profile_conflicts_signal')}"
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
