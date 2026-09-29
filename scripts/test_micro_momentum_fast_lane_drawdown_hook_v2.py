from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "src" / "live_bot.py"
SETTINGS = ROOT / "config" / "settings.py"


def main():
    print("[MICRO MOMENTUM FAST-LANE DRAWDOWN HOOK TEST V2]")

    live_text = LIVE.read_text(encoding="utf-8")
    settings_text = SETTINGS.read_text(encoding="utf-8")

    required = [
        'if bool(getattr(_mm_settings, "ENABLE_GLOBAL_DRAWDOWN_STOP", False)):',
        'drawdown_exceeded, floating_pnl = is_drawdown_exceeded(SYMBOL)',
        'reason=global_drawdown_stop',
        'reason=global_drawdown_check_failed',
        'skip_cooldown=True',
    ]
    for snippet in required:
        if snippet not in live_text:
            raise AssertionError(
                f"missing Micro Momentum fast-lane safety wiring: {snippet}"
            )

    tree = ast.parse(settings_text)
    enabled = None
    max_dd = None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "ENABLE_GLOBAL_DRAWDOWN_STOP":
                enabled = ast.literal_eval(node.value)
            elif target.id == "MAX_DRAWDOWN_USD":
                max_dd = ast.literal_eval(node.value)

    print(f"ENABLE_GLOBAL_DRAWDOWN_STOP={enabled}")
    print(f"MAX_DRAWDOWN_USD={max_dd}")

    if enabled is not False:
        raise AssertionError(
            "test expects global drawdown stop to remain operator-disabled"
        )

    fn_start = live_text.index("def process_intrabar_micro_momentum_live(")
    fn_end = live_text.index(
        "\ndef process_intrabar_micro_momentum_fast_lane_once",
        fn_start,
    )
    fn_text = live_text[fn_start:fn_end]

    guard_pos = fn_text.index("trade_allowed, guard_reason = check_trade_guard(")
    skip_pos = fn_text.index("skip_cooldown=True", guard_pos)
    dd_pos = fn_text.index("ENABLE_GLOBAL_DRAWDOWN_STOP", skip_pos)
    plan_pos = fn_text.index("trade_plan = calculate_trade_plan(", dd_pos)

    if not (guard_pos < skip_pos < dd_pos < plan_pos):
        raise AssertionError(
            "expected order: trade guard -> Micro Momentum cooldown bypass -> "
            "drawdown hook -> trade-plan build"
        )

    execution_mode_pos = fn_text.index(
        'trade_plan["execution_mode"] = "LIVE_INTRABAR_MICRO_MOMENTUM"'
    )
    suppress_pos = fn_text.index(
        'trade_plan["suppress_routine_telegram"] = True',
        execution_mode_pos,
    )
    geometry_pos = fn_text.index(
        'trade_plan["execution_geometry_authority"] = strategy_name',
        suppress_pos,
    )

    if not (execution_mode_pos < suppress_pos < geometry_pos):
        raise AssertionError(
            "routine Telegram suppression must be metadata-only and precede "
            "final Micro Momentum geometry authority"
        )

    print(
        "\nPASS: Micro Momentum fast lane keeps the per-candidate global "
        "drawdown hook after its shared trade guard and before trade-plan "
        "construction. The generic 1-minute cooldown bypass is isolated to "
        "Micro Momentum, and the drawdown switch remains OFF until explicitly "
        "enabled by the operator."
    )


if __name__ == "__main__":
    main()
