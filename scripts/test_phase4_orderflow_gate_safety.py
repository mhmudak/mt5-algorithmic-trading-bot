import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"
REPORT_PATH = INTEL_DIR / "phase4_orderflow_gate_safety_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_orderflow_gate_safety_summary.txt"


def complete_metrics():
    return {
        "bid_volume": 1000,
        "ask_volume": 1200,
        "delta": 200,
        "cumulative_delta": 5000,
        "footprint_imbalance": 1.4,
        "dom_bid_depth": 800,
        "dom_ask_depth": 900,
        "volume_profile_poc": 4029.5,
        "value_area_high": 4105.5,
        "value_area_low": 4005.0,
    }


def run_case(name, snapshot, expected_can_influence):
    from src.order_flow_adapter import evaluate_order_flow_availability

    gate = evaluate_order_flow_availability(snapshot)
    actual = gate.get("can_influence_decision")

    return {
        "case": name,
        "expected_can_influence_decision": expected_can_influence,
        "actual_can_influence_decision": actual,
        "ok": actual == expected_can_influence,
        "gate_status": gate.get("gate_status"),
        "decision_impact": gate.get("decision_impact"),
        "reason": gate.get("reason"),
        "missing_required_metrics": gate.get("missing_required_metrics"),
    }


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    cases = [
        run_case(
            "no_real_provider",
            {
                "mode": "OBSERVE_ONLY",
                "provider": "NO_ORDER_FLOW_PROVIDER",
                "available": False,
                "status": "NOT_CONNECTED",
                "data_quality": "UNAVAILABLE",
                "metrics": {},
            },
            False,
        ),
        run_case(
            "provider_unavailable",
            {
                "mode": "OBSERVE_ONLY",
                "provider": "REAL_PROVIDER_PLACEHOLDER",
                "available": False,
                "status": "DISCONNECTED",
                "data_quality": "REALTIME",
                "metrics": complete_metrics(),
            },
            False,
        ),
        run_case(
            "bad_data_quality",
            {
                "mode": "OBSERVE_ONLY",
                "provider": "REAL_PROVIDER_PLACEHOLDER",
                "available": True,
                "status": "CONNECTED",
                "data_quality": "SIMULATED",
                "metrics": complete_metrics(),
            },
            False,
        ),
        run_case(
            "missing_required_metrics",
            {
                "mode": "OBSERVE_ONLY",
                "provider": "REAL_PROVIDER_PLACEHOLDER",
                "available": True,
                "status": "CONNECTED",
                "data_quality": "REALTIME",
                "metrics": {
                    "delta": 200,
                    "cumulative_delta": 5000,
                },
            },
            False,
        ),
        run_case(
            "complete_realtime_but_observe_only",
            {
                "mode": "OBSERVE_ONLY",
                "provider": "REAL_PROVIDER_PLACEHOLDER",
                "available": True,
                "status": "CONNECTED",
                "data_quality": "REALTIME",
                "metrics": complete_metrics(),
            },
            False,
        ),
        run_case(
            "complete_realtime_but_live_mode_still_review_required",
            {
                "mode": "LIVE_DECISION",
                "provider": "REAL_PROVIDER_PLACEHOLDER",
                "available": True,
                "status": "CONNECTED",
                "data_quality": "REALTIME",
                "metrics": complete_metrics(),
            },
            False,
        ),
    ]

    all_ok = all(case["ok"] for case in cases)

    report = {
        "phase": "PHASE_4F_ORDERFLOW_GATE_SAFETY_TESTS",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "all_ok": all_ok,
        "cases": cases,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "ORDER_FLOW_GATE_SAFETY_OK"
            if all_ok
            else "FIX_ORDER_FLOW_GATE_IMMEDIATELY"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4F ORDER-FLOW GATE SAFETY TESTS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"all_ok = {report['all_ok']}",
        "",
        "[CASES]",
    ]

    for case in cases:
        lines.append(
            f"{case['case']} | ok={case['ok']} | "
            f"can_influence={case['actual_can_influence_decision']} | "
            f"gate_status={case['gate_status']}"
        )

    lines += [
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