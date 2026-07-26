from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_providers.rithmic_snapshot_adapter import (
    build_rithmic_provider_status,
    load_latest_rithmic_state,
    write_provider_status_text,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="GCQ6")
    parser.add_argument("--input-dir", default="data/order_flow/rithmic")
    parser.add_argument("--stale-after-seconds", type=int, default=30)
    parser.add_argument(
        "--output-json",
        default="data/order_flow/rithmic/phase5f_rithmic_provider_status.json",
    )
    parser.add_argument(
        "--output-txt",
        default="data/order_flow/rithmic/phase5f_rithmic_provider_status.txt",
    )
    args = parser.parse_args()

    snapshot_path = Path(args.input_dir) / f"{args.symbol}_phase5c_rithmic_state_latest.json"
    loaded = load_latest_rithmic_state(snapshot_path)

    snapshot = loaded.get("snapshot") if loaded.get("loaded") else None

    status = build_rithmic_provider_status(
        snapshot,
        snapshot_path=snapshot_path,
        stale_after_seconds=args.stale_after_seconds,
    )

    if not loaded.get("loaded"):
        status["load_error"] = loaded.get("error")

    output_json = Path(args.output_json)
    output_txt = Path(args.output_txt)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_txt.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    write_provider_status_text(status, output_txt)

    print("[DONE] Phase 5F Rithmic provider status built")
    print("symbol =", status.get("symbol"))
    print("provider_status =", status.get("provider_status"))
    print("decision_impact =", status.get("decision_impact"))
    print("can_influence_decision =", status.get("can_influence_decision"))
    print("login_ok =", status["connection"]["login_ok"])
    print("market_data_ok =", status["connection"]["market_data_ok"])
    print("dom_available =", status["adapter_metrics"]["dom_available"])
    print("delta =", status["adapter_metrics"]["delta"])
    print("cumulative_delta =", status["adapter_metrics"]["cumulative_delta"])
    print("dom_bid_depth =", status["adapter_metrics"]["dom_bid_depth"])
    print("dom_ask_depth =", status["adapter_metrics"]["dom_ask_depth"])
    print("warnings =", ", ".join(status.get("warnings") or []))
    print("output_json =", output_json)
    print("output_txt =", output_txt)


if __name__ == "__main__":
    main()
