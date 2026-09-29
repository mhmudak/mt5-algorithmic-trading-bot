from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETTINGS = ROOT / "config" / "settings.py"
EXECUTION = ROOT / "src" / "execution.py"
LIVE = ROOT / "src" / "live_bot.py"
DAILY = ROOT / "src" / "daily_guard.py"
NOTIFIER = ROOT / "src" / "notifier.py"
ORDER_EXECUTOR = ROOT / "src" / "order_executor.py"


def assigned_value(tree, name):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"setting not found: {name}")


def main():
    print("[MICRO MOMENTUM HIGH-FREQUENCY POLICY TEST V2]")

    settings_text = SETTINGS.read_text(encoding="utf-8")
    settings_tree = ast.parse(settings_text)

    max_daily = assigned_value(settings_tree, "MAX_TRADES_PER_DAY")
    routine_tg = assigned_value(
        settings_tree,
        "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS",
    )

    print(f"MAX_TRADES_PER_DAY={max_daily}")
    print(
        "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS="
        f"{routine_tg}"
    )

    if max_daily != 4000:
        raise AssertionError(f"expected daily cap 4000, got {max_daily}")
    if routine_tg is not False:
        raise AssertionError("routine Micro Momentum Telegram must be disabled")

    execution_text = EXECUTION.read_text(encoding="utf-8")
    if "def check_trade_guard(signal, tick, *, skip_cooldown=False):" not in execution_text:
        raise AssertionError("check_trade_guard skip_cooldown API missing")
    if "if not skip_cooldown and in_cooldown_period(SYMBOL):" not in execution_text:
        raise AssertionError("generic cooldown bypass hook missing")
    if "if reached_max_trades_today(SYMBOL):" not in execution_text:
        raise AssertionError("daily entry guard was removed")
    if "same_direction_count >= MAX_SAME_DIRECTION_TRADES" not in execution_text:
        raise AssertionError("same-direction guard was removed")

    live_text = LIVE.read_text(encoding="utf-8")
    start = live_text.index("def process_intrabar_micro_momentum_live(")
    end = live_text.index(
        "\ndef process_intrabar_micro_momentum_fast_lane_once",
        start,
    )
    mm_fn = live_text[start:end]

    for snippet in (
        "skip_cooldown=True",
        'trade_plan["suppress_routine_telegram"] = True',
        'trade_plan["execution_geometry_authority"] = strategy_name',
        "ENABLE_GLOBAL_DRAWDOWN_STOP",
    ):
        if snippet not in mm_fn:
            raise AssertionError(f"missing Micro Momentum wiring: {snippet}")

    daily_text = DAILY.read_text(encoding="utf-8")
    if "Counted entry deal" in daily_text:
        raise AssertionError("per-ticket daily guard console spam remains")
    if "return count >= MAX_TRADES_PER_DAY" not in daily_text:
        raise AssertionError("daily guard decision was changed unexpectedly")

    notifier_text = NOTIFIER.read_text(encoding="utf-8")
    for snippet in (
        "def _should_suppress_micro_momentum_routine",
        "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS",
        "Routine Micro Momentum Telegram suppressed",
    ):
        if snippet not in notifier_text:
            raise AssertionError(f"notifier suppression missing: {snippet}")

    oe_text = ORDER_EXECUTOR.read_text(encoding="utf-8")
    if 'trade_plan.get("suppress_routine_telegram", False)' not in oe_text:
        raise AssertionError("execution success Telegram suppression flag missing")
    if 'f"✅ Trade Executed\\n"' not in oe_text:
        raise AssertionError("normal execution Telegram message was removed")

    marker = 'if not bool(\n        trade_plan.get("suppress_routine_telegram", False)\n    ):'
    if marker not in oe_text:
        raise AssertionError("success notification is not conditionally suppressed")

    print(
        "\nPASS: Micro Momentum bypasses only the generic 1-minute cooldown; "
        "spread/live permission, max-same-direction, daily entry cap, "
        "drawdown hook, and final geometry remain present. Daily cap is 4000. "
        "Routine Micro Momentum detection/execution Telegram is silent while "
        "normal strategy and safety/error Telegram paths remain available."
    )


if __name__ == "__main__":
    main()
