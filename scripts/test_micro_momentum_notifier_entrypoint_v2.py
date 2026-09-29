from __future__ import annotations

from unittest.mock import patch

from config import settings
from src import notifier


def main():
    print("[MICRO MOMENTUM NOTIFIER ENTRYPOINT TEST V2]")
    print(
        "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS="
        f"{settings.MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS}"
    )

    assert settings.MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS is False

    runner_message = (
        "🏃 Low-MAE Momentum Runner Promoted\n"
        "Setup: IMM-SELL-TEST\n"
        "Position: 123456789\n"
        "Signal: SELL\n"
        "MFE: 1.6R\n"
        "MAE: 0.1R\n"
        "Efficiency: 16.0x\n"
        "SL: 4259.4\n"
        "TP: 4257.5"
    )

    assert notifier._suppress_micro_momentum_routine_telegram(
        runner_message
    ) is True

    with patch.object(
        notifier.requests,
        "post",
        side_effect=AssertionError(
            "requests.post must not be reached for routine Micro Momentum "
            "Runner promotion Telegram"
        ),
    ) as mocked_post:
        result = notifier.send_telegram_message(runner_message)

    assert result is True
    assert mocked_post.call_count == 0

    safety_message = (
        "⚠️ Execution blocked: high adverse slippage\n"
        "Strategy: INTRABAR_MICRO_MOMENTUM"
    )
    assert notifier._suppress_micro_momentum_routine_telegram(
        safety_message
    ) is False

    normal_message = (
        "📊 Trade Executed\n"
        "Strategy: ORB\n"
        "Signal: SELL"
    )
    assert notifier._suppress_micro_momentum_routine_telegram(
        normal_message
    ) is False

    print("runner_helper_suppressed=True")
    print("runner_public_entrypoint_http_calls=0")
    print("safety_message_suppressed=False")
    print("normal_strategy_message_suppressed=False")
    print("")
    print(
        "PASS: send_telegram_message() routes through the generalized Micro "
        "Momentum routine suppressor. Low-MAE Runner promotion is suppressed "
        "before HTTP while safety/error and normal-strategy messages remain "
        "eligible."
    )


if __name__ == "__main__":
    main()
