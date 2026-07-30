from __future__ import annotations

from datetime import datetime
from typing import Any


PHASE = "PHASE_5AH_SETUP_CONFLICT_RESOLVER"

DEFAULT_MAX_MINUTES = 30
DEFAULT_MAX_ENTRY_DISTANCE = 3.0
DEFAULT_MIN_CONFLICT_RR = 2.5


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def normalize_direction(value: Any) -> str:
    text = safe_text(value).upper()
    if text in {"BUY", "LONG", "BULLISH"}:
        return "BUY"
    if text in {"SELL", "SHORT", "BEARISH"}:
        return "SELL"
    return ""


def opposite_direction(a: Any, b: Any) -> bool:
    da = normalize_direction(a)
    db = normalize_direction(b)
    return bool(da and db and da != db)


def parse_time(value: Any) -> datetime | None:
    if value is None:
        return None

    text = safe_text(value)
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1]

    candidates = [
        text,
        text.replace(" ", "T"),
    ]

    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            pass

    return None


def minutes_between(a: Any, b: Any) -> float | None:
    ta = parse_time(a)
    tb = parse_time(b)

    if not ta or not tb:
        return None

    return abs((tb - ta).total_seconds()) / 60.0


def get_entry(setup: dict[str, Any]) -> float:
    return safe_float(
        setup.get("entry")
        or setup.get("entry_price")
        or setup.get("price")
        or setup.get("planned_entry")
    )


def get_rr(setup: dict[str, Any]) -> float:
    return safe_float(
        setup.get("rr")
        or setup.get("risk_reward")
        or setup.get("rr_value")
        or setup.get("reward_risk")
    )


def get_score(setup: dict[str, Any]) -> float:
    return safe_float(setup.get("score") or setup.get("setup_score"))


def get_min_required_score(setup: dict[str, Any]) -> float:
    return safe_float(
        setup.get("min_required_score")
        or setup.get("required_score")
        or setup.get("min_score")
    )


def setup_state(setup: dict[str, Any]) -> str:
    explicit_state = safe_text(setup.get("state") or setup.get("status")).upper()
    if explicit_state:
        return explicit_state

    reason = safe_text(
        setup.get("entry_skip_reason")
        or setup.get("skip_reason")
        or setup.get("rejection_reason")
        or setup.get("reason")
    ).lower()

    if "m5_body_too_small" in reason:
        return "ENTRY_SKIPPED_WEAK_CONFIRMATION"

    if "score_too_low" in reason:
        return "REJECTED_SCORE_TOO_LOW"

    if "rejected" in reason:
        return "TRACKED_REJECTED_CANDIDATE"

    return "SETUP_DETECTED"


def combined_setup_text(setup: dict[str, Any]) -> str:
    return "|".join(
        [
            safe_text(setup.get("strategy")),
            safe_text(setup.get("entry_model")),
            safe_text(setup.get("type")),
            safe_text(setup.get("trigger")),
            safe_text(setup.get("reason")),
        ]
    ).upper()


def infer_strategy_family(setup: dict[str, Any]) -> str:
    text = combined_setup_text(setup)

    if "MICRO_SR_SWEEP_RECLAIM" in text or "SWEEP_RECLAIM" in text:
        return "SWEEP_RECLAIM"

    if "FAILED_FVG_REVERSAL" in text or "FAILED_FVG" in text:
        return "FAILED_FVG_REVERSAL"

    if "KEY_LEVEL_BREAK_HOLD" in text or "BREAK_HOLD" in text:
        return "BREAK_HOLD"

    if "ORDER_BLOCK" in text or "MTF_OB" in text or "OB_ENTRY" in text:
        return "ORDER_BLOCK"

    if "PRO_TRADER_REPLICATION" in text:
        return "PRO_TRADER_REPLICATION"

    if "ORB" in text or "OPENING_RANGE" in text:
        return "ORB"

    if "INTRABAR" in text or "TICK_SNIPER" in text:
        return "INTRABAR"

    strategy = safe_text(setup.get("strategy")).upper()
    return strategy or "UNKNOWN"


