from __future__ import annotations

import runpy
from pathlib import Path
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


def main() -> int:
    profile_name = str(
        settings.PROP_FIRM_PROFILE
    ).strip().upper()

    profiles = settings.PROP_FIRM_PROFILES
    profile = (
        profiles.get(profile_name)
        if isinstance(profiles, dict)
        else None
    )

    print("=" * 72, flush=True)
    print(
        "PHASE 7A5 — HARD-BLOCKED FUNDED STARTUP DRY-RUN",
        flush=True,
    )
    print("=" * 72, flush=True)

    if not isinstance(profile, dict):
        print("[BLOCKED] Funded profile is missing", flush=True)
        return 1

    if not mt5.initialize():
        print(
            f"[BLOCKED] MT5 initialization failed: "
            f"{mt5.last_error()}",
            flush=True,
        )
        return 1

    try:
        account_info = mt5.account_info()

        if account_info is None:
            print(
                f"[BLOCKED] Account information unavailable: "
                f"{mt5.last_error()}",
                flush=True,
            )
            return 1

        activation = evaluate_funded_account_activation(
            account=account_info,
            enabled=True,
            profile_name=profile_name,
            profile=profile,
            fail_closed=True,
        )

        positions = mt5.positions_get()
        pending_orders = mt5.orders_get()

        if positions is None:
            print(
                f"[BLOCKED] positions_get failed: "
                f"{mt5.last_error()}",
                flush=True,
            )
            return 1

        if pending_orders is None:
            print(
                f"[BLOCKED] orders_get failed: "
                f"{mt5.last_error()}",
                flush=True,
            )
            return 1

        positions = list(positions)
        pending_orders = list(pending_orders)

        print(
            f"Connected login: {account_info.login}",
            flush=True,
        )
        print(
            f"Connected server: {account_info.server}",
            flush=True,
        )
        print(
            f"Connected balance: {account_info.balance}",
            flush=True,
        )
        print(
            f"Activation decision: "
            f"{activation.get('reason')}",
            flush=True,
        )
        print(
            f"Open positions: {len(positions)}",
            flush=True,
        )
        print(
            f"Pending orders: {len(pending_orders)}",
            flush=True,
        )

        if not activation.get("allowed", False):
            print(
                "[BLOCKED] Funded account identity failed",
                flush=True,
            )
            return 1

        if positions:
            print(
                "[BLOCKED] Close or remove all open positions "
                "before the startup dry-run",
                flush=True,
            )
            return 1

        if pending_orders:
            print(
                "[BLOCKED] Remove all pending orders before "
                "the startup dry-run",
                flush=True,
            )
            return 1

    finally:
        mt5.shutdown()

    calendar = get_prop_firm_news_calendar_snapshot()

    print(
        f"Calendar available: "
        f"{calendar.get('available')}",
        flush=True,
    )
    print(
        f"Calendar fetch status: "
        f"{calendar.get('fetch_ok')}",
        flush=True,
    )

    if not calendar.get("available"):
        print(
            f"[BLOCKED] Economic calendar unavailable: "
            f"{calendar.get('error')}",
            flush=True,
        )
        return 1

    # Runtime-only safety overrides. The settings file is not changed.
    settings.ENABLE_PROP_FIRM_SAFE_MODE = True
    settings.EXECUTION_MODE = "SIMULATION"
    settings.ALLOW_LIVE_TRADING = False

    original_order_send = mt5.order_send

    def blocked_order_send(request):
        print(
            "[PHASE 7A5 HARD BLOCK] "
            "mt5.order_send ATTEMPTED — request rejected",
            file=sys.stderr,
            flush=True,
        )
        print(
            f"[PHASE 7A5 HARD BLOCK] request={request}",
            file=sys.stderr,
            flush=True,
        )
        raise RuntimeError(
            "Phase 7A5 prohibits every MT5 order submission"
        )

    mt5.order_send = blocked_order_send

    print(
        "[PASS] Funded account identity verified",
        flush=True,
    )
    print(
        "[SAFE] ENABLE_PROP_FIRM_SAFE_MODE=True "
        "(runtime override)",
        flush=True,
    )
    print(
        "[SAFE] EXECUTION_MODE=SIMULATION "
        "(runtime override)",
        flush=True,
    )
    print(
        "[SAFE] ALLOW_LIVE_TRADING=False "
        "(runtime override)",
        flush=True,
    )
    print(
        "[SAFE] MT5 ORDER_SEND HARD BLOCK INSTALLED",
        flush=True,
    )
    print(
        "[START] Launching live-bot loop in protected dry-run mode",
        flush=True,
    )

    try:
        runpy.run_module(
            "src.live_bot",
            run_name="__main__",
        )
    finally:
        mt5.order_send = original_order_send

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
