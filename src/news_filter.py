from datetime import datetime, timedelta

from config.settings import (
    ENABLE_NEWS_FILTER,
    NEWS_BLACKOUT_WINDOWS,
    NEWS_BLOCK_BEFORE_MINUTES,
    NEWS_BLOCK_AFTER_MINUTES,
)
from src.logger import logger


def _parse_news_time(value):
    """
    Expected format: YYYY-MM-DD HH:MM
    Example: 2026-05-06 15:30
    """
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def is_news_blackout_active(now=None):
    if not ENABLE_NEWS_FILTER:
        return False, "news_filter_disabled"

    if now is None:
        now = datetime.now()

    for event in NEWS_BLACKOUT_WINDOWS:
        try:
            event_time = _parse_news_time(event["time"])
            event_name = event.get("name", "High-impact news")

            start = event_time - timedelta(minutes=NEWS_BLOCK_BEFORE_MINUTES)
            end = event_time + timedelta(minutes=NEWS_BLOCK_AFTER_MINUTES)

            if start <= now <= end:
                reason = (
                    f"News blackout active | "
                    f"event={event_name} "
                    f"time={event_time.strftime('%Y-%m-%d %H:%M')} "
                    f"window={start.strftime('%H:%M')}->{end.strftime('%H:%M')}"
                )
                logger.info(f"[NEWS FILTER] {reason}")
                return True, reason

        except Exception as e:
            logger.error(f"[NEWS FILTER] Invalid news event config: {event} | error={e}")
            continue

    return False, "no_news_blackout"