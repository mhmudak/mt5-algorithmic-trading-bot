from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.setup_selection_advisory import (
    build_setup_selection_shadow_snapshot,
    normalize_setup_selection_stage,
)
import src.setup_outcome_tracker as tracker


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[SETUP SELECTION SHADOW OUTCOME TEST V1]")

    print("\n[STAGE NORMALIZATION]")
    checks = {
        "SETUP_DETECTED": "DETECTED",
        "CANDIDATE_REJECTED_LOW_RR": "LOW_RR",
        "EXECUTION_SUCCESS": "EXECUTED",
        "CANDIDATE_REJECTED": "BLOCKED",
        "SOMETHING_NEW": "OTHER",
    }
    for event, expected in checks.items():
        actual = normalize_setup_selection_stage(event=event)
        print(f"{event} -> {actual}")
        assert_true(actual == expected, (event, actual, expected))

    snapshot = build_setup_selection_shadow_snapshot(
        strategy="FAILED_FVG_REVERSAL",
        direction="BUY",
        entry_model="FAILED_BULLISH_FVG_REVERSAL",
        session="NEWYORK",
        market_condition="RANGING",
        event="SETUP_DETECTED",
        account_name="Tickmill-Demo_25323531",
    )

    print("\n[DIRECT SNAPSHOT]")
    print(snapshot)
    assert_true(snapshot["schema_version"] == 1, snapshot)
    assert_true(snapshot["stage"] == "DETECTED", snapshot)
    assert_true(snapshot["live_authority"] is False, snapshot)
    assert_true(snapshot["decision_impact"] == "NONE", snapshot)
    assert_true("captured_at_utc" in snapshot, snapshot)
    assert_true(snapshot["badge"] != "NO_DATA", snapshot)

    # Isolate register_setup_outcome from disk and Google Sheets.
    memory = {}

    original_load = tracker.load_setup_outcomes
    original_save = tracker.save_setup_outcomes
    original_sheet = tracker.send_setup_outcome_to_google_sheets

    def fake_load():
        return copy.deepcopy(memory)

    def fake_save(items):
        memory.clear()
        memory.update(copy.deepcopy(items))

    def fake_sheet(_item):
        return True

    tracker.load_setup_outcomes = fake_load
    tracker.save_setup_outcomes = fake_save
    tracker.send_setup_outcome_to_google_sheets = fake_sheet

    try:
        setup_id = "SHADOW-OOS-TEST-1"

        first = tracker.register_setup_outcome(
            symbol="XAUUSD",
            setup_id=setup_id,
            event="SETUP_DETECTED",
            strategy="FAILED_FVG_REVERSAL",
            signal="BUY",
            entry_model="FAILED_BULLISH_FVG_REVERSAL",
            score=95,
            session="NEWYORK",
            market_condition="RANGING",
            entry=4300.0,
            sl=4295.0,
            tp=4310.0,
            reason="unit_test",
            extra={"source": "unit_test"},
        )
        assert_true(first is True, first)
        stored = memory[setup_id]
        frozen = copy.deepcopy(stored.get("setup_selection_shadow"))

        print("\n[FIRST REGISTRATION SHADOW]")
        print(frozen)
        assert_true(isinstance(frozen, dict), stored)
        assert_true(frozen.get("live_authority") is False, frozen)
        assert_true(frozen.get("decision_impact") == "NONE", frozen)
        assert_true(frozen.get("stage") == "DETECTED", frozen)

        # Re-register same setup ID under another tracked event. The outcome
        # tracker may add source_events, but the frozen selection snapshot must
        # remain byte-for-byte equivalent as a Python structure.
        second = tracker.register_setup_outcome(
            symbol="XAUUSD",
            setup_id=setup_id,
            event="CANDIDATE_REJECTED_LOW_RR",
            strategy="FAILED_FVG_REVERSAL",
            signal="BUY",
            entry_model="FAILED_BULLISH_FVG_REVERSAL",
            score=95,
            session="NEWYORK",
            market_condition="RANGING",
            entry=4300.0,
            sl=4295.0,
            tp=4310.0,
            reason="unit_test_second_event",
            extra={"source": "unit_test_second"},
        )
        assert_true(second is True, second)

        frozen_after = memory[setup_id].get("setup_selection_shadow")
        print("\n[AFTER SECOND REGISTRATION]")
        print(frozen_after)
        assert_true(frozen_after == frozen, (frozen_after, frozen))

    finally:
        tracker.load_setup_outcomes = original_load
        tracker.save_setup_outcomes = original_save
        tracker.send_setup_outcome_to_google_sheets = original_sheet

    print(
        "\nPASS: first-registration snapshot is versioned, advisory-only, "
        "stage-normalized, disk-isolated in test, and immutable across "
        "later setup events."
    )


if __name__ == "__main__":
    main()
