from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.order_flow_features.rithmic_evidence_families import (
    BUY,
    CONFLICT,
    NEUTRAL,
    SELL,
    UNAVAILABLE,
    build_rithmic_evidence_families,
)


def base_bridge() -> dict:
    return {
        "feed_integrity": {
            "engine": (
                "RITHMIC_FEED_INTEGRITY_GUARD_V1"
            ),
            "status": "HEALTHY",
            "integrity_ok": True,
            "continuity_valid": True,
        },
        "anti_fakeout": {
            "engine": "RITHMIC_ANTI_FAKEOUT_V1",
            "status": "NEUTRAL",
            "freshness_gate": {
                "has_fresh_trade": True,
                "has_fresh_bbo": True,
                "has_fresh_order_book": True,
                "all_fresh": True,
            },
            "executed_flow": {
                "trade_count": 82,
                "total_volume": 84.0,
                "delta": -16.0,
                "cumulative_delta": -16.0,
                "flow_imbalance": -0.190476,
                "direction": -1,
                "sufficient": True,
            },
            "footprint": {
                "footprint_imbalance": -0.190476,
                "direction": -1,
                "recent_candle_delta": -16.0,
                "recent_candle_volume": 68.0,
                "strength_ok": True,
            },
            "spoof_risk": False,
            "dom_only_untrusted": False,
        },
        "absorption_exhaustion": {
            "engine": (
                "RITHMIC_ABSORPTION_EXHAUSTION_V1"
            ),
            "status": "SELL_AGGRESSION_EFFECTIVE",
            "flow": {
                "direction": -1,
            },
            "classification": {
                "aggression_effective": True,
                "absorbed": False,
                "exhaustion": False,
            },
        },
        "liquidity_pull_replenishment": {
            "engine": (
                "RITHMIC_LIQUIDITY_PULL_REPLENISHMENT_V1"
            ),
            "status": "STABLE_OR_MIXED",
            "bid": {
                "replenishment": False,
                "pull_risk": False,
            },
            "ask": {
                "replenishment": False,
                "pull_risk": False,
            },
            "policy": {
                "aggregate_depth_only": True,
            },
        },
        "delta_price_divergence": {
            "engine": (
                "RITHMIC_DELTA_PRICE_DIVERGENCE_V1"
            ),
            "status": "DELTA_CHANGE_TOO_SMALL",
            "classification": {
                "potential_trapped_buyers": False,
                "potential_trapped_sellers": False,
                "buyer_flow_effective": False,
                "seller_flow_effective": False,
                "bullish_price_without_delta": False,
                "bearish_price_without_delta": False,
            },
        },
        "volume_profile_migration": {
            "engine": (
                "RITHMIC_VOLUME_PROFILE_MIGRATION_V1"
            ),
            "status": (
                "PRICE_ACCEPTING_NEAR_STABLE_POC"
            ),
            "poc": {
                "change_ticks": 0.0,
                "migrating_up": False,
                "migrating_down": False,
                "stable": True,
            },
            "price_context": {
                "price_vs_poc_ticks": -1.0,
                "accepting_near_poc": True,
                "rejection_above_poc": False,
                "rejection_below_poc": False,
                "price_following_up_migration": False,
                "price_following_down_migration": False,
                "migration_price_conflict": False,
            },
        },
        "order_flow_regime": {
            "regime": "SELL_FLOW_EFFECTIVE",
            "direction": "SELL",
            "confidence": "MODERATE",
        },
    }


def assert_state(
    result: dict,
    family: str,
    expected: str,
) -> None:
    actual = (
        result["families"][family]["state"]
    )

    assert actual == expected, (
        family,
        actual,
        expected,
    )


