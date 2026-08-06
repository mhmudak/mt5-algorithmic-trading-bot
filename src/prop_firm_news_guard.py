from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional


RESTRICTED_ENTRY_ACTIONS = {
    "OPEN_POSITION",
    "INCREASE_POSITION",
    "PLACE_PENDING_ORDER",
}

RESTRICTED_EXIT_ACTIONS = {
    "PARTIAL_CLOSE_POSITION",
    "FULL_CLOSE_POSITION",
}

RESTRICTED_PROTECTIVE_MODIFICATION_ACTIONS = {
    "MODIFY_PROTECTIVE_SL_TP",
}


def _decision(
    *,
    allowed: bool,
    reason: str,
    profile_name: str,
    snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "allowed": bool(allowed),
        "reason": reason,
        "profile": profile_name,
        "snapshot": snapshot or {},
    }


def _normalized_values(values: Iterable[Any]) -> set[str]:
    return {
        str(value or "").strip().upper()
        for value in values or ()
        if str(value or "").strip()
    }


def _comparable_datetimes(
    current_time: datetime,
    event_time: datetime,
) -> tuple[datetime, datetime]:
    if current_time.tzinfo is None and event_time.tzinfo is not None:
        event_time = event_time.replace(tzinfo=None)

    elif current_time.tzinfo is not None and event_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=None)

    elif (
        current_time.tzinfo is not None
        and event_time.tzinfo is not None
    ):
        event_time = event_time.astimezone(current_time.tzinfo)

    return current_time, event_time


def evaluate_prop_firm_news_restriction(
    *,
    enabled: bool,
    profile_name: str,
    profile: Optional[Dict[str, Any]],
    calendar_snapshot: Optional[Dict[str, Any]],
    action: str = "OPEN_POSITION",
    now: Optional[datetime] = None,
    fail_closed: bool = True,
) -> Dict[str, Any]:
    normalized_profile = str(profile_name or "").strip().upper()
    normalized_action = str(action or "").strip().upper()

    if not enabled:
        return _decision(
            allowed=True,
            reason="prop_firm_news_guard_disabled",
            profile_name=normalized_profile,
        )

    if normalized_action in RESTRICTED_ENTRY_ACTIONS:
        action_category = "ENTRY"
    elif normalized_action in RESTRICTED_EXIT_ACTIONS:
        action_category = "AUTOMATED_EXIT"
    elif (
        normalized_action
        in RESTRICTED_PROTECTIVE_MODIFICATION_ACTIONS
    ):
        action_category = "PROTECTIVE_MODIFICATION"
    else:
        return _decision(
            allowed=True,
            reason="action_not_restricted_by_news_guard",
            profile_name=normalized_profile,
            snapshot={
                "action": normalized_action,
                "action_category": "UNRESTRICTED",
            },
        )

    if not isinstance(profile, dict):
        return _decision(
            allowed=not fail_closed,
            reason="prop_firm_news_profile_missing",
            profile_name=normalized_profile,
        )

    if not bool(profile.get("news_restriction_enabled", True)):
        return _decision(
            allowed=True,
            reason="profile_news_restriction_disabled",
            profile_name=normalized_profile,
        )

    if (
        action_category == "AUTOMATED_EXIT"
        and not bool(
            profile.get(
                "news_block_automated_position_closes",
                True,
            )
        )
    ):
        return _decision(
            allowed=True,
            reason="automated_exit_news_guard_disabled",
            profile_name=normalized_profile,
            snapshot={
                "action": normalized_action,
                "action_category": action_category,
            },
        )

    if (
        action_category == "PROTECTIVE_MODIFICATION"
        and not bool(
            profile.get(
                "news_freeze_sl_tp_modifications",
                True,
            )
        )
    ):
        return _decision(
            allowed=True,
            reason="protective_modification_news_guard_disabled",
            profile_name=normalized_profile,
            snapshot={
                "action": normalized_action,
                "action_category": action_category,
            },
        )

    snapshot = (
        calendar_snapshot
        if isinstance(calendar_snapshot, dict)
        else {}
    )

    calendar_available = bool(snapshot.get("available"))
    calendar_fail_closed = bool(
        profile.get("news_calendar_fail_closed", fail_closed)
    )

    base_snapshot = {
        "action": normalized_action,
        "action_category": action_category,
        "calendar_available": calendar_available,
        "calendar_provider": snapshot.get("provider"),
        "calendar_error": snapshot.get("error"),
        "event_count": len(snapshot.get("events") or []),
        "orders_sent": 0,
    }

    if not calendar_available:
        return _decision(
            allowed=not calendar_fail_closed,
            reason="prop_firm_news_calendar_unavailable",
            profile_name=normalized_profile,
            snapshot=base_snapshot,
        )

    current_time = now or datetime.now()

    before_minutes = max(
        float(profile.get("news_before_minutes", 5)),
        0.0,
    )
    after_minutes = max(
        float(profile.get("news_after_minutes", 5)),
        0.0,
    )

    restricted_currencies = _normalized_values(
        profile.get("news_restricted_currencies", ("USD",))
    )
    required_impacts = _normalized_values(
        profile.get("news_required_impacts", ("HIGH",))
    )

    matching_events = []

    for event in snapshot.get("events") or []:
        if not isinstance(event, dict):
            continue

        event_time = event.get("time")

        if not isinstance(event_time, datetime):
            continue

        currency = str(
            event.get("currency") or ""
        ).strip().upper()
        impact = str(
            event.get("impact") or ""
        ).strip().upper()
        source = str(
            event.get("source") or ""
        ).strip().upper()

        if restricted_currencies and currency not in restricted_currencies:
            continue

        # Manually configured events are explicitly treated as restricted.
        if (
            source != "MANUAL"
            and required_impacts
            and impact not in required_impacts
        ):
            continue

        comparable_now, comparable_event = _comparable_datetimes(
            current_time,
            event_time,
        )

        minutes_from_event = (
            comparable_now - comparable_event
        ).total_seconds() / 60.0

        if -before_minutes <= minutes_from_event <= after_minutes:
            matching_events.append({
                "name": event.get("name"),
                "currency": currency,
                "impact": impact,
                "source": source,
                "event_time": event_time.isoformat(),
                "minutes_from_event": round(
                    minutes_from_event,
                    2,
                ),
            })

    if matching_events:
        restricted_event = min(
            matching_events,
            key=lambda item: abs(
                float(item["minutes_from_event"])
            ),
        )

        return _decision(
            allowed=False,
            reason="prop_firm_restricted_news_window_active",
            profile_name=normalized_profile,
            snapshot={
                **base_snapshot,
                "before_minutes": before_minutes,
                "after_minutes": after_minutes,
                "restricted_event": restricted_event,
            },
        )

    return _decision(
        allowed=True,
        reason="no_prop_firm_restricted_news_window",
        profile_name=normalized_profile,
        snapshot={
            **base_snapshot,
            "before_minutes": before_minutes,
            "after_minutes": after_minutes,
        },
    )

