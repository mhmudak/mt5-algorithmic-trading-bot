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
    ENABLE_NEWS_CONTEXT_MEMORY,
    NEWS_CONTEXT_BEFORE_MINUTES,
    NEWS_CONTEXT_AFTER_MINUTES,
)
from src.logger import logger


_cached_events = {
    "fetched_at": None,
    "events": [],
    "fetch_ok": None,
    "error": None,
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
        response = requests.get(
            FOREX_FACTORY_CALENDAR_URL,
            timeout=8,
        )

        if response.status_code != 200:
            error = (
                f"ForexFactory HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            _cached_events["fetch_ok"] = False
            _cached_events["error"] = error
            logger.error(f"[NEWS FILTER] {error}")
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

            event_time = _parse_forex_factory_datetime(
                date_value,
                time_value,
            )

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

        _cached_events["fetch_ok"] = True
        _cached_events["error"] = None

        logger.info(
            f"[NEWS FILTER] Loaded {len(events)} "
            f"relevant ForexFactory events"
        )
        return events

    except Exception as exc:
        error = f"ForexFactory fetch failed: {exc}"
        _cached_events["fetch_ok"] = False
        _cached_events["error"] = error
        logger.error(f"[NEWS FILTER] {error}")
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



def _safe_nonnegative_minutes(value, default):
    try:
        return max(float(value), 0.0)
    except Exception:
        return max(float(default), 0.0)


def _get_active_news_block_minutes():
    """
    Resolve the effective entry blackout window.

    Normal account:
        Uses the existing generic settings.

    Enabled prop-firm account:
        Uses the selected prop-firm profile.
    """
    generic_before = _safe_nonnegative_minutes(
        NEWS_BLOCK_BEFORE_MINUTES,
        15.0,
    )
    generic_after = _safe_nonnegative_minutes(
        NEWS_BLOCK_AFTER_MINUTES,
        15.0,
    )

    try:
        from config import settings as runtime_settings

        if not bool(
            getattr(
                runtime_settings,
                "ENABLE_PROP_FIRM_SAFE_MODE",
                False,
            )
        ):
            return generic_before, generic_after

        profile_name = str(
            getattr(
                runtime_settings,
                "PROP_FIRM_PROFILE",
                "",
            )
            or ""
        ).strip().upper()

        profiles = getattr(
            runtime_settings,
            "PROP_FIRM_PROFILES",
            {},
        )

        profile = (
            profiles.get(profile_name)
            if isinstance(profiles, dict)
            else None
        )

        if not isinstance(profile, dict):
            return generic_before, generic_after

        if not bool(
            profile.get(
                "news_restriction_enabled",
                True,
            )
        ):
            return generic_before, generic_after

        funded_before = _safe_nonnegative_minutes(
            profile.get(
                "news_before_minutes",
                generic_before,
            ),
            generic_before,
        )
        funded_after = _safe_nonnegative_minutes(
            profile.get(
                "news_after_minutes",
                generic_after,
            ),
            generic_after,
        )

        return funded_before, funded_after

    except Exception:
        return generic_before, generic_after

def _manual_news_blackout(now):
    before_minutes, after_minutes = (
        _get_active_news_block_minutes()
    )

    for event in NEWS_BLACKOUT_WINDOWS:
        try:
            event_time = _parse_manual_news_time(event["time"])
            event_name = event.get("name", "High-impact news")

            start = event_time - timedelta(minutes=before_minutes)
            end = event_time + timedelta(minutes=after_minutes)

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
    before_minutes, after_minutes = (
        _get_active_news_block_minutes()
    )
    events = _get_auto_news_events()

    for event in events:
        event_time = event["time"]

        start = event_time - timedelta(minutes=before_minutes)
        end = event_time + timedelta(minutes=after_minutes)

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


def get_prop_firm_news_calendar_snapshot(now=None):
    """
    Return normalized restricted-news events and calendar health.

    No order operation is performed here.
    """
    if now is None:
        now = datetime.now()

    manual_events = []

    for event in NEWS_BLACKOUT_WINDOWS:
        try:
            event_time = _parse_manual_news_time(event["time"])

            manual_events.append({
                "name": event.get(
                    "name",
                    "Manual high-impact news",
                ),
                "time": event_time,
                "currency": event.get("currency", "USD"),
                "impact": event.get("impact", "High"),
                "source": "MANUAL",
            })
        except Exception as exc:
            logger.error(
                f"[NEWS FILTER] Invalid manual news config: "
                f"{event} | {exc}"
            )

    auto_events = []

    if ENABLE_AUTO_NEWS_FILTER:
        auto_events = list(_get_auto_news_events())

    auto_available = (
        ENABLE_AUTO_NEWS_FILTER
        and _cached_events.get("fetch_ok") is True
    )
    manual_available = bool(manual_events)

    available = bool(auto_available or manual_available)

    return {
        "available": available,
        "provider": ECONOMIC_CALENDAR_PROVIDER,
        "events": manual_events + auto_events,
        "manual_event_count": len(manual_events),
        "auto_event_count": len(auto_events),
        "fetched_at": _cached_events.get("fetched_at"),
        "fetch_ok": _cached_events.get("fetch_ok"),
        "error": _cached_events.get("error"),
        "checked_at": now,
    }

def classify_news_event_name(name):
    text = str(name or "").upper()

    if any(key in text for key in ["NFP", "NON-FARM", "NON FARM", "NONFARM", "PAYROLL"]):
        return "NFP"

    if "CPI" in text or "INFLATION" in text:
        return "CPI"

    if "PPI" in text:
        return "PPI"

    if any(key in text for key in ["FOMC", "FED", "POWELL", "FEDERAL FUNDS", "RATE DECISION", "INTEREST RATE"]):
        return "FOMC"

    if "PCE" in text:
        return "PCE"

    if "GDP" in text:
        return "GDP"

    if "RETAIL SALES" in text:
        return "RETAIL_SALES"

    if "ISM" in text or "PMI" in text:
        return "PMI"

    if "JOLTS" in text:
        return "JOLTS"

    if "ADP" in text:
        return "ADP"

    if "UNEMPLOYMENT" in text or "JOBLESS" in text or "CLAIMS" in text:
        return "JOBS"

    return "HIGH_IMPACT_NEWS"


def get_active_news_context(now=None):
    if not ENABLE_NEWS_CONTEXT_MEMORY:
        return None

    if now is None:
        now = datetime.now()

    candidates = []

    # Manual news
    for event in NEWS_BLACKOUT_WINDOWS:
        try:
            event_time = _parse_manual_news_time(event["time"])
            event_name = event.get("name", "High-impact news")

            start = event_time - timedelta(minutes=NEWS_CONTEXT_BEFORE_MINUTES)
            end = event_time + timedelta(minutes=NEWS_CONTEXT_AFTER_MINUTES)

            if start <= now <= end:
                candidates.append({
                    "news_tag": classify_news_event_name(event_name),
                    "news_event": event_name,
                    "news_currency": event.get("currency", ""),
                    "news_impact": event.get("impact", "Manual"),
                    "news_time": event_time.strftime("%Y-%m-%d %H:%M"),
                    "news_source": "MANUAL",
                    "minutes_from_news": round((now - event_time).total_seconds() / 60, 1),
                })

        except Exception:
            continue

    # Auto news
    for event in _get_auto_news_events():
        event_time = event["time"]

        start = event_time - timedelta(minutes=NEWS_CONTEXT_BEFORE_MINUTES)
        end = event_time + timedelta(minutes=NEWS_CONTEXT_AFTER_MINUTES)

        if start <= now <= end:
            candidates.append({
                "news_tag": classify_news_event_name(event.get("name")),
                "news_event": event.get("name"),
                "news_currency": event.get("currency"),
                "news_impact": event.get("impact"),
                "news_time": event_time.strftime("%Y-%m-%d %H:%M"),
                "news_source": event.get("source"),
                "minutes_from_news": round((now - event_time).total_seconds() / 60, 1),
            })

    if not candidates:
        return None

    # Pick nearest event by absolute time distance.
    return min(
        candidates,
        key=lambda item: abs(float(item.get("minutes_from_news", 999999)))
    )

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