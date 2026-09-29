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


from src.order_flow_features.rithmic_numeric_shadow_translation import (  # noqa: E402
    build_numeric_shadow_translation_context,
    evaluate_basis_for_numeric_shadow,
    evaluate_phase5c_state_for_numeric_shadow,
    extract_gc_structural_anchors,
    translate_gc_anchors_to_xauusd,
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
        "max_abs_basis_jump": 0.5,
        "basis_ready_observe_only": True,
        "decision_grade_ready": False,
        "automation_allowed": False,
    },
    "decision_impact": "NONE",
    "can_influence_decision": False,
    "safe_for_execution": False,
    "trade_action": "NO_AUTO_TRADE",
}


STATE = {
    "symbol": "GCZ6",
    "exchange": "COMEX",
    "state_status": "OBSERVE_ONLY_READY",
    "updated_at_epoch": NOW - 2.0,

    "freshness": {
        "stale_after_seconds": 15,
        "last_trade_age_seconds": 0.5,
        "last_bbo_age_seconds": 0.3,
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
        "high_trade_price": 4216.0,
        "low_trade_price": 4209.8,
    },

    "volume_profile": {
        "rolling_poc_price": 4213.0,
        "top_volume_at_price": [
            {
                "price": 4213.0,
                "buy_volume": 20,
                "sell_volume": 15,
                "total_volume": 35,
                "delta": 5,
                "trade_count": 12,
            },
            {
                "price": 4215.0,
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
                "size": 8,
                "orders": 3,
                "implicit_size": 0,
            },
            {
                "level": 2,
                "price": 4213.2,
                "size": 15,
                "orders": 5,
                "implicit_size": 0,
            },
        ],
        "ask_levels": [
            {
                "level": 1,
                "price": 4213.9,
                "size": 7,
                "orders": 2,
                "implicit_size": 0,
            },
            {
                "level": 2,
                "price": 4214.4,
                "size": 18,
                "orders": 6,
                "implicit_size": 0,
            },
        ],
    },
}


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