def evaluate_runtime_prop_firm_news_action(
    *,
    action: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Evaluate the currently selected prop-firm profile using the
    configured runtime calendar.

    This helper never submits, modifies, or closes an order.
    """
    enabled = False
    fail_closed = True
    profile_name = ""

    try:
        from config import settings as runtime_settings

        enabled = bool(
            getattr(
                runtime_settings,
                "ENABLE_PROP_FIRM_SAFE_MODE",
                False,
            )
        )
        fail_closed = bool(
            getattr(
                runtime_settings,
                "PROP_FIRM_SAFE_MODE_FAIL_CLOSED",
                True,
            )
        )

        profile_name = str(
            getattr(
                runtime_settings,
                "PROP_FIRM_PROFILE",
                "",
            )
            or ""
        ).strip().upper()

        if not enabled:
            return _decision(
                allowed=True,
                reason="prop_firm_news_guard_disabled",
                profile_name=profile_name,
                snapshot={"action": str(action).upper()},
            )

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

        from src.news_filter import (
            get_prop_firm_news_calendar_snapshot,
        )

        calendar_snapshot = (
            get_prop_firm_news_calendar_snapshot(now=now)
        )

        return evaluate_prop_firm_news_restriction(
            enabled=True,
            profile_name=profile_name,
            profile=profile,
            calendar_snapshot=calendar_snapshot,
            action=action,
            now=now,
            fail_closed=fail_closed,
        )

    except Exception as exc:
        return _decision(
            allowed=not (enabled and fail_closed),
            reason="prop_firm_news_runtime_evaluation_failed",
            profile_name=profile_name,
            snapshot={
                "action": str(action or "").upper(),
                "error": str(exc),
                "orders_sent": 0,
            },
        )
