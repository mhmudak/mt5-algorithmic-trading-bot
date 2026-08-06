from __future__ import annotations

import argparse
from pathlib import Path
import sys

import MetaTrader5 as mt5


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import (
    PROP_FIRM_PROFILE,
    PROP_FIRM_PROFILES,
)
from src.funded_account_safe_mode import (
    evaluate_funded_account_activation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check funded-account activation identity without "
            "submitting any order."
        )
    )
    parser.add_argument(
        "--expected-login",
        default=None,
        help=(
            "Temporary expected-login override for diagnostic "
            "testing only."
        ),
    )
    parser.add_argument(
        "--expected-server",
        default=None,
        help="Temporary expected-server override.",
    )
    parser.add_argument(
        "--expected-currency",
        default=None,
        help="Temporary expected-currency override.",
    )
    parser.add_argument(
        "--balance-tolerance-pct",
        type=float,
        default=None,
        help="Temporary balance-tolerance override.",
    )
    args = parser.parse_args()

    profile_name = str(PROP_FIRM_PROFILE).strip().upper()
    configured_profile = PROP_FIRM_PROFILES.get(profile_name)

    if not isinstance(configured_profile, dict):
        print("STATUS: BLOCKED")
        print("Reason: funded_profile_missing")
        print(f"Profile: {profile_name}")
        print("Orders sent: 0")
        return 0

    profile = dict(configured_profile)

    if args.expected_login is not None:
        profile["expected_login"] = args.expected_login

    if args.expected_server is not None:
        profile["expected_server"] = args.expected_server

    if args.expected_currency is not None:
        profile["expected_currency"] = args.expected_currency

    if args.balance_tolerance_pct is not None:
        profile["activation_balance_tolerance_pct"] = (
            args.balance_tolerance_pct
        )

    if not mt5.initialize():
        print("STATUS: BLOCKED")
        print("Reason: mt5_initialization_failed")
        print(f"MT5 error: {mt5.last_error()}")
        print("Orders sent: 0")
        return 0

    try:
        account = mt5.account_info()

        decision = evaluate_funded_account_activation(
            account=account,
            enabled=True,
            profile_name=profile_name,
            profile=profile,
            fail_closed=True,
        )

        snapshot = decision.get("snapshot") or {}
        status = (
            "ALLOWED"
            if decision.get("allowed")
            else "BLOCKED"
        )

        print(f"STATUS: {status}")
        print(f"Reason: {decision.get('reason')}")
        print(f"Profile: {profile_name}")
        print(
            "Connected login: "
            f"{snapshot.get('connected_login')}"
        )
        print(
            "Connected server: "
            f"{snapshot.get('connected_server')}"
        )
        print(
            "Connected currency: "
            f"{snapshot.get('connected_currency')}"
        )
        print(
            "Connected balance: "
            f"{snapshot.get('connected_balance')}"
        )
        print(
            "Expected login: "
            f"{snapshot.get('expected_login')}"
        )
        print(
            "Expected server: "
            f"{snapshot.get('expected_server')}"
        )
        print(
            "Expected balance range: "
            f"{snapshot.get('minimum_allowed_balance')} - "
            f"{snapshot.get('maximum_allowed_balance')}"
        )
        print("Orders sent: 0")

        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