def test_basis_formula():
    gate = (
        evaluate_basis_for_numeric_shadow(
            basis_payload=BASIS,
            basis_file_mtime_epoch=(
                NOW - 30
            ),
            now_epoch=NOW,
            expected_rithmic_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is True
    )

    translated = (
        translate_gc_anchors_to_xauusd(
            anchors=[
                {
                    "anchor_id": "TEST",
                    "family": "TEST",
                    "side": "NEUTRAL",
                    "gc_price": 4213.7,
                    "metadata": {},
                }
            ],
            basis_evaluation=gate,
        )
    )

    price = (
        translated["candidates"][0]
        ["xauusd_price"]
    )

    assert price == 4224.8

    print(
        "PASS: XAUUSD = GC + basis "
        "translation is exact"
    )


def test_negative_basis():
    payload = deepcopy(
        BASIS
    )

    payload[
        "summary"
    ][
        "avg_basis"
    ] = -4.25

    gate = (
        evaluate_basis_for_numeric_shadow(
            basis_payload=payload,
            basis_file_mtime_epoch=(
                NOW - 10
            ),
            now_epoch=NOW,
            expected_rithmic_symbol="GCZ6",
        )
    )

    translated = (
        translate_gc_anchors_to_xauusd(
            anchors=[
                {
                    "anchor_id": "TEST",
                    "family": "TEST",
                    "side": "NEUTRAL",
                    "gc_price": 4213.7,
                    "metadata": {},
                }
            ],
            basis_evaluation=gate,
        )
    )

    assert (
        translated["candidates"][0]
        ["xauusd_price"]
        == 4209.45
    )

    print(
        "PASS: negative basis is handled "
        "without sign inversion"
    )


def test_stale_basis_blocks():
    gate = (
        evaluate_basis_for_numeric_shadow(
            basis_payload=BASIS,
            basis_file_mtime_epoch=(
                NOW - 301
            ),
            now_epoch=NOW,
            max_basis_age_seconds=300,
            expected_rithmic_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is False
    )

    assert (
        gate["reason"]
        == "basis_stale"
    )

    assert_zero_authority(gate)

    print(
        "PASS: stale basis blocks numeric shadow"
    )


def test_bad_basis_statistics_block():
    payload = deepcopy(
        BASIS
    )

    payload[
        "summary"
    ][
        "valid_pair_count"
    ] = 12

    gate = (
        evaluate_basis_for_numeric_shadow(
            basis_payload=payload,
            basis_file_mtime_epoch=(
                NOW - 10
            ),
            now_epoch=NOW,
            expected_rithmic_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is False
    )

    assert (
        gate["reason"]
        == "basis_statistical_quality_not_ready"
    )

    print(
        "PASS: weak basis statistics block translation"
    )


def test_fresh_phase5c_state():
    gate = (
        evaluate_phase5c_state_for_numeric_shadow(
            state=STATE,
            now_epoch=NOW,
            expected_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is True
    )

    assert (
        gate["spread"]
        == 0.3
    )

    assert_zero_authority(gate)

    print(
        "PASS: fresh two-sided Phase5C state passes"
    )


def test_stale_phase5c_state_blocks():
    state = deepcopy(
        STATE
    )

    state[
        "updated_at_epoch"
    ] = NOW - 30

    gate = (
        evaluate_phase5c_state_for_numeric_shadow(
            state=state,
            now_epoch=NOW,
            expected_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is False
    )

    assert (
        gate["reason"]
        == "phase5c_snapshot_stale"
    )

    print(
        "PASS: stale Phase5C snapshot blocks"
    )


def test_component_freshness_blocks():
    state = deepcopy(
        STATE
    )

    state[
        "freshness"
    ][
        "has_fresh_order_book"
    ] = False

    gate = (
        evaluate_phase5c_state_for_numeric_shadow(
            state=state,
            now_epoch=NOW,
            expected_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is False
    )

    assert (
        gate["reason"]
        == "phase5c_component_not_fresh"
    )

    print(
        "PASS: stale component blocks numeric shadow"
    )


def test_wide_spread_blocks():
    state = deepcopy(
        STATE
    )

    state["bbo"] = {
        "last_bid": 4211.0,
        "last_ask": 4215.6,
    }

    gate = (
        evaluate_phase5c_state_for_numeric_shadow(
            state=state,
            now_epoch=NOW,
            max_gc_spread=1.0,
            expected_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is False
    )

    assert (
        gate["reason"]
        == "phase5c_spread_too_wide"
    )

    print(
        "PASS: closed/thin wide-spread state blocks"
    )


def test_one_sided_book_blocks():
    state = deepcopy(
        STATE
    )

    state[
        "order_book"
    ][
        "ask_levels"
    ] = []

    gate = (
        evaluate_phase5c_state_for_numeric_shadow(
            state=state,
            now_epoch=NOW,
            expected_symbol="GCZ6",
        )
    )

    assert (
        gate["usable_for_numeric_shadow"]
        is False
    )

    assert (
        gate["reason"]
        == "phase5c_two_sided_depth_missing"
    )

    print(
        "PASS: one-sided depth blocks numeric shadow"
    )


def test_structural_anchor_extraction():
    anchors = (
        extract_gc_structural_anchors(
            STATE
        )
    )

    ids = {
        row["anchor_id"]
        for row in anchors
    }

    required = {
        "CURRENT_MID",
        "LATEST_TRADE",
        "ROLLING_POC",
        "ROLLING_HIGH",
        "ROLLING_LOW",
        "TOP_VAP_1",
        "BID_DEPTH_1",
        "ASK_DEPTH_1",
    }

    assert required.issubset(
        ids
    )

    print(
        "PASS: real Phase5C structure becomes "
        "candidate anchors without plan selection"
    )


def test_full_context_ready_but_no_plan():
    result = (
        build_numeric_shadow_translation_context(
            state=STATE,
            basis_payload=BASIS,
            basis_file_mtime_epoch=(
                NOW - 20
            ),
            now_epoch=NOW,
            expected_symbol="GCZ6",
        )
    )

    assert (
        result["status"]
        == "SHADOW_CANDIDATES_READY"
    )

    assert (
        result["translation"]
        ["candidate_count"]
        > 0
    )

    assert (
        result["selection_status"]
        == "NOT_IMPLEMENTED_PHASE3A"
    )

    assert (
        result["suggested_entry"]
        is None
    )

    assert (
        result["suggested_sl"]
        is None
    )

    assert (
        result["suggested_tp"]
        is None
    )

    assert_zero_authority(result)

    print(
        "PASS: Phase3A can translate structure "
        "but cannot choose Entry/SL/TP"
    )


def test_symbol_mismatch_blocks():
    payload = deepcopy(
        BASIS
    )

    payload[
        "rithmic_symbol"
    ] = "GCV6"

    result = (
        build_numeric_shadow_translation_context(
            state=STATE,
            basis_payload=payload,
            basis_file_mtime_epoch=(
                NOW - 20
            ),
            now_epoch=NOW,
            expected_symbol="GCZ6",
        )
    )

    assert (
        result["status"]
        == "BLOCKED"
    )

    assert (
        result["basis_gate"]
        ["reason"]
        == "basis_rithmic_symbol_mismatch"
    )

    print(
        "PASS: contract-roll symbol mismatch blocks"
    )


def test_no_execution_coupling():
    source = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_numeric_shadow_translation.py"
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
        "PASS: numeric translation layer has "
        "zero execution coupling"
    )


def main():
    test_basis_formula()
    test_negative_basis()
    test_stale_basis_blocks()
    test_bad_basis_statistics_block()
    test_fresh_phase5c_state()
    test_stale_phase5c_state_blocks()
    test_component_freshness_blocks()
    test_wide_spread_blocks()
    test_one_sided_book_blocks()
    test_structural_anchor_extraction()
    test_full_context_ready_but_no_plan()
    test_symbol_mismatch_blocks()
    test_no_execution_coupling()

    print("")
    print(
        "[PASS] Phase 3A numeric-shadow "
        "translation foundation verified."
    )


if __name__ == "__main__":
    main()
