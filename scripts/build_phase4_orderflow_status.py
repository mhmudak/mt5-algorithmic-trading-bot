import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

REPORT_PATH = INTEL_DIR / "phase4_orderflow_status_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_orderflow_status_summary.txt"


def main():
    from src.order_flow_adapter import get_order_flow_snapshot

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    snapshot = get_order_flow_snapshot(symbol="XAUUSD")

    report = {
        "phase": "PHASE_4A_ORDERFLOW_STATUS",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "orderflow_snapshot": snapshot,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "CONNECT_REAL_COMEX_OR_FUTURES_DATA_PROVIDER_BEFORE_USING_ORDER_FLOW"
            if not snapshot.get("available")
            else "ORDER_FLOW_PROVIDER_AVAILABLE_OBSERVE_ONLY_REVIEW_REQUIRED"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4A ORDER-FLOW STATUS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision = {report['decision']}",
        "",
        "[PROVIDER]",
        f"provider = {snapshot.get('provider')}",
        f"available = {snapshot.get('available')}",
        f"status = {snapshot.get('status')}",
        f"data_quality = {snapshot.get('data_quality')}",
        f"decision_impact = {snapshot.get('decision_impact')}",
        "",
        "[WARNING]",
        snapshot.get("warning"),
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