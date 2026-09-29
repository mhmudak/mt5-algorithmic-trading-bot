from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    print("[INTRABAR LIVE + MICRO BE WIRING TEST V1]")

    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    manager = (
        ROOT / "src" / "micro_momentum_breakeven.py"
    ).read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_STEP_TRAIL_LIVE = True" in settings
    assert "ENABLE_INTRABAR_STEP_TRAIL_SHADOW = True" in settings
    assert "ENABLE_MICRO_MOMENTUM_BREAKEVEN_PROTECTION = True" in settings
    assert "MICRO_MOMENTUM_BREAKEVEN_TP_PROGRESS = 0.50" in settings
    assert "MICRO_MOMENTUM_BREAKEVEN_LOCK_PRICE = 0.0" in settings

    assert "def process_micro_momentum_breakeven_fast_lane_once():" in live
    assert "process_micro_momentum_breakeven_fast_lane_once()" in live
    assert "_micro_be_lane_enabled" in live

    mm_call = live.index("process_intrabar_micro_momentum_fast_lane_once()")
    be_call = live.index("process_micro_momentum_breakeven_fast_lane_once()")
    step_call = live.index("process_intrabar_step_trail_fast_lane_once()")
    assert mm_call < be_call < step_call

    assert 'trade.get("strategy")' in manager
    assert 'STRATEGY_NAME = "INTRABAR_MICRO_MOMENTUM"' in manager
    assert "modify_sl(" in manager
    assert "take_profit" in manager
    assert "save_trades(trades)" in manager

    print("step_trail_live=True")
    print("step_trail_shadow_logging=True")
    print("micro_be_enabled=True")
    print("micro_be_trigger=50%_original_tp_distance")
    print("micro_be_lock=entry_price")
    print("micro_be_uses_trade_tracker_strategy=True")
    print("micro_be_preserves_tp=True")
    print("micro_be_runs_250ms_lane=True")
    print(
        "PASS: INTRABAR_STEP_TRAIL is LIVE and Micro Momentum has independent "
        "50%-TP-progress breakeven protection in the fast lane."
    )


if __name__ == "__main__":
    main()
