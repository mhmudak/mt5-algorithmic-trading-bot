
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scripts.run_phase6s_scheduled_market_reports import (
    due_report_types,
    is_in_due_window,
    parse_hhmm,
    report_schedule_key,
)


TZ = ZoneInfo("Asia/Beirut")


def test_parse_hhmm():
    value = parse_hhmm("08:00")

    assert value.hour == 8
    assert value.minute == 0


def test_due_daily_and_weekly_monday_0800():
    now = datetime(2026, 8, 3, 8, 0, tzinfo=TZ)
    state = {"sent_report_keys": {}}

    due = due_report_types(
        now=now,
        state=state,
        daily_time=parse_hhmm("08:00"),
        weekly_time=parse_hhmm("08:00"),
        ny_time=parse_hhmm("14:30"),
        due_window_minutes=45,
    )

    assert "daily" in due
    assert "weekly" in due
    assert "ny_update" not in due


def test_due_ny_update():
    now = datetime(2026, 8, 3, 14, 30, tzinfo=TZ)
    state = {"sent_report_keys": {}}

    due = due_report_types(
        now=now,
        state=state,
        daily_time=parse_hhmm("08:00"),
        weekly_time=parse_hhmm("08:00"),
        ny_time=parse_hhmm("14:30"),
        due_window_minutes=45,
    )

    assert due == ["ny_update"]


def test_due_window_expires():
    now = datetime(2026, 8, 3, 8, 46, tzinfo=TZ)

    assert is_in_due_window(now, parse_hhmm("08:00"), 45) is False


def test_sent_key_suppresses_duplicate():
    now = datetime(2026, 8, 3, 8, 5, tzinfo=TZ)
    key = report_schedule_key("daily", now)
    state = {"sent_report_keys": {key: {"sent_at": "test"}}}

    due = due_report_types(
        now=now,
        state=state,
        daily_time=parse_hhmm("08:00"),
        weekly_time=parse_hhmm("08:00"),
        ny_time=parse_hhmm("14:30"),
        due_window_minutes=45,
    )

    assert "daily" not in due
    assert "weekly" in due


def test_weekend_no_regular_daily_or_ny():
    now = datetime(2026, 8, 8, 8, 0, tzinfo=TZ)
    state = {"sent_report_keys": {}}

    due = due_report_types(
        now=now,
        state=state,
        daily_time=parse_hhmm("08:00"),
        weekly_time=parse_hhmm("08:00"),
        ny_time=parse_hhmm("14:30"),
        due_window_minutes=45,
    )

    assert due == []


def test_force_report_type_ignores_schedule():
    now = datetime(2026, 8, 8, 23, 0, tzinfo=TZ)
    state = {"sent_report_keys": {"daily:2026-08-08": {}}}

    due = due_report_types(
        now=now,
        state=state,
        daily_time=parse_hhmm("08:00"),
        weekly_time=parse_hhmm("08:00"),
        ny_time=parse_hhmm("14:30"),
        due_window_minutes=45,
        force_report_type="daily",
    )

    assert due == ["daily"]

    due_all = due_report_types(
        now=now,
        state=state,
        daily_time=parse_hhmm("08:00"),
        weekly_time=parse_hhmm("08:00"),
        ny_time=parse_hhmm("14:30"),
        due_window_minutes=45,
        force_report_type="all",
    )

    assert due_all == ["daily", "weekly", "ny_update"]


if __name__ == "__main__":
    test_parse_hhmm()
    test_due_daily_and_weekly_monday_0800()
    test_due_ny_update()
    test_due_window_expires()
    test_sent_key_suppresses_duplicate()
    test_weekend_no_regular_daily_or_ny()
    test_force_report_type_ignores_schedule()
    print("[PASS] Phase 6S3 scheduled market reports passed.")
