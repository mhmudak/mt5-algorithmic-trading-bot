from datetime import datetime

from config.settings import (
    ENABLE_TRADING_TIME_BLACKOUT,
    TRADING_BLACKOUT_WINDOWS,
)


def _parse_hhmm(value):
    hour, minute = value.split(":")
    return int(hour), int(minute)


def is_trading_blackout_active(now=None):
    if not ENABLE_TRADING_TIME_BLACKOUT:
        return False, "time_blackout_disabled"

    if now is None:
        now = datetime.now()

    now_minutes = now.hour * 60 + now.minute

    for window in TRADING_BLACKOUT_WINDOWS:
        name = window.get("name", "Trading blackout")
        start_hour, start_minute = _parse_hhmm(window["start"])
        end_hour, end_minute = _parse_hhmm(window["end"])

        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute

        if start_minutes <= end_minutes:
            active = start_minutes <= now_minutes <= end_minutes
        else:
            # Supports windows crossing midnight.
            active = now_minutes >= start_minutes or now_minutes <= end_minutes

        if active:
            return (
                True,
                f"{name} active | window={window['start']}->{window['end']}",
            )

    return False, "no_time_blackout"