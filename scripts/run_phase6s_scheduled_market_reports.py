
from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

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


PHASE = "PHASE_6S3_SCHEDULED_MARKET_OUTLOOK_REPORTS"
DEFAULT_TIMEZONE = "Asia/Beirut"
STATE_DIR = Path("data/reports/market_outlook/schedule_state")


def parse_hhmm(value: str) -> dt_time:
    parts = str(value).strip().split(":")

    if len(parts) != 2:
        raise ValueError(f"Invalid HH:MM time: {value}")

    hour = int(parts[0])
    minute = int(parts[1])

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid HH:MM time: {value}")

    return dt_time(hour=hour, minute=minute)


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


def state_path(symbol: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{_safe_symbol(symbol)}_scheduled_reports_state.json"


def load_state(symbol: str) -> dict[str, Any]:
    path = state_path(symbol)

    if not path.exists():
        return {"sent_report_keys": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"sent_report_keys": {}}

    if "sent_report_keys" not in data or not isinstance(data["sent_report_keys"], dict):
        data["sent_report_keys"] = {}

    return data


def save_state(symbol: str, state: dict[str, Any]) -> Path:
    path = state_path(symbol)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def is_weekday_market_day(now: datetime) -> bool:
    return now.weekday() < 5


def is_in_due_window(now: datetime, scheduled: dt_time, due_window_minutes: int) -> bool:
    scheduled_dt = now.replace(
        hour=scheduled.hour,
        minute=scheduled.minute,
        second=0,
        microsecond=0,
    )

    return scheduled_dt <= now <= scheduled_dt + timedelta(minutes=max(1, due_window_minutes))


def report_schedule_key(report_type: str, now: datetime) -> str:
    report_type = report_type.lower()

    if report_type == "weekly":
        iso = now.isocalendar()
        return f"weekly:{iso.year}-W{iso.week:02d}"

    return f"{report_type}:{now.date().isoformat()}"


def due_report_types(
    *,
    now: datetime,
    state: dict[str, Any],
    daily_time: dt_time,
    weekly_time: dt_time,
    ny_time: dt_time,
    due_window_minutes: int,
    force_report_type: str | None = None,
) -> list[str]:
    if force_report_type:
        force_report_type = force_report_type.lower()

        if force_report_type == "all":
            return ["daily", "weekly", "ny_update"]

        return [force_report_type]

    sent = state.get("sent_report_keys") or {}
    due: list[str] = []

    if is_weekday_market_day(now) and is_in_due_window(now, daily_time, due_window_minutes):
        key = report_schedule_key("daily", now)

        if key not in sent:
            due.append("daily")

    if now.weekday() == 0 and is_in_due_window(now, weekly_time, due_window_minutes):
        key = report_schedule_key("weekly", now)

        if key not in sent:
            due.append("weekly")

    if is_weekday_market_day(now) and is_in_due_window(now, ny_time, due_window_minutes):
        key = report_schedule_key("ny_update", now)

        if key not in sent:
            due.append("ny_update")

    return due


def report_label(report_type: str) -> str:
    mapping = {
        "daily": "DAILY 08:00 BEIRUT OUTLOOK",
        "weekly": "WEEKLY MONDAY 08:00 BEIRUT OUTLOOK",
        "ny_update": "NY UPDATE 14:30 BEIRUT OUTLOOK",
    }

    return mapping.get(report_type, report_type.upper())


def build_and_send_report(
    *,
    symbol: str,
    report_type: str,
    now: datetime,
    send_telegram: bool,
    news_events_json: str | None,
) -> dict[str, Any]:
    frames = fetch_market_frames(symbol)
    news_events = load_news_events(news_events_json)

    outlook = build_market_outlook(
        frames,
        report_type=report_type,
        symbol=symbol,
        generated_at=now,
        news_events=news_events,
    )

    report_path = save_market_outlook(outlook)

    message = ensure_likely_scenarios_heading(
        format_market_outlook_telegram(outlook)
    )

    message = (
        f"📅 {PHASE}\n"
        f"Scheduled Report: {report_label(report_type)}\n\n"
        + message
    )

    telegram_sent = False

    if send_telegram:
        telegram_sent = send_telegram_message_safe(message)

    return {
        "phase": PHASE,
        "symbol": symbol,
        "report_type": report_type,
        "scheduled_label": report_label(report_type),
        "generated_at": now.isoformat(timespec="seconds"),
        "report_path": str(report_path),
        "send_telegram": send_telegram,
        "telegram_sent": telegram_sent,
        "decision_impact": "NONE",
        "auto_trade_allowed": False,
        "can_execute": False,
        "message": message,
    }


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    tz = ZoneInfo(args.timezone)
    now = datetime.now(tz)

    state = load_state(args.symbol)

    due = due_report_types(
        now=now,
        state=state,
        daily_time=parse_hhmm(args.daily_time),
        weekly_time=parse_hhmm(args.weekly_time),
        ny_time=parse_hhmm(args.ny_time),
        due_window_minutes=args.due_window_minutes,
        force_report_type=args.force_report_type,
    )

    results: list[dict[str, Any]] = []

    for report_type in due:
        result = build_and_send_report(
            symbol=args.symbol,
            report_type=report_type,
            now=now,
            send_telegram=args.send_telegram,
            news_events_json=args.news_events_json,
        )
        results.append(result)

        schedule_key = report_schedule_key(report_type, now)

        # Only mark scheduled reports as sent if Telegram actually succeeded.
        # Force runs are test/manual runs and do not consume the daily schedule key.
        if (
            args.send_telegram
            and result["telegram_sent"]
            and not args.force_report_type
        ):
            state["sent_report_keys"][schedule_key] = {
                "report_type": report_type,
                "sent_at": now.isoformat(timespec="seconds"),
                "report_path": result["report_path"],
            }

    state["last_checked_at"] = now.isoformat(timespec="seconds")
    state["last_due_report_types"] = due
    state_file = save_state(args.symbol, state)

    summary = {
        "phase": PHASE,
        "symbol": args.symbol,
        "timezone": args.timezone,
        "now": now.isoformat(timespec="seconds"),
        "due_report_types": due,
        "send_telegram": args.send_telegram,
        "state_file": str(state_file),
        "reports_generated": len(results),
        "decision_impact": "NONE",
        "auto_trade_allowed": False,
        "can_execute": False,
        "results": [
            {
                key: value
                for key, value in result.items()
                if key != "message"
            }
            for result in results
        ],
    }

    print("[PHASE 6S3 SCHEDULED MARKET OUTLOOK REPORTS]")
    for key, value in summary.items():
        if key != "results":
            print(f"{key} = {value}")

    if summary["results"]:
        print("results =")
        print(json.dumps(summary["results"], indent=2, ensure_ascii=False))

    for result in results:
        print("")
        print(result["message"])

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--daily-time", default="08:00")
    parser.add_argument("--weekly-time", default="08:00")
    parser.add_argument("--ny-time", default="14:30")
    parser.add_argument("--due-window-minutes", type=int, default=45)
    parser.add_argument("--check-interval-seconds", type=int, default=60)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--news-events-json", default=None)
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument(
        "--force-report-type",
        choices=["daily", "weekly", "ny_update", "all"],
        default=None,
        help="Manual test mode: build/send a report immediately without consuming schedule state.",
    )

    args = parser.parse_args()

    if not args.loop:
        run_once(args)
        return

    started = time.time()

    while True:
        run_once(args)

        if args.duration_seconds > 0 and (time.time() - started) >= args.duration_seconds:
            break

        time.sleep(max(60, args.check_interval_seconds))


if __name__ == "__main__":
    main()
