from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import json
import os
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.order_flow_features.rithmic_numeric_shadow_runtime import (  # noqa: E402
    build_rithmic_numeric_shadow_runtime_context,
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


VERDICT = {
    "verdict": "SUPPORTS_SETUP",
    "alignment": "SUPPORTS_SETUP",
    "setup_direction": "BUY",
    "supports_setup": True,
    "against_setup": False,
}


def write_inputs(
    root: Path,
    *,
    basis_age_seconds: float = 20.0,
):
    state_path = (
        root
        / "GCZ6_phase5c_rithmic_state_latest.json"
    )

    basis_path = (
        root
        / "phase5ac_xauusd_rithmic_basis_calibration.json"
    )

    state_path.write_text(
        json.dumps(
            STATE,
            indent=2,
        ),
        encoding="utf-8",
    )

    basis_path.write_text(
        json.dumps(
            BASIS,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.utime(
        basis_path,
        (
            NOW - basis_age_seconds,
            NOW - basis_age_seconds,
        ),
    )

    return (
        state_path,
        basis_path,
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


def test_disabled_short_circuit():
    missing_state = (
        ROOT
        / "__definitely_missing_state__.json"
    )

    missing_basis = (
        ROOT
        / "__definitely_missing_basis__.json"
    )

    result = (
        build_rithmic_numeric_shadow_runtime_context(
            enabled=False,
            signal="BUY",
            rithmic_verdict=VERDICT,
            state_path=missing_state,
            basis_path=missing_basis,
            now_epoch=NOW,
        )
    )

    assert (
        result["status"]
        == "DISABLED"
    )

    assert (
        result["state_path"]
        is None
    )

    assert (
        result["basis_path"]
        is None
    )

    assert (
        result["numeric_shadow_plan"]
        is None
    )

    assert_zero_authority(
        result
    )

    print(
        "PASS: disabled runtime performs "
        "zero numeric file inspection"
    )


def test_supportive_runtime_ready():
    with tempfile.TemporaryDirectory() as tmp:
        state_path, basis_path = (
            write_inputs(
                Path(tmp)
            )
        )

        result = (
            build_rithmic_numeric_shadow_runtime_context(
                enabled=True,
                signal="BUY",
                rithmic_verdict=VERDICT,
                rithmic_symbol="GCZ6",
                exchange="COMEX",
                state_path=state_path,
                basis_path=basis_path,
                now_epoch=NOW,
            )
        )

    assert (
        result["status"]
        == "NUMERIC_SHADOW_READY"
    )

    plan = result[
        "numeric_shadow_plan"
    ]

    assert (
        plan["status"]
        == "NUMERIC_SHADOW_PLAN"
    )

    assert (
        plan[
            "suggested_entry"
        ]
        == 4224.5
    )

    assert (
        plan[
            "suggested_sl"
        ]
        == 4220.9
    )

    assert (
        plan[
            "suggested_tp_ladder"
        ][0]["price"]
        == 4225.5
    )

    assert (
        plan[
            "suggested_tp_ladder"
        ][1]["price"]
        == 4227.1
    )

    assert_zero_authority(
        result
    )

    print(
        "PASS: enabled runtime builds "
        "validated structural shadow plan"
    )


def test_stale_basis_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        state_path, basis_path = (
            write_inputs(
                Path(tmp),
                basis_age_seconds=600.0,
            )
        )

        result = (
            build_rithmic_numeric_shadow_runtime_context(
                enabled=True,
                signal="BUY",
                rithmic_verdict=VERDICT,
                state_path=state_path,
                basis_path=basis_path,
                now_epoch=NOW,
                max_basis_age_seconds=300.0,
            )
        )

    assert (
        result["status"]
        == "BLOCKED"
    )

    assert (
        "basis_stale"
        in result["reason"]
    )

    assert (
        result[
            "numeric_shadow_plan"
        ]
        is None
    )

    print(
        "PASS: stale basis blocks "
        "runtime numeric shadow"
    )


def test_state_block_reason_is_not_masked_by_ready_basis():
    verdict = deepcopy(
        VERDICT
    )

    with tempfile.TemporaryDirectory() as tmp:
        state_path, basis_path = (
            write_inputs(
                Path(tmp)
            )
        )

        blocked_state = deepcopy(
            STATE
        )

        blocked_state[
            "state_status"
        ] = "STARTING"

        state_path.write_text(
            json.dumps(
                blocked_state,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = (
            build_rithmic_numeric_shadow_runtime_context(
                enabled=True,
                signal="BUY",
                rithmic_verdict=verdict,
                rithmic_symbol="GCZ6",
                exchange="COMEX",
                state_path=state_path,
                basis_path=basis_path,
                now_epoch=NOW,
            )
        )

    assert (
        result["status"]
        == "BLOCKED"
    )

    translation = (
        result[
            "translation_context"
        ]
    )

    assert (
        translation[
            "basis_gate"
        ][
            "usable_for_numeric_shadow"
        ]
        is True
    )

    assert (
        translation[
            "state_gate"
        ][
            "usable_for_numeric_shadow"
        ]
        is False
    )

    assert (
        translation[
            "state_gate"
        ][
            "reason"
        ]
        == "phase5c_state_not_ready"
    )

    assert (
        result["reason"]
        == (
            "translation_blocked:"
            "phase5c_state_not_ready"
        )
    )

    assert (
        "basis_ready_for_shadow_translation"
        not in result[
            "reason"
        ]
    )

    assert_zero_authority(
        result
    )

    print(
        "PASS: blocked state reason is not "
        "masked by ready basis reason"
    )


def test_mixed_verdict_blocks_plan():
    verdict = deepcopy(
        VERDICT
    )

    verdict["verdict"] = "NEUTRAL"
    verdict["alignment"] = "NEUTRAL"
    verdict["supports_setup"] = False

    with tempfile.TemporaryDirectory() as tmp:
        state_path, basis_path = (
            write_inputs(
                Path(tmp)
            )
        )

        result = (
            build_rithmic_numeric_shadow_runtime_context(
                enabled=True,
                signal="BUY",
                rithmic_verdict=verdict,
                state_path=state_path,
                basis_path=basis_path,
                now_epoch=NOW,
            )
        )

    assert (
        result["status"]
        == "BLOCKED"
    )

    assert (
        result["reason"]
        == (
            "plan_blocked:"
            "rithmic_alignment_not_supportive"
        )
    )

    print(
        "PASS: mixed verdict cannot "
        "produce runtime numeric plan"
    )


def test_settings_hard_off():
    source = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8-sig",
    )

    tree = ast.parse(
        source
    )

    values = {}

    for node in tree.body:
        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]

        if not isinstance(
            target,
            ast.Name,
        ):
            continue

        if (
            target.id.startswith(
                "RITHMIC_NUMERIC_SHADOW_"
            )
            or target.id
            == "ENABLE_RITHMIC_NUMERIC_SHADOW_ADVISORY"
        ):
            try:
                values[
                    target.id
                ] = ast.literal_eval(
                    node.value
                )
            except Exception:
                pass

    assert (
        values[
            "ENABLE_RITHMIC_NUMERIC_SHADOW_ADVISORY"
        ]
        is False
    )

    assert (
        values[
            "RITHMIC_NUMERIC_SHADOW_SYMBOL"
        ]
        == "GCZ6"
    )

    assert (
        values[
            "RITHMIC_NUMERIC_SHADOW_EXCHANGE"
        ]
        == "COMEX"
    )

    print(
        "PASS: runtime feature flag "
        "is hard OFF by default"
    )


def test_live_bot_wiring_is_display_only():
    source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig",
    )

    assert (
        "build_rithmic_numeric_shadow_runtime_context"
        in source
    )

    assert (
        "numeric_shadow_enabled=("
        in source
    )

    assert (
        "numeric_shadow_plan=("
        in source
    )

    assert (
        'verdict[\n'
        '                    "numeric_shadow_runtime"\n'
        "                ] = numeric_shadow_runtime"
        in source
    )

    forbidden = (
        "detected_trade_plan = numeric_shadow",
        "trade_plan = numeric_shadow",
        '["entry"] = numeric_shadow',
        '["sl"] = numeric_shadow',
        '["tp"] = numeric_shadow',
        "execute_trade(numeric_shadow",
    )

    for token in forbidden:
        assert token not in source, token

    print(
        "PASS: live_bot wiring remains "
        "display/observation only"
    )


def test_runtime_adapter_zero_execution_coupling():
    source = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_numeric_shadow_runtime.py"
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
        "PASS: runtime adapter has "
        "zero execution coupling"
    )


def main():
    test_disabled_short_circuit()
    test_supportive_runtime_ready()
    test_stale_basis_blocks()
    test_state_block_reason_is_not_masked_by_ready_basis()
    test_mixed_verdict_blocks_plan()
    test_settings_hard_off()
    test_live_bot_wiring_is_display_only()
    test_runtime_adapter_zero_execution_coupling()

    print("")
    print(
        "[PASS] Phase 3D runtime wiring "
        "contract verified."
    )


if __name__ == "__main__":
    main()
