from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from src.market_outlook_advisory_bridge import (
    build_outlook_advisory_bridge_result,
    load_advisory_state,
    mark_advisory_sent,
    save_advisory_state,
    should_send_advisory,
)

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
    parser.add_argument("--force-send", action="store_true")

    args = parser.parse_args()

    setup = load_setup_json(args.setup_json, args)

    result = build_outlook_advisory_bridge_result(
        setup=setup,
        symbol=args.symbol,
        report_type=args.report_type,
    )

    telegram_sent = False
    should_notify = False
    state_file = None

    if result["ready"]:
        state = load_advisory_state(args.symbol, args.report_type)
        should_notify = should_send_advisory(
            state=state,
            fingerprint=result["advisory_fingerprint"],
            force_send=args.force_send,
        )

        if args.send_telegram and should_notify:
            telegram_sent = send_telegram_message_safe(result["message"])

            if telegram_sent:
                state = mark_advisory_sent(
                    state=state,
                    fingerprint=result["advisory_fingerprint"],
                    result=result,
                    sent_at=datetime.now(ZoneInfo("Asia/Beirut")).isoformat(timespec="seconds"),
                )

        state["last_checked_at"] = datetime.now(ZoneInfo("Asia/Beirut")).isoformat(timespec="seconds")
        state["last_ready"] = result["ready"]
        state["last_should_notify"] = should_notify
        state_file = save_advisory_state(args.symbol, args.report_type, state)

    print("[PHASE 6S5 OUTLOOK ADVISORY BRIDGE]")
    print(f"ready = {result.get('ready')}")
    print(f"symbol = {args.symbol}")
    print(f"report_type = {args.report_type}")
    print(f"risk_level = {result.get('risk_level')}")
    print(f"alignment = {result.get('alignment')}")
    print(f"advisory_fingerprint = {result.get('advisory_fingerprint')}")
    print(f"should_notify = {should_notify}")
    print(f"send_telegram = {args.send_telegram}")
    print(f"telegram_sent = {telegram_sent}")
    print(f"state_file = {state_file}")
    print(f"decision_impact = {result.get('decision_impact')}")
    print(f"auto_trade_allowed = {result.get('auto_trade_allowed')}")
    print(f"can_execute = {result.get('can_execute')}")
    print(f"can_block_trade = {result.get('can_block_trade')}")
    print(f"can_modify_risk = {result.get('can_modify_risk')}")

    if not result["ready"]:
        print(f"reason = {result.get('reason')}")
        return

    print("")
    print(result["message"])


if __name__ == "__main__":
    main()
