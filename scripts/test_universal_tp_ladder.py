from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.notifier import build_trade_message

from src.order_executor import (
    prepare_main_tp_ladder_execution,
    _format_execution_tp_management,
)

from src.universal_tp_ladder import (
    build_universal_tp_ladder,
    ensure_universal_tp_ladder,
    format_tp_plan_from_levels,
    format_tp_plan_from_trade_plan,
)


SYMBOL_INFO = SimpleNamespace(
    point=0.01,
    volume_min=0.01,
    volume_step=0.01,
    volume_max=100.0,
)


def test_high_rr_orb_example():
    ladder = (
        build_universal_tp_ladder(
            signal="BUY",
            entry=4436.61,
            sl=4425.19,
            tp3=4489.75,
        )
    )

    assert ladder is not None

    assert (
        ladder[0]["price"]
        == 4448.03
    )

    assert (
        ladder[1]["price"]
        == 4459.45
    )

    assert (
        ladder[2]["price"]
        == 4489.75
    )

    assert (
        ladder[0]["rr"]
        == 1.0
    )

    assert (
        ladder[1]["rr"]
        == 2.0
    )

    assert (
        ladder[2]["rr"]
        == 4.65
    )


def test_low_rr_not_rescued():
    plan = {
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit": 104.0,
        "rr": 0.40,
        "risk_reward": 0.40,
        "original_rr": 0.40,
    }

    adjusted = (
        ensure_universal_tp_ladder(
            "BUY",
            plan,
            source="TEST",
        )
    )

    ladder = adjusted[
        "tp_ladder"
    ]

    assert (
        ladder[0]["price"]
        == 102.0
    )

    assert (
        ladder[1]["price"]
        == 103.0
    )

    assert (
        ladder[2]["price"]
        == 104.0
    )

    assert (
        adjusted["rr"]
        == 0.40
    )

    assert (
        adjusted["risk_reward"]
        == 0.40
    )

    assert (
        adjusted["original_rr"]
        == 0.40
    )

    assert (
        adjusted["take_profit"]
        == 104.0
    )


def test_existing_structural_ladder_preserved():
    structural = [
        {
            "name": "TP1_STRUCTURAL",
            "price": 108.0,
            "rr": 0.8,
        },
        {
            "name": "TP2_STRUCTURAL",
            "price": 120.0,
            "rr": 2.0,
        },
        {
            "name": "TP3_STRUCTURAL",
            "price": 130.0,
            "rr": 3.0,
        },
    ]

    plan = {
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit": 108.0,
        "original_take_profit": 130.0,
        "rr": 3.0,
        "risk_reward": 3.0,
        "original_rr": 3.0,
        "tp_ladder": structural,
    }

    adjusted = (
        ensure_universal_tp_ladder(
            "BUY",
            plan,
            source="TEST",
        )
    )

    assert (
        adjusted["tp_ladder"]
        == structural
    )

    assert (
        adjusted.get(
            "universal_tp_ladder_generated"
        )
        is False
    )

    assert (
        adjusted.get(
            "universal_tp_ladder_preserved_existing"
        )
        is True
    )

    # Existing Key-Level execution TP is untouched.
    assert (
        adjusted[
            "take_profit"
        ]
        == 108.0
    )


def test_final_execution_fallback_survives_rebase_guard():
    plan = {
        "entry_price": 4400.0,
        "stop_loss": 4390.0,
        "take_profit": 4430.0,
        "rr": 3.0,
        "risk_reward": 3.0,
        "original_rr": 3.0,
        "lot": 0.25,
        "reason": (
            "MOMENTUM_CONTINUATION_AFTER_PRICE_DRIFT"
        ),
    }

    generated = (
        ensure_universal_tp_ladder(
            "BUY",
            plan,
            source=(
                "ORDER_EXECUTOR_FINAL_GEOMETRY"
            ),
            geometry_phase=(
                "FINAL_EXECUTION"
            ),
        )
    )

    assert (
        generated[
            "tp_ladder_geometry_phase"
        ]
        == "FINAL_EXECUTION"
    )

    result = (
        prepare_main_tp_ladder_execution(
            "BUY",
            generated,
            "XAUUSD",
            same_direction_count=0,
            symbol_info=SYMBOL_INFO,
        )
    )

    assert (
        result[
            "main_tp_ladder_managed"
        ]
        is True
    )

    assert (
        result[
            "decision_take_profit"
        ]
        == 4430.0
    )

    assert (
        result[
            "rr"
        ]
        == 3.0
    )


