from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.rithmic_setup_verdict as rv


def test_v1_shadow_and_v2_both_display() -> None:
    verdict = {
        "verdict": "NEUTRAL",
        "setup_direction": "BUY",
        "reason": (
            "evidence_family_coverage_below_minimum"
        ),
        "rithmic_symbol": "GCZ6",
        "exchange": "COMEX",
        "source_age_seconds": 0.4,
        "trade_count": 491,
        "metrics": {
            "delta": -143.0,
            "cumulative_delta": -143.0,
            "dom_depth_imbalance": -0.038,
        },

        "legacy_v1_evaluated": True,
        "legacy_v1_support_score": 2,
        "legacy_v1_against_score": 1,
        "legacy_v1_alignment": "SUPPORTS_BUY",
        "legacy_v1_mode": "SHADOW_ONLY",
        "legacy_v1_can_influence_decision": False,

        "support_score": 0,
        "against_score": 1,
        "evidence_family_coverage": "3/6",
        "evidence_family_states": {
            "AGGRESSION": "SELL",
            "AUCTION_PROFILE": "NEUTRAL",
            "FOOTPRINT_ACCEPTANCE": "UNAVAILABLE",
            "ABSORPTION_EXHAUSTION": "NEUTRAL",
            "LIQUIDITY_DYNAMICS": "UNAVAILABLE",
            "DIVERGENCE_TRAP": "UNAVAILABLE",
        },
        "evidence_feed_status": "HEALTHY",
        "evidence_order_flow_regime": (
            "SELL_FLOW_EFFECTIVE"
        ),

        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }

    block = (
        rv
        .format_rithmic_setup_verdict_telegram_block(
            verdict
        )
    )

    assert "V1 LEGACY — SHADOW ONLY" in block
    assert "Trades 491" in block
    assert (
        "Evidence: 2 SUPPORT / 1 AGAINST"
        in block
    )

    assert (
        "V2 EVIDENCE FAMILIES — VERDICT MODEL"
        in block
    )

    assert (
        "Aggression: 🔴 AGAINST"
        in block
    )

    assert (
        "Families: 0 SUPPORT / 1 AGAINST"
        in block
    )

    assert "Coverage: 3 / 6" in block
    assert (
        "Regime: SELL_FLOW_EFFECTIVE"
        in block
    )
    assert (
        "Feed Integrity: HEALTHY"
        in block
    )

    print(
        "PASS: setup form displays V1 shadow "
        "and V2 family verdict together"
    )


def test_v1_disagreement_cannot_change_v2_verdict() -> None:
    """
    Prove the architecture:
    raw V1 can be strongly BUY while V2 is strongly SELL.
    Production verdict must follow V2.
    """

    old_registration = (
        rv._load_phase5v_registration
    )

    old_loader = (
        rv._load_phase5g_evidence_families_v2
    )

    try:
        rv._load_phase5v_registration = (
            lambda: {
                "registered": True,
                "reason": "ok",
                "payload": {
                    "symbol": "GCZ6",
                    "source_market": "COMEX",
                },
            }
        )

        rv._load_phase5g_evidence_families_v2 = (
            lambda symbol: (
                {
                    "engine": (
                        "RITHMIC_EVIDENCE_FAMILIES_V2"
                    ),
                    "feed_gate": {
                        "usable": True,
                        "reason": "healthy",
                        "feed_status": "HEALTHY",
                    },
                    "families": {
                        "AGGRESSION": {
                            "state": "SELL",
                            "reason": "test",
                        },
                        "AUCTION_PROFILE": {
                            "state": "SELL",
                            "reason": "test",
                        },
                        "FOOTPRINT_ACCEPTANCE": {
                            "state": "UNAVAILABLE",
                            "reason": "test",
                        },
                        "ABSORPTION_EXHAUSTION": {
                            "state": "NEUTRAL",
                            "reason": "test",
                        },
                        "LIQUIDITY_DYNAMICS": {
                            "state": "NEUTRAL",
                            "reason": "test",
                        },
                        "DIVERGENCE_TRAP": {
                            "state": "NEUTRAL",
                            "reason": "test",
                        },
                    },
                    "modifiers": {
                        "order_flow_regime": {
                            "regime": "SELL_FLOW_EFFECTIVE",
                        },
                    },
                    "decision_impact": "NONE",
                    "can_influence_decision": False,
                    "safe_for_execution": False,
                    "execution_allowed": False,
                },
                "ok",
                0.2,
            )
        )

        # Strongly bullish legacy raw metrics.
        context = {
            "rithmic": {
                "available": True,
                "status": "OBSERVE_ONLY_READY",
                "rithmic_symbol": "GCZ6",
                "exchange": "COMEX",
                "cache_status": "FRESH_CACHE",
                "cache_age_seconds": 0.2,
                "freshness": {
                    "snapshot_age_seconds": 0.2,
                    "snapshot_fresh": True,
                    "last_trade_age_seconds": 0.2,
                    "last_bbo_age_seconds": 0.2,
                    "last_order_book_age_seconds": 0.2,
                    "has_fresh_trade": True,
                    "has_fresh_bbo": True,
                    "has_fresh_order_book": True,
                },
                "metrics": {
                    "trade_count": 50,
                    "bbo_count": 50,
                    "nonzero_bbo_count": 50,
                    "order_book_count": 50,
                    "delta": 50.0,
                    "cumulative_delta": 100.0,
                    "dom_depth_imbalance": 0.8,
                    "dom_bid_depth": 5000.0,
                    "dom_ask_depth": 1000.0,
                },
            }
        }

        result = (
            rv.build_rithmic_setup_verdict(
                context,
                "BUY",
            )
        )

    finally:
        rv._load_phase5v_registration = (
            old_registration
        )

        rv._load_phase5g_evidence_families_v2 = (
            old_loader
        )

    assert result["legacy_v1_evaluated"] is True
    assert (
        result["legacy_v1_support_score"]
        >= 2
    )

    # V2 is two independent SELL families.
    assert result["against_score"] == 2
    assert result["support_score"] == 0

    assert result["verdict"] == "AGAINST_SETUP"
    assert result["alignment"] == "AGAINST_BUY"

    assert result["decision_impact"] == "NONE"
    assert (
        result["can_influence_decision"]
        is False
    )
    assert result["execution_allowed"] is False

    print(
        "PASS: V1 shadow disagreement cannot "
        "override production V2 verdict"
    )


def test_source_contains_explicit_shadow_policy() -> None:
    source = Path(
        rv.__file__
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        '"legacy_v1_mode": "SHADOW_ONLY"'
        in source
    )

    assert (
        '"legacy_v1_can_influence_decision": False'
        in source
    )

    print(
        "PASS: V1 legacy scorer is explicitly "
        "marked shadow-only/non-authoritative"
    )


def main() -> None:
    test_v1_shadow_and_v2_both_display()
    test_v1_disagreement_cannot_change_v2_verdict()
    test_source_contains_explicit_shadow_policy()

    print("")
    print(
        "[PASS] Rithmic dual V1-shadow / "
        "V2-verdict setup-form contract verified."
    )


if __name__ == "__main__":
    main()
