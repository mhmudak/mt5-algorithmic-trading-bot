from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_phase5p_event_driven_rithmic_watcher import (  # noqa: E402
    compute_rithmic_directional_alignment,
    format_telegram_message,
)


ACCOUNT_NAME = "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / ACCOUNT_NAME

REPORT_PATH = INTEL_DIR / "phase5r_rithmic_alignment_message_test_report.json"
SUMMARY_PATH = INTEL_DIR / "phase5r_rithmic_alignment_message_test_summary.txt"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_test_event(direction: str) -> dict[str, Any]:
    direction = direction.upper().strip()

    if direction not in {"BUY", "SELL"}:
        raise ValueError("direction must be BUY or SELL")

    if direction == "BUY":
        entry = 4000.0
        sl = 3992.0
        tp = 4016.0
    else:
        entry = 4000.0
        sl = 4008.0
        tp = 3984.0

    return {
        "event_type": "SYNTHETIC_PHASE5R_TEST_SETUP",
        "source_file": "PHASE5R_SYNTHETIC_TEST_ONLY",
        "code": "PHASE5R_SYNTHETIC_TEST",
        "status": "TEST_ONLY_NOT_REAL_SETUP",
        "grade": "MANUAL_REVIEW_TEST_ONLY",
        "strategy": "PHASE5R_RITHMIC_ALIGNMENT_TEST",
        "setup_id": f"PHASE5R_{direction}_TEST",
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": 2.0,
        "summary": "Synthetic test event only. Not a real setup. Do not trade.",
        "raw": {
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": 2.0,
            "warning": "SYNTHETIC_TEST_ONLY_NOT_REAL_MARKET_SIGNAL",
        },
    }


def metrics_for_case(direction: str, case: str) -> dict[str, Any]:
    direction = direction.upper().strip()
    case = case.lower().strip()

    if direction == "BUY":
        support_metrics = {
            "trade_count": 20,
            "spread": 1.0,
            "dom_available": True,
            "dom_bid_depth": 120,
            "dom_ask_depth": 60,
            "dom_depth_imbalance": 0.333,
            "delta": 18,
            "cumulative_delta": 42,
            "order_book_update_type": "SOLO",
        }

        against_metrics = {
            "trade_count": 20,
            "spread": 1.0,
            "dom_available": True,
            "dom_bid_depth": 40,
            "dom_ask_depth": 130,
            "dom_depth_imbalance": -0.529,
            "delta": -15,
            "cumulative_delta": -38,
            "order_book_update_type": "SOLO",
        }

    else:
        support_metrics = {
            "trade_count": 20,
            "spread": 1.0,
            "dom_available": True,
            "dom_bid_depth": 50,
            "dom_ask_depth": 140,
            "dom_depth_imbalance": -0.474,
            "delta": -22,
            "cumulative_delta": -55,
            "order_book_update_type": "SOLO",
        }

        against_metrics = {
            "trade_count": 20,
            "spread": 1.0,
            "dom_available": True,
            "dom_bid_depth": 150,
            "dom_ask_depth": 50,
            "dom_depth_imbalance": 0.5,
            "delta": 19,
            "cumulative_delta": 44,
            "order_book_update_type": "SOLO",
        }

    neutral_metrics = {
        "trade_count": 20,
        "spread": 1.0,
        "dom_available": True,
        "dom_bid_depth": 100,
        "dom_ask_depth": 100,
        "dom_depth_imbalance": 0.0,
        "delta": 0,
        "cumulative_delta": 0,
        "order_book_update_type": "SOLO",
    }

    if case == "supports":
        return support_metrics

    if case == "against":
        return against_metrics

    if case == "neutral":
        return neutral_metrics

    raise ValueError("case must be supports, against, neutral, or bad-quality")


def build_quality(direction: str, case: str) -> dict[str, Any]:
    case = case.lower().strip()

    if case == "bad-quality":
        overall_status = "RITHMIC_CONNECTED_BUT_DATA_QUALITY_BAD"
        all_quality_ok = False
        metrics = metrics_for_case(direction, "supports")
        quality_failures = ["trade_count_enough", "spread_reasonable", "two_sided_dom"]
    else:
        overall_status = "RITHMIC_DATA_QUALITY_VALIDATED_OBSERVE_ONLY"
        all_quality_ok = True
        metrics = metrics_for_case(direction, case)
        quality_failures = []

    validations = [
        {
            "symbol": "GCQ6",
            "status": overall_status,
            "hard_failures": [],
            "quality_failures": quality_failures,
            "metrics": metrics,
        },
        {
            "symbol": "MGCQ6",
            "status": overall_status,
            "hard_failures": [],
            "quality_failures": quality_failures,
            "metrics": metrics,
        },
    ]

    return {
        "phase": "PHASE_5R_SYNTHETIC_TEST_ONLY",
        "mode": "OBSERVE_ONLY",
        "overall_status": overall_status,
        "all_hard_ok": True,
        "all_quality_ok": all_quality_ok,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "validations": validations,
        "recommendation": "Synthetic test only. Do not trade.",
    }


def send_telegram(message: str) -> dict[str, Any]:
    from src.notifier import send_telegram_message

    result = send_telegram_message(message)

    return {
        "ok": result is not False,
        "response": str(result)[:300],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--case", choices=["supports", "against", "neutral", "bad-quality"], default="supports")
    parser.add_argument("--send-telegram", action="store_true")
    args = parser.parse_args()

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    event = build_test_event(args.direction)
    quality = build_quality(args.direction, args.case)
    alignment = compute_rithmic_directional_alignment([event], quality, quality_ok=quality["all_quality_ok"])

    message = format_telegram_message([event], quality)

    header = (
        "🧪 SYNTHETIC PHASE 5R TEST ONLY\n"
        "NOT A REAL SETUP. DO NOT TRADE.\n\n"
    )

    message = header + message

    send_result = None

    if args.send_telegram:
        send_result = send_telegram(message)

    report = {
        "phase": "PHASE_5R_RITHMIC_ALIGNMENT_MESSAGE_TEST",
        "updated_at": now_iso(),
        "mode": "OBSERVE_ONLY",
        "synthetic_test_only": True,
        "direction": args.direction,
        "case": args.case,
        "send_telegram": args.send_telegram,
        "send_result": send_result,
        "alignment": alignment,
        "message_preview": message,
        "trade_action": "NO_AUTO_TRADE",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "recommendation": "Use this only to verify Telegram wording and alignment logic.",
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 5R RITHMIC ALIGNMENT MESSAGE TEST]",
        f"updated_at = {report['updated_at']}",
        f"synthetic_test_only = {report['synthetic_test_only']}",
        f"direction = {args.direction}",
        f"case = {args.case}",
        f"send_telegram = {args.send_telegram}",
        f"trade_action = {report['trade_action']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        "",
        "[ALIGNMENT]",
        f"setup_direction = {alignment.get('setup_direction')}",
        f"alignment = {alignment.get('alignment')}",
        f"supports_setup = {alignment.get('supports_setup')}",
        f"against_setup = {alignment.get('against_setup')}",
        f"support_score = {alignment.get('support_score')}",
        f"against_score = {alignment.get('against_score')}",
        "",
        "[MESSAGE PREVIEW]",
        message,
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()