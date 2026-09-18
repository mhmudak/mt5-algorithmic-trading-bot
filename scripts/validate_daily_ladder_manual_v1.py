from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

from config import settings
from src.daily_ladder_provider import (
    DailyLadderValidationError,
    derive_broker_date_from_current_d1_time,
    load_manual_avo_ladder,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the current manual Avo daily ladder for DLLB."
    )
    parser.add_argument(
        "--path",
        default=getattr(
            settings,
            "DAILY_LEVEL_LADDER_MANUAL_PATH",
            "config/daily_ladder_manual.json",
        ),
    )
    parser.add_argument(
        "--symbol",
        default=getattr(settings, "SYMBOL", "XAUUSD"),
    )
    parser.add_argument(
        "--broker-date",
        help="YYYY-MM-DD override. If omitted, derive it from the current MT5 D1 bar.",
    )
    return parser.parse_args()


def _current_broker_date_from_mt5(symbol: str) -> date:
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        raise DailyLadderValidationError(
            f"MetaTrader5 import failed: {exc}"
        ) from exc

    if not mt5.initialize():
        raise DailyLadderValidationError(
            f"MT5 initialize failed: {mt5.last_error()}"
        )

    try:
        rates = mt5.copy_rates_from_pos(
            symbol,
            mt5.TIMEFRAME_D1,
            0,
            2,
        )
        if rates is None or len(rates) < 1:
            raise DailyLadderValidationError(
                f"unable to read current D1 bar for {symbol}"
            )
        return derive_broker_date_from_current_d1_time(
            rates[-1]["time"]
        )
    finally:
        mt5.shutdown()


def main() -> int:
    args = _parse_args()
    try:
        expected_date = (
            date.fromisoformat(args.broker_date)
            if args.broker_date
            else _current_broker_date_from_mt5(args.symbol)
        )
        ladder = load_manual_avo_ladder(
            Path(args.path),
            expected_symbol=args.symbol,
            expected_broker_date=expected_date,
        )
    except (DailyLadderValidationError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS: manual daily ladder is valid")
    print(f"symbol={ladder.symbol}")
    print(f"broker_date={ladder.broker_date.isoformat()}")
    print(f"pivot={ladder.pivot}")
    print(f"upper_count={len(ladder.upper)}")
    print(f"lower_count={len(ladder.lower)}")
    print(f"source={args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
