
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.notifier import send_telegram_message
from src.strategy_evidence_digest import (
    build_phase6t_strategy_evidence_digest,
    load_phase6t_strategy_evidence_dashboard,
    maybe_send_phase6t_strategy_evidence_digest,
    write_phase6t_strategy_evidence_digest,
)


def main():
    parser = argparse.ArgumentParser(description="Send Phase 6T2 strategy evidence digest.")
    parser.add_argument(
        "--dashboard-path",
        default="data/reports/strategy_evidence_dashboard/phase6t_strategy_evidence_dashboard_latest.json",
    )
    parser.add_argument("--output-dir", default="data/reports/strategy_evidence_digest")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--no-write", action="store_true")

    args = parser.parse_args()

    loaded = load_phase6t_strategy_evidence_dashboard(args.dashboard_path)
    dashboard = loaded.get("dashboard") or {}

    digest = build_phase6t_strategy_evidence_digest(dashboard, top_n=args.top_n)

    written = None
    if not args.no_write:
        written = write_phase6t_strategy_evidence_digest(digest, output_dir=args.output_dir)

    send_result = maybe_send_phase6t_strategy_evidence_digest(
        digest,
        send_telegram=bool(args.send_telegram),
        notifier=send_telegram_message,
    )

    print(json.dumps({
        "phase": digest["phase"],
        "decision_impact": digest["decision_impact"],
        "can_execute": digest["can_execute"],
        "can_block_trade": digest["can_block_trade"],
        "can_modify_risk": digest["can_modify_risk"],
        "dashboard_loaded": loaded.get("exists"),
        "dashboard_error": loaded.get("error"),
        "message_preview": digest["message"][:1000],
        "written": written,
        "send_result": send_result,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
