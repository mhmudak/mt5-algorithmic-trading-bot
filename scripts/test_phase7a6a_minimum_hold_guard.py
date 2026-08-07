from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from src.prop_firm_minimum_hold_guard import (
    evaluate_runtime_prop_firm_minimum_hold,
)
import src.position_manager as position_manager


PROFILE_NAME = "GETLEVERAGED_TURBO_EVALUATION_50K"
NOW = 1_786_021_800.0


def position(*, opened_at):
    return SimpleNamespace(
        ticket=7001,
        symbol="XAUUSD",
        type=position_manager.mt5.POSITION_TYPE_BUY,
        volume=0.03,
        time=opened_at,
    )


def test_profile_and_default_state():
    profile = settings.PROP_FIRM_PROFILES[
        PROFILE_NAME
    ]

    assert settings.ENABLE_PROP_FIRM_SAFE_MODE is True
    assert settings.PROP_FIRM_SAFE_MODE_FAIL_CLOSED is True
    assert settings.EXECUTION_MODE == "LIVE"
    assert settings.ALLOW_LIVE_TRADING is True

    assert (
        profile["minimum_automated_hold_seconds"]
        == 120
    )
    assert profile["minimum_hold_fail_closed"] is True
    assert (
        profile[
            "minimum_hold_emergency_drawdown_exception"
        ]
        is True
    )
    assert (
        profile[
            "minimum_hold_broker_protection_exception"
        ]
        is True
    )


def test_hold_boundary():
    original_enabled = (
        settings.ENABLE_PROP_FIRM_SAFE_MODE
    )

    try:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = True

        blocked = evaluate_runtime_prop_firm_minimum_hold(
            position=position(
                opened_at=NOW - 119,
            ),
            action="FULL_CLOSE_POSITION",
            now_timestamp=NOW,
        )

        assert blocked["allowed"] is False
        assert (
            blocked["reason"]
            == "prop_firm_minimum_hold_active"
        )
        assert (
            blocked["snapshot"][
                "remaining_hold_seconds"
            ]
            == 1.0
        )
        assert blocked["snapshot"]["orders_sent"] == 0

        allowed = evaluate_runtime_prop_firm_minimum_hold(
            position=position(
                opened_at=NOW - 120,
            ),
            action="PARTIAL_CLOSE_POSITION",
            now_timestamp=NOW,
        )

        assert allowed["allowed"] is True
        assert (
            allowed["reason"]
            == "prop_firm_minimum_hold_satisfied"
        )

        missing_time = (
            evaluate_runtime_prop_firm_minimum_hold(
                position=position(
                    opened_at=None,
                ),
                action="FULL_CLOSE_POSITION",
                now_timestamp=NOW,
            )
        )

        assert missing_time["allowed"] is False
        assert (
            missing_time["reason"]
            == "prop_firm_position_open_time_unavailable"
        )

    finally:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = (
            original_enabled
        )


def test_manager_blocks_zero_orders():
    original_enabled = (
        settings.ENABLE_PROP_FIRM_SAFE_MODE
    )
    original_news_guard = (
        position_manager
        .evaluate_runtime_prop_firm_news_action
    )
    original_order_send = (
        position_manager.mt5.order_send
    )

    order_calls = []

    try:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = True

        position_manager.evaluate_runtime_prop_firm_news_action = (
            lambda **_: {
                "allowed": True,
                "reason": "synthetic_news_clear",
                "snapshot": {
                    "orders_sent": 0,
                },
            }
        )

        def forbidden_order_send(request):
            order_calls.append(request)
            raise AssertionError(
                "order_send called before 120 seconds"
            )

        position_manager.mt5.order_send = (
            forbidden_order_send
        )

        result = (
            position_manager.close_position_volume(
                position(
                    opened_at=NOW - 30,
                ),
                0.01,
                SimpleNamespace(
                    bid=4269.0,
                    ask=4269.2,
                    time=NOW,
                ),
                reason=(
                    "Synthetic early partial close"
                ),
            )
        )

        assert result is False
        assert order_calls == []

    finally:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = (
            original_enabled
        )
        position_manager.evaluate_runtime_prop_firm_news_action = (
            original_news_guard
        )
        position_manager.mt5.order_send = (
            original_order_send
        )


def test_source_markers():
    manager_source = (
        ROOT / "src" / "position_manager.py"
    ).read_text(encoding="utf-8")

    emergency_source = (
        ROOT / "src" / "emergency_close.py"
    ).read_text(encoding="utf-8")

    assert (
        "evaluate_runtime_prop_firm_minimum_hold"
        in manager_source
    )
    assert (
        "PROP FIRM MINIMUM HOLD GUARD"
        in manager_source
    )
    assert (
        "explicit safety exception"
        in emergency_source
    )


if __name__ == "__main__":
    test_profile_and_default_state()
    test_hold_boundary()
    test_manager_blocks_zero_orders()
    test_source_markers()

    print(
        "[PASS] Phase 7A6A minimum holding-period "
        "guard passed."
    )
