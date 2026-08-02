
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from src.market_outlook_change_detector import (
    detect_outlook_changes,
    format_outlook_change_telegram,
    outlook_watch_snapshot,
)

from src.market_outlook_engine import (
    build_market_outlook,
    format_market_outlook_telegram,
    save_market_outlook,
)

from send_phase6s_market_outlook import (
    ensure_likely_scenarios_heading,
    fetch_market_frames,
    load_news_events,
    send_telegram_message_safe,
)


STATE_DIR = Path("data/reports/market_outlook/watch_state")


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


def state_path(symbol: str, report_type: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{_safe_symbol(symbol)}_{report_type.lower()}_watch_state.json"


def load_state(symbol: str, report_type: str) -> dict[str, Any]:
    path = state_path(symbol, report_type)

    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(symbol: str, report_type: str, state: dict[str, Any]) -> Path:
    path = state_path(symbol, report_type)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.symbol, args.report_type)

    # In live Telegram mode, compare against the last successfully notified snapshot
    # so failed sends can be retried.
    # In dry-run mode, compare against last checked snapshot so local testing is stable.
    if args.send_telegram:
        previous_snapshot = state.get("last_notified_snapshot")
    else:
        previous_snapshot = state.get("last_checked_snapshot")

    frames = fetch_market_frames(args.symbol)
    news_events = load_news_events(args.news_events_json)

    outlook = build_market_outlook(
        frames,
        report_type=args.report_type,
        symbol=args.symbol,
        generated_at=datetime.now(),
        news_events=news_events,
    )

    report_path = save_market_outlook(outlook)

    change = detect_outlook_changes(
        previous_snapshot,
        outlook,
        score_delta_threshold=args.score_delta_threshold,
    )

    full_outlook_message = ensure_likely_scenarios_heading(
        format_market_outlook_telegram(outlook)
    )

    change_message = format_outlook_change_telegram(outlook, change)

    if args.include_full_outlook:
        message = change_message + "\n\n" + full_outlook_message
    else:
        message = change_message

    should_notify = bool(args.force_send or change.get("changed"))
    telegram_sent = False

    if args.send_telegram and should_notify:
        telegram_sent = send_telegram_message_safe(message)

    current_snapshot = outlook_watch_snapshot(outlook)

    state["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_checked_snapshot"] = current_snapshot
    state["last_report_path"] = str(report_path)
    state["last_change"] = change

    if args.send_telegram and should_notify and telegram_sent:
        state["last_notified_at"] = datetime.now().isoformat(timespec="seconds")
        state["last_notified_snapshot"] = current_snapshot

    state_file = save_state(args.symbol, args.report_type, state)

    result = {
        "phase": "PHASE_6S2_SCENARIO_CHANGE_WATCHER",
        "symbol": args.symbol,
        "report_type": args.report_type,
        "changed": change.get("changed"),
        "severity": change.get("severity"),
        "reasons": change.get("reasons"),
        "should_notify": should_notify,
        "send_telegram": args.send_telegram,
        "telegram_sent": telegram_sent,
        "report_path": str(report_path),
        "state_file": str(state_file),
        "decision_impact": "NONE",
        "auto_trade_allowed": False,
        "can_execute": False,
    }

    print("[PHASE 6S2 SCENARIO CHANGE WATCHER]")
    for key, value in result.items():
        print(f"{key} = {value}")

    print("")
    print(message)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--report-type", default="scenario_update", choices=["daily", "weekly", "ny_update", "scenario_update"])
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--score-delta-threshold", type=int, default=10)
    parser.add_argument("--news-events-json", default=None)
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--force-send", action="store_true")
    parser.add_argument("--include-full-outlook", action="store_true")
    parser.add_argument("--loop", action="store_true")

    args = parser.parse_args()

    if not args.loop:
        run_once(args)
        return

    started = time.time()

    while True:
        run_once(args)

        if args.duration_seconds > 0 and (time.time() - started) >= args.duration_seconds:
            break

        time.sleep(max(60, args.interval_seconds))


if __name__ == "__main__":
    main()
