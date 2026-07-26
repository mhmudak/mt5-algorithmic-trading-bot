from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_providers.rithmic_monitoring_bridge import (
    build_rithmic_monitoring_bridge,
    write_bridge_json,
    write_bridge_text,
)
from src.order_flow_providers.rithmic_snapshot_adapter import (
    build_rithmic_provider_status,
    load_latest_rithmic_state,
)


def _safe_symbol_for_file(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="GCQ6")
    parser.add_argument("--input-dir", default="data/order_flow/rithmic")
    parser.add_argument("--stale-after-seconds", type=int, default=30)
    parser.add_argument("--output-dir", default="data/order_flow/rithmic")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    snapshot_path = input_dir / f"{args.symbol}_phase5c_rithmic_state_latest.json"

    loaded = load_latest_rithmic_state(snapshot_path)
    snapshot = loaded.get("snapshot") if loaded.get("loaded") else None

    provider_status = build_rithmic_provider_status(
        snapshot,
        snapshot_path=snapshot_path,
        stale_after_seconds=args.stale_after_seconds,
    )

    if not loaded.get("loaded"):
        provider_status["load_error"] = loaded.get("error")

    bridge = build_rithmic_monitoring_bridge(provider_status)

    safe_symbol = _safe_symbol_for_file(args.symbol)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_json = output_dir / f"{safe_symbol}_phase5g_rithmic_monitoring_bridge.json"
    output_txt = output_dir / f"{safe_symbol}_phase5g_rithmic_monitoring_bridge.txt"

    write_bridge_json(bridge, output_json)
    write_bridge_text(bridge, output_txt)

    print("[DONE] Phase 5G Rithmic monitoring bridge built")
    print("symbol =", bridge.get("symbol"))
    print("bridge_status =", bridge.get("bridge_status"))
    print("provider_status =", bridge.get("provider_status"))
    print("decision_impact =", bridge.get("decision_impact"))
    print("can_influence_decision =", bridge.get("can_influence_decision"))
    print("adapter_metric_format_ready =", bridge["phase4_compatibility"]["adapter_metric_format_ready"])
    print("can_replace_no_order_flow_provider =", bridge["phase4_compatibility"]["can_replace_no_order_flow_provider"])
    print("delta =", bridge["adapter_metrics"]["delta"])
    print("cumulative_delta =", bridge["adapter_metrics"]["cumulative_delta"])
    print("dom_available =", bridge["adapter_metrics"]["dom_available"])
    print("dom_bid_depth =", bridge["adapter_metrics"]["dom_bid_depth"])
    print("dom_ask_depth =", bridge["adapter_metrics"]["dom_ask_depth"])
    print("warnings =", ", ".join(bridge.get("warnings") or []))
    print("output_json =", output_json)
    print("output_txt =", output_txt)


if __name__ == "__main__":
    main()
