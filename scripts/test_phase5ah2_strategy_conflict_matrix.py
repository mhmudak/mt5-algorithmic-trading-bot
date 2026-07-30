from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.setup_conflict_resolver import resolve_setup_conflict


def run_case(name, previous_setup, new_setup):
    report = resolve_setup_conflict(previous_setup, new_setup)

    matrix = report["strategy_family_matrix"]

    print("")
    print(f"[CASE] {name}")
    print(f"conflict_status = {report['conflict_status']}")
    print(f"priority_conflict_review = {report['priority_conflict_review']}")
    print(f"trade_action = {report['trade_action']}")
    print(f"pair = {matrix['pair']}")
    print(f"rule = {matrix['rule']}")
    print(f"priority_side = {matrix['priority_side']}")
    print(json.dumps(report, indent=2))

    return report


def main() -> None:
    # Your real case.
    previous_buy = {
        "setup_id": "FAI-BUY-1785386706",
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "score": 100,
        "entry": 4086.77,
        "sl": 4074.92,
        "tp": 4116.35,
        "rr": 2.5,
        "created_at": "2026-07-30T04:45:00",
        "state": "ENTRY_SKIPPED_WEAK_CONFIRMATION",
        "entry_skip_reason": "m5_body_too_small",
    }

    new_sell = {
        "setup_id": "MIC-SELL-8d786c56fb",
        "strategy": "MICRO_SR_SWEEP_RECLAIM",
        "signal": "SELL",
        "entry_model": "MICRO_RESISTANCE_SWEEP_RECLAIM",
        "score": 92,
        "min_required_score": 94,
        "entry": 4085.17,
        "sl": 4092.5,
        "tp": 4065.04,
        "rr": 2.75,
        "created_at": "2026-07-30T05:00:00",
        "state": "REJECTED_SCORE_TOO_LOW",
        "rejection_reason": "score_too_low 92/94",
    }

    report_1 = run_case("FAILED_FVG_BUY_vs_MICRO_SWEEP_SELL", previous_buy, new_sell)

    assert report_1["conflict_detected"] is True
    assert report_1["priority_conflict_review"] is True
    assert report_1["strategy_family_matrix"]["pair"] == "FAILED_FVG_REVERSAL_VS_SWEEP_RECLAIM"
    assert report_1["strategy_family_matrix"]["priority_side"] == "NEW_SETUP"

    # Generic conflict: should detect conflict but not priority-promote yet.
    previous_break = {
        "setup_id": "KEY-BUY-TEST",
        "strategy": "KEY_LEVEL_BREAK_HOLD",
        "signal": "BUY",
        "score": 94,
        "entry": 4080.0,
        "rr": 1.8,
        "created_at": "2026-07-30T10:00:00",
        "state": "SETUP_DETECTED",
    }

    new_ob = {
        "setup_id": "OB-SELL-TEST",
        "strategy": "MTF_OB_ENTRY",
        "signal": "SELL",
        "score": 93,
        "entry": 4079.2,
        "rr": 2.0,
        "created_at": "2026-07-30T10:15:00",
        "state": "SETUP_DETECTED",
    }

    report_2 = run_case("BREAK_HOLD_BUY_vs_ORDER_BLOCK_SELL", previous_break, new_ob)

    assert report_2["conflict_detected"] is True
    assert report_2["priority_conflict_review"] is False
    assert report_2["conflict_status"] == "DIRECTIONAL_CONFLICT_SAME_ZONE"
    assert report_2["trade_action"] == "WAIT"

    # Prior micro sweep remains important if later opposite setup appears.
    previous_micro = {
        "setup_id": "MIC-SELL-PRIOR",
        "strategy": "MICRO_SR_SWEEP_RECLAIM",
        "signal": "SELL",
        "entry_model": "MICRO_RESISTANCE_SWEEP_RECLAIM",
        "score": 92,
        "min_required_score": 94,
        "entry": 4085.0,
        "rr": 2.8,
        "created_at": "2026-07-30T05:00:00",
        "state": "REJECTED_SCORE_TOO_LOW",
        "rejection_reason": "score_too_low 92/94",
    }

    new_fvg = {
        "setup_id": "FAI-BUY-LATER",
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "score": 96,
        "entry": 4086.0,
        "rr": 2.2,
        "created_at": "2026-07-30T05:15:00",
        "state": "SETUP_DETECTED",
    }

    report_3 = run_case("PRIOR_MICRO_SWEEP_SELL_vs_FAILED_FVG_BUY", previous_micro, new_fvg)

    assert report_3["conflict_detected"] is True
    assert report_3["priority_conflict_review"] is True
    assert report_3["strategy_family_matrix"]["pair"] == "SWEEP_RECLAIM_VS_FAILED_FVG_REVERSAL"
    assert report_3["strategy_family_matrix"]["priority_side"] == "PREVIOUS_SETUP"

    print("")
    print("[PASS] Phase 5AH2 strategy conflict matrix works.")


if __name__ == "__main__":
    main()