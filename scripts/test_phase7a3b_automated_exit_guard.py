from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prop_firm_news_guard import (
    evaluate_prop_firm_news_restriction,
)
from src import manual_trailing_manager
from src import position_manager


PROFILE_NAME = "GETLEVERAGED_TURBO_EVALUATION_50K"
NOW = datetime(2026, 8, 6, 15, 30)

PROFILE = {
    "news_restriction_enabled": True,
    "news_before_minutes": 5,
    "news_after_minutes": 5,
    "news_restricted_currencies": ("USD",),
    "news_required_impacts": ("HIGH",),
    "news_calendar_fail_closed": True,
    "news_block_automated_position_closes": True,
    "news_freeze_sl_tp_modifications": True,
    "news_preserve_existing_sl_tp": True,
}

CALENDAR = {
    "available": True,
    "provider": "SYNTHETIC_TEST",
    "events": [
        {
            "name": "Synthetic High Impact",
            "time": NOW,
            "currency": "USD",
            "impact": "High",
            "source": "SYNTHETIC_TEST",
        }
    ],
    "error": None,
}


def evaluate(action):
    return evaluate_prop_firm_news_restriction(
        enabled=True,
        profile_name=PROFILE_NAME,
        profile=PROFILE,
        calendar_snapshot=CALENDAR,
        action=action,
        now=NOW,
        fail_closed=True,
    )


def test_restricted_actions():
    cases = (
        ("PARTIAL_CLOSE_POSITION", "AUTOMATED_EXIT"),
        ("FULL_CLOSE_POSITION", "AUTOMATED_EXIT"),
        (
            "MODIFY_PROTECTIVE_SL_TP",
            "PROTECTIVE_MODIFICATION",
        ),
    )

    for action, expected_category in cases:
        result = evaluate(action)

        assert result["allowed"] is False
        assert (
            result["reason"]
            == "prop_firm_restricted_news_window_active"
        )
        assert (
            result["snapshot"]["action_category"]
            == expected_category
        )
        assert result["snapshot"]["orders_sent"] == 0


def test_broker_triggered_protection_is_untouched():
    result = evaluate("BROKER_TRIGGERED_SL_TP")

    assert result["allowed"] is True
    assert (
        result["reason"]
        == "action_not_restricted_by_news_guard"
    )


class FakeMT5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    TRADE_ACTION_DEAL = 10
    TRADE_ACTION_SLTP = 20

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0

    TRADE_RETCODE_DONE = 10009

    def __init__(self):
        self.order_send_count = 0

    def order_send(self, request):
        self.order_send_count += 1
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
        )

    def last_error(self):
        return (0, "OK")


BLOCKED = {
    "allowed": False,
    "reason": "prop_firm_restricted_news_window_active",
    "snapshot": {
        "action_category": "TEST",
        "orders_sent": 0,
    },
}


def build_position(volume=0.03):
    return SimpleNamespace(
        ticket=123456,
        symbol="XAUUSD",
        type=0,
        volume=volume,
        price_open=4250.0,
        sl=4240.0,
        tp=4270.0,
    )


def test_manager_close_sends_zero_orders():
    original_mt5 = position_manager.mt5
    original_guard = (
        position_manager
        .evaluate_runtime_prop_firm_news_action
    )

    fake = FakeMT5()

    try:
        position_manager.mt5 = fake
        position_manager.evaluate_runtime_prop_firm_news_action = (
            lambda **kwargs: BLOCKED
        )

        result = position_manager.close_position_volume(
            build_position(volume=0.03),
            0.01,
            SimpleNamespace(
                bid=4255.0,
                ask=4255.2,
            ),
            reason="synthetic partial close",
        )

        assert result is False
        assert fake.order_send_count == 0

    finally:
        position_manager.mt5 = original_mt5
        position_manager.evaluate_runtime_prop_firm_news_action = (
            original_guard
        )


def test_manager_protection_update_sends_zero_orders():
    original_mt5 = position_manager.mt5
    original_guard = (
        position_manager
        .evaluate_runtime_prop_firm_news_action
    )

    fake = FakeMT5()

    try:
        position_manager.mt5 = fake
        position_manager.evaluate_runtime_prop_firm_news_action = (
            lambda **kwargs: BLOCKED
        )

        result = position_manager.modify_sl(
            build_position(),
            4251.0,
            4270.0,
            reason="synthetic manager SL update",
        )

        assert result is False
        assert fake.order_send_count == 0

    finally:
        position_manager.mt5 = original_mt5
        position_manager.evaluate_runtime_prop_firm_news_action = (
            original_guard
        )


def test_manual_trailing_update_sends_zero_orders():
    original_mt5 = manual_trailing_manager.mt5
    original_guard = (
        manual_trailing_manager
        .evaluate_runtime_prop_firm_news_action
    )

    fake = FakeMT5()

    try:
        manual_trailing_manager.mt5 = fake
        manual_trailing_manager.evaluate_runtime_prop_firm_news_action = (
            lambda **kwargs: BLOCKED
        )

        result = manual_trailing_manager.modify_sl(
            build_position(),
            4251.0,
            4270.0,
            reason="synthetic manual trailing update",
        )

        assert result is False
        assert fake.order_send_count == 0

    finally:
        manual_trailing_manager.mt5 = original_mt5
        manual_trailing_manager.evaluate_runtime_prop_firm_news_action = (
            original_guard
        )


def test_source_markers_and_default_state():
    manager_source = (
        ROOT / "src" / "position_manager.py"
    ).read_text(encoding="utf-8")

    manual_source = (
        ROOT / "src" / "manual_trailing_manager.py"
    ).read_text(encoding="utf-8")

    settings_source = (
        ROOT / "config" / "settings.py"
    ).read_text(encoding="utf-8")

    assert "PROP FIRM NEWS EXIT GUARD" in manager_source
    assert (
        "PROP FIRM NEWS PROTECTION GUARD"
        in manager_source
    )
    assert (
        "PROP FIRM NEWS PROTECTION GUARD"
        in manual_source
    )

    assert (
        '"news_block_automated_position_closes": True'
        in settings_source
    )
    assert (
        '"news_freeze_sl_tp_modifications": True'
        in settings_source
    )
    assert (
        '"news_preserve_existing_sl_tp": True'
        in settings_source
    )

    assert (
        "ENABLE_PROP_FIRM_SAFE_MODE = False"
        in settings_source
    )


if __name__ == "__main__":
    test_restricted_actions()
    test_broker_triggered_protection_is_untouched()
    test_manager_close_sends_zero_orders()
    test_manager_protection_update_sends_zero_orders()
    test_manual_trailing_update_sends_zero_orders()
    test_source_markers_and_default_state()

    print(
        "[PASS] Phase 7A3B automated exit and "
        "protection guard passed."
    )
