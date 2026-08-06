from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from src import news_filter


def test_generic_account_keeps_fifteen_minutes():
    original_enabled = settings.ENABLE_PROP_FIRM_SAFE_MODE

    try:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = False

        before, after = (
            news_filter._get_active_news_block_minutes()
        )

        assert before == 15.0
        assert after == 15.0

    finally:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = (
            original_enabled
        )


def test_funded_account_uses_five_minutes():
    original_enabled = settings.ENABLE_PROP_FIRM_SAFE_MODE

    try:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = True

        before, after = (
            news_filter._get_active_news_block_minutes()
        )

        assert before == 5.0
        assert after == 5.0

    finally:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = (
            original_enabled
        )


def test_six_minutes_after_event_differs_by_mode():
    original_enabled = settings.ENABLE_PROP_FIRM_SAFE_MODE
    original_windows = list(
        news_filter.NEWS_BLACKOUT_WINDOWS
    )

    event_time = datetime(2026, 8, 6, 15, 30)
    current_time = event_time + timedelta(minutes=6)

    try:
        news_filter.NEWS_BLACKOUT_WINDOWS[:] = [
            {
                "name": "Synthetic USD High Impact",
                "time": event_time.strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "currency": "USD",
                "impact": "High",
            }
        ]

        settings.ENABLE_PROP_FIRM_SAFE_MODE = False
        generic_blocked, _ = (
            news_filter._manual_news_blackout(
                current_time
            )
        )

        settings.ENABLE_PROP_FIRM_SAFE_MODE = True
        funded_blocked, _ = (
            news_filter._manual_news_blackout(
                current_time
            )
        )

        assert generic_blocked is True
        assert funded_blocked is False

    finally:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = (
            original_enabled
        )
        news_filter.NEWS_BLACKOUT_WINDOWS[:] = (
            original_windows
        )


def test_default_configuration_remains_inactive():
    source = (
        ROOT / "config" / "settings.py"
    ).read_text(encoding="utf-8")

    assert "ENABLE_PROP_FIRM_SAFE_MODE = False" in source


if __name__ == "__main__":
    test_generic_account_keeps_fifteen_minutes()
    test_funded_account_uses_five_minutes()
    test_six_minutes_after_event_differs_by_mode()
    test_default_configuration_remains_inactive()

    print(
        "[PASS] Phase 7A3 effective news-window "
        "resolution passed."
    )
