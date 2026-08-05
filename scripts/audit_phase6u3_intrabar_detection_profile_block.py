from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_detection_profile_audit import build_phase6u3_settings_audit, write_phase6u3_audit_report


def main():
    parser = argparse.ArgumentParser(description="Audit Phase 6U3 intrabar detection profile hard block.")
    parser.add_argument("--output-dir", default="data/reports/intrabar_detection_profile_audit")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    report = build_phase6u3_settings_audit()
    written = None
    if not args.no_write:
        written = write_phase6u3_audit_report(report, output_dir=args.output_dir)

    print(json.dumps({
        "phase": report["phase"],
        "decision_impact": report["decision_impact"],
        "can_execute": report["can_execute"],
        "can_block_trade": report["can_block_trade"],
        "can_modify_risk": report["can_modify_risk"],
        "can_modify_detection": report["can_modify_detection"],
        "settings_flags": report.get("settings_flags"),
        "settings_pass": report.get("settings_pass"),
        "profile_list_found": report["profile_list_found"],
        "status": report["status"],
        "pass": report["pass"],
        "profile_count": report["profile_count"],
        "allowed_strategies": report["allowed_strategies"],
        "blocked_examples": report["blocked_examples"],
        "detected_strategy_names": report["detected_strategy_names"],
        "blocked_profiles_remaining": report["blocked_profiles_remaining"],
        "unknown_profiles_remaining": report["unknown_profiles_remaining"],
        "written": written,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
