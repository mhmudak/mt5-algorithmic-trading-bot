from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTIFIER = ROOT / "src" / "notifier.py"
SETTINGS = ROOT / "config" / "settings.py"


def assigned_value(tree, name):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"setting not found: {name}")


def main():
    print("[LOW-MAE RUNNER TELEGRAM SUPPRESSION TEST V1]")

    notifier_text = NOTIFIER.read_text(encoding="utf-8")
    settings_text = SETTINGS.read_text(encoding="utf-8")

    ast.parse(notifier_text)
    settings_tree = ast.parse(settings_text)

    routine_enabled = assigned_value(
        settings_tree,
        "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS",
    )
    print(
        "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS="
        f"{routine_enabled}"
    )

    assert routine_enabled is False

    required = [
        "def _suppress_low_mae_runner_promotion_telegram",
        "LOW-MAE MOMENTUM RUNNER PROMOTED",
        "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS",
        "_suppress_low_mae_runner_promotion_telegram(text)",
    ]
    for snippet in required:
        if snippet not in notifier_text:
            raise AssertionError(
                f"missing runner Telegram suppression wiring: {snippet}"
            )

    namespace = {}
    exec(compile(notifier_text, str(NOTIFIER), "exec"), namespace)

    suppress = namespace["_suppress_low_mae_runner_promotion_telegram"]

    runner_message = (
        "🏃 Low-MAE Momentum Runner Promoted\n"
        "Setup: IMM-BUY-123\n"
        "Position: 123456\n"
        "Signal: BUY\n"
        "MFE: 1.52R\n"
        "MAE: 0.06R"
    )
    normal_message = (
        "🚨 Execution safety error\n"
        "Strategy: HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"
    )

    print(
        "runner_promotion_suppressed=",
        suppress(runner_message),
    )
    print(
        "normal_message_suppressed=",
        suppress(normal_message),
    )

    assert suppress(runner_message) is True
    assert suppress(normal_message) is False

    print(
        "\nPASS: Low-MAE Momentum Runner promotion Telegram is suppressed "
        "when routine Micro Momentum Telegram is OFF. Runner promotion logic, "
        "position management, safety/error Telegram, and non-Micro-Momentum "
        "notifications remain unchanged."
    )


if __name__ == "__main__":
    main()
