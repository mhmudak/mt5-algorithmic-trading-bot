from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.order_flow_features.rithmic_trade_plan_advisory import (  # noqa: E402
    build_rithmic_trade_plan_advisory,
)


BOT_BUY = {
    "entry_price": 4300.0,
    "stop_loss": 4290.0,
    "take_profit": 4320.0,
    "tp_ladder": [
        {
            "price": 4310.0,
            "rr": 1.0,
        },
        {
            "price": 4320.0,
            "rr": 2.0,
        },
    ],
}


READY_BASIS = {
    "sample_count": 45,
    "valid_pair_count": 44,
    "valid_pair_rate": 44 / 45,
    "avg_basis": 11.1025,
    "basis_std": 0.208742,
    "max_abs_basis_jump": 0.45,
    "basis_ready_observe_only": True,
    "decision_grade_ready": False,
    "automation_allowed": False,
    "decision_impact": "NONE",
    "can_influence_decision": False,
}


def verdict(
    *,
    alignment,
    coverage="5/6",
    support=2,
    against=0,
    feed="HEALTHY",
    regime="BUY_FLOW_EFFECTIVE",
):
    return {
        "alignment": alignment,
        "support_score": support,
        "against_score": against,
        "evidence_family_coverage": coverage,
        "evidence_order_flow_regime": regime,
        "evidence_feed_status": feed,

        # Legacy values are intentionally irrelevant to V1 advisory.
        "legacy_v1_support_score": 99,
        "legacy_v1_against_score": 0,
        "legacy_v1_mode": "SHADOW_ONLY",
    }


def assert_safety(
    result,
):
    assert (
        result["decision_impact"]
        == "NONE"
    )

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

    assert (
        result["trade_action"]
        == "NO_AUTO_TRADE"
    )

    assert (
        result["can_modify_entry"]
        is False
    )

    assert (
        result["can_modify_sl"]
        is False
    )

    assert (
        result["can_modify_tp"]
        is False
    )

    assert (
        result["can_modify_size"]
        is False
    )


def test_supporting_v2():
    original = deepcopy(
        BOT_BUY
    )

    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=verdict(
                alignment="SUPPORTS_SETUP",
                support=3,
                against=0,
            ),
            basis_summary=READY_BASIS,
        )
    )

    assert result["status"] == (
        "QUALITATIVE_ONLY"
    )

    assert result["rithmic_plan"][
        "posture"
    ] == "SETUP_SUPPORTED"

    assert (
        "BETTER_ENTRY"
        in result["rithmic_plan"][
            "entry_context"
        ]
    )

    assert (
        "EXTENSION_PRESSURE_SUPPORTED"
        in result["rithmic_plan"][
            "tp_context"
        ]
    )

    assert (
        result["rithmic_plan"][
            "numeric_plan_available"
        ]
        is False
    )

    assert (
        result["rithmic_plan"][
            "suggested_entry"
        ]
        is None
    )

    assert BOT_BUY == original

    assert_safety(result)

    print(
        "PASS: supporting V2 evidence creates "
        "qualitative shadow guidance only"
    )


def test_opposing_v2():
    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=verdict(
                alignment="AGAINST_SETUP",
                support=1,
                against=3,
                regime=(
                    "SELL_FLOW_EFFECTIVE"
                ),
            ),
            basis_summary=READY_BASIS,
        )
    )

    assert result["status"] == (
        "QUALITATIVE_ONLY"
    )

    assert result["rithmic_plan"][
        "posture"
    ] == "SETUP_OPPOSED"

    assert (
        "AVOID_CHASING"
        in result["rithmic_plan"][
            "entry_context"
        ]
    )

    assert (
        result["rithmic_plan"][
            "sl_context"
        ]
        == "ELEVATED_STOP_RISK_CONTEXT"
    )

    assert (
        result["rithmic_plan"][
            "tp_context"
        ]
        == "CLOSER_TARGET_PRESSURE_CONTEXT"
    )

    assert_safety(result)

    print(
        "PASS: opposing V2 evidence creates "
        "defensive qualitative context only"
    )


def test_mixed_v2():
    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=verdict(
                alignment="NEUTRAL_MIXED",
                support=2,
                against=2,
                regime=(
                    "MIXED_OR_INSUFFICIENT"
                ),
            ),
            basis_summary=READY_BASIS,
        )
    )

    plan = result["rithmic_plan"]

    assert (
        plan["posture"]
        == "MIXED_OR_NEUTRAL"
    )

    assert (
        plan["entry_context"]
        == "KEEP_ORIGINAL"
    )

    assert (
        plan["sl_context"]
        == "KEEP_ORIGINAL"
    )

    assert (
        plan["tp_context"]
        == "KEEP_ORIGINAL"
    )

    print(
        "PASS: mixed V2 evidence preserves "
        "the original plan"
    )


