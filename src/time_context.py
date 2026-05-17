from config.settings import (
    ENABLE_TIME_CONTEXT_ENGINE,
    TIME_CONTEXT_WINDOWS,
)
from src.logger import logger


def _to_minutes(value):
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _is_inside_window(now_minutes, start, end):
    start_minutes = _to_minutes(start)
    end_minutes = _to_minutes(end)

    if start_minutes <= end_minutes:
        return start_minutes <= now_minutes <= end_minutes

    return now_minutes >= start_minutes or now_minutes <= end_minutes


def analyze_time_context(current_time):
    if not ENABLE_TIME_CONTEXT_ENGINE:
        return None

    now_minutes = current_time.hour * 60 + current_time.minute
    active_windows = []

    for window in TIME_CONTEXT_WINDOWS:
        if _is_inside_window(now_minutes, window["start"], window["end"]):
            active_windows.append(window)

    if not active_windows:
        logger.info("[TIME CONTEXT] No active time context")
        return {
            "active": False,
            "windows": [],
            "reasons": [],
        }

    reasons = [window["name"] for window in active_windows]

    logger.info(f"[TIME CONTEXT] Active windows={reasons}")

    return {
        "active": True,
        "windows": active_windows,
        "reasons": reasons,
    }


def apply_time_context_confirmation(signal_data, context):
    if not ENABLE_TIME_CONTEXT_ENGINE:
        return 0, []

    if not signal_data or not context or not context.get("active"):
        return 0, []

    strategy = signal_data.get("strategy")

    if not strategy:
        return 0, []

    score_adjustment = 0
    reasons = []

    for window in context.get("windows", []):
        boost_strategies = window.get("boost_strategies", [])
        penalty_strategies = window.get("penalty_strategies", [])

        if strategy in boost_strategies:
            boost = window.get("boost", 0)
            score_adjustment += boost
            reasons.append(f"time_boost_{window.get('name')}")

        if strategy in penalty_strategies:
            penalty = window.get("penalty", 0)
            score_adjustment -= penalty
            reasons.append(f"time_penalty_{window.get('name')}")

    return score_adjustment, reasons