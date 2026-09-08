from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from config import settings

from src.order_executor import (
    prepare_main_tp_ladder_execution,
    _main_tp_ladder_volume_supported,
)

from src.position_manager import (
    _main_ladder_stage_close_volume,
    _main_ladder_target_reached,
    _select_direction_main,
)

from src.trade_tracker import (
    _resolve_execution_trade_role,
)


SYMBOL_INFO = SimpleNamespace(
    point=0.01,
    volume_min=0.01,
    volume_step=0.01,
)


def sample_plan(
    lot=0.25,
):
    # Mirrors current Key-Level ladder semantics:
    # live take_profit may still be TP1 while the
    # original strategy target is persisted as TP3.
    return {
        "entry_price": 4400.0,
        "stop_loss": 4390.0,
        "take_profit": 4410.0,
        "original_take_profit": 4430.0,
        "original_rr": 3.0,
        "rr": 3.0,
        "risk_reward": 3.0,
        "strategy": "ORB",
        "setup_id": "TEST-ORB-BUY",
        "lot": lot,
        "reason": "synthetic",
        "tp_ladder": [
            {
                "name": "TP1",
                "price": 4410.0,
                "rr": 1.0,
            },
            {
                "name": "TP2",
                "price": 4420.0,
                "rr": 2.0,
            },
            {
                "name": "TP3",
                "price": 4430.0,
                "rr": 3.0,
            },
        ],
    }


def test_settings_preserve_legacy_split_config():
    assert (
        settings.
        ENABLE_MAIN_TP_LADDER_MANAGEMENT
        is True
    )

    # Legacy capability remains configured;
    # central execution bypasses it while
    # MAIN ladder management is enabled.
    assert (
        settings.
        ENABLE_TP_LADDER_SPLIT_EXECUTION
        is True
    )

    assert (
        settings.
        EXTRA_ENTRY_TAKE_PROFIT_PRICE
        == 6.0
    )


def test_main_is_one_position_with_tp3_decision_target():
    result = (
        prepare_main_tp_ladder_execution(
            "BUY",
            sample_plan(),
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
            "main_tp_ladder_role"
        ]
        == "MAIN"
    )

    assert (
        result[
            "pre_main_ladder_take_profit"
        ]
        == 4410.0
    )

    assert (
        result[
            "take_profit"
        ]
        == 4430.0
    )

    assert (
        result[
            "decision_take_profit"
        ]
        == 4430.0
    )

    assert (
        result[
            "main_tp1"
        ]
        == 4410.0
    )

    assert (
        result[
            "main_tp2"
        ]
        == 4420.0
    )

    assert (
        result[
            "main_tp3"
        ]
        == 4430.0
    )

    assert (
        result[
            "broker_take_profit"
        ]
        > 4430.0
    )

    assert (
        result[
            "main_runner_after_tp3"
        ]
        is True
    )


def test_extra_is_not_main_ladder_managed():
    result = (
        prepare_main_tp_ladder_execution(
            "BUY",
            sample_plan(),
            "XAUUSD",
            same_direction_count=1,
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
            "main_tp_ladder_role"
        )
        == "EXTRA"
    )

    # Existing EXTRA behavior is untouched.
    assert (
        result[
            "take_profit"
        ]
        == 4410.0
    )

    assert (
        "broker_take_profit"
        not in result
    )


def test_small_lot_fails_safe():
    result = (
        prepare_main_tp_ladder_execution(
            "BUY",
            sample_plan(
                lot=0.03
            ),
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
            'unsupported_broker_volume_geometry'
        )
    )

    # Never move its TP farther if partial
    # realization cannot be supported.
    assert (
        "broker_take_profit"
        not in result
    )


def test_execution_rebase_fails_safe():
    plan = sample_plan()

    plan[
        "reason"
    ] = (
        "synthetic | "
        "HIGH_SLIPPAGE_RETRACEMENT"
    )

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


def test_managed_main_cannot_be_demoted():
    main_position = SimpleNamespace(
        ticket=100,
        price_open=4400.0,
    )

    better_extra = SimpleNamespace(
        ticket=200,
        price_open=4395.0,
    )

    main_trade = {
        "trade_role": "MAIN",
        "main_tp_ladder_managed": True,
    }

    extra_trade = {
        "trade_role": "EXTRA",
        "main_tp_ladder_managed": False,
    }

    position, trade = (
        _select_direction_main(
            "BUY",
            [
                (
                    main_position,
                    main_trade,
                ),
                (
                    better_extra,
                    extra_trade,
                ),
            ],
        )
    )

    assert (
        position.ticket
        == 100
    )

    assert (
        trade is main_trade
    )


