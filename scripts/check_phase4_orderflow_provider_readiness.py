import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

ORDERFLOW_STATUS_PATH = INTEL_DIR / "phase4_orderflow_status_report.json"
ORDERFLOW_GATE_PATH = INTEL_DIR / "phase4_orderflow_availability_gate_report.json"
REPORT_PATH = INTEL_DIR / "phase4_orderflow_provider_readiness_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_orderflow_provider_readiness_summary.txt"


REQUIRED_REAL_ORDERFLOW_METRICS = [
    "bid_volume",
    "ask_volume",
    "delta",
    "cumulative_delta",
    "footprint_imbalance",
    "dom_bid_depth",
    "dom_ask_depth",
    "volume_profile_poc",
    "value_area_low",
    "value_area_high",
]


REQUIRED_PROVIDER_CAPABILITIES = [
    "REAL_FUTURES_OR_EXCHANGE_VOLUME",
    "BID_ASK_VOLUME_SPLIT",
    "FOOTPRINT_OR_VOLUME_AT_PRICE",
    "DOM_DEPTH_OR_MARKET_DEPTH",
    "TIMESTAMPED_SNAPSHOTS",
    "SYMBOL_MAPPING_XAUUSD_TO_FUTURES_CONTRACT",
    "OBSERVE_ONLY_VALIDATION_MODE",
]


def load_json(path):
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_nested(data, *keys, default=None):
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def setting_value(*names):
    try:
        import config.settings as settings
    except Exception:
        settings = None

    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value

    if settings is not None:
        for name in names:
            value = getattr(settings, name, None)
            if value not in (None, ""):
                return value

    return None


