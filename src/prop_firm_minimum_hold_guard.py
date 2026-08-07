from __future__ import annotations

from datetime import datetime, timezone


RESTRICTED_CLOSE_ACTIONS = {
    "PARTIAL_CLOSE_POSITION",
    "FULL_CLOSE_POSITION",
}


def _result(
    *,
    allowed,
    reason,
    action,
    snapshot=None,
):
    payload = dict(snapshot or {})
    payload.setdefault("action", action)
    payload.setdefault("orders_sent", 0)

    return {
        "allowed": bool(allowed),
        "reason": reason,
        "snapshot": payload,
    }


def evaluate_runtime_prop_firm_minimum_hold(
    *,
    position,
    action,
    now_timestamp=None,
):
    """
    Enforce the funded profile minimum duration for normal
    bot-controlled partial and full market closes.

    Broker-triggered SL/TP protection is not intercepted.
    Emergency drawdown liquidation is handled separately.
    """
    action_key = str(action or "").strip().upper()

    if action_key not in RESTRICTED_CLOSE_ACTIONS:
        return _result(
            allowed=True,
            reason="prop_firm_minimum_hold_action_not_restricted",
            action=action_key,
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
            return _result(
                allowed=True,
                reason="prop_firm_minimum_hold_guard_disabled",
                action=action_key,
            )

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

        global_fail_closed = bool(
            getattr(
                runtime_settings,
                "PROP_FIRM_SAFE_MODE_FAIL_CLOSED",
                True,
            )
        )

        if not isinstance(profile, dict):
            return _result(
                allowed=not global_fail_closed,
                reason="prop_firm_minimum_hold_profile_missing",
                action=action_key,
                snapshot={
                    "profile": profile_name,
                },
            )

        required_seconds = float(
            profile.get(
                "minimum_automated_hold_seconds",
                120,
            )
            or 0
        )

        fail_closed = bool(
            profile.get(
                "minimum_hold_fail_closed",
                global_fail_closed,
            )
        )

        base_snapshot = {
            "profile": profile_name,
            "ticket": getattr(position, "ticket", None),
            "symbol": getattr(position, "symbol", None),
            "required_hold_seconds": required_seconds,
        }

        if required_seconds <= 0:
            return _result(
                allowed=True,
                reason="prop_firm_minimum_hold_not_required",
                action=action_key,
                snapshot=base_snapshot,
            )

        try:
            opened_at = float(
                getattr(position, "time", None)
            )
        except (TypeError, ValueError):
            opened_at = 0.0

        if opened_at <= 0:
            return _result(
                allowed=not fail_closed,
                reason="prop_firm_position_open_time_unavailable",
                action=action_key,
                snapshot=base_snapshot,
            )

        if now_timestamp is None:
            now_timestamp = datetime.now(
                timezone.utc
            ).timestamp()

        try:
            current_time = float(now_timestamp)
        except (TypeError, ValueError):
            current_time = 0.0

        if current_time <= 0:
            return _result(
                allowed=not fail_closed,
                reason="prop_firm_current_time_unavailable",
                action=action_key,
                snapshot={
                    **base_snapshot,
                    "position_open_timestamp": opened_at,
                },
            )

        age_seconds = max(
            0.0,
            current_time - opened_at,
        )

        remaining_seconds = max(
            0.0,
            required_seconds - age_seconds,
        )

        snapshot = {
            **base_snapshot,
            "position_open_timestamp": opened_at,
            "current_timestamp": current_time,
            "position_age_seconds": round(
                age_seconds,
                3,
            ),
            "remaining_hold_seconds": round(
                remaining_seconds,
                3,
            ),
            "emergency_drawdown_exception": bool(
                profile.get(
                    "minimum_hold_emergency_drawdown_exception",
                    True,
                )
            ),
            "broker_protection_exception": bool(
                profile.get(
                    "minimum_hold_broker_protection_exception",
                    True,
                )
            ),
        }

        if age_seconds < required_seconds:
            return _result(
                allowed=False,
                reason="prop_firm_minimum_hold_active",
                action=action_key,
                snapshot=snapshot,
            )

        return _result(
            allowed=True,
            reason="prop_firm_minimum_hold_satisfied",
            action=action_key,
            snapshot=snapshot,
        )

    except Exception as exc:
        return _result(
            allowed=False,
            reason="prop_firm_minimum_hold_evaluation_failed",
            action=action_key,
            snapshot={
                "error": str(exc),
            },
        )
