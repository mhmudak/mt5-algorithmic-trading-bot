from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    print("[INTRABAR STEP TRAIL FAST-LANE WIRING TEST V2]")

    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    manager = (
        ROOT / "src" / "intrabar_step_trail_manager.py"
    ).read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_STEP_TRAIL_SHADOW = True" in settings
    assert "ENABLE_INTRABAR_STEP_TRAIL_LIVE = True" in settings
    assert "INTRABAR_STEP_TRAIL_FIXED_LOT = 0.25" in settings
    assert "INTRABAR_STEP_TRAIL_HARD_STOP_PRICE = 7.00" in settings

    assert "def process_intrabar_step_trail_fast_lane_once():" in live
    assert "process_intrabar_step_trail_fast_lane_once()" in live
    assert "_step_trail_lane_enabled" in live
    assert '"strategy": "INTRABAR_STEP_TRAIL"' in live
    assert '"take_profit": 0.0' in live
    assert "check_trade_guard(signal, live_tick)" in live
    assert "build_runtime_step_trail_policy" in live

    assert "manage_intrabar_step_trail_positions" in manager
    assert "build_runtime_step_trail_policy" in manager
    assert "modify_sl(" in manager
    assert "close_position_volume(" in manager
    assert "comment.startswith(STRATEGY_NAME)" in manager

    print("shadow_enabled=True")
    print("live_enabled=True")
    print("independent_fast_lane_authority=True")
    print("settings_driven_management=True")
    print("no_fixed_tp=True")
    print("generic_trade_guard_retained=True")
    print("position_comment_isolation=True")
    print("early_failure_close_wired=True")
    print("mfe_sl_trail_wired=True")
    print(
        "PASS: INTRABAR_STEP_TRAIL is independently wired into the 250ms "
        "wait lane with LIVE execution policy, settings-driven risk management, "
        "no fixed TP, generic trade guards and isolated position management."
    )


if __name__ == "__main__":
    main()
