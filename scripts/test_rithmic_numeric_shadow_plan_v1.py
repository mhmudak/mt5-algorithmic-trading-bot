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


from src.order_flow_features.rithmic_numeric_shadow_plan import (  # noqa: E402
    build_rithmic_numeric_shadow_plan,
)
from src.order_flow_features.rithmic_numeric_shadow_translation import (  # noqa: E402
    build_numeric_shadow_translation_context,
)


NOW = 2_000_000_000.0


BASIS = {
    "phase": (
        "PHASE_5AC_XAUUSD_RITHMIC_BASIS_CALIBRATION"
    ),
    "mt5_symbol": "XAUUSD",
    "rithmic_symbol": "GCZ6",
    "updated_at": "2033-05-18T03:33:20",
    "summary": {
        "sample_count": 60,
        "valid_pair_count": 58,
        "valid_pair_rate": 0.9667,
        "avg_basis": 11.1,
        "basis_std": 0.25,
        "basis_ready_observe_only": True,
        "decision_grade_ready": False,
        "automation_allowed": False,
    },
    "decision_impact": "NONE",
    "can_influence_decision": False,
    "safe_for_execution": False,
    "trade_action": "NO_AUTO_TRADE",
}


def base_state():
    return {
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "state_status": "OBSERVE_ONLY_READY",
        "updated_at_epoch": NOW - 1.0,

        "freshness": {
            "stale_after_seconds": 15,
            "last_trade_age_seconds": 0.3,
            "last_bbo_age_seconds": 0.2,
            "last_order_book_age_seconds": 0.4,
            "has_fresh_trade": True,
            "has_fresh_bbo": True,
            "has_fresh_order_book": True,
        },

        "latest_trade": {
            "price": 4213.7,
        },

        "bbo": {
            "last_bid": 4213.6,
            "last_ask": 4213.9,
        },

        "trade_flow": {
            "high_trade_price": 4218.0,
            "low_trade_price": 4209.8,
        },

        "volume_profile": {
            "rolling_poc_price": 4213.0,
            "top_volume_at_price": [
                {
                    "price": 4213.4,
                    "buy_volume": 20,
                    "sell_volume": 15,
                    "total_volume": 35,
                    "delta": 5,
                    "trade_count": 12,
                },
                {
                    "price": 4212.8,
                    "buy_volume": 11,
                    "sell_volume": 8,
                    "total_volume": 19,
                    "delta": 3,
                    "trade_count": 7,
                },
            ],
        },

        "order_book": {
            "available": True,

            "bid_levels": [
                {
                    "level": 1,
                    "price": 4213.6,
                    "size": 2,
                    "orders": 1,
                    "implicit_size": 0,
                },
                {
                    "level": 2,
                    "price": 4212.5,
                    "size": 20,
                    "orders": 5,
                    "implicit_size": 0,
                },
                {
                    "level": 3,
                    "price": 4209.0,
                    "size": 30,
                    "orders": 7,
                    "implicit_size": 0,
                },
            ],

            "ask_levels": [
                {
                    "level": 1,
                    "price": 4213.9,
                    "size": 1,
                    "orders": 1,
                    "implicit_size": 0,
                },
                {
                    "level": 2,
                    "price": 4214.4,
                    "size": 18,
                    "orders": 6,
                    "implicit_size": 0,
                },
                {
                    "level": 3,
                    "price": 4216.0,
                    "size": 25,
                    "orders": 8,
                    "implicit_size": 0,
                },
            ],
        },
    }


def build_context(
    state,
):
    return (
        build_numeric_shadow_translation_context(
            state=state,
            basis_payload=BASIS,
            basis_file_mtime_epoch=NOW - 20,
            now_epoch=NOW,
            expected_symbol="GCZ6",
        )
    )


def assert_zero_authority(
    value,
):
    assert (
        value["decision_impact"]
        == "NONE"
    )

    assert (
        value["can_influence_decision"]
        is False
    )

    assert (
        value["safe_for_execution"]
        is False
    )

    assert (
        value["execution_allowed"]
        is False
    )

    assert (
        value["trade_action"]
        == "NO_AUTO_TRADE"
    )

    assert (
        value["can_modify_entry"]
        is False
    )

    assert (
        value["can_modify_sl"]
        is False
    )

    assert (
        value["can_modify_tp"]
        is False
    )

    assert (
        value["can_modify_size"]
        is False
    )


