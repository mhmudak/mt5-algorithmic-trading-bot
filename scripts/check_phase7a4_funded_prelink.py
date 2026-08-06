from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import MetaTrader5 as mt5


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from src.funded_account_safe_mode import (
    evaluate_funded_account_activation,
)
from src.news_filter import (
    get_prop_firm_news_calendar_snapshot,
)
from src.prop_firm_news_guard import (
    evaluate_prop_firm_news_restriction,
)


def pass_fail(value):
    return "PASS" if value else "FAIL"


def main() -> int:
    profile_name = str(
        settings.PROP_FIRM_PROFILE
    ).strip().upper()

    profile = settings.PROP_FIRM_PROFILES.get(
        profile_name
    )

    print("=" * 72)
    print("PHASE 7A4 — FUNDED ACCOUNT PRE-LINK DRY-RUN")
    print("=" * 72)
    print("Order submission capability: NOT USED")
    print("Orders sent: 0")
    print()

    if not isinstance(profile, dict):
        print("PRE-LINK STATUS: BLOCKED")
        print("Reason: funded_profile_missing")
        return 1

    toggle_safe = (
        settings.ENABLE_PROP_FIRM_SAFE_MODE is False
    )

    required_profile_fields = (
        "initial_balance",
        "official_daily_loss_pct",
        "official_trailing_drawdown_pct",
        "daily_safety_buffer_pct",
        "trailing_safety_buffer_pct",
        "activation_require_explicit_identity",
        "news_before_minutes",
        "news_after_minutes",
        "news_calendar_fail_closed",
        "news_block_automated_position_closes",
        "news_freeze_sl_tp_modifications",
        "news_preserve_existing_sl_tp",
    )

    missing_fields = [
        field
        for field in required_profile_fields
        if field not in profile
    ]

    profile_valid = not missing_fields

    print(
        f"Safe mode currently disabled: "
        f"{pass_fail(toggle_safe)}"
    )
    print(
        f"Selected profile exists: "
        f"{pass_fail(True)}"
    )
    print(
        f"Required profile fields: "
        f"{pass_fail(profile_valid)}"
    )

    if missing_fields:
        print(
            "Missing profile fields: "
            + ", ".join(missing_fields)
        )

    print()
    print(f"Profile: {profile_name}")
    print(
        f"Configured initial balance: "
        f"{profile.get('initial_balance')}"
    )
    print(
        "Daily limit / buffer: "
        f"{profile.get('official_daily_loss_pct')}% / "
        f"{profile.get('daily_safety_buffer_pct')}%"
    )
    print(
        "Trailing limit / buffer: "
        f"{profile.get('official_trailing_drawdown_pct')}% / "
        f"{profile.get('trailing_safety_buffer_pct')}%"
    )
    print(
        "Restricted-news window: "
        f"-{profile.get('news_before_minutes')} / "
        f"+{profile.get('news_after_minutes')} minutes"
    )

    synthetic_profile = dict(profile)
    synthetic_profile.update({
        "expected_login": "777001",
        "expected_server": "GetLeveraged-Test",
        "expected_currency": "USD",
    })

    synthetic_activation = (
        evaluate_funded_account_activation(
            account=SimpleNamespace(
                login=777001,
                server="GetLeveraged-Test",
                currency="USD",
                balance=50000.0,
                equity=50000.0,
            ),
            enabled=True,
            profile_name=profile_name,
            profile=synthetic_profile,
            fail_closed=True,
        )
    )

    synthetic_activation_ok = bool(
        synthetic_activation.get("allowed")
    )

    print()
    print(
        "Synthetic $50K account activation: "
        f"{pass_fail(synthetic_activation_ok)}"
    )
    print(
        "Synthetic activation reason: "
        f"{synthetic_activation.get('reason')}"
    )

    synthetic_event = {
        "name": "Synthetic High Impact",
        "time": __import__("datetime").datetime.now(),
        "currency": "USD",
        "impact": "High",
        "source": "SYNTHETIC_TEST",
    }

    restricted_actions = (
        "OPEN_POSITION",
        "INCREASE_POSITION",
        "PLACE_PENDING_ORDER",
        "PARTIAL_CLOSE_POSITION",
        "FULL_CLOSE_POSITION",
        "MODIFY_PROTECTIVE_SL_TP",
    )

    synthetic_news_results = {}

    for action in restricted_actions:
        decision = evaluate_prop_firm_news_restriction(
            enabled=True,
            profile_name=profile_name,
            profile=synthetic_profile,
            calendar_snapshot={
                "available": True,
                "provider": "SYNTHETIC_TEST",
                "events": [synthetic_event],
                "error": None,
            },
            action=action,
            now=synthetic_event["time"],
            fail_closed=True,
        )

        synthetic_news_results[action] = (
            decision.get("allowed") is False
            and decision.get("snapshot", {}).get(
                "orders_sent"
            ) == 0
        )

    synthetic_news_ok = all(
        synthetic_news_results.values()
    )

    print()
    print(
        "Synthetic restricted-news actions: "
        f"{pass_fail(synthetic_news_ok)}"
    )

    for action, blocked_correctly in (
        synthetic_news_results.items()
    ):
        print(
            f"  {action}: "
            f"{pass_fail(blocked_correctly)}"
        )

    print()
    print("Checking economic-calendar feed...")

    calendar = get_prop_firm_news_calendar_snapshot()
    calendar_available = bool(
        calendar.get("available")
    )

    print(
        f"Calendar available: "
        f"{pass_fail(calendar_available)}"
    )
    print(
        f"Calendar provider: "
        f"{calendar.get('provider')}"
    )
    print(
        f"Calendar fetch status: "
        f"{calendar.get('fetch_ok')}"
    )
    print(
        f"Manual events loaded: "
        f"{calendar.get('manual_event_count')}"
    )
    print(
        f"Automatic events loaded: "
        f"{calendar.get('auto_event_count')}"
    )

    if calendar.get("error"):
        print(
            f"Calendar error: "
            f"{calendar.get('error')}"
        )

    print()
    print("Checking currently connected MT5 account...")

    mt5_initialized = mt5.initialize()

    if not mt5_initialized:
        print("MT5 connection: FAIL")
        print(f"MT5 error: {mt5.last_error()}")
        current_account_check_ok = False
    else:
        try:
            account_info = mt5.account_info()

            if account_info is None:
                print("MT5 account information: FAIL")
                print(f"MT5 error: {mt5.last_error()}")
                current_account_check_ok = False
            else:
                current_account_check_ok = True

                current_decision = (
                    evaluate_funded_account_activation(
                        account=account_info,
                        enabled=True,
                        profile_name=profile_name,
                        profile=profile,
                        fail_closed=True,
                    )
                )

                print("MT5 connection: PASS")
                print(
                    f"Connected login: "
                    f"{account_info.login}"
                )
                print(
                    f"Connected server: "
                    f"{account_info.server}"
                )
                print(
                    f"Connected currency: "
                    f"{account_info.currency}"
                )
                print(
                    f"Connected balance: "
                    f"{account_info.balance}"
                )
                print(
                    "Current account activation decision: "
                    f"{current_decision.get('reason')}"
                )

                if profile.get("expected_login") is None:
                    print(
                        "Funded identity binding: "
                        "PENDING — expected_login is not "
                        "configured yet"
                    )
                else:
                    print(
                        "Funded identity binding: CONFIGURED"
                    )

        finally:
            mt5.shutdown()

    ready = all((
        toggle_safe,
        profile_valid,
        synthetic_activation_ok,
        synthetic_news_ok,
        calendar_available,
        current_account_check_ok,
    ))

    print()
    print("=" * 72)

    if ready:
        print(
            "PRE-LINK STATUS: "
            "READY_TO_CONNECT_FUNDED_ACCOUNT"
        )
        print(
            "Next action: connect MT5 to the funded "
            "$50K account while safe mode remains OFF."
        )
        print("Orders sent: 0")
        return 0

    print("PRE-LINK STATUS: BLOCKED")
    print(
        "Resolve every FAIL above before connecting "
        "the funded account."
    )
    print("Orders sent: 0")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
