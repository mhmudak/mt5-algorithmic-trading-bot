from __future__ import annotations

from typing import Any, Dict

from src.funded_account_safe_mode import (
    evaluate_funded_account_safe_mode,
)


FUNDED_EQUITY_BREACH_REASONS = {
    "funded_daily_safety_floor_reached",
    "funded_trailing_safety_floor_reached",
}


def classify_funded_watch_decision(
    decision: Dict[str, Any],
) -> Dict[str, Any]:
    result = dict(decision or {})

    allowed = bool(result.get("allowed", False))
    reason = str(
        result.get("reason")
        or "funded_runtime_watch_unknown"
    )

    snapshot = dict(
        result.get("snapshot")
        or {}
    )
    snapshot.setdefault("orders_sent", 0)

    result["allowed"] = allowed
    result["reason"] = reason
    result["snapshot"] = snapshot

    result["should_block_cycle"] = not allowed
    result["should_close_positions"] = (
        not allowed
        and reason in FUNDED_EQUITY_BREACH_REASONS
    )

    return result


def evaluate_runtime_funded_account_watch(
    *,
    mt5_module,
    symbol,
):
    """
    Re-evaluate the funded account's dynamic equity floor on
    every live-bot loop.

    This function never sends, modifies, or closes an order.
    """
    try:
        from config import settings as runtime_settings

        enabled = bool(
            getattr(
                runtime_settings,
                "ENABLE_PROP_FIRM_SAFE_MODE",
                False,
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

        profiles = getattr(
            runtime_settings,
            "PROP_FIRM_PROFILES",
            {},
        )

        fail_closed = bool(
            getattr(
                runtime_settings,
                "PROP_FIRM_SAFE_MODE_FAIL_CLOSED",
                True,
            )
        )

        account_wide = bool(
            getattr(
                runtime_settings,
                "PROP_FIRM_SAFE_MODE_ACCOUNT_WIDE",
                True,
            )
        )

        decision = evaluate_funded_account_safe_mode(
            mt5_module=mt5_module,
            symbol=symbol,
            trade_plan={
                "setup_id": "FUNDED-RUNTIME-WATCH",
                "strategy": "FUNDED_RUNTIME_WATCH",
            },
            enabled=enabled,
            profile_name=profile_name,
            profiles=profiles,
            fail_closed=fail_closed,
            account_wide=account_wide,
        )

        return classify_funded_watch_decision(
            decision
        )

    except Exception as exc:
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
        except Exception:
            enabled = True
            fail_closed = True

        return classify_funded_watch_decision({
            "allowed": (
                not enabled
                or not fail_closed
            ),
            "reason": (
                "funded_runtime_watch_evaluation_failed"
            ),
            "profile": None,
            "snapshot": {
                "error": str(exc),
                "orders_sent": 0,
            },
        })