def test_legacy_best_entry_promotion_remains():
    p1 = SimpleNamespace(
        ticket=1,
        price_open=4400.0,
    )

    p2 = SimpleNamespace(
        ticket=2,
        price_open=4395.0,
    )

    position, _ = (
        _select_direction_main(
            "BUY",
            [
                (p1, {}),
                (p2, {}),
            ],
        )
    )

    assert (
        position.ticket
        == 2
    )


def test_025_lot_keeps_runner():
    initial = 0.25

    close1 = (
        _main_ladder_stage_close_volume(
            initial_volume=initial,
            close_pct=0.25,
            current_volume=0.25,
            symbol_info=SYMBOL_INFO,
        )
    )

    remaining1 = round(
        0.25 - close1,
        2,
    )

    close2 = (
        _main_ladder_stage_close_volume(
            initial_volume=initial,
            close_pct=0.25,
            current_volume=remaining1,
            symbol_info=SYMBOL_INFO,
        )
    )

    remaining2 = round(
        remaining1 - close2,
        2,
    )

    close3 = (
        _main_ladder_stage_close_volume(
            initial_volume=initial,
            close_pct=0.25,
            current_volume=remaining2,
            symbol_info=SYMBOL_INFO,
        )
    )

    runner = round(
        remaining2 - close3,
        2,
    )

    assert close1 == 0.06
    assert close2 == 0.06
    assert close3 == 0.06

    assert runner == 0.07

    assert (
        runner
        >= initial
        * settings.
        MAIN_RUNNER_REMAINING_PCT
    )


def test_directional_targets():
    assert (
        _main_ladder_target_reached(
            "BUY",
            4410.0,
            4410.0,
        )
        is True
    )

    assert (
        _main_ladder_target_reached(
            "BUY",
            4409.99,
            4410.0,
        )
        is False
    )

    assert (
        _main_ladder_target_reached(
            "SELL",
            4390.0,
            4390.0,
        )
        is True
    )

    assert (
        _main_ladder_target_reached(
            "SELL",
            4390.01,
            4390.0,
        )
        is False
    )


