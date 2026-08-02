
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market_outlook_outcome_attribution import (
    build_phase6s_outcome_attribution_report,
    find_default_outcome_files,
    write_phase6s_outcome_attribution_report,
)


def main():
    parser = argparse.ArgumentParser(description="Run Phase 6S9 outlook outcome attribution report.")
    parser.add_argument(
        "--annotation-dir",
        default="data/reports/market_outlook/execution_annotations",
        help="Directory containing Phase 6S8 execution annotation JSONL files.",
    )
    parser.add_argument(
        "--outcome-path",
        action="append",
        default=None,
        help="Optional trade/setup outcome JSON file. Can be repeated.",
    )
    parser.add_argument(
        "--source-root",
        default="data",
        help="Root used to auto-discover trades.json and setup_outcomes.json when no outcome path is provided.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/reports/market_outlook/outcome_attribution",
        help="Directory where Phase 6S9 report files will be written.",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
        help="Minimum sample warning threshold for interpretation.",
    )

    args = parser.parse_args()

    outcome_paths = args.outcome_path
    if not outcome_paths:
        outcome_paths = find_default_outcome_files(args.source_root)

    report = build_phase6s_outcome_attribution_report(
        annotation_dir=args.annotation_dir,
        outcome_paths=outcome_paths,
        source_root=args.source_root,
        min_samples=args.min_samples,
    )

    written = write_phase6s_outcome_attribution_report(report, output_dir=args.output_dir)

    print(json.dumps({
        "phase": report["phase"],
        "decision_impact": report["decision_impact"],
        "can_execute": report["can_execute"],
        "can_block_trade": report["can_block_trade"],
        "can_modify_risk": report["can_modify_risk"],
        "counts": report["counts"],
        "written": written,
    }, indent=2, default=str))

    print("[DONE] Phase 6S9 outcome attribution report completed.")


if __name__ == "__main__":
    main()
