import argparse
import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.confirmation_engine import run_universal_confirmation
from src.confirmation_risk_notifier import (
    build_confirmation_risk_alert,
    maybe_notify_confirmation_risk,
    resolve_telegram_sender,
    get_telegram_sender_diagnostics,
)


def build_test_dataframe():
    rows = []
    base = 2400.0

    for i in range(40):
        rows.append({
            "open": base + ((i % 5) - 2) * 0.4,
            "high": base + 5 + (i % 3) * 0.2,
            "low": base - 5 - (i % 2) * 0.2,
            "close": base + ((i % 7) - 3) * 0.35,
            "atr_14": 2.5,
            "ema_20": base,
            "tick_volume": 100 + (i % 8) * 10,
            "real_volume": 0,
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Test confirmation-engine Telegram risk alerts."
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send one Telegram alert. Without this flag, dry-run only.",
    )

    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Print full Telegram sender diagnostics.",
    )

    args = parser.parse_args()

    module_name, function_name, _ = resolve_telegram_sender()

    print("telegram_sender_found =", bool(module_name and function_name))
    print("telegram_sender =", f"{module_name}.{function_name}" if module_name else None)

    if args.diagnostics:
        diagnostics = get_telegram_sender_diagnostics()
        print(json.dumps(diagnostics, indent=2, ensure_ascii=False))

    df = build_test_dataframe()

    signal_data = {
        "setup_id": "TEST-RISK-TELEGRAM-001",
        "strategy": "RANGE_SWEEP_RECLAIM",
        "signal": "BUY",
        "entry_model": "SWEEP_RECLAIM",
        "market_condition": "RANGING",
        "session": "NEWYORK_OPEN",
    }

    trade_plan = {
        "setup_id": "TEST-RISK-TELEGRAM-001",
        "strategy": "RANGE_SWEEP_RECLAIM",
        "signal": "BUY",
        "entry_price": 2397.0,
        "stop_loss": 2392.0,
        "take_profit": 2406.0,
        "rr": 1.8,
    }

    report = run_universal_confirmation(
        signal_data=signal_data,
        trade_plan=trade_plan,
        df=df,
        tick=None,
        session="NEWYORK_OPEN",
        market_condition="RANGING",
        orderflow_snapshot=None,
        min_rr=1.2,
        max_spread=0.5,
        enforce_required=False,
    )

    alert = build_confirmation_risk_alert(
        report=report,
        signal_data=signal_data,
        trade_plan=trade_plan,
        setup_source_bucket="SMOKE_TEST",
    )

    print("should_notify =", alert.get("should_notify"))
    print("module =", alert.get("module"))
    print()
    print(alert.get("message"))

    result = maybe_notify_confirmation_risk(
        report=report,
        signal_data=signal_data,
        trade_plan=trade_plan,
        setup_source_bucket="SMOKE_TEST",
        dry_run=not args.send,
    )

    print()
    print("send_mode =", "REAL_SEND" if args.send else "DRY_RUN")
    print("result =", result)

    if args.send and not result:
        raise SystemExit(
            "Telegram send was requested but failed. Run with --diagnostics and check sender module/function."
        )


if __name__ == "__main__":
    main()
