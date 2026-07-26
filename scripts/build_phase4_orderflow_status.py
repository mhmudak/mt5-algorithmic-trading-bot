import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

REPORT_PATH = INTEL_DIR / "phase4_orderflow_status_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_orderflow_status_summary.txt"


RITHMIC_DIR = ROOT / "data" / "order_flow" / "rithmic"


def _safe_symbol_for_file(symbol):
    return str(symbol).replace("/", "_").replace("\\", "_").replace(".", "_")


def _configured_rithmic_symbol():
    return os.getenv("RITHMIC_SYMBOL", "GCQ6")


def _load_rithmic_bridge():
    symbol = _configured_rithmic_symbol()
    path = RITHMIC_DIR / f"{_safe_symbol_for_file(symbol)}_phase5g_rithmic_monitoring_bridge.json"

    if not path.exists():
        return {
            "loaded": False,
            "symbol": symbol,
            "path": str(path),
            "bridge_status": "RITHMIC_BRIDGE_NOT_BUILT",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "warnings": ["PHASE5G_RITHMIC_BRIDGE_REPORT_NOT_FOUND"],
        }

    try:
        bridge = json.loads(path.read_text(encoding="utf-8"))
        bridge["loaded"] = True
        bridge["path"] = str(path)
        return bridge
    except Exception as exc:
        return {
            "loaded": False,
            "symbol": symbol,
            "path": str(path),
            "bridge_status": "RITHMIC_BRIDGE_READ_ERROR",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "warnings": [f"PHASE5G_RITHMIC_BRIDGE_READ_ERROR: {exc}"],
        }


def main():
    from src.order_flow_adapter import get_order_flow_snapshot

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    snapshot = get_order_flow_snapshot(symbol="XAUUSD")
    rithmic_bridge = _load_rithmic_bridge()

    report = {
        "phase": "PHASE_4A_ORDERFLOW_STATUS",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "orderflow_snapshot": snapshot,
        "rithmic_protocol_bridge": rithmic_bridge,
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
        "[RITHMIC PROTOCOL BRIDGE]",
        f"loaded = {rithmic_bridge.get('loaded')}",
        f"symbol = {rithmic_bridge.get('symbol')}",
        f"bridge_status = {rithmic_bridge.get('bridge_status')}",
        f"provider_status = {rithmic_bridge.get('provider_status')}",
        f"decision_impact = {rithmic_bridge.get('decision_impact')}",
        f"can_influence_decision = {rithmic_bridge.get('can_influence_decision')}",
        f"adapter_metric_format_ready = {(rithmic_bridge.get('phase4_compatibility') or {}).get('adapter_metric_format_ready')}",
        f"can_replace_no_order_flow_provider = {(rithmic_bridge.get('phase4_compatibility') or {}).get('can_replace_no_order_flow_provider')}",
        f"delta = {(rithmic_bridge.get('adapter_metrics') or {}).get('delta')}",
        f"cumulative_delta = {(rithmic_bridge.get('adapter_metrics') or {}).get('cumulative_delta')}",
        f"dom_available = {(rithmic_bridge.get('adapter_metrics') or {}).get('dom_available')}",
        f"dom_bid_depth = {(rithmic_bridge.get('adapter_metrics') or {}).get('dom_bid_depth')}",
        f"dom_ask_depth = {(rithmic_bridge.get('adapter_metrics') or {}).get('dom_ask_depth')}",
        "note = Rithmic bridge is observe-only and does not replace the Phase 4 no-order-flow gate yet.",
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