def masked_presence(value):
    if value in (None, ""):
        return False
    return True


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    status_report = load_json(ORDERFLOW_STATUS_PATH)
    gate_report = load_json(ORDERFLOW_GATE_PATH)

    snapshot = status_report.get("orderflow_snapshot") or status_report.get("snapshot") or {}
    gate = gate_report.get("gate") or {}

    provider_name = (
        setting_value("ORDER_FLOW_PROVIDER", "ORDERFLOW_PROVIDER")
        or snapshot.get("provider")
        or "NO_ORDER_FLOW_PROVIDER"
    )

    provider_api_url_present = masked_presence(
        setting_value("ORDER_FLOW_API_URL", "ORDERFLOW_API_URL", "ORDER_FLOW_BASE_URL")
    )

    provider_api_key_present = masked_presence(
        setting_value("ORDER_FLOW_API_KEY", "ORDERFLOW_API_KEY", "ORDER_FLOW_TOKEN")
    )

    provider_symbol = (
        setting_value("ORDER_FLOW_SYMBOL", "ORDERFLOW_SYMBOL")
        or "NOT_CONFIGURED"
    )

    provider_mode = (
        setting_value("ORDER_FLOW_MODE", "ORDERFLOW_MODE")
        or snapshot.get("mode")
        or "OBSERVE_ONLY"
    )

    metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), dict) else {}

    missing_metrics = [
        metric for metric in REQUIRED_REAL_ORDERFLOW_METRICS
        if metrics.get(metric) is None
    ]

    connected_to_real_provider = provider_name not in (
        None,
        "",
        "NO_ORDER_FLOW_PROVIDER",
        "BASE_PROVIDER",
    )

    readiness_blocks = []

    if not connected_to_real_provider:
        readiness_blocks.append("NO_REAL_ORDERFLOW_PROVIDER_SELECTED")

    if not provider_api_url_present:
        readiness_blocks.append("ORDER_FLOW_API_URL_NOT_CONFIGURED")

    if not provider_api_key_present:
        readiness_blocks.append("ORDER_FLOW_API_KEY_NOT_CONFIGURED")

    if provider_symbol == "NOT_CONFIGURED":
        readiness_blocks.append("ORDER_FLOW_SYMBOL_MAPPING_NOT_CONFIGURED")

    if provider_mode != "OBSERVE_ONLY":
        readiness_blocks.append("ORDER_FLOW_MODE_MUST_START_AS_OBSERVE_ONLY")

    if missing_metrics:
        readiness_blocks.append("REQUIRED_REAL_ORDERFLOW_METRICS_NOT_AVAILABLE")

    gate_status = gate.get("gate_status")
    can_influence_decision = bool(gate.get("can_influence_decision"))

    if can_influence_decision:
        readiness_blocks.append("SAFETY_GATE_SHOULD_NOT_ALLOW_DECISION_IMPACT_YET")

    if not connected_to_real_provider:
        readiness_status = "READY_TO_SELECT_PROVIDER_NOT_CONNECTED"
        next_step = "Choose a real provider with API access for futures/order-flow data."
    elif readiness_blocks:
        readiness_status = "PROVIDER_SELECTED_BUT_CONTRACT_INCOMPLETE"
        next_step = "Complete provider API config and required metrics mapping in observe-only mode."
    else:
        readiness_status = "PROVIDER_READY_FOR_OBSERVE_ONLY_VALIDATION"
        next_step = "Run provider feed in observe-only for validation before any live decision impact."

    report = {
        "phase": "PHASE_4Q_ORDERFLOW_PROVIDER_READINESS",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "provider_name": provider_name,
        "provider_mode": provider_mode,
        "provider_symbol": provider_symbol,
        "provider_api_url_present": provider_api_url_present,
        "provider_api_key_present": provider_api_key_present,
        "connected_to_real_provider": connected_to_real_provider,
        "required_real_orderflow_metrics": REQUIRED_REAL_ORDERFLOW_METRICS,
        "missing_required_metrics": missing_metrics,
        "required_provider_capabilities": REQUIRED_PROVIDER_CAPABILITIES,
        "orderflow_gate_status": gate_status,
        "orderflow_can_influence_decision": can_influence_decision,
        "readiness_blocks": readiness_blocks,
        "readiness_status": readiness_status,
        "next_step": next_step,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "warning": (
            "Do not use MT5 tick-volume proxy as real order flow. "
            "Real order-flow provider data must be validated in observe-only mode first."
        ),
        "recommendation": (
            "START_PROVIDER_SELECTION_AND_OBSERVE_ONLY_INTEGRATION"
            if readiness_status == "READY_TO_SELECT_PROVIDER_NOT_CONNECTED"
            else "COMPLETE_PROVIDER_CONTRACT_BEFORE_VALIDATION"
            if readiness_blocks
            else "RUN_PROVIDER_OBSERVE_ONLY_VALIDATION"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4Q ORDER-FLOW PROVIDER READINESS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"readiness_status = {report['readiness_status']}",
        f"provider_name = {report['provider_name']}",
        f"provider_mode = {report['provider_mode']}",
        f"provider_symbol = {report['provider_symbol']}",
        f"connected_to_real_provider = {report['connected_to_real_provider']}",
        f"provider_api_url_present = {report['provider_api_url_present']}",
        f"provider_api_key_present = {report['provider_api_key_present']}",
        "",
        "[ORDER FLOW GATE]",
        f"gate_status = {report['orderflow_gate_status']}",
        f"can_influence_decision = {report['orderflow_can_influence_decision']}",
        "",
        "[REQUIRED REAL ORDER-FLOW METRICS]",
    ]

    for metric in REQUIRED_REAL_ORDERFLOW_METRICS:
        state = "MISSING" if metric in missing_metrics else "AVAILABLE"
        lines.append(f"{metric} = {state}")

    lines += [
        "",
        "[READINESS BLOCKS]",
    ]

    if readiness_blocks:
        for block in readiness_blocks:
            lines.append(f"- {block}")
    else:
        lines.append("No readiness blocks detected.")

    lines += [
        "",
        "[REQUIRED PROVIDER CAPABILITIES]",
    ]

    for capability in REQUIRED_PROVIDER_CAPABILITIES:
        lines.append(f"- {capability}")

    lines += [
        "",
        "[NEXT STEP]",
        report["next_step"],
        "",
        "[WARNING]",
        report["warning"],
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