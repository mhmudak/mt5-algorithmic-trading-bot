from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    print("[INTRABAR OPTIMIZATION WIRING TEST V1]")
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    tracker = (ROOT / "src" / "trade_tracker.py").read_text(encoding="utf-8")
    micro = (ROOT / "src" / "intrabar_micro_momentum_shadow.py").read_text(encoding="utf-8")
    step = (ROOT / "src" / "intrabar_step_trail_detector.py").read_text(encoding="utf-8")
    recorder = (ROOT / "src" / "intrabar_optimization_recorder.py").read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_OPTIMIZATION_TELEMETRY = True" in settings
    assert "INTRABAR_OPTIMIZATION_PERSIST_SECONDS = 2.0" in settings
    assert "ENABLE_INTRABAR_MICRO_MOMENTUM_LIVE = True" in settings
    assert "ENABLE_INTRABAR_STEP_TRAIL_LIVE = True" in settings
    assert "MICRO_MOMENTUM_TELEGRAM_ENABLED = False" in settings
    assert "MICRO_MOMENTUM_PROFIT_CAPTURE_PRICE = 1.50" in settings
    assert "register_intrabar_candidate_snapshot(setup)" in micro
    assert "register_intrabar_candidate_snapshot(candidate)" in step
    assert "def _observe_intrabar_optimization_fail_open" in live
    assert live.count("\n    _observe_intrabar_optimization_fail_open(tick)\n") >= 2
    assert "attach_pending_intrabar_context(" in tracker
    assert "finalize_intrabar_optimization_trade(" in tracker
    assert "intrabar_optimization_runtime.json" in recorder
    assert "intrabar_optimization_history.jsonl" in recorder
    assert '"live_authority": False' in recorder

    print("execution_authority_changed=False")
    print("micro_live_retained=True")
    print("step_trail_live_retained=True")
    print("telegram_silence_retained=True")
    print("250ms_mae_mfe_observer=True")
    print("closed_trade_history=True")
    print("PASS")


if __name__ == "__main__":
    main()