def is_micro_sweep_reclaim(setup: dict[str, Any]) -> bool:
    return infer_strategy_family(setup) == "SWEEP_RECLAIM"


def has_entry_quality_weakness(setup: dict[str, Any]) -> bool:
    state = setup_state(setup)
    reason = safe_text(
        setup.get("entry_skip_reason")
        or setup.get("skip_reason")
        or setup.get("rejection_reason")
        or setup.get("reason")
    ).lower()

    return (
        state == "ENTRY_SKIPPED_WEAK_CONFIRMATION"
        or "m5_body_too_small" in reason
        or "weak_confirmation" in reason
        or "body_too_small" in reason
    )


def is_score_rejected(setup: dict[str, Any]) -> bool:
    state = setup_state(setup)
    reason = safe_text(setup.get("rejection_reason") or setup.get("reason")).lower()

    return state == "REJECTED_SCORE_TOO_LOW" or "score_too_low" in reason


def below_required_score(setup: dict[str, Any]) -> bool:
    score = get_score(setup)
    required = get_min_required_score(setup)
    return bool(required and score and score < required)


def is_high_value_sweep_reclaim(
    setup: dict[str, Any],
    *,
    min_conflict_rr: float,
) -> bool:
    return bool(
        infer_strategy_family(setup) == "SWEEP_RECLAIM"
        and get_rr(setup) >= min_conflict_rr
        and get_score(setup) >= 88
    )


def classify_family_conflict(previous_family: str, new_family: str) -> dict[str, Any]:
    pair = f"{previous_family}_VS_{new_family}"

    rules = {
        "FAILED_FVG_REVERSAL_VS_SWEEP_RECLAIM": {
            "rule": "SWEEP_RECLAIM_CAN_OVERRIDE_WEAK_FAILED_FVG_ENTRY",
            "preferred_confirmation": "sweep_reclaim_plus_failed_continuation",
            "default_action": "PRIORITY_REVIEW_IF_WEAK_OR_REJECTED",
        },
        "SWEEP_RECLAIM_VS_FAILED_FVG_REVERSAL": {
            "rule": "PRIOR_SWEEP_RECLAIM_REMAINS_IMPORTANT_AGAINST_NEW_FAILED_FVG",
            "preferred_confirmation": "respect_prior_sweep_reclaim_until_invalidated",
            "default_action": "PRIORITY_REVIEW_IF_WEAK_OR_REJECTED",
        },
        "BREAK_HOLD_VS_SWEEP_RECLAIM": {
            "rule": "BREAKOUT_VS_TRAP_CONFLICT",
            "preferred_confirmation": "wait_for_hold_or_reclaim_failure",
            "default_action": "WAIT",
        },
        "SWEEP_RECLAIM_VS_BREAK_HOLD": {
            "rule": "TRAP_VS_BREAKOUT_CONFLICT",
            "preferred_confirmation": "wait_for_retest_or_displacement",
            "default_action": "WAIT",
        },
        "ORDER_BLOCK_VS_SWEEP_RECLAIM": {
            "rule": "ORDER_BLOCK_VS_LIQUIDITY_TRAP",
            "preferred_confirmation": "fresh_ob_plus_sweep_reclaim_context",
            "default_action": "WAIT",
        },
        "SWEEP_RECLAIM_VS_ORDER_BLOCK": {
            "rule": "LIQUIDITY_TRAP_VS_ORDER_BLOCK",
            "preferred_confirmation": "absorption_or_reclaim_confirmation",
            "default_action": "WAIT",
        },
    }

    return rules.get(
        pair,
        {
            "rule": "GENERIC_OPPOSITE_STRATEGY_CONFLICT",
            "preferred_confirmation": "wait_for_closed_candle_retest_or_sweep_reclaim",
            "default_action": "WAIT",
        },
    ) | {"pair": pair}


