
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategy_evidence_dashboard import (
    build_phase6t_strategy_evidence_dashboard,
    write_phase6t_strategy_evidence_dashboard,
)


def main():
    parser = argparse.ArgumentParser(description="Run Phase 6T1 strategy evidence dashboard.")
    parser.add_argument(
        "--attribution-report-path",
        default="data/reports/market_outlook/outcome_attribution/phase6s_outcome_attribution_latest.json",
    )
    parser.add_argument("--output-dir", default="data/reports/strategy_evidence_dashboard")
    parser.add_argument("--min-matched-samples", type=int, default=5)
    parser.add_argument("--promising-min-win-rate", type=float, default=55.0)
    parser.add_argument("--weak-max-win-rate", type=float, default=40.0)
    parser.add_argument("--no-write", action="store_true")

    args = parser.parse_args()

    dashboard = build_phase6t_strategy_evidence_dashboard(
        attribution_report_path=args.attribution_report_path,
        min_matched_samples=args.min_matched_samples,
        promising_min_win_rate=args.promising_min_win_rate,
        weak_max_win_rate=args.weak_max_win_rate,
    )

    written = None

    if not args.no_write:
        written = write_phase6t_strategy_evidence_dashboard(dashboard, output_dir=args.output_dir)

    print(json.dumps({
        "phase": dashboard["phase"],
        "decision_impact": dashboard["decision_impact"],
        "can_execute": dashboard["can_execute"],
        "can_block_trade": dashboard["can_block_trade"],
        "can_modify_risk": dashboard["can_modify_risk"],
        "can_modify_strategy_policy": dashboard["can_modify_strategy_policy"],
        "source": dashboard["source"],
        "classification_counts": dashboard["classification_counts"],
        "strategy_rows": len(dashboard["strategy_rows"]),
        "strategy_tag_rows": len(dashboard["strategy_tag_rows"]),
        "tag_rows": len(dashboard["tag_rows"]),
        "written": written,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
