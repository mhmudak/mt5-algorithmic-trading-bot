from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.rithmic_setup_verdict as verdict_module


def registration() -> dict:
    return {
        "registered": True,
        "reason": "ok",
        "payload": {
            "symbol": "GCZ6",
            "source_market": "COMEX",
        },
    }


def context(
    *,
    delta: float = 50.0,
    cumulative_delta: float = 100.0,
    dom_depth_imbalance: float = 0.8,
    dom_bid_depth: float = 1000.0,
    dom_ask_depth: float = 100.0,
) -> dict:
    return {
        "rithmic": {
            "available": True,
            "status": "AVAILABLE",
            "rithmic_symbol": "GCZ6",
            "exchange": "COMEX",
            "cache_status": "FRESH",
            "cache_age_seconds": 0.1,
            "freshness": {
                "snapshot_fresh": True,
                "has_fresh_trade": True,
                "has_fresh_bbo": True,
                "has_fresh_order_book": True,
                "snapshot_age_seconds": 0.1,
                "last_trade_age_seconds": 0.1,
                "last_bbo_age_seconds": 0.1,
                "last_order_book_age_seconds": 0.1,
            },
            "metrics": {
                "trade_count": 40,
                "bbo_count": 40,
                "nonzero_bbo_count": 40,
                "order_book_count": 40,
                "delta": delta,
                "cumulative_delta": cumulative_delta,
                "dom_depth_imbalance": dom_depth_imbalance,
                "dom_bid_depth": dom_bid_depth,
                "dom_ask_depth": dom_ask_depth,
            },
        }
    }


def family(
    state: str,
    reason: str = "synthetic_test",
) -> dict:
    return {
        "state": state,
        "reason": reason,
        "available": state != "UNAVAILABLE",
        "directional": state in {
            "BUY",
            "SELL",
        },
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
    }


def payload(
    *,
    aggression: str = "NEUTRAL",
    auction: str = "NEUTRAL",
    footprint: str = "UNAVAILABLE",
    absorption: str = "NEUTRAL",
    liquidity: str = "NEUTRAL",
    divergence: str = "NEUTRAL",
    feed_usable: bool = True,
) -> dict:
    return {
        "engine": "RITHMIC_EVIDENCE_FAMILIES_V2",
        "feed_gate": {
            "usable": feed_usable,
            "reason": (
                "healthy"
                if feed_usable
                else "synthetic_bad_feed"
            ),
        },
        "families": {
            "AGGRESSION": family(
                aggression
            ),
            "AUCTION_PROFILE": family(
                auction
            ),
            "FOOTPRINT_ACCEPTANCE": family(
                footprint
            ),
            "ABSORPTION_EXHAUSTION": family(
                absorption
            ),
            "LIQUIDITY_DYNAMICS": family(
                liquidity
            ),
            "DIVERGENCE_TRAP": family(
                divergence
            ),
        },
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }


def run_build(
    direction: str,
    v2_payload: dict,
):
    old_registration = (
        verdict_module._load_phase5v_registration
    )
    old_loader = (
        verdict_module
        ._load_phase5g_evidence_families_v2
    )

    try:
        verdict_module._load_phase5v_registration = (
            registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            lambda symbol: (
                v2_payload,
                "ok",
                0.2,
            )
        )

        return (
            verdict_module
            .build_rithmic_setup_verdict(
                context(),
                direction,
            )
        )

    finally:
        verdict_module._load_phase5v_registration = (
            old_registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            old_loader
        )


def test_two_independent_supporting_families():
    result = run_build(
        "BUY",
        payload(
            aggression="BUY",
            auction="BUY",
        ),
    )

    assert (
        result["verdict"]
        == "SUPPORTS_SETUP"
    )
    assert result["support_score"] == 2
    assert result["against_score"] == 0
    assert (
        result["evidence_family_coverage"]
        == "5/6"
    )

    print(
        "PASS: two independent BUY families "
        "support a BUY setup"
    )


def test_two_independent_opposing_families():
    result = run_build(
        "BUY",
        payload(
            aggression="SELL",
            auction="SELL",
        ),
    )

    assert (
        result["verdict"]
        == "AGAINST_SETUP"
    )
    assert result["support_score"] == 0
    assert result["against_score"] == 2

    print(
        "PASS: two independent SELL families "
        "oppose a BUY setup"
    )


def test_one_vs_one_is_mixed():
    result = run_build(
        "BUY",
        payload(
            aggression="BUY",
            auction="SELL",
        ),
    )

    assert result["verdict"] == "NEUTRAL"
    assert result["support_score"] == 1
    assert result["against_score"] == 1
    assert result["alignment"] == (
        "NEUTRAL_OR_MIXED_EVIDENCE_FAMILIES"
    )

    print(
        "PASS: BUY-vs-SELL family disagreement "
        "remains neutral/mixed"
    )


def test_low_coverage_cannot_be_decisive():
    result = run_build(
        "BUY",
        payload(
            aggression="BUY",
            auction="BUY",
            footprint="UNAVAILABLE",
            absorption="UNAVAILABLE",
            liquidity="UNAVAILABLE",
            divergence="NEUTRAL",
        ),
    )

    assert result["support_score"] == 2
    assert (
        result["evidence_family_available_count"]
        == 3
    )
    assert result["verdict"] == "NEUTRAL"
    assert result["alignment"] == (
        "NEUTRAL_INSUFFICIENT_"
        "EVIDENCE_FAMILY_COVERAGE"
    )

    print(
        "PASS: 3/6 coverage cannot create a "
        "decisive setup verdict"
    )


