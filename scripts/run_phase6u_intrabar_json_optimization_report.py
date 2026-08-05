
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_json_optimization_report import (
    build_phase6u_intrabar_json_optimization_report,
    write_phase6u_intrabar_json_optimization_report,
)


def main():
    parser = argparse.ArgumentParser(description="Run Phase 6U intrabar JSON optimization report.")
    parser.add_argument(
        "--strategy-performance-report-path",
        default="data/strategy_intelligence/Tickmill-Demo_25323531/strategy_performance_report.json",
    )
    parser.add_argument(
        "--setup-outcomes-path",
        default="data/accounts/Tickmill-Demo_25323531/setup_outcomes.json",
    )
    parser.add_argument("--output-dir", default="data/reports/intrabar_json_optimization")
    parser.add_argument(
        "--allowed-strategy",
        action="append",
        default=["AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"],
    )
    parser.add_argument("--do-not-block-others", action="store_true")
    parser.add_argument("--no-write", action="store_true")

    args = parser.parse_args()

    report = build_phase6u_intrabar_json_optimization_report(
        strategy_performance_report_path=args.strategy_performance_report_path,
        setup_outcomes_path=args.setup_outcomes_path,
        allowed_strategies=args.allowed_strategy,
        block_others=not args.do_not_block_others,
    )

    written = None
    if not args.no_write:
        written = write_phase6u_intrabar_json_optimization_report(report, output_dir=args.output_dir)

    print(json.dumps({
        "phase": report["phase"],
        "decision_impact": report["decision_impact"],
        "can_execute": report["can_execute"],
        "can_block_trade": report["can_block_trade"],
        "can_modify_risk": report["can_modify_risk"],
        "can_modify_detection": report["can_modify_detection"],
        "input_files": report["input_files"],
        "user_rule": report["user_rule"],
        "counts": report["counts"],
        "by_recommended_action": report["by_recommended_action"],
        "by_strategy": report["by_strategy"],
        "keep_executing_preview": report["keep_executing"][:10],
        "block_or_disable_preview": report["block_or_disable"][:10],
        "written": written,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