def test_old_structural_ladder_rebase_still_fails_safe():
    plan = {
        "entry_price": 4400.0,
        "stop_loss": 4390.0,
        "take_profit": 4410.0,
        "original_take_profit": 4430.0,
        "rr": 3.0,
        "risk_reward": 3.0,
        "original_rr": 3.0,
        "lot": 0.25,
        "reason": (
            "MOMENTUM_CONTINUATION_AFTER_PRICE_DRIFT"
        ),
        "tp_ladder": [
            {
                "price": 4410.0,
                "rr": 1.0,
            },
            {
                "price": 4420.0,
                "rr": 2.0,
            },
            {
                "price": 4430.0,
                "rr": 3.0,
            },
        ],
    }

    result = (
        prepare_main_tp_ladder_execution(
            "BUY",
            plan,
            "XAUUSD",
            same_direction_count=0,
            symbol_info=SYMBOL_INFO,
        )
    )

    assert (
        result.get(
            "main_tp_ladder_managed"
        )
        is False
    )

    assert (
        result.get(
            "main_tp_ladder_skip_reason"
        )
        == (
            "execution_entry_rebased_"
            "ladder_not_refrozen"
        )
    )


def test_visual_plan_without_sl():
    text = (
        format_tp_plan_from_levels(
            signal="SELL",
            entry=100.0,
            sl=None,
            tp=90.0,
        )
    )

    assert "TP1: 95.0" in text
    assert "TP2: 92.5" in text
    assert "TP3: 90.0" in text


def test_trade_plan_formatter():
    plan = {
        "entry_price": 100.0,
        "stop_loss": 110.0,
        "take_profit": 80.0,
    }

    text = (
        format_tp_plan_from_trade_plan(
            "SELL",
            plan,
        )
    )

    assert "TP1:" in text
    assert "TP2:" in text
    assert "TP3:" in text


def test_detected_setup_message_has_three_targets():
    message = build_trade_message(
        {
            "stage": (
                "SETUP DETECTED #TEST"
            ),
            "signal": "BUY",
            "strategy": "ORB_V00",
            "entry_model": "RAW",
            "entry": 100.0,
            "sl": 90.0,
            "tp": 130.0,
            "score": 95,
            "rr": 3.0,
            "session": "NY",
            "reason": "synthetic",
        }
    )

    assert "TP1:" in message
    assert "TP2:" in message
    assert "TP3:" in message

    assert (
        "Full RR (TP3): 3.0"
        in message
    )


def test_execution_message_managed_main_claims_ladder():
    plan = {
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit": 130.0,
        "rr": 3.0,
        "risk_reward": 3.0,
        "original_rr": 3.0,
        "lot": 0.25,
        "reason": "TEST",
    }

    generated = (
        ensure_universal_tp_ladder(
            "BUY",
            plan,
            source="TEST",
            geometry_phase="FINAL_EXECUTION",
        )
    )

    managed = (
        prepare_main_tp_ladder_execution(
            "BUY",
            generated,
            "XAUUSD",
            same_direction_count=0,
            symbol_info=SYMBOL_INFO,
        )
    )

    text = (
        _format_execution_tp_management(
            "BUY",
            managed,
        )
    )

    assert (
        managed[
            "main_tp_ladder_managed"
        ]
        is True
    )

    assert "Execution Role: MAIN" in text
    assert "TP1:" in text
    assert "TP2:" in text
    assert "TP3:" in text

    assert (
        "Full RR (TP3): 3.0"
        in text
    )

    assert (
        "Runner After TP3: True"
        in text
    )


