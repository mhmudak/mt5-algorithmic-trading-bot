from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import emergency_close
from src import telegram_signal_executor


BLOCKED = {
    "allowed": False,
    "reason": "prop_firm_restricted_news_window_active",
    "snapshot": {
        "action_category": "AUTOMATED_EXIT",
        "orders_sent": 0,
    },
}

ALLOWED = {
    "allowed": True,
    "reason": "no_prop_firm_restricted_news_window",
    "snapshot": {},
}


class FakeMT5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    TRADE_ACTION_DEAL = 10
    TRADE_ACTION_SLTP = 20

    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1

    TRADE_RETCODE_DONE = 10009

    def __init__(self, positions=None):
        self.positions = list(positions or [])
        self.order_send_count = 0
        self.sent_requests = []

    def positions_get(self, symbol=None):
        return list(self.positions)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(
            bid=4250.0,
            ask=4250.2,
        )

    def order_send(self, request):
        self.order_send_count += 1
        self.sent_requests.append(dict(request))

        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
        )

    def last_error(self):
        return (0, "OK")


def build_position(ticket=1001):
    return SimpleNamespace(
        ticket=ticket,
        symbol="XAUUSD",
        type=0,
        volume=0.01,
        sl=4240.0,
        tp=4270.0,
    )


def test_emergency_close_blocked_sends_zero_orders():
    original_mt5 = emergency_close.mt5
    original_guard = (
        emergency_close
        .evaluate_runtime_prop_firm_news_action
    )

    fake = FakeMT5([build_position()])

    try:
        emergency_close.mt5 = fake
        emergency_close.evaluate_runtime_prop_firm_news_action = (
            lambda **kwargs: BLOCKED
        )

        result = emergency_close.close_all_positions(
            "XAUUSD"
        )

        assert result["blocked"] is True
        assert result["all_closed"] is False
        assert result["orders_sent"] == 0
        assert fake.order_send_count == 0

    finally:
        emergency_close.mt5 = original_mt5
        emergency_close.evaluate_runtime_prop_firm_news_action = (
            original_guard
        )


def test_emergency_close_allowed_confirms_completion():
    original_mt5 = emergency_close.mt5
    original_guard = (
        emergency_close
        .evaluate_runtime_prop_firm_news_action
    )

    fake = FakeMT5([
        build_position(ticket=1001),
        build_position(ticket=1002),
    ])

    try:
        emergency_close.mt5 = fake
        emergency_close.evaluate_runtime_prop_firm_news_action = (
            lambda **kwargs: ALLOWED
        )

        result = emergency_close.close_all_positions(
            "XAUUSD"
        )

        assert result["blocked"] is False
        assert result["all_closed"] is True
        assert result["position_count"] == 2
        assert result["closed_count"] == 2
        assert result["failed_count"] == 0
        assert fake.order_send_count == 2

    finally:
        emergency_close.mt5 = original_mt5
        emergency_close.evaluate_runtime_prop_firm_news_action = (
            original_guard
        )


def test_telegram_tp_update_blocked_sends_zero_orders():
    original_mt5 = telegram_signal_executor.mt5
    original_guard = (
        telegram_signal_executor
        .evaluate_runtime_prop_firm_news_action
    )
    original_find = (
        telegram_signal_executor
        ._find_open_trade_by_message
    )

    position = build_position(ticket=2001)
    fake = FakeMT5([position])

    try:
        telegram_signal_executor.mt5 = fake

        telegram_signal_executor.evaluate_runtime_prop_firm_news_action = (
            lambda **kwargs: BLOCKED
        )

        telegram_signal_executor._find_open_trade_by_message = (
            lambda parsed: ("2001", {})
        )

        success, reason = (
            telegram_signal_executor
            ._update_existing_trade_tp(
                {
                    "type": "SIGNAL",
                    "tp1": 4280.0,
                    "source_name": "Synthetic",
                    "source_message_id": "TEST-1",
                    "direction": "BUY",
                },
                "XAUUSD",
            )
        )

        assert success is False
        assert (
            reason
            == "prop_firm_restricted_news_window_active"
        )
        assert fake.order_send_count == 0

    finally:
        telegram_signal_executor.mt5 = original_mt5
        telegram_signal_executor.evaluate_runtime_prop_firm_news_action = (
            original_guard
        )
        telegram_signal_executor._find_open_trade_by_message = (
            original_find
        )


def test_live_bot_does_not_exit_after_blocked_close():
    source = (
        ROOT / "src" / "live_bot.py"
    ).read_text(encoding="utf-8")

    assert "emergency_result = close_all_positions" in source
    assert '"all_closed"' in source
    assert '"blocked"' in source
    assert "Bot remains active and will retry" in source


def test_source_markers_and_default_state():
    emergency_source = (
        ROOT / "src" / "emergency_close.py"
    ).read_text(encoding="utf-8")

    telegram_source = (
        ROOT / "src" / "telegram_signal_executor.py"
    ).read_text(encoding="utf-8")

    settings_source = (
        ROOT / "config" / "settings.py"
    ).read_text(encoding="utf-8")

    assert (
        "PROP FIRM NEWS EMERGENCY GUARD"
        in emergency_source
    )
    assert (
        "evaluate_runtime_prop_firm_news_action"
        in emergency_source
    )
    assert (
        "PROP FIRM NEWS TELEGRAM GUARD"
        in telegram_source
    )
    assert (
        "ENABLE_PROP_FIRM_SAFE_MODE = False"
        in settings_source
    )


if __name__ == "__main__":
    test_emergency_close_blocked_sends_zero_orders()
    test_emergency_close_allowed_confirms_completion()
    test_telegram_tp_update_blocked_sends_zero_orders()
    test_live_bot_does_not_exit_after_blocked_close()
    test_source_markers_and_default_state()

    print(
        "[PASS] Phase 7A3C remaining news paths passed."
    )