def test_bad_family_feed_gate_is_unavailable():
    result = run_build(
        "SELL",
        payload(
            aggression="SELL",
            auction="SELL",
            feed_usable=False,
        ),
    )

    assert result["verdict"] == "UNAVAILABLE"
    assert result["support_score"] == 0
    assert result["against_score"] == 0
    assert result["alignment"] == (
        "NOT_AVAILABLE_"
        "EVIDENCE_FAMILIES_FEED_GATE"
    )

    print(
        "PASS: unusable V2 feed gate cannot "
        "create a setup verdict"
    )


def test_missing_v2_never_falls_back_to_raw_score():
    old_registration = (
        verdict_module._load_phase5v_registration
    )
    old_loader = (
        verdict_module
        ._load_phase5g_evidence_families_v2
    )

    try:
        verdict_module._load_phase5v_registration = (
            registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            lambda symbol: (
                {},
                "evidence_families_v2_missing",
                0.2,
            )
        )

        # Raw metrics are intentionally extremely bullish.
        # They must NOT become a fallback verdict.
        result = (
            verdict_module
            .build_rithmic_setup_verdict(
                context(
                    delta=999.0,
                    cumulative_delta=9999.0,
                    dom_depth_imbalance=0.99,
                    dom_bid_depth=9999.0,
                    dom_ask_depth=1.0,
                ),
                "BUY",
            )
        )

    finally:
        verdict_module._load_phase5v_registration = (
            old_registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            old_loader
        )

    assert result["verdict"] == "UNAVAILABLE"
    assert result["support_score"] == 0
    assert result["against_score"] == 0

    print(
        "PASS: missing Evidence Families V2 "
        "never falls back to correlated raw scoring"
    )


def test_family_scoring_one_vote_max_per_family():
    p = payload(
        aggression="BUY",
        auction="BUY",
        absorption="SELL",
        liquidity="CONFLICT",
        divergence="NEUTRAL",
    )

    (
        support,
        against,
        evidence,
        summary,
    ) = (
        verdict_module
        .score_rithmic_evidence_families_for_direction(
            "BUY",
            p,
        )
    )

    assert support == 2
    assert against == 1
    assert summary["available_count"] == 5
    assert len(evidence) == 6

    print(
        "PASS: each top-level family contributes "
        "at most one directional vote"
    )


def test_safety_contract_remains_observe_only():
    result = run_build(
        "SELL",
        payload(
            aggression="SELL",
            auction="SELL",
        ),
    )

    assert result["decision_impact"] == "NONE"
    assert (
        result["can_influence_decision"]
        is False
    )
    assert (
        result["safe_for_execution"]
        is False
    )
    assert (
        result["execution_allowed"]
        is False
    )

    print(
        "PASS: V2 setup verdict remains "
        "observe-only with zero execution authority"
    )


def test_legacy_raw_scorer_is_shadow_only():
    source = (
        Path(
            verdict_module.__file__
        )
        .read_text(
            encoding="utf-8-sig"
        )
    )

    build_start = source.index(
        "def build_rithmic_setup_verdict("
    )

    build_end = source.index(
        "\ndef _format_signed",
        build_start,
    )

    build_source = source[
        build_start:build_end
    ]

    # V1 is deliberately retained as a research/shadow
    # benchmark for the setup form.
    assert (
        "score_rithmic_setup_alignment_for_direction("
        in build_source
    )

    # V2 remains the production verdict scorer.
    assert (
        "score_rithmic_evidence_families_for_direction("
        in build_source
    )

    assert (
        '"legacy_v1_mode": "SHADOW_ONLY"'
        in source
    )

    assert (
        '"legacy_v1_can_influence_decision": False'
        in source
    )

    # The V1 shadow calculation must happen before V2 scoring
    # and must not act as a fallback if V2 is unavailable.
    v1_pos = build_source.index(
        "score_rithmic_setup_alignment_for_direction("
    )

    v2_loader_pos = build_source.index(
        "_load_phase5g_evidence_families_v2("
    )

    v2_score_pos = build_source.index(
        "score_rithmic_evidence_families_for_direction("
    )

    assert (
        v1_pos
        < v2_loader_pos
        < v2_score_pos
    )

    print(
        "PASS: legacy V1 raw scorer is retained "
        "only as shadow diagnostics while V2 "
        "remains the production verdict scorer"
    )


def main():
    test_two_independent_supporting_families()
    test_two_independent_opposing_families()
    test_one_vs_one_is_mixed()
    test_low_coverage_cannot_be_decisive()
    test_bad_family_feed_gate_is_unavailable()
    test_missing_v2_never_falls_back_to_raw_score()
    test_family_scoring_one_vote_max_per_family()
    test_safety_contract_remains_observe_only()
    test_legacy_raw_scorer_is_shadow_only()

    print("")
    print(
        "[PASS] Rithmic setup verdict Evidence "
        "Families V2 migration verified."
    )


if __name__ == "__main__":
    main()
