from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.strategies.strategy_psych_round_number_rejection import generate_signal  # noqa: E402


def build_rows_for_sell() -> pd.DataFrame:
    rows = []

    price = 4075.0

    for i in range(90):
        rows.append(
            {
                "time": f"2026-07-31T10:{i:02d}:00",
                "open": price,
                "high": price + 1.5,
                "low": price - 1.5,
                "close": price + 0.2,
                "tick_volume": 100,
            }
        )
        price += 0.01

    # Closed rejection candle around 4075 minor psych level.
    rows.append(
        {
            "time": "2026-07-31T11:31:00",
            "open": 4075.70,
            "high": 4077.20,
            "low": 4074.90,
            "close": 4074.60,
            "tick_volume": 180,
        }
    )

    # Current forming candle ignored by generate_signal.
    rows.append(
        {
            "time": "2026-07-31T11:32:00",
            "open": 4074.60,
            "high": 4074.80,
            "low": 4074.40,
            "close": 4074.70,
            "tick_volume": 50,
        }
    )

    return pd.DataFrame(rows)


def build_rows_for_buy() -> pd.DataFrame:
    rows = []

    price = 4075.0

    for i in range(90):
        rows.append(
            {
                "time": f"2026-07-31T12:{i:02d}:00",
                "open": price,
                "high": price + 1.5,
                "low": price - 1.5,
                "close": price - 0.2,
                "tick_volume": 100,
            }
        )
        price -= 0.01

    rows.append(
        {
            "time": "2026-07-31T13:31:00",
            "open": 4074.30,
            "high": 4075.10,
            "low": 4072.70,
            "close": 4075.45,
            "tick_volume": 180,
        }
    )

    rows.append(
        {
            "time": "2026-07-31T13:32:00",
            "open": 4075.45,
            "high": 4075.70,
            "low": 4075.20,
            "close": 4075.50,
            "tick_volume": 50,
        }
    )

    return pd.DataFrame(rows)


def main() -> None:
    sell = generate_signal(build_rows_for_sell())

    print("[SELL CASE]")
    print(sell)

    assert sell is not None
    assert sell["strategy"] == "PSYCH_ROUND_NUMBER_REJECTION"
    assert sell["signal"] == "SELL"
    assert sell["entry_model"] == "PSYCHOLOGICAL_LEVEL_REJECTION"
    assert sell["sl_reference"] > sell["entry_reference"]
    assert sell["tp_reference"] < sell["entry_reference"]
    assert sell["score"] >= 94
    assert sell["auto_trade_allowed"] is True

    buy = generate_signal(build_rows_for_buy())

    print("")
    print("[BUY CASE]")
    print(buy)

    assert buy is not None
    assert buy["strategy"] == "PSYCH_ROUND_NUMBER_REJECTION"
    assert buy["signal"] == "BUY"
    assert buy["sl_reference"] < buy["entry_reference"]
    assert buy["tp_reference"] > buy["entry_reference"]
    assert buy["score"] >= 94

    live_bot = ROOT / "src" / "live_bot.py"
    settings = ROOT / "config" / "settings.py"

    live_text = live_bot.read_text(encoding="utf-8")
    settings_text = settings.read_text(encoding="utf-8")

    assert "ENABLE_PSYCH_ROUND_NUMBER_REJECTION" in settings_text
    assert "psych_round_number_rejection_signal" in live_text
    assert '"PSYCH_ROUND_NUMBER_REJECTION"' in live_text
    assert "if not ENABLE_PSYCH_ROUND_NUMBER_REJECTION" in live_text

    print("")
    print("[PASS] Phase 6C psychological round number rejection is integrated into live_bot.")


if __name__ == "__main__":
    main()