def resolve_setup_conflict(
    previous_setup: dict[str, Any],
    new_setup: dict[str, Any],
    *,
    max_minutes: int = DEFAULT_MAX_MINUTES,
    max_entry_distance: float = DEFAULT_MAX_ENTRY_DISTANCE,
    min_conflict_rr: float = DEFAULT_MIN_CONFLICT_RR,
) -> dict[str, Any]:
    previous_direction = normalize_direction(previous_setup.get("signal") or previous_setup.get("direction"))
    new_direction = normalize_direction(new_setup.get("signal") or new_setup.get("direction"))

    previous_entry = get_entry(previous_setup)
    new_entry = get_entry(new_setup)
    entry_distance = abs(previous_entry - new_entry) if previous_entry and new_entry else None

    time_gap_minutes = minutes_between(
        previous_setup.get("created_at") or previous_setup.get("time") or previous_setup.get("detected_at"),
        new_setup.get("created_at") or new_setup.get("time") or new_setup.get("detected_at"),
    )

    previous_state = setup_state(previous_setup)
    new_state = setup_state(new_setup)

    previous_family = infer_strategy_family(previous_setup)
    new_family = infer_strategy_family(new_setup)
    family_rule = classify_family_conflict(previous_family, new_family)

    same_zone = (
        entry_distance is not None
        and entry_distance <= max_entry_distance
    )

    time_close = (
        time_gap_minutes is not None
        and time_gap_minutes <= max_minutes
    )

    directional_conflict = opposite_direction(previous_direction, new_direction)

    previous_rr = get_rr(previous_setup)
    new_rr = get_rr(new_setup)
    previous_score = get_score(previous_setup)
    new_score = get_score(new_setup)
    previous_min_required_score = get_min_required_score(previous_setup)
    new_min_required_score = get_min_required_score(new_setup)

    previous_entry_weak = has_entry_quality_weakness(previous_setup)
    new_entry_weak = has_entry_quality_weakness(new_setup)

    previous_score_rejected = is_score_rejected(previous_setup)
    new_score_rejected = is_score_rejected(new_setup)

    previous_below_required = below_required_score(previous_setup)
    new_below_required = below_required_score(new_setup)

    conflict_detected = bool(directional_conflict and same_zone and time_close)

    # Phase 5AL tightening:
    # A sweep/reclaim conflict is NOT automatically priority just because it has good RR.
    # Historical backfill showed that broad promotion can be dangerous.
    # Priority now requires the OPPOSING setup to have entry-quality weakness
    # such as m5_body_too_small / weak confirmation.
    new_sweep_priority = bool(
        conflict_detected
        and is_high_value_sweep_reclaim(new_setup, min_conflict_rr=min_conflict_rr)
        and previous_entry_weak
        and (
            new_score_rejected
            or new_below_required
            or new_family == "SWEEP_RECLAIM"
        )
    )

    previous_sweep_priority = bool(
        conflict_detected
        and is_high_value_sweep_reclaim(previous_setup, min_conflict_rr=min_conflict_rr)
        and new_entry_weak
        and (
            previous_score_rejected
            or previous_below_required
            or previous_family == "SWEEP_RECLAIM"
        )
    )

    priority_conflict_review = bool(new_sweep_priority or previous_sweep_priority)

    if new_sweep_priority:
        conflict_status = "DIRECTIONAL_CONFLICT_SAME_ZONE_PRIORITY_REVIEW"
        previous_action = (
            "DOWNGRADE_OLDER_SETUP_ENTRY_QUALITY_WEAK"
            if previous_entry_weak
            else "REVIEW_OLDER_SETUP_AGAINST_NEW_SWEEP_RECLAIM"
        )
        new_action = "PROMOTE_REJECTED_MICRO_SWEEP_TO_PRIORITY_CONFLICT_REVIEW"
        trade_action = "WAIT_OR_MANUAL_REVIEW"
        priority_side = "NEW_SETUP"
        priority_family = new_family

    elif previous_sweep_priority:
        conflict_status = "DIRECTIONAL_CONFLICT_SAME_ZONE_PRIORITY_REVIEW"
        previous_action = "KEEP_PRIOR_MICRO_SWEEP_PRIORITY_REVIEW"
        new_action = "REVIEW_NEW_SETUP_AGAINST_PRIOR_MICRO_SWEEP_CONFLICT"
        trade_action = "WAIT_OR_MANUAL_REVIEW"
        priority_side = "PREVIOUS_SETUP"
        priority_family = previous_family

    elif conflict_detected:
        conflict_status = "DIRECTIONAL_CONFLICT_SAME_ZONE"
        previous_action = "REVIEW_OLDER_SETUP"
        new_action = "REVIEW_NEW_SETUP"
        trade_action = "WAIT"
        priority_side = "NONE"
        priority_family = "NONE"

    else:
        conflict_status = "NO_DIRECTIONAL_CONFLICT"
        previous_action = "UNCHANGED"
        new_action = "UNCHANGED"
        trade_action = "NO_CONFLICT_ACTION"
        priority_side = "NONE"
        priority_family = "NONE"

    return {
        "phase": PHASE,
        "conflict_detected": conflict_detected,
        "priority_conflict_review": priority_conflict_review,
        "conflict_status": conflict_status,
        "trade_action": trade_action,
        "auto_trade_allowed": False,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "strategy_family_matrix": {
            "previous_family": previous_family,
            "new_family": new_family,
            "pair": family_rule.get("pair"),
            "rule": family_rule.get("rule"),
            "preferred_confirmation": family_rule.get("preferred_confirmation"),
            "default_action": family_rule.get("default_action"),
            "priority_side": priority_side,
            "priority_family": priority_family,
            "priority_policy": "STRICT_OPPOSING_ENTRY_WEAKNESS_REQUIRED_OBSERVE_ONLY",
        },
        "previous_setup": {
            "setup_id": previous_setup.get("setup_id"),
            "strategy": previous_setup.get("strategy"),
            "family": previous_family,
            "direction": previous_direction,
            "entry": previous_entry,
            "score": previous_score,
            "min_required_score": previous_min_required_score,
            "rr": previous_rr,
            "state": previous_state,
            "entry_quality_weakness": previous_entry_weak,
            "score_rejected": previous_score_rejected,
            "below_required_score": previous_below_required,
            "action": previous_action,
        },
        "new_setup": {
            "setup_id": new_setup.get("setup_id"),
            "strategy": new_setup.get("strategy"),
            "family": new_family,
            "direction": new_direction,
            "entry": new_entry,
            "score": new_score,
            "min_required_score": new_min_required_score,
            "rr": new_rr,
            "state": new_state,
            "is_micro_sweep_reclaim": new_family == "SWEEP_RECLAIM",
            "score_rejected": new_score_rejected,
            "below_required_score": new_below_required,
            "action": new_action,
        },
        "conflict_metrics": {
            "time_gap_minutes": time_gap_minutes,
            "entry_distance": entry_distance,
            "same_zone": same_zone,
            "time_close": time_close,
            "directional_conflict": directional_conflict,
            "max_minutes": max_minutes,
            "max_entry_distance": max_entry_distance,
            "min_conflict_rr": min_conflict_rr,
        },
        "daily_pivot_rule": "CONTEXT_ONLY_NOT_HARD_BLOCK",
        "order_flow_rule": "OPTIONAL_CONFIRMATION_LAYER_NOT_REQUIRED_FOR_CONFLICT_STATE",
        "recommendation": (
            "Do not silently discard strong sweep/reclaim rejected candidates during same-zone opposite-direction conflicts. "
            "Use strategy-family conflict rules for manual review first. Keep observe-only until statistics prove execution safety."
        ),
    }
