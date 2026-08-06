from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prop_firm_news_guard import (
    evaluate_prop_firm_news_restriction,
)


PROFILE_NAME = "GETLEVERAGED_TURBO_EVALUATION_50K"
NOW = datetime(2026, 8, 6, 15, 30)

PROFILE = {
    "news_restriction_enabled": True,
    "news_before_minutes": 5,
    "news_after_minutes": 5,
    "news_restricted_currencies": ("USD",),
    "news_required_impacts": ("HIGH",),
    "news_calendar_fail_closed": True,
}


def snapshot(events, available=True):
    return {
        "available": available,
        "provider": "TEST",
        "events": events,
        "error": None if available else "test unavailable",
    }


def event(
    *,
    minutes_from_now=0,
    currency="USD",
    impact="High",
    source="TEST",
):
    return {
        "name": "Test Event",
        "time": NOW - timedelta(minutes=minutes_from_now),
        "currency": currency,
        "impact": impact,
        "source": source,
    }


def evaluate(calendar, action="OPEN_POSITION"):
    return evaluate_prop_firm_news_restriction(
        enabled=True,
        profile_name=PROFILE_NAME,
        profile=PROFILE,
        calendar_snapshot=calendar,
        action=action,
        now=NOW,
        fail_closed=True,
    )


def test_event_at_release_is_blocked():
    result = evaluate(snapshot([event()]))

    assert result["allowed"] is False
    assert (
        result["reason"]
        == "prop_firm_restricted_news_window_active"
    )
    assert result["snapshot"]["orders_sent"] == 0


def test_five_minutes_before_is_blocked():
    result = evaluate(
        snapshot([
            event(minutes_from_now=-5),
        ])
    )

    assert result["allowed"] is False


def test_five_minutes_after_is_blocked():
    result = evaluate(
        snapshot([
            event(minutes_from_now=5),
        ])
    )

    assert result["allowed"] is False


def test_outside_window_is_allowed():
    result = evaluate(
        snapshot([
            event(minutes_from_now=5.1),
        ])
    )

    assert result["allowed"] is True


def test_non_usd_event_is_allowed():
    result = evaluate(
        snapshot([
            event(currency="JPY"),
        ])
    )

    assert result["allowed"] is True


def test_non_high_event_is_allowed():
    result = evaluate(
        snapshot([
            event(impact="Medium"),
        ])
    )

    assert result["allowed"] is True


def test_manual_event_is_restricted():
    result = evaluate(
        snapshot([
            event(
                impact="Manual",
                source="MANUAL",
            ),
        ])
    )

    assert result["allowed"] is False


def test_calendar_unavailable_fails_closed():
    result = evaluate(
        snapshot([], available=False)
    )

    assert result["allowed"] is False
    assert (
        result["reason"]
        == "prop_firm_news_calendar_unavailable"
    )


def test_non_entry_action_is_not_blocked():
    result = evaluate(
        snapshot([event()]),
        action="MODIFY_PROTECTIVE_SL",
    )

    assert result["allowed"] is True
    assert (
        result["reason"]
        == "action_not_restricted_by_entry_guard"
    )


def test_source_markers_exist():
    executor = (
        ROOT / "src" / "order_executor.py"
    ).read_text(encoding="utf-8")

    settings = (
        ROOT / "config" / "settings.py"
    ).read_text(encoding="utf-8")

    assert "PROP FIRM NEWS GUARD" in executor
    assert "get_prop_firm_news_calendar_snapshot" in executor
    assert '"news_before_minutes": 5' in settings
    assert '"news_after_minutes": 5' in settings
    assert "ENABLE_PROP_FIRM_SAFE_MODE = False" in settings


if __name__ == "__main__":
    test_event_at_release_is_blocked()
    test_five_minutes_before_is_blocked()
    test_five_minutes_after_is_blocked()
    test_outside_window_is_allowed()
    test_non_usd_event_is_allowed()
    test_non_high_event_is_allowed()
    test_manual_event_is_restricted()
    test_calendar_unavailable_fails_closed()
    test_non_entry_action_is_not_blocked()
    test_source_markers_exist()

    print("[PASS] Phase 7A3 prop-firm news entry guard passed.")