def test_live_like_case_avoids_double_counting():
    bridge = base_bridge()

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert_state(
        result,
        "AGGRESSION",
        SELL,
    )
    assert_state(
        result,
        "AUCTION_PROFILE",
        NEUTRAL,
    )
    assert_state(
        result,
        "FOOTPRINT_ACCEPTANCE",
        UNAVAILABLE,
    )
    assert_state(
        result,
        "ABSORPTION_EXHAUSTION",
        NEUTRAL,
    )
    assert_state(
        result,
        "LIQUIDITY_DYNAMICS",
        NEUTRAL,
    )
    assert_state(
        result,
        "DIVERGENCE_TRAP",
        NEUTRAL,
    )

    summary = result["summary"]

    assert summary["coverage"] == "5/6"
    assert summary["buy_count"] == 0
    assert summary["sell_count"] == 1
    assert summary["neutral_count"] == 4
    assert summary["unavailable_count"] == 1

    assert summary["support_count"] == 0
    assert summary["against_count"] == 1

    print(
        "PASS: effective SELL flow becomes one "
        "independent family vote, not duplicated "
        "across footprint/absorption/divergence"
    )


def test_stale_trade_flow_cannot_vote_aggression():
    bridge = base_bridge()

    bridge[
        "anti_fakeout"
    ][
        "freshness_gate"
    ][
        "has_fresh_trade"
    ] = False

    bridge[
        "anti_fakeout"
    ][
        "freshness_gate"
    ][
        "all_fresh"
    ] = False

    bridge[
        "anti_fakeout"
    ]["status"] = "STALE"

    result = build_rithmic_evidence_families(
        bridge,
        signal="SELL",
    )

    assert_state(
        result,
        "AGGRESSION",
        UNAVAILABLE,
    )

    assert (
        result["summary"]["support_count"]
        == 0
    )

    print(
        "PASS: stale executed trades cannot create "
        "an Aggression family vote even when the "
        "overall BBO/DOM feed remains usable"
    )


def test_nonproduction_feed_gates_all_families():
    bridge = base_bridge()

    bridge[
        "feed_integrity"
    ][
        "production_data_eligible"
    ] = False

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert (
        result["feed_gate"]["usable"]
        is False
    )

    assert (
        result["feed_gate"]["reason"]
        == "feed_not_production_data_eligible"
    )

    assert (
        result["summary"]["available_count"]
        == 0
    )

    assert (
        result["summary"]["unavailable_count"]
        == 6
    )

    print(
        "PASS: explicitly non-production Rithmic "
        "feed cannot create Evidence Families votes"
    )


def test_bad_feed_makes_every_family_unavailable():
    bridge = base_bridge()

    bridge["feed_integrity"][
        "integrity_ok"
    ] = False

    result = build_rithmic_evidence_families(
        bridge,
        signal="SELL",
    )

    assert (
        result["summary"]["available_count"]
        == 0
    )
    assert (
        result["summary"]["unavailable_count"]
        == 6
    )
    assert (
        result["summary"]["support_count"]
        == 0
    )
    assert (
        result["summary"]["against_count"]
        == 0
    )

    print(
        "PASS: Feed Integrity is a hard evidence "
        "availability gate, never a directional vote"
    )


def test_absorbed_buyers_vote_sell_once():
    bridge = base_bridge()

    bridge["anti_fakeout"][
        "executed_flow"
    ]["direction"] = 1

    bridge["anti_fakeout"][
        "executed_flow"
    ]["delta"] = 20

    bridge["anti_fakeout"][
        "executed_flow"
    ]["flow_imbalance"] = 0.25

    absorption = bridge[
        "absorption_exhaustion"
    ]

    absorption[
        "status"
    ] = "BUY_AGGRESSION_ABSORBED"

    absorption[
        "flow"
    ]["direction"] = 1

    absorption[
        "classification"
    ]["absorbed"] = True

    absorption[
        "classification"
    ]["aggression_effective"] = False

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert_state(
        result,
        "AGGRESSION",
        BUY,
    )
    assert_state(
        result,
        "ABSORPTION_EXHAUSTION",
        SELL,
    )

    assert (
        result["summary"]["support_count"]
        == 1
    )
    assert (
        result["summary"]["against_count"]
        == 1
    )

    print(
        "PASS: buy aggression and buyer absorption "
        "remain separate conflicting families"
    )


