from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.notifier as notifier


def main():
    print("[MICRO MOMENTUM MANAGER TELEGRAM ISOLATION TEST V1]")

    helper = notifier._suppress_micro_momentum_routine_telegram
    original_lookup = notifier._strategy_for_position_id

    try:
        notifier._strategy_for_position_id = (
            lambda position_id: "INTRABAR_MICRO_MOMENTUM"
        )

        runner = (
            "🏃 Low-MAE Momentum Runner Promoted\n"
            "Setup: IMM-BUY-123\n"
            "Position: 336369962"
        )
        tp1 = (
            "🎯 MAIN TP1 Reached\n"
            "Position: 336369962\n"
            "Symbol: XAUUSD"
        )
        tp2 = (
            "🎯 MAIN TP2 Reached\n"
            "Position: 336369962\n"
            "Symbol: XAUUSD"
        )
        partial = (
            "Partial Close\n"
            "Position: 336369962\n"
            "Role: MAIN\n"
            "Symbol: XAUUSD"
        )
        safety = (
            "⛔ Trade Blocked\n"
            "Position: 336369962\n"
            "Reason: High slippage"
        )

        print("runner_suppressed=", helper(runner))
        print("tp1_suppressed=", helper(tp1))
        print("tp2_suppressed=", helper(tp2))
        print("partial_suppressed=", helper(partial))
        print("safety_suppressed=", helper(safety))

        assert helper(runner) is True
        assert helper(tp1) is True
        assert helper(tp2) is True
        assert helper(partial) is True
        assert helper(safety) is False

        notifier._strategy_for_position_id = (
            lambda position_id: "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"
        )

        print("normal_tp1_suppressed=", helper(tp1))
        print("normal_partial_suppressed=", helper(partial))

        assert helper(tp1) is False
        assert helper(partial) is False

    finally:
        notifier._strategy_for_position_id = original_lookup

    print(
        "\nPASS: routine MAIN-management Telegram is silent only for "
        "INTRABAR_MICRO_MOMENTUM positions. Management actions still run; "
        "normal-strategy and safety/error Telegram remain available."
    )


if __name__ == "__main__":
    main()
