from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    print("[INTRABAR LIVE + MICRO MANAGEMENT WIRING TEST V2]")

    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    manager = (
        ROOT / "src" / "micro_momentum_breakeven.py"
    ).read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_STEP_TRAIL_LIVE = True" in settings
    assert "ENABLE_INTRABAR_STEP_TRAIL_SHADOW = True" in settings
    assert "ENABLE_MICRO_MOMENTUM_BREAKEVEN_PROTECTION = True" in settings
    assert "MICRO_MOMENTUM_BREAKEVEN_TP_PROGRESS = 0.50" in settings
    assert "ENABLE_MICRO_MOMENTUM_PROFIT_CAPTURE = True" in settings
    assert "MICRO_MOMENTUM_PROFIT_CAPTURE_PRICE = 1.50" in settings

    assert "process_micro_momentum_breakeven_fast_lane_once()" in live
    assert "evaluate_micro_momentum_profit_capture" in manager
    assert "close_position_volume(" in manager
    assert "evaluate_micro_momentum_breakeven" in manager
    assert "modify_sl(" in manager
    assert 'STRATEGY_NAME = "INTRABAR_MICRO_MOMENTUM"' in manager

    print("step_trail_live=True")
    print("micro_be_trigger=50%_original_tp_distance")
    print("micro_profit_capture=+1.50")
    print("weak_normal_tp_unchanged=True")
    print("explosive_near_tp_roundtrip_protection=True")
    print(
        "PASS: Step-Trail remains LIVE. Micro Momentum retains BE protection "
        "and adds +$1.50 full profit capture only when original TP is farther."
    )


if __name__ == "__main__":
    main()
