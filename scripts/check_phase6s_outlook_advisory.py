
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

from src.market_outlook_advisor import (
    evaluate_setup_against_outlook,
    format_outlook_advisory_telegram,
)

from src.market_outlook_engine import load_latest_market_outlook

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

    parser.add_argument("--send-telegram", action="store_true")

    args = parser.parse_args()

    outlook = load_latest_market_outlook(args.symbol, args.report_type)

    if not outlook:
        raise SystemExit(
            f"[STOP] No latest outlook found for {args.symbol} {args.report_type}. "
            f"Run watch_phase6s_market_outlook_changes.py first."
        )

    setup = load_setup_json(args.setup_json, args)
    advisory = evaluate_setup_against_outlook(setup, outlook)
    message = format_outlook_advisory_telegram(advisory)

    telegram_sent = False

    if args.send_telegram:
        telegram_sent = send_telegram_message_safe(message)

    print("[PHASE 6S4 OUTLOOK ADVISORY]")
    print(f"symbol = {args.symbol}")
    print(f"report_type = {args.report_type}")
    print(f"setup_direction = {advisory['setup_direction']}")
    print(f"alignment = {advisory['alignment']}")
    print(f"risk_level = {advisory['risk_level']}")
    print(f"send_telegram = {args.send_telegram}")
    print(f"telegram_sent = {telegram_sent}")
    print(f"decision_impact = {advisory['decision_impact']}")
    print(f"auto_trade_allowed = {advisory['auto_trade_allowed']}")
    print(f"can_block_trade = {advisory['can_block_trade']}")
    print("")
    print(message)


if __name__ == "__main__":
    main()
