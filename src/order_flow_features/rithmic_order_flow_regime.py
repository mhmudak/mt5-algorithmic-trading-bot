from __future__ import annotations

from typing import Any

DECISION_IMPACT = "NONE"
CAN_INFLUENCE_DECISION = False
SAFE_FOR_EXECUTION = False


def _status(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("status") or "").upper()


def _bool(payload: dict[str, Any] | None, section: str, key: str) -> bool:
    if not isinstance(payload, dict):
        return False
    block = payload.get(section)
    if not isinstance(block, dict):
        return False
    return bool(block.get(key))


def evaluate_rithmic_order_flow_regime(
    *,
    feed_integrity: dict[str, Any] | None = None,
    absorption_exhaustion: dict[str, Any] | None = None,
    liquidity_pull_replenishment: dict[str, Any] | None = None,
    delta_price_divergence: dict[str, Any] | None = None,
    volume_profile_migration: dict[str, Any] | None = None,
    anti_fakeout: dict[str, Any] | None = None,
    signal: str | None = None,
    session: str | None = None,
) -> dict[str, Any]:
    feed_integrity = feed_integrity if isinstance(feed_integrity, dict) else {}
    absorption_exhaustion = absorption_exhaustion if isinstance(absorption_exhaustion, dict) else {}
    liquidity_pull_replenishment = liquidity_pull_replenishment if isinstance(liquidity_pull_replenishment, dict) else {}
    delta_price_divergence = delta_price_divergence if isinstance(delta_price_divergence, dict) else {}
    volume_profile_migration = volume_profile_migration if isinstance(volume_profile_migration, dict) else {}
    anti_fakeout = anti_fakeout if isinstance(anti_fakeout, dict) else {}

    signal_name = str(signal or "").upper()
    integrity_ok = bool(feed_integrity.get("integrity_ok"))
    continuity_valid = bool(feed_integrity.get("continuity_valid"))

    absorption_status = _status(absorption_exhaustion)
    liquidity_status = _status(liquidity_pull_replenishment)
    divergence_status = _status(delta_price_divergence)
    profile_status = _status(volume_profile_migration)
    anti_fakeout_status = _status(anti_fakeout)

    buy_effective = bool(
        absorption_status == "BUY_AGGRESSION_EFFECTIVE"
        or divergence_status == "BUY_FLOW_PRICE_CONFIRMED"
    )
    sell_effective = bool(
        absorption_status == "SELL_AGGRESSION_EFFECTIVE"
        or divergence_status == "SELL_FLOW_PRICE_CONFIRMED"
    )

    buy_confirm_count = sum([
        absorption_status == "BUY_AGGRESSION_EFFECTIVE",
        divergence_status == "BUY_FLOW_PRICE_CONFIRMED",
        profile_status == "POC_MIGRATING_UP_WITH_PRICE",
        _bool(volume_profile_migration, "signal_context", "profile_supports_signal")
        and signal_name == "BUY",
    ])
    sell_confirm_count = sum([
        absorption_status == "SELL_AGGRESSION_EFFECTIVE",
        divergence_status == "SELL_FLOW_PRICE_CONFIRMED",
        profile_status == "POC_MIGRATING_DOWN_WITH_PRICE",
        _bool(volume_profile_migration, "signal_context", "profile_supports_signal")
        and signal_name == "SELL",
    ])

    buy_failure = bool(
        divergence_status == "POTENTIAL_TRAPPED_BUYERS"
        or absorption_status.startswith("BUY_AGGRESSION_ABSORBED")
    )
    sell_failure = bool(
        divergence_status == "POTENTIAL_TRAPPED_SELLERS"
        or absorption_status.startswith("SELL_AGGRESSION_ABSORBED")
    )
    buy_exhaustion = absorption_status == "BUY_AGGRESSION_EXHAUSTING"
    sell_exhaustion = absorption_status == "SELL_AGGRESSION_EXHAUSTING"

    liquidity_unstable = "LIQUIDITY_PULL_RISK" in liquidity_status
    anti_fakeout_risk = bool(
        "SPOOF" in anti_fakeout_status
        or "FLICKER" in anti_fakeout_status
        or "UNTRUST" in anti_fakeout_status
    )
    profile_conflict = bool(
        profile_status == "POC_PRICE_MIGRATION_CONFLICT"
        or _bool(volume_profile_migration, "signal_context", "profile_conflicts_signal")
    )
    value_acceptance = profile_status == "PRICE_ACCEPTING_NEAR_STABLE_POC"
    directional_conflict = bool(
        (buy_effective and sell_effective)
        or (buy_confirm_count > 0 and sell_confirm_count > 0)
    )

    if not integrity_ok or not continuity_valid:
        regime, direction, confidence = "FEED_UNUSABLE", "NEUTRAL", "NONE"
    elif liquidity_unstable or anti_fakeout_risk:
        regime, direction, confidence = "LIQUIDITY_UNSTABLE", "NEUTRAL", "LOW"
    elif directional_conflict or profile_conflict:
        regime, direction, confidence = "CONFLICTING_FLOW", "NEUTRAL", "LOW"
    elif buy_failure:
        regime, direction, confidence = "BUY_AGGRESSION_FAILURE_RISK", "SELL_RISK", "MODERATE"
    elif sell_failure:
        regime, direction, confidence = "SELL_AGGRESSION_FAILURE_RISK", "BUY_RISK", "MODERATE"
    elif buy_exhaustion:
        regime, direction, confidence = "BUY_EXHAUSTION_RISK", "SELL_RISK", "MODERATE"
    elif sell_exhaustion:
        regime, direction, confidence = "SELL_EXHAUSTION_RISK", "BUY_RISK", "MODERATE"
    elif buy_confirm_count >= 2 and buy_effective:
        regime, direction, confidence = "BUY_TREND_CONFIRMED", "BUY", "HIGH"
    elif sell_confirm_count >= 2 and sell_effective:
        regime, direction, confidence = "SELL_TREND_CONFIRMED", "SELL", "HIGH"
    elif buy_effective:
        regime, direction, confidence = "BUY_FLOW_EFFECTIVE", "BUY", "MODERATE"
    elif sell_effective:
        regime, direction, confidence = "SELL_FLOW_EFFECTIVE", "SELL", "MODERATE"
    elif value_acceptance:
        regime, direction, confidence = "VALUE_ACCEPTANCE_BALANCED", "NEUTRAL", "MODERATE"
    else:
        regime, direction, confidence = "MIXED_OR_INSUFFICIENT", "NEUTRAL", "LOW"

    signal_alignment = "NOT_APPLICABLE"
    if signal_name in ("BUY", "SELL"):
        if direction == signal_name:
            signal_alignment = "ALIGNED"
        elif direction in ("BUY", "SELL"):
            signal_alignment = "CONFLICT"
        elif (signal_name == "BUY" and direction == "BUY_RISK") or (
            signal_name == "SELL" and direction == "SELL_RISK"
        ):
            signal_alignment = "SUPPORTIVE_RISK"
        elif (signal_name == "BUY" and direction == "SELL_RISK") or (
            signal_name == "SELL" and direction == "BUY_RISK"
        ):
            signal_alignment = "ADVERSE_RISK"
        else:
            signal_alignment = "NEUTRAL"

    return {
        "engine": "RITHMIC_ORDER_FLOW_REGIME_V1",
        "regime": regime,
        "direction": direction,
        "confidence": confidence,
        "signal": signal_name or None,
        "session": session,
        "signal_alignment": signal_alignment,
        "evidence": {
            "buy_confirm_count": buy_confirm_count,
            "sell_confirm_count": sell_confirm_count,
            "buy_effective": buy_effective,
            "sell_effective": sell_effective,
            "buy_aggression_failure": buy_failure,
            "sell_aggression_failure": sell_failure,
            "buy_exhaustion": buy_exhaustion,
            "sell_exhaustion": sell_exhaustion,
            "liquidity_unstable": liquidity_unstable,
            "anti_fakeout_risk": anti_fakeout_risk,
            "profile_conflict": profile_conflict,
            "value_acceptance": value_acceptance,
            "directional_conflict": directional_conflict,
        },
        "component_status": {
            "feed_integrity": _status(feed_integrity),
            "absorption_exhaustion": absorption_status,
            "liquidity_pull_replenishment": liquidity_status,
            "delta_price_divergence": divergence_status,
            "volume_profile_migration": profile_status,
            "anti_fakeout": anti_fakeout_status,
        },
        "policy": {
            "creates_new_signal": False,
            "summarizes_existing_evidence_only": True,
            "executed_flow_required_for_trend_confirmation": True,
            "dom_cannot_confirm_trend_alone": True,
            "research_only": True,
        },
        "decision_impact": DECISION_IMPACT,
        "can_influence_decision": CAN_INFLUENCE_DECISION,
        "safe_for_execution": SAFE_FOR_EXECUTION,
        "trade_action": "NO_AUTO_TRADE",
    }


def format_order_flow_regime_text(result: dict[str, Any]) -> str:
    evidence = result.get("evidence") or {}
    lines = [
        "[RITHMIC ORDER-FLOW REGIME]",
        f"regime = {result.get('regime')}",
        f"direction = {result.get('direction')}",
        f"confidence = {result.get('confidence')}",
        f"signal = {result.get('signal')}",
        f"signal_alignment = {result.get('signal_alignment')}",
        f"session = {result.get('session')}",
        f"buy_confirm_count = {evidence.get('buy_confirm_count')}",
        f"sell_confirm_count = {evidence.get('sell_confirm_count')}",
        f"liquidity_unstable = {evidence.get('liquidity_unstable')}",
        f"directional_conflict = {evidence.get('directional_conflict')}",
        f"decision_impact = {result.get('decision_impact')}",
        f"can_influence_decision = {result.get('can_influence_decision')}",
        f"safe_for_execution = {result.get('safe_for_execution')}",
    ]
    return "\n".join(lines)