def test_low_coverage():
    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=verdict(
                alignment="SUPPORTS_SETUP",
                coverage="3/6",
                support=3,
            ),
            basis_summary=READY_BASIS,
        )
    )

    assert result["status"] == (
        "QUALITATIVE_ONLY"
    )

    assert result["reason"] == (
        "insufficient_independent_family_coverage"
    )

    assert result["rithmic_plan"][
        "posture"
    ] == "INSUFFICIENT_COVERAGE"

    assert (
        "NO_DIRECTIONAL_ADVISORY"
        in result["rithmic_plan"][
            "entry_context"
        ]
    )

    print(
        "PASS: less than 4/6 coverage cannot "
        "create directional trade-plan guidance"
    )


def test_bad_feed():
    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=verdict(
                alignment="SUPPORTS_SETUP",
                feed="UNUSABLE",
            ),
            basis_summary=READY_BASIS,
        )
    )

    assert result["status"] == (
        "UNAVAILABLE"
    )

    assert result["reason"] == (
        "rithmic_feed_not_usable"
    )

    assert result["rithmic_plan"][
        "posture"
    ] == "UNAVAILABLE"

    assert_safety(result)

    print(
        "PASS: unusable feed blocks the "
        "Rithmic trade-plan advisory"
    )


def test_unavailable_verdict():
    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=verdict(
                alignment=(
                    "NOT_AVAILABLE_STALE_RITHMIC_SOURCE"
                ),
            ),
            basis_summary=READY_BASIS,
        )
    )

    assert result["status"] == (
        "UNAVAILABLE"
    )

    assert result["reason"] == (
        "rithmic_verdict_unavailable"
    )

    print(
        "PASS: stale/unavailable V2 verdict "
        "fails closed"
    )


def test_bot_plan_geometry():
    bad = {
        "entry_price": 4300.0,
        "stop_loss": 4310.0,
        "take_profit": 4320.0,
    }

    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=bad,
            rithmic_verdict=verdict(
                alignment="SUPPORTS_SETUP",
            ),
            basis_summary=READY_BASIS,
        )
    )

    assert result["status"] == (
        "UNAVAILABLE"
    )

    assert result["reason"] == (
        "bot_trade_plan_invalid_geometry"
    )

    print(
        "PASS: malformed authoritative bot "
        "plan cannot create an advisory"
    )


def test_basis_ready_still_no_numeric_prices():
    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=verdict(
                alignment="SUPPORTS_SETUP",
            ),
            basis_summary=READY_BASIS,
        )
    )

    assert result["basis"][
        "basis_ready_observe_only"
    ] is True

    assert result["basis"][
        "statistically_ready"
    ] is True

    assert result["basis"][
        "numeric_translation_allowed"
    ] is False

    assert (
        "freshness_and_price_anchor_contract"
        in result["basis"]["reason"]
    )

    assert result["rithmic_plan"][
        "suggested_entry"
    ] is None

    assert result["rithmic_plan"][
        "suggested_sl"
    ] is None

    assert result["rithmic_plan"][
        "suggested_tp"
    ] is None

    print(
        "PASS: statistically ready basis does "
        "not bypass the missing live freshness/"
        "price-anchor contract"
    )


def test_v1_cannot_override_v2():
    payload = verdict(
        alignment="AGAINST_SETUP",
        support=1,
        against=2,
    )

    payload[
        "legacy_v1_support_score"
    ] = 999

    payload[
        "legacy_v1_against_score"
    ] = 0

    result = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_BUY,
            rithmic_verdict=payload,
            basis_summary=READY_BASIS,
        )
    )

    assert result["rithmic_plan"][
        "posture"
    ] == "SETUP_OPPOSED"

    print(
        "PASS: legacy V1 shadow evidence cannot "
        "override the V2 advisory posture"
    )


def test_no_execution_coupling():
    source_path = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_trade_plan_advisory.py"
    )

    source = source_path.read_text(
        encoding="utf-8-sig",
    )

    forbidden = (
        "MetaTrader5",
        "mt5.order_send",
        "order_send(",
        "execute_trade(",
        "place_order(",
        "modify_position(",
        "position_modify(",
    )

    for token in forbidden:
        assert token not in source, token

    print(
        "PASS: Phase-1 advisory module has "
        "zero MT5 execution coupling"
    )


def main():
    test_supporting_v2()
    test_opposing_v2()
    test_mixed_v2()
    test_low_coverage()
    test_bad_feed()
    test_unavailable_verdict()
    test_bot_plan_geometry()
    test_basis_ready_still_no_numeric_prices()
    test_v1_cannot_override_v2()
    test_no_execution_coupling()

    print("")
    print(
        "[PASS] Rithmic Trade-Plan Advisory V1 "
        "Phase-1 contract verified."
    )


if __name__ == "__main__":
    main()
