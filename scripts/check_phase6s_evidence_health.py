
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market_outlook_evidence_health import (
    build_phase6s_evidence_health_report,
    write_phase6s_evidence_health_report,
)


def main():
    parser = argparse.ArgumentParser(description="Check Phase 6S evidence collection health.")
    parser.add_argument("--settings-path", default="config/settings.py")
    parser.add_argument("--annotation-dir", default="data/reports/market_outlook/execution_annotations")
    parser.add_argument(
        "--latest-attribution-path",
        default="data/reports/market_outlook/outcome_attribution/phase6s_outcome_attribution_latest.json",
    )
    parser.add_argument("--output-dir", default="data/reports/market_outlook/evidence_health")
    parser.add_argument("--no-write", action="store_true")

    args = parser.parse_args()

    report = build_phase6s_evidence_health_report(
        settings_path=args.settings_path,
        annotation_dir=args.annotation_dir,
        latest_attribution_path=args.latest_attribution_path,
    )

    written = None

    if not args.no_write:
        written = write_phase6s_evidence_health_report(report, output_dir=args.output_dir)

    print(json.dumps({
        "phase": report["phase"],
        "health_status": report["health_status"],
        "decision_impact": report["decision_impact"],
        "can_execute": report["can_execute"],
        "can_block_trade": report["can_block_trade"],
        "can_modify_risk": report["can_modify_risk"],
        "settings": report["settings"],
        "annotation_count": report["annotations"]["annotations"],
        "annotation_tags": report["annotations"]["tags"],
        "latest_attribution_counts": report["latest_attribution"].get("counts"),
        "written": written,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
