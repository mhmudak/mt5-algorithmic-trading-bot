
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from src.market_outlook_advisory_runtime import maybe_send_runtime_outlook_advisory

from send_phase6s_market_outlook import send_telegram_message_safe


def load_setup_json(path: str | None, args: argparse.Namespace) -> dict[str, Any]:
    if path:
        p = Path(path)
        return json.loads(p.read_text(encoding="utf-8"))

    return {
        "setup_id": args.setup_id,
        "strategy": args.strategy,
        "signal": args.signal,
        "entry_reference": args.entry,
        "sl_reference": args.sl,
        "tp_reference": args.tp,
        "rr": args.rr,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--report-type", default="scenario_update")
    parser.add_argument("--setup-json", default=None)

    parser.add_argument("--setup-id", default="MANUAL-SETUP")
    parser.add_argument("--strategy", default="UNKNOWN")
    parser.add_argument("--signal", default="BUY", choices=["BUY", "SELL"])
    parser.add_argument("--entry", type=float, default=None)
    parser.add_argument("--sl", type=float, default=None)
    parser.add_argument("--tp", type=float, default=None)
    parser.add_argument("--rr", type=float, default=None)

    parser.add_argument("--enable-advisory", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--force-send", action="store_true")

    args = parser.parse_args()

    raw_setup = load_setup_json(args.setup_json, args)

    summary = maybe_send_runtime_outlook_advisory(
        raw_setup=raw_setup,
        symbol=args.symbol,
        report_type=args.report_type,
        enabled=args.enable_advisory,
        send_telegram=args.send_telegram,
        force_send=args.force_send,
        notifier=send_telegram_message_safe,
    )

    print("[PHASE 6S6 OUTLOOK ADVISORY RUNTIME HOOK]")
    print(f"ready = {summary.get('ready')}")
    print(f"enabled = {summary.get('enabled')}")
    print(f"symbol = {summary.get('symbol')}")
    print(f"report_type = {summary.get('report_type')}")
    print(f"risk_level = {summary.get('risk_level')}")
    print(f"alignment = {summary.get('alignment')}")
    print(f"advisory_fingerprint = {summary.get('advisory_fingerprint')}")
    print(f"should_notify = {summary.get('should_notify')}")
    print(f"send_telegram = {summary.get('send_telegram')}")
    print(f"telegram_sent = {summary.get('telegram_sent')}")
    print(f"state_file = {summary.get('state_file')}")
    print(f"reason = {summary.get('reason')}")
    print(f"decision_impact = {summary.get('decision_impact')}")
    print(f"auto_trade_allowed = {summary.get('auto_trade_allowed')}")
    print(f"can_execute = {summary.get('can_execute')}")
    print(f"can_block_trade = {summary.get('can_block_trade')}")
    print(f"can_modify_risk = {summary.get('can_modify_risk')}")

    result = summary.get("result") or {}

    if result.get("ready"):
        print("")
        print(result["message"])


if __name__ == "__main__":
    main()