def test_tp3_remains_rr_authority():
    result = (
        prepare_main_tp_ladder_execution(
            "BUY",
            sample_plan(),
            "XAUUSD",
            same_direction_count=0,
            symbol_info=SYMBOL_INFO,
        )
    )

    assert (
        result[
            "take_profit"
        ]
        == 4430.0
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

    assert (
        result[
            "risk_reward"
        ]
        == 3.0
    )

    assert (
        result[
            "original_rr"
        ]
        == 3.0
    )


def test_role_contract_applies_without_ladder():
    plan = sample_plan()

    plan.pop(
        "tp_ladder"
    )

    result = (
        prepare_main_tp_ladder_execution(
            "BUY",
            plan,
            "XAUUSD",
            same_direction_count=1,
            symbol_info=SYMBOL_INFO,
        )
    )

    assert (
        result[
            "execution_trade_role"
        ]
        == "EXTRA"
    )

    assert (
        result[
            "execution_same_direction_count"
        ]
        == 1
    )

    assert (
        result[
            "execution_role_authority"
        ]
        == (
            "MT5_PHYSICAL_"
            "SAME_DIRECTION_COUNT_AT_T0"
        )
    )

    assert (
        result.get(
            "main_tp_ladder_managed"
        )
        is not True
    )


def test_tracker_explicit_main_beats_stale_tracker():
    stale_trades = {
        "999": {
            "symbol": "XAUUSD",
            "signal": "BUY",
            "status": "OPEN",
            "trade_role": "MAIN",
        }
    }

    (
        role,
        main_position_id,
        locked,
    ) = _resolve_execution_trade_role(
        stale_trades,
        "XAUUSD",
        "BUY",
        "123",
        {
            "execution_trade_role": "MAIN",
        },
    )

    assert role == "MAIN"
    assert main_position_id == "123"
    assert locked is True


def test_tracker_explicit_extra_survives_untracked_main():
    (
        role,
        main_position_id,
        locked,
    ) = _resolve_execution_trade_role(
        {},
        "XAUUSD",
        "BUY",
        "123",
        {
            "execution_trade_role": "EXTRA",
        },
    )

    assert role == "EXTRA"

    assert (
        main_position_id
        == "UNTRACKED_PHYSICAL_MAIN"
    )

    assert locked is True


def test_legacy_tracker_role_fallback_preserved():
    trades = {
        "999": {
            "symbol": "XAUUSD",
            "signal": "BUY",
            "status": "OPEN",
            "trade_role": "MAIN",
        }
    }

    (
        role,
        main_position_id,
        locked,
    ) = _resolve_execution_trade_role(
        trades,
        "XAUUSD",
        "BUY",
        "123",
        {},
    )

    assert role == "EXTRA"
    assert main_position_id == "999"
    assert locked is False


def test_locked_extra_cannot_be_promoted_to_main():
    position = SimpleNamespace(
        ticket=400,
        price_open=4390.0,
    )

    selection = (
        _select_direction_main(
            "BUY",
            [
                (
                    position,
                    {
                        "trade_role": "EXTRA",
                        "trade_role_locked": True,
                    },
                ),
            ],
        )
    )

    assert selection is None


def test_broker_step_volume_validation():
    good = SimpleNamespace(
        volume_min=0.01,
        volume_step=0.01,
        volume_max=100.0,
    )

    coarse = SimpleNamespace(
        volume_min=0.01,
        volume_step=0.10,
        volume_max=100.0,
    )

    too_small = SimpleNamespace(
        volume_min=0.10,
        volume_step=0.10,
        volume_max=100.0,
    )

    assert (
        _main_tp_ladder_volume_supported(
            0.25,
            good,
        )
        is True
    )

    assert (
        _main_tp_ladder_volume_supported(
            0.25,
            coarse,
        )
        is False
    )

    assert (
        _main_tp_ladder_volume_supported(
            0.25,
            too_small,
        )
        is False
    )


def test_source_contracts():
    order_source = (
        ROOT
        / "src"
        / "order_executor.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    tracker_source = (
        ROOT
        / "src"
        / "trade_tracker.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    manager_source = (
        ROOT
        / "src"
        / "position_manager.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "and not "
        "ENABLE_MAIN_TP_LADDER_MANAGEMENT"
        in order_source
    )

    assert (
        '"broker_take_profit"'
        in order_source
    )

    assert (
        '"main_tp_ladder_managed"'
        in tracker_source
    )

    assert (
        "manage_main_tp_ladder_trade"
        in manager_source
    )

    # Adjacent Python string literals may span
    # physical source lines, so validate the compiled
    # semantic string through the AST rather than
    # searching for one contiguous raw-source substring.
    manager_tree = ast.parse(
        manager_source
    )

    manager_string_constants = {
        node.value
        for node in ast.walk(
            manager_tree
        )
        if isinstance(
            node,
            ast.Constant,
        )
        and isinstance(
            node.value,
            str,
        )
    }

    assert (
        "Main TP3 runner protection -> TP2"
        in manager_string_constants
    )


if __name__ == "__main__":
    test_settings_preserve_legacy_split_config()
    test_main_is_one_position_with_tp3_decision_target()
    test_extra_is_not_main_ladder_managed()
    test_small_lot_fails_safe()
    test_execution_rebase_fails_safe()
    test_managed_main_cannot_be_demoted()
    test_legacy_best_entry_promotion_remains()
    test_025_lot_keeps_runner()
    test_directional_targets()
    test_tp3_remains_rr_authority()
    test_role_contract_applies_without_ladder()
    test_tracker_explicit_main_beats_stale_tracker()
    test_tracker_explicit_extra_survives_untracked_main()
    test_legacy_tracker_role_fallback_preserved()
    test_locked_extra_cannot_be_promoted_to_main()
    test_broker_step_volume_validation()
    test_source_contracts()

    print(
        "[PASS] MAIN TP1/TP2/TP3 + runner "
        "infrastructure preserves one physical MAIN, "
        "keeps EXTRAs separate, and fails safe on "
        "small lots or stale execution geometry."
    )
