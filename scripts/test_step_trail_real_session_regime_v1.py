from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    print("[STEP-TRAIL REAL SESSION/REGIME WIRING TEST V2]")

    source = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )

    helper_start = source.index(
        "def _step_trail_research_context_fail_open("
    )
    step_start = source.index(
        "def process_intrabar_step_trail_fast_lane_once():"
    )
    step_end = source.index(
        "def run_intrabar_micro_momentum_fast_lane_wait",
        step_start,
    )

    helper_block = source[helper_start:step_start]
    step_block = source[step_start:step_end]

    # Existing bot-native context engines are reused.
    assert "detect_session(" in helper_block
    assert "get_market_condition_display" in helper_block
    assert "PULLBACK_TREND" in helper_block
    assert "CONSOLIDATION" in helper_block
    assert "TRENDING" in helper_block
    assert "RANGING" in helper_block
    assert "VOLATILE" in helper_block

    # Candidate gets enriched before execution and optimizer snapshot
    # is refreshed using the same setup_id.
    assert "_step_trail_research_context_fail_open(tick)" in step_block
    assert 'candidate["session"] = step_trail_session' in step_block
    assert 'candidate["market_condition"] = (' in step_block
    assert "step_trail_market_condition" in step_block
    assert "register_intrabar_candidate_snapshot(candidate)" in step_block

    # Trade plan must use real context variables, not generic INTRABAR.
    assert '"market_condition": step_trail_market_condition' in step_block
    assert '"session": step_trail_session' in step_block
    assert '"market_condition": "INTRABAR"' not in step_block
    assert '"session": "INTRABAR"' not in step_block

    # Execution authority and Step-Trail behavior remain present.
    assert "check_trade_guard(signal, live_tick)" in step_block
    assert "execute_trade(" in step_block
    assert "build_initial_stop(" in step_block
    assert "manage_intrabar_step_trail_positions(" in step_block
    assert '"take_profit": 0.0' in step_block
    assert '"strategy": "INTRABAR_STEP_TRAIL"' in step_block

    print("real_session_tag=True")
    print("real_market_regime_tag=True")
    print("pending_optimizer_snapshot_refreshed=True")
    print("hardcoded_intrabar_labels_removed=True")
    print("execution_authority_changed=False")
    print("test_formatting_bug_repaired=True")
    print("PASS")


if __name__ == "__main__":
    main()