def test_buy_plan():
    state = base_state()

    context = build_context(
        state
    )

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=context,
        )
    )

    assert (
        result["status"]
        == "NUMERIC_SHADOW_PLAN"
    )

    assert (
        result["numeric_plan_available"]
        is True
    )

    # Entry = nearest favorable profile level:
    # GC 4213.4 + basis 11.1
    assert (
        result["suggested_entry"]
        == 4224.5
    )

    # SL = executed rolling low:
    # GC 4209.8 + basis 11.1
    assert (
        result["suggested_sl"]
        == 4220.9
    )

    # Strongest ASK walls:
    # size 18 @ 4214.4
    # size 25 @ 4216.0
    assert (
        result["suggested_tp_ladder"][0]
        ["price"]
        == 4225.5
    )

    assert (
        result["suggested_tp_ladder"][1]
        ["price"]
        == 4227.1
    )

    assert (
        result["entry_anchor"]
        ["anchor_id"]
        == "TOP_VAP_1"
    )

    assert (
        result["sl_anchor"]
        ["anchor_id"]
        == "ROLLING_LOW"
    )

    assert_zero_authority(
        result
    )

    print(
        "PASS: BUY shadow plan comes only "
        "from translated real structure"
    )


def test_sell_plan():
    state = base_state()

    state[
        "volume_profile"
    ][
        "rolling_poc_price"
    ] = 4214.2

    state[
        "volume_profile"
    ][
        "top_volume_at_price"
    ] = [
        {
            "price": 4214.0,
            "buy_volume": 8,
            "sell_volume": 14,
            "total_volume": 22,
            "delta": -6,
            "trade_count": 9,
        }
    ]

    context = build_context(
        state
    )

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="SELL",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=context,
        )
    )

    assert (
        result["status"]
        == "NUMERIC_SHADOW_PLAN"
    )

    # Nearest favorable profile above current:
    # TOP_VAP_1 4214.0 + 11.1
    assert (
        result["suggested_entry"]
        == 4225.1
    )

    # Rolling high 4218 + 11.1
    assert (
        result["suggested_sl"]
        == 4229.1
    )

    # Two strongest bid walls:
    # 4212.5 size 20
    # 4209.0 size 30
    # SELL ladder nearest first.
    assert (
        result["suggested_tp_ladder"][0]
        ["price"]
        == 4223.6
    )

    assert (
        result["suggested_tp_ladder"][1]
        ["price"]
        == 4220.1
    )

    assert (
        result["entry_anchor"]
        ["anchor_id"]
        == "TOP_VAP_1"
    )

    assert (
        result["sl_anchor"]
        ["anchor_id"]
        == "ROLLING_HIGH"
    )

    assert_zero_authority(
        result
    )

    print(
        "PASS: SELL shadow plan geometry "
        "is structurally valid"
    )


def test_strongest_wall_not_nearest():
    state = base_state()

    context = build_context(
        state
    )

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=context,
        )
    )

    ids = [
        row["anchor_id"]
        for row in result[
            "suggested_tp_ladder"
        ]
    ]

    assert (
        "ASK_DEPTH_1"
        not in ids
    )

    assert set(ids) == {
        "ASK_DEPTH_2",
        "ASK_DEPTH_3",
    }

    print(
        "PASS: weak nearest touch is not "
        "mistaken for a liquidity wall"
    )


def test_mixed_alignment_blocks():
    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment="NEUTRAL",
            translation_context=(
                build_context(
                    base_state()
                )
            ),
        )
    )

    assert (
        result["numeric_plan_available"]
        is False
    )

    assert (
        result["reason"]
        == "rithmic_alignment_not_supportive"
    )

    assert (
        result["suggested_entry"]
        is None
    )

    print(
        "PASS: mixed Rithmic verdict "
        "cannot create numeric plan"
    )


