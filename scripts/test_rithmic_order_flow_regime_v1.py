from __future__ import annotations

from pathlib import Path

from src.order_flow_features.rithmic_order_flow_regime import (
    evaluate_rithmic_order_flow_regime,
)

ROOT = Path(__file__).resolve().parents[1]

def healthy_feed():
    return {"status": "HEALTHY", "integrity_ok": True, "continuity_valid": True}

def test_buy_trend_confirmed():
    result = evaluate_rithmic_order_flow_regime(
        feed_integrity=healthy_feed(),
        absorption_exhaustion={"status": "BUY_AGGRESSION_EFFECTIVE"},
        delta_price_divergence={"status": "BUY_FLOW_PRICE_CONFIRMED"},
        volume_profile_migration={"status": "POC_MIGRATING_UP_WITH_PRICE"},
        liquidity_pull_replenishment={"status": "STABLE_OR_MIXED"},
        anti_fakeout={"status": "CONFIRMED"},
        signal="BUY",
        session="NEW_YORK_OPEN",
    )
    assert result["regime"] == "BUY_TREND_CONFIRMED"
    assert result["direction"] == "BUY"
    assert result["signal_alignment"] == "ALIGNED"
    assert result["confidence"] == "HIGH"

def test_buyers_trapped_reversal_risk():
    result = evaluate_rithmic_order_flow_regime(
        feed_integrity=healthy_feed(),
        absorption_exhaustion={"status": "BUY_AGGRESSION_ABSORBED"},
        delta_price_divergence={"status": "POTENTIAL_TRAPPED_BUYERS"},
        liquidity_pull_replenishment={"status": "STABLE_OR_MIXED"},
        volume_profile_migration={"status": "STABLE_OR_TRANSITIONAL"},
        signal="BUY",
    )
    assert result["regime"] == "BUY_AGGRESSION_FAILURE_RISK"
    assert result["direction"] == "SELL_RISK"
    assert result["signal_alignment"] == "ADVERSE_RISK"

def test_liquidity_instability_has_priority():
    result = evaluate_rithmic_order_flow_regime(
        feed_integrity=healthy_feed(),
        absorption_exhaustion={"status": "BUY_AGGRESSION_EFFECTIVE"},
        delta_price_divergence={"status": "BUY_FLOW_PRICE_CONFIRMED"},
        liquidity_pull_replenishment={"status": "BID_LIQUIDITY_PULL_RISK"},
        volume_profile_migration={"status": "POC_MIGRATING_UP_WITH_PRICE"},
        signal="BUY",
    )
    assert result["regime"] == "LIQUIDITY_UNSTABLE"
    assert result["direction"] == "NEUTRAL"

def test_conflicting_directional_evidence():
    result = evaluate_rithmic_order_flow_regime(
        feed_integrity=healthy_feed(),
        absorption_exhaustion={"status": "BUY_AGGRESSION_EFFECTIVE"},
        delta_price_divergence={"status": "SELL_FLOW_PRICE_CONFIRMED"},
        liquidity_pull_replenishment={"status": "STABLE_OR_MIXED"},
        volume_profile_migration={"status": "STABLE_OR_TRANSITIONAL"},
    )
    assert result["regime"] == "CONFLICTING_FLOW"
    assert result["evidence"]["directional_conflict"] is True

def test_value_acceptance_balanced():
    result = evaluate_rithmic_order_flow_regime(
        feed_integrity=healthy_feed(),
        absorption_exhaustion={"status": "BALANCED_OR_TRANSITIONAL"},
        delta_price_divergence={"status": "DELTA_CHANGE_TOO_SMALL"},
        liquidity_pull_replenishment={"status": "STABLE_OR_MIXED"},
        volume_profile_migration={"status": "PRICE_ACCEPTING_NEAR_STABLE_POC"},
    )
    assert result["regime"] == "VALUE_ACCEPTANCE_BALANCED"
    assert result["direction"] == "NEUTRAL"

def test_feed_failure_blocks_regime():
    result = evaluate_rithmic_order_flow_regime(
        feed_integrity={
            "status": "BBO_AND_ORDER_BOOK_STALE",
            "integrity_ok": False,
            "continuity_valid": False,
        },
        absorption_exhaustion={"status": "BUY_AGGRESSION_EFFECTIVE"},
        delta_price_divergence={"status": "BUY_FLOW_PRICE_CONFIRMED"},
    )
    assert result["regime"] == "FEED_UNUSABLE"
    assert result["confidence"] == "NONE"

def test_policy_observe_only():
    result = evaluate_rithmic_order_flow_regime(feed_integrity=healthy_feed())
    assert result["policy"]["creates_new_signal"] is False
    assert result["policy"]["dom_cannot_confirm_trend_alone"] is True
    assert result["decision_impact"] == "NONE"
    assert result["can_influence_decision"] is False
    assert result["safe_for_execution"] is False

def test_phase5g_wiring_is_observe_only():
    source = (
        ROOT / "scripts" / "build_phase5g_rithmic_monitoring_bridge.py"
    ).read_text(encoding="utf-8", errors="replace")
    required = (
        'bridge["order_flow_regime"]',
        "evaluate_rithmic_order_flow_regime",
        "format_order_flow_regime_text",
        "order_flow_regime_status",
    )
    for marker in required:
        assert marker in source, marker
    assert "execute_trade(" not in source
    assert "order_send(" not in source

def main():
    test_buy_trend_confirmed()
    test_buyers_trapped_reversal_risk()
    test_liquidity_instability_has_priority()
    test_conflicting_directional_evidence()
    test_value_acceptance_balanced()
    test_feed_failure_blocks_regime()
    test_policy_observe_only()
    test_phase5g_wiring_is_observe_only()
    print("PASS: aligned executed flow + delta/price can classify buy trend")
    print("PASS: trapped/absorbed buyers classify aggression-failure risk")
    print("PASS: liquidity instability overrides directional confirmation")
    print("PASS: conflicting directional evidence remains conflict")
    print("PASS: stable POC acceptance can classify balanced value")
    print("PASS: feed-integrity failure makes regime unavailable")
    print("PASS: regime classifier creates no new trading signal")
    print("PASS: Phase 5G regime wiring has no execution authority")

if __name__ == "__main__":
    main()
