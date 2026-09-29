from __future__ import annotations

from unittest.mock import patch

from config import settings
from src import notifier


def assert_suppressed(message: str) -> None:
    assert notifier._suppress_all_micro_momentum_telegram(message) is True

    with patch.object(
        notifier.requests,
        "post",
        side_effect=AssertionError(
            "requests.post must not be reached for Micro Momentum Telegram"
        ),
    ) as mocked_post:
        result = notifier.send_telegram_message(message)

    assert result is True
    assert mocked_post.call_count == 0


def main():
    print("[MICRO MOMENTUM TELEGRAM MASTER FIREWALL TEST V1]")
    print(
        "MICRO_MOMENTUM_TELEGRAM_ENABLED="
        f"{settings.MICRO_MOMENTUM_TELEGRAM_ENABLED}"
    )
    assert settings.MICRO_MOMENTUM_TELEGRAM_ENABLED is False

    samples = {
        "detected": (
            "⚡ Micro Momentum Detected\n"
            "Setup: IMM-BUY-1790276938133"
        ),
        "executed": (
            "⚡ Micro Momentum Executed #IMM-SELL-1790277057532\n"
            "Symbol: XAUUSD\n"
            "Signal: SELL\n"
            "Strength: WEAK_VALID"
        ),
        "strategy": (
            "Execution warning\n"
            "Strategy: INTRABAR_MICRO_MOMENTUM\n"
            "Signal: BUY"
        ),
        "setup_id": (
            "Trade update\n"
            "Setup ID: IMM-BUY-1790276938133"
        ),
        "runner": (
            "🏃 Low-MAE Momentum Runner Promoted\n"
            "Setup: IMM-SELL-1790277057532"
        ),
        "closed": (
            "Trade Closed\n"
            "Strategy: INTRABAR_MICRO_MOMENTUM\n"
            "Setup ID: IMM-BUY-1790276938133"
        ),
    }

    for label, message in samples.items():
        assert_suppressed(message)
        print(f"{label}_suppressed=True")

    normal = (
        "📊 Trade Executed\n"
        "Strategy: FCR_M1_FVG\n"
        "Signal: SELL"
    )
    assert notifier._suppress_all_micro_momentum_telegram(normal) is False

    unrelated = "🚨 CRITICAL BOT ERROR\nMT5 connection lost"
    assert notifier._suppress_all_micro_momentum_telegram(unrelated) is False

    print("normal_strategy_suppressed=False")
    print("unrelated_critical_suppressed=False")
    print(
        "PASS: the public Telegram boundary hard-suppresses identifiable "
        "Micro Momentum messages before HTTP while leaving other strategies "
        "and unrelated bot-wide critical alerts eligible."
    )


if __name__ == "__main__":
    main()