def test_against_alignment_blocks():
    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "AGAINST_SETUP"
            ),
            translation_context=(
                build_context(
                    base_state()
                )
            ),
        )
    )

    assert (
        result["numeric_plan_available"]
        is False
    )

    assert (
        result["reason"]
        == "rithmic_alignment_not_supportive"
    )

    print(
        "PASS: opposing verdict remains "
        "qualitative only"
    )


def test_missing_second_wall_blocks():
    state = base_state()

    state[
        "order_book"
    ][
        "ask_levels"
    ] = [
        {
            "level": 1,
            "price": 4214.4,
            "size": 18,
            "orders": 6,
            "implicit_size": 0,
        }
    ]

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=(
                build_context(
                    state
                )
            ),
        )
    )

    assert (
        result["numeric_plan_available"]
        is False
    )

    assert (
        result["reason"]
        == "two_opposing_depth_targets_required"
    )

    print(
        "PASS: incomplete TP structure "
        "withholds entire numeric plan"
    )


def test_invalid_sl_geometry_blocks():
    state = base_state()

    state[
        "trade_flow"
    ][
        "low_trade_price"
    ] = 4213.6

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=(
                build_context(
                    state
                )
            ),
        )
    )

    assert (
        result["numeric_plan_available"]
        is False
    )

    assert (
        result["reason"]
        == "structural_invalidation_missing"
    )

    print(
        "PASS: invalid SL geometry fails closed"
    )


def test_missing_favorable_profile_blocks():
    state = base_state()

    state[
        "volume_profile"
    ][
        "rolling_poc_price"
    ] = 4215.0

    state[
        "volume_profile"
    ][
        "top_volume_at_price"
    ] = [
        {
            "price": 4216.0,
            "buy_volume": 1,
            "sell_volume": 1,
            "total_volume": 2,
            "delta": 0,
            "trade_count": 1,
        }
    ]

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=(
                build_context(
                    state
                )
            ),
        )
    )

    assert (
        result["numeric_plan_available"]
        is False
    )

    assert (
        result["reason"]
        == "favorable_profile_entry_missing"
    )

    print(
        "PASS: no favorable profile "
        "means no fabricated entry"
    )


def test_upstream_authority_tamper_blocks():
    context = build_context(
        base_state()
    )

    context[
        "execution_allowed"
    ] = True

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=context,
        )
    )

    assert (
        result["numeric_plan_available"]
        is False
    )

    assert (
        result["reason"]
        == "upstream_authority_contract_invalid"
    )

    print(
        "PASS: authority-contract tampering "
        "fails closed"
    )


def test_selected_prices_are_existing_candidates():
    context = build_context(
        base_state()
    )

    result = (
        build_rithmic_numeric_shadow_plan(
            signal="BUY",
            rithmic_alignment=(
                "SUPPORTS_SETUP"
            ),
            translation_context=context,
        )
    )

    candidate_prices = {
        row["xauusd_price"]
        for row in (
            context[
                "translation"
            ][
                "candidates"
            ]
        )
    }

    selected = {
        result[
            "suggested_entry"
        ],
        result[
            "suggested_sl"
        ],
        *[
            row["price"]
            for row in result[
                "suggested_tp_ladder"
            ]
        ],
    }

    assert selected.issubset(
        candidate_prices
    )

    print(
        "PASS: every selected level "
        "already existed in translated structure"
    )


def test_no_execution_coupling():
    source = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_numeric_shadow_plan.py"
    ).read_text(
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
        "PASS: structural selector has "
        "zero execution coupling"
    )


def main():
    test_buy_plan()
    test_sell_plan()
    test_strongest_wall_not_nearest()
    test_mixed_alignment_blocks()
    test_against_alignment_blocks()
    test_missing_second_wall_blocks()
    test_invalid_sl_geometry_blocks()
    test_missing_favorable_profile_blocks()
    test_upstream_authority_tamper_blocks()
    test_selected_prices_are_existing_candidates()
    test_no_execution_coupling()

    print("")
    print(
        "[PASS] Phase 3B structural numeric "
        "shadow-plan selector verified."
    )


if __name__ == "__main__":
    main()
