from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    import src.setup_conflict_memory as memory

    test_dir = ROOT / "data" / "strategy_intelligence" / "phase5ah_setup_conflicts_test"

    if test_dir.exists():
        shutil.rmtree(test_dir)

    test_dir.mkdir(parents=True, exist_ok=True)

    memory.DATA_DIR = test_dir
    memory.EVENTS_PATH = test_dir / "phase5ah_setup_state_events.json"
    memory.CONFLICTS_PATH = test_dir / "phase5ah_setup_conflicts.json"
    memory.CONFLICTS_JSONL_PATH = test_dir / "phase5ah_setup_conflicts.jsonl"
    memory.LATEST_CONFLICT_PATH = test_dir / "phase5ah_latest_setup_conflict.json"

    buy_detected = {
        "symbol": "XAUUSD",
        "setup_id": "TEST-FAI-BUY-1785386706",
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "score": 100,
        "session": "ASIA",
        "market_condition": "PULLBACK_TREND",
        "entry": 4086.77,
        "sl": 4074.92,
        "tp": 4116.35,
        "rr": 2.5,
        "state": "SETUP_DETECTED",
        "reason": "Failed bearish FVG BUY, bullish displacement confirmed",
        "created_at": "2026-07-30T04:45:00",
    }

    buy_extra_skipped = {
        "symbol": "XAUUSD",
        "setup_id": "TEST-FAI-BUY-1785386706",
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "score": 100,
        "session": "ASIA",
        "market_condition": "PULLBACK_TREND",
        "entry": 4086.77,
        "sl": 4074.92,
        "tp": 4116.35,
        "rr": 2.5,
        "state": "ENTRY_SKIPPED_WEAK_CONFIRMATION",
        "entry_skip_reason": "m5_body_too_small",
        "reason": "m5_body_too_small",
        "created_at": "2026-07-30T04:45:08",
    }

    sell_rejected = {
        "symbol": "XAUUSD",
        "setup_id": "TEST-MIC-SELL-8d786c56fb",
        "strategy": "MICRO_SR_SWEEP_RECLAIM",
        "signal": "SELL",
        "entry_model": "MICRO_RESISTANCE_SWEEP_RECLAIM",
        "score": 92,
        "min_required_score": 94,
        "session": "ASIA",
        "market_condition": "PULLBACK_TREND",
        "entry": 4085.17,
        "sl": 4092.5,
        "tp": 4065.04,
        "rr": 2.75,
        "state": "REJECTED_SCORE_TOO_LOW",
        "rejection_reason": "score_too_low 92/94",
        "reason": "score_too_low 92/94",
        "created_at": "2026-07-30T05:00:05",
    }

    r1 = memory.record_setup_state_event(buy_detected)
    r2 = memory.record_setup_state_event(buy_extra_skipped)
    r3 = memory.record_setup_state_event(sell_rejected)

    print("[PHASE 5AM SETUP CONFLICT MEMORY SEQUENCE TEST]")
    print(f"first_event_conflict = {bool(r1)}")
    print(f"second_event_conflict = {bool(r2)}")
    print(f"third_event_conflict = {bool(r3)}")

    if r3:
        print(f"conflict_status = {r3.get('conflict_status')}")
        print(f"priority_conflict_review = {r3.get('priority_conflict_review')}")
        print(f"trade_action = {r3.get('trade_action')}")
        print(f"duplicate_conflict = {r3.get('duplicate_conflict')}")
        print("")
        print(memory.format_conflict_telegram_message(r3))
        print("")
        print(json.dumps(r3, indent=2))

    events = json.loads(memory.EVENTS_PATH.read_text(encoding="utf-8"))
    conflicts = json.loads(memory.CONFLICTS_PATH.read_text(encoding="utf-8"))

    assert len(events) == 3
    assert len(conflicts) == 1
    assert r3 is not None
    assert r3["conflict_status"] == "DIRECTIONAL_CONFLICT_SAME_ZONE_PRIORITY_REVIEW"
    assert r3["priority_conflict_review"] is True
    assert r3["auto_trade_allowed"] is False
    assert r3["decision_impact"] == "NONE"
    assert r3["strategy_family_matrix"]["priority_policy"] == "STRICT_OPPOSING_ENTRY_WEAKNESS_REQUIRED_OBSERVE_ONLY"

    print("")
    print("[PASS] Phase 5AM live memory sequence detects the real-style conflict safely.")


if __name__ == "__main__":
    main()