def test_execution_message_extra_does_not_claim_ladder():
    plan = {
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit": 130.0,
        "rr": 3.0,
        "risk_reward": 3.0,
        "original_rr": 3.0,
        "lot": 0.25,
        "reason": "TEST",
    }

    generated = (
        ensure_universal_tp_ladder(
            "BUY",
            plan,
            source="TEST",
            geometry_phase="FINAL_EXECUTION",
        )
    )

    extra = (
        prepare_main_tp_ladder_execution(
            "BUY",
            generated,
            "XAUUSD",
            same_direction_count=1,
            symbol_info=SYMBOL_INFO,
        )
    )

    text = (
        _format_execution_tp_management(
            "BUY",
            extra,
        )
    )

    assert (
        extra[
            "execution_trade_role"
        ]
        == "EXTRA"
    )

    assert (
        extra.get(
            "main_tp_ladder_managed"
        )
        is False
    )

    assert "Execution Role: EXTRA" in text
    # EXTRA execution telemetry must not advertise
    # the planned TP ladder as active management.
    #
    # "Runner After TP3: False" is an intentional status
    # line, so do not use the overly broad substring
    # assertion `"TP3:" not in text`.
    assert "TP Plan:" not in text
    assert "\nTP1:" not in text
    assert "\nTP2:" not in text
    assert "\nTP3:" not in text
    assert "TP3_ORIGINAL_STRATEGY_TARGET" not in text

    assert (
        "EXTRA +6.0 price-profit"
        in text
    )

    assert (
        "Runner After TP3: False"
        in text
    )


def test_execution_message_volume_fallback_does_not_claim_ladder():
    plan = {
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit": 130.0,
        "rr": 3.0,
        "risk_reward": 3.0,
        "original_rr": 3.0,
        "lot": 0.03,
        "reason": "TEST",
    }

    generated = (
        ensure_universal_tp_ladder(
            "BUY",
            plan,
            source="TEST",
            geometry_phase="FINAL_EXECUTION",
        )
    )

    fallback = (
        prepare_main_tp_ladder_execution(
            "BUY",
            generated,
            "XAUUSD",
            same_direction_count=0,
            symbol_info=SYMBOL_INFO,
        )
    )

    text = (
        _format_execution_tp_management(
            "BUY",
            fallback,
        )
    )

    assert (
        fallback.get(
            "main_tp_ladder_managed"
        )
        is False
    )

    assert (
        fallback.get(
            "main_tp_ladder_skip_reason"
        )
        == (
            "unsupported_broker_volume_geometry"
        )
    )

    # Fallback MAIN may mention TP3 in the status
    # line "Runner After TP3: False". What must be absent
    # is an advertised ACTIVE TP ladder.
    assert "TP Plan:" not in text
    assert "\nTP1:" not in text
    assert "\nTP2:" not in text
    assert "\nTP3:" not in text
    assert "TP3_ORIGINAL_STRATEGY_TARGET" not in text

    assert (
        "TP Ladder Skip: "
        "unsupported_broker_volume_geometry"
        in text
    )

    assert (
        "Runner After TP3: False"
        in text
    )


def test_source_contracts():
    order_source = (
        ROOT
        / "src"
        / "order_executor.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    live_source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "ensure_universal_tp_ladder"
        in order_source
    )

    assert (
        "FINAL_EXECUTION"
        in order_source
    )

    assert (
        "_format_universal_tp_plan_from_levels"
        in live_source
    )

    assert (
        "_format_telegram_tp123_from_trade_plan"
        in live_source
    )


if __name__ == "__main__":
    test_high_rr_orb_example()
    test_low_rr_not_rescued()
    test_existing_structural_ladder_preserved()
    test_final_execution_fallback_survives_rebase_guard()
    test_old_structural_ladder_rebase_still_fails_safe()
    test_visual_plan_without_sl()
    test_trade_plan_formatter()
    test_detected_setup_message_has_three_targets()
    test_execution_message_managed_main_claims_ladder()
    test_execution_message_extra_does_not_claim_ladder()
    test_execution_message_volume_fallback_does_not_claim_ladder()
    test_source_contracts()

    print(
        "[PASS] Universal TP ladder keeps TP3 as "
        "the original RR authority, generates "
        "TP1/TP2 management targets, preserves "
        "structural ladders, and supports MAIN runner."
    )
