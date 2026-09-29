from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "src" / "live_bot.py"
SETTINGS = ROOT / "config" / "settings.py"


def main():
    print("[MICRO MOMENTUM FAST-LANE DRAWDOWN HOOK TEST V1]")

    live_text = LIVE.read_text(encoding="utf-8")
    settings_text = SETTINGS.read_text(encoding="utf-8")

    required = [
        'if bool(getattr(_mm_settings, "ENABLE_GLOBAL_DRAWDOWN_STOP", False)):',
        'drawdown_exceeded, floating_pnl = is_drawdown_exceeded(SYMBOL)',
        'reason=global_drawdown_stop',
        'reason=global_drawdown_check_failed',
    ]
    for snippet in required:
        if snippet not in live_text:
            raise AssertionError(f"missing fast-lane drawdown hook: {snippet}")

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
            "Patch must not enable global drawdown stop automatically"
        )

    fn_start = live_text.index("def process_intrabar_micro_momentum_live(")
    fn_end = live_text.index(
        "\ndef process_intrabar_micro_momentum_fast_lane_once",
        fn_start,
    )
    fn_text = live_text[fn_start:fn_end]

    guard_pos = fn_text.index("check_trade_guard(signal, live_tick)")
    dd_pos = fn_text.index("ENABLE_GLOBAL_DRAWDOWN_STOP")
    plan_pos = fn_text.index("trade_plan = calculate_trade_plan(")

    if not (guard_pos < dd_pos < plan_pos):
        raise AssertionError(
            "drawdown hook must be after trade guard and before trade-plan build"
        )

    print(
        "\nPASS: Micro Momentum fast lane now has a per-candidate global "
        "drawdown hook at the execution boundary. The hook is dormant while "
        "ENABLE_GLOBAL_DRAWDOWN_STOP=False, so current live behavior is "
        "unchanged until the operator explicitly enables it."
    )


if __name__ == "__main__":
    main()