def test_profile_requires_price_confirmation():
    bridge = base_bridge()

    profile = bridge[
        "volume_profile_migration"
    ]

    profile[
        "status"
    ] = "POC_MIGRATING_UP"

    profile["poc"]["migrating_up"] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "AUCTION_PROFILE",
        NEUTRAL,
    )

    profile[
        "status"
    ] = "POC_MIGRATING_UP_WITH_PRICE"

    profile[
        "price_context"
    ][
        "price_following_up_migration"
    ] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "AUCTION_PROFILE",
        BUY,
    )

    print(
        "PASS: POC movement alone is context; "
        "POC + price confirmation becomes directional"
    )


def test_liquidity_context_is_directional_but_secondary():
    bridge = base_bridge()

    liquidity = bridge[
        "liquidity_pull_replenishment"
    ]

    liquidity[
        "bid"
    ]["replenishment"] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "LIQUIDITY_DYNAMICS",
        BUY,
    )

    liquidity[
        "ask"
    ]["replenishment"] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "LIQUIDITY_DYNAMICS",
        CONFLICT,
    )

    print(
        "PASS: aggregate liquidity cues create at "
        "most one liquidity-family vote"
    )


def test_trapped_sellers_vote_buy():
    bridge = base_bridge()

    divergence = bridge[
        "delta_price_divergence"
    ]

    divergence[
        "status"
    ] = "POTENTIAL_TRAPPED_SELLERS"

    divergence[
        "classification"
    ][
        "potential_trapped_sellers"
    ] = True

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert_state(
        result,
        "DIVERGENCE_TRAP",
        BUY,
    )

    assert (
        result["summary"]["support_count"]
        == 1
    )

    print(
        "PASS: trapped-seller divergence supports "
        "BUY as one independent family"
    )


def test_effective_flow_is_not_recounted_as_divergence():
    bridge = base_bridge()

    divergence = bridge[
        "delta_price_divergence"
    ]

    divergence[
        "status"
    ] = "SELL_FLOW_PRICE_CONFIRMED"

    divergence[
        "classification"
    ][
        "seller_flow_effective"
    ] = True

    result = build_rithmic_evidence_families(
        bridge
    )

    assert_state(
        result,
        "DIVERGENCE_TRAP",
        NEUTRAL,
    )

    print(
        "PASS: flow effectiveness is not counted "
        "again inside Divergence/Trap"
    )


def test_safety_contract():
    result = build_rithmic_evidence_families(
        base_bridge(),
        signal="SELL",
    )

    assert result["decision_impact"] == "NONE"
    assert (
        result["can_influence_decision"]
        is False
    )
    assert result["safe_for_execution"] is False
    assert result["execution_allowed"] is False

    assert (
        result["policy"][
            "one_vote_max_per_family"
        ]
        is True
    )

    assert (
        result["policy"][
            "unavailable_is_not_neutral"
        ]
        is True
    )

    print(
        "PASS: Evidence Families V2 has zero "
        "decision/execution authority"
    )


def main() -> None:
    test_live_like_case_avoids_double_counting()
    test_stale_trade_flow_cannot_vote_aggression()
    test_nonproduction_feed_gates_all_families()
    test_bad_feed_makes_every_family_unavailable()
    test_absorbed_buyers_vote_sell_once()
    test_profile_requires_price_confirmation()
    test_liquidity_context_is_directional_but_secondary()
    test_trapped_sellers_vote_buy()
    test_effective_flow_is_not_recounted_as_divergence()
    test_safety_contract()

    print("")
    print(
        "[PASS] Rithmic Evidence Families V2 "
        "independent-family contract verified."
    )


if __name__ == "__main__":
    main()
