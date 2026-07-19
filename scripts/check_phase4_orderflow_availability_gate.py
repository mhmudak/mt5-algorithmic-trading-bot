import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

REPORT_PATH = INTEL_DIR / "phase4_orderflow_availability_gate_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_orderflow_availability_gate_summary.txt"


def main():
    from src.order_flow_adapter import get_order_flow_availability_gate

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    result = get_order_flow_availability_gate(symbol="XAUUSD")
    snapshot = result.get("snapshot", {})
    gate = result.get("gate", {})

    report = {
        "phase": "PHASE_4C_ORDERFLOW_AVAILABILITY_GATE",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot": snapshot,
        "gate": gate,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "ORDER_FLOW_BLOCKED_SAFE_DEFAULT"
            if not gate.get("can_influence_decision")
            else "MANUAL_REVIEW_REQUIRED_BEFORE_ANY_LIVE_USE"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4C ORDER-FLOW AVAILABILITY GATE]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision = {report['decision']}",
        "",
        "[SNAPSHOT]",
        f"provider = {snapshot.get('provider')}",
        f"available = {snapshot.get('available')}",
        f"status = {snapshot.get('status')}",
        f"data_quality = {snapshot.get('data_quality')}",
        "",
        "[GATE]",
        f"gate_status = {gate.get('gate_status')}",
        f"can_influence_decision = {gate.get('can_influence_decision')}",
        f"decision_impact = {gate.get('decision_impact')}",
        f"missing_required_metrics = {gate.get('missing_required_metrics')}",
        f"reason = {gate.get('reason')}",
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