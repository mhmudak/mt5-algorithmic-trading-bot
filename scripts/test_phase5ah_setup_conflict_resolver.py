from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.setup_conflict_resolver import resolve_setup_conflict


def main() -> None:
    previous_buy = {
        "setup_id": "FAI-BUY-1785386706",
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "score": 100,
        "session": "ASIA",
        "type": "FAILED_BEARISH_FVG_REVERSAL",
        "entry": 4086.77,
        "sl": 4074.92,
        "tp": 4116.35,
        "rr": 2.5,
        "created_at": "2026-07-30T04:45:00",
        "state": "ENTRY_SKIPPED_WEAK_CONFIRMATION",
        "entry_skip_reason": "m5_body_too_small",
        "reason": (
            "Failed bearish FVG BUY -> bearish FVG 4076.92-4079.12 failed -> "
            "bullish displacement confirmed -> SMC ema_bullish,displacement,bullish_bos"
        ),
    }

    new_sell = {
        "setup_id": "MIC-SELL-8d786c56fb",
        "strategy": "MICRO_SR_SWEEP_RECLAIM",
        "signal": "SELL",
        "entry_model": "MICRO_RESISTANCE_SWEEP_RECLAIM",
        "session": "ASIA",
        "market": "PULLBACK_TREND",
        "score": 92,
        "min_required_score": 94,
        "entry": 4085.17,
        "sl": 4092.5,
        "tp": 4065.04,
        "rr": 2.75,
        "created_at": "2026-07-30T05:00:00",
        "state": "REJECTED_SCORE_TOO_LOW",
        "rejection_reason": "score_too_low 92/94",
        "daily_pivot_context": "PRICE_ABOVE_DAILY_PIVOT",
    }

    report = resolve_setup_conflict(previous_buy, new_sell)

    print("[PHASE 5AH SETUP CONFLICT RESOLVER TEST]")
    print(f"conflict_status = {report['conflict_status']}")
    print(f"conflict_detected = {report['conflict_detected']}")
    print(f"priority_conflict_review = {report['priority_conflict_review']}")
    print(f"trade_action = {report['trade_action']}")
    print(f"auto_trade_allowed = {report['auto_trade_allowed']}")
    print(f"previous_action = {report['previous_setup']['action']}")
    print(f"new_action = {report['new_setup']['action']}")
    print(f"time_gap_minutes = {report['conflict_metrics']['time_gap_minutes']}")
    print(f"entry_distance = {report['conflict_metrics']['entry_distance']}")
    print(f"daily_pivot_rule = {report['daily_pivot_rule']}")
    print(f"order_flow_rule = {report['order_flow_rule']}")
    print("")

    print(json.dumps(report, indent=2))

    assert report["conflict_detected"] is True
    assert report["priority_conflict_review"] is True
    assert report["conflict_status"] == "DIRECTIONAL_CONFLICT_SAME_ZONE_PRIORITY_REVIEW"
    assert report["trade_action"] == "WAIT_OR_MANUAL_REVIEW"
    assert report["auto_trade_allowed"] is False
    assert report["previous_setup"]["entry_quality_weakness"] is True
    assert report["new_setup"]["is_micro_sweep_reclaim"] is True
    assert report["daily_pivot_rule"] == "CONTEXT_ONLY_NOT_HARD_BLOCK"

    print("")
    print("[PASS] Phase 5AH resolver correctly detected your BUY vs SELL same-zone conflict.")


if __name__ == "__main__":
    main()