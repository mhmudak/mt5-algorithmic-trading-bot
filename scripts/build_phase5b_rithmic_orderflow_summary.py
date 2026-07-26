from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_features.rithmic_summary import (
    build_rithmic_orderflow_summary,
    find_rithmic_jsonl_files,
    load_jsonl_events,
    write_summary_text,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/order_flow/rithmic")
    parser.add_argument("--symbol", default="GCQ6")
    parser.add_argument("--all-files", action="store_true")
    parser.add_argument("--tick-size", type=float, default=0.1)
    parser.add_argument("--bucket-seconds", type=int, default=60)
    parser.add_argument("--top-levels", type=int, default=20)
    parser.add_argument(
        "--output-json",
        default="data/order_flow/rithmic/phase5b_rithmic_orderflow_summary.json",
    )
    parser.add_argument(
        "--output-txt",
        default="data/order_flow/rithmic/phase5b_rithmic_orderflow_summary.txt",
    )

    args = parser.parse_args()

    files = find_rithmic_jsonl_files(
        args.input_dir,
        symbol=args.symbol,
        latest_only=not args.all_files,
    )

    if not files:
        raise SystemExit(f"[STOP] No Rithmic JSONL files found for symbol={args.symbol} in {args.input_dir}")

    events, skipped = load_jsonl_events(files)

    summary = build_rithmic_orderflow_summary(
        events,
        symbol=args.symbol,
        exchange=None,
        tick_size=args.tick_size,
        bucket_seconds=args.bucket_seconds,
        top_levels=args.top_levels,
    )

    summary["input_files"] = [str(p) for p in files]
    summary["skipped_bad_json_lines"] = skipped

    output_json = Path(args.output_json)
    output_txt = Path(args.output_txt)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_txt.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary_text(summary, output_txt)

    print("[DONE] Phase 5B Rithmic order-flow summary built")
    print("[INPUT FILES]")
    for p in files:
        print(" -", p)

    print("")
    print("[SUMMARY]")
    print("symbol =", summary.get("symbol"))
    print("quality_status =", summary["quality"]["quality_status"])
    print("decision_impact =", summary.get("decision_impact"))
    print("last_trade_count =", summary["sample"]["last_trade_count"])
    print("buy_volume =", summary["trade_flow"]["buy_volume"])
    print("sell_volume =", summary["trade_flow"]["sell_volume"])
    print("delta =", summary["trade_flow"]["delta"])
    print("cumulative_delta =", summary["trade_flow"]["cumulative_delta"])
    print("poc_price =", summary["volume_profile"]["poc_price"])
    print("footprint_candle_count =", summary["footprint"]["candle_count"])
    print("output_json =", output_json)
    print("output_txt =", output_txt)


if __name__ == "__main__":
    main()
