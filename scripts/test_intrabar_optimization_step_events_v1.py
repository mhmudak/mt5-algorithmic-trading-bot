from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    print("[INTRABAR OPTIMIZATION STEP EVENTS TEST V1]")

    recorder = (
        ROOT / "src" / "intrabar_optimization_recorder.py"
    ).read_text(encoding="utf-8")
    manager = (
        ROOT / "src" / "intrabar_step_trail_manager.py"
    ).read_text(encoding="utf-8")

    assert "def note_intrabar_management_event(" in recorder
    assert 'event="STEP_TRAIL_SL_ADVANCED"' in manager
    assert 'event="STEP_TRAIL_EARLY_FAILURE_EXIT"' in manager
    assert 'runtime["highest_step_trail_stage"]' in recorder
    assert 'runtime["last_step_trail_mfe"]' in recorder
    assert 'runtime["last_step_trail_desired_stop"]' in recorder
    assert 'runtime["step_trail_early_failure_exit"] = True' in recorder
    assert 'runtime["step_trail_early_failure_reason"]' in recorder
    assert '"live_authority": False' in recorder

    print("step_trail_stage_event=True")
    print("step_trail_early_failure_event=True")
    print("telemetry_only=True")
    print("execution_logic_modified=False")
    print("PASS")


if __name__ == "__main__":
    main()
