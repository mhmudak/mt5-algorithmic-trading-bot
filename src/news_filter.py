from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

import requests

from config.settings import (
    ENABLE_NEWS_FILTER,
    NEWS_BLACKOUT_WINDOWS,
    NEWS_BLOCK_BEFORE_MINUTES,
    NEWS_BLOCK_AFTER_MINUTES,
    ENABLE_AUTO_NEWS_FILTER,
    ECONOMIC_CALENDAR_PROVIDER,
    FOREX_FACTORY_CALENDAR_URL,
    FOREX_FACTORY_TIME_OFFSET_HOURS,
    AUTO_NEWS_CURRENCIES,
    AUTO_NEWS_IMPACT,
    AUTO_NEWS_KEYWORDS,
)
from src.logger import logger


_cached_events = {
    "fetched_at": None,
    "events": [],
}


def _parse_manual_news_time(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def _parse_forex_factory_datetime(date_value, time_value):
    if not date_value or not time_value:
        return None

    raw = f"{date_value.strip()} {time_value.strip()}"

    formats = [
        "%m-%d-%Y %I:%M%p",
        "%m-%d-%y %I:%M%p",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %I:%M%p",
        "%b %d, %Y %I:%M%p",
        "%b %d, %Y %H:%M",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(raw.replace(" ", ""), fmt.replace(" ", ""))
            return parsed + timedelta(hours=FOREX_FACTORY_TIME_OFFSET_HOURS)
        except ValueError:
            continue

    # Some XML files include separated date/time with spaces, so try raw normally too.
    for fmt in formats:
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed + timedelta(hours=FOREX_FACTORY_TIME_OFFSET_HOURS)
        except ValueError:
            continue

    return None


def _text(node, name):
    child = node.find(name)

    if child is None or child.text is None:
        return ""

    return child.text.strip()


def _matches_currency(currency):
    return currency.upper() in [item.upper() for item in AUTO_NEWS_CURRENCIES]


def _matches_impact(impact):
    return impact.lower() in [item.lower() for item in AUTO_NEWS_IMPACT]


def _matches_keyword(title):
    title_lower = title.lower()
    return any(keyword.lower() in title_lower for keyword in AUTO_NEWS_KEYWORDS)


def _is_relevant_event(event):
    currency = event.get("currency", "")
    impact = event.get("impact", "")
    title = event.get("title", "")

    if not _matches_currency(currency):
        return False

    return _matches_impact(impact) or _matches_keyword(title)


def _fetch_forex_factory_events():
    try:
        response = requests.get(FOREX_FACTORY_CALENDAR_URL, timeout=8)

        if response.status_code != 200:
            logger.error(
                f"[NEWS FILTER] ForexFactory HTTP {response.status_code}: {response.text[:200]}"
            )
            return []

        root = ET.fromstring(response.content)
        events = []

        for item in root.findall(".//event"):
            title = _text(item, "title")
            country = _text(item, "country")
            currency = _text(item, "currency") or country
            impact = _text(item, "impact")
            date_value = _text(item, "date")
            time_value = _text(item, "time")

            event_time = _parse_forex_factory_datetime(date_value, time_value)

            if event_time is None:
                continue

            event = {
                "name": title,
                "time": event_time,
                "country": country,
                "currency": currency,
                "impact": impact,
                "source": "FOREX_FACTORY",
            }

            if not _is_relevant_event(event):
                continue

            events.append(event)

        logger.info(f"[NEWS FILTER] Loaded {len(events)} relevant ForexFactory events")
        return events

    except Exception as e:
        logger.error(f"[NEWS FILTER] Failed to fetch ForexFactory calendar: {e}")
        return []


def _get_auto_news_events():
    if not ENABLE_AUTO_NEWS_FILTER:
        return []

    if ECONOMIC_CALENDAR_PROVIDER != "FOREX_FACTORY":
        logger.info(f"[NEWS FILTER] Unsupported provider: {ECONOMIC_CALENDAR_PROVIDER}")
        return []

    now = datetime.now()
    fetched_at = _cached_events.get("fetched_at")

    # Cache for 30 minutes.
    if fetched_at and (now - fetched_at).total_seconds() < 60 * 30:
        return _cached_events["events"]

    events = _fetch_forex_factory_events()

    _cached_events["fetched_at"] = now
    _cached_events["events"] = events

    return events


def _manual_news_blackout(now):
    for event in NEWS_BLACKOUT_WINDOWS:
        try:
            event_time = _parse_manual_news_time(event["time"])
            event_name = event.get("name", "High-impact news")

            start = event_time - timedelta(minutes=NEWS_BLOCK_BEFORE_MINUTES)
            end = event_time + timedelta(minutes=NEWS_BLOCK_AFTER_MINUTES)

            if start <= now <= end:
                reason = (
                    f"Manual news blackout active | "
                    f"event={event_name} "
                    f"time={event_time.strftime('%Y-%m-%d %H:%M')} "
                    f"window={start.strftime('%H:%M')}->{end.strftime('%H:%M')}"
                )
                logger.info(f"[NEWS FILTER] {reason}")
                return True, reason

        except Exception as e:
            logger.error(f"[NEWS FILTER] Invalid manual news config: {event} | {e}")
            continue

    return False, "no_manual_news_blackout"


def _auto_news_blackout(now):
    events = _get_auto_news_events()

    for event in events:
        event_time = event["time"]

        start = event_time - timedelta(minutes=NEWS_BLOCK_BEFORE_MINUTES)
        end = event_time + timedelta(minutes=NEWS_BLOCK_AFTER_MINUTES)

        if start <= now <= end:
            reason = (
                f"Auto news blackout active | "
                f"event={event['name']} "
                f"currency={event['currency']} "
                f"impact={event['impact']} "
                f"time={event_time.strftime('%Y-%m-%d %H:%M')} "
                f"source={event['source']} "
                f"window={start.strftime('%H:%M')}->{end.strftime('%H:%M')}"
            )
            logger.info(f"[NEWS FILTER] {reason}")
            return True, reason

    return False, "no_auto_news_blackout"


def is_news_blackout_active(now=None):
    if not ENABLE_NEWS_FILTER:
        return False, "news_filter_disabled"

    if now is None:
        now = datetime.now()

    manual_blocked, manual_reason = _manual_news_blackout(now)

    if manual_blocked:
        return True, manual_reason

    auto_blocked, auto_reason = _auto_news_blackout(now)

    if auto_blocked:
        return True, auto_reason

    return False, "no_news_blackout"