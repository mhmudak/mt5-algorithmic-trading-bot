from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.strategies.strategy_session_exhaustion_reversal import generate_signal  # noqa: E402


def build_sell_case() -> pd.DataFrame:
    rows = []
    price = 4050.0

    for i in range(50):
        price += 0.35
        rows.append(
            {
                "time": f"2026-07-31T10:{i:02d}:00",
                "open": price - 0.15,
                "high": price + 0.75,
                "low": price - 0.75,
                "close": price,
                "tick_volume": 100,
            }
        )

    rows.append(
        {
            "time": "2026-07-31T11:01:00",
            "open": 4068.80,
            "high": 4071.40,
            "low": 4067.30,
            "close": 4067.70,
            "tick_volume": 190,
        }
    )

    rows.append(
        {
            "time": "2026-07-31T11:02:00",
            "open": 4067.70,
            "high": 4068.00,
            "low": 4067.20,
            "close": 4067.90,
            "tick_volume": 50,
        }
    )

    return pd.DataFrame(rows)


def build_buy_case() -> pd.DataFrame:
    rows = []
    price = 4070.0

    for i in range(50):
        price -= 0.35
        rows.append(
            {
                "time": f"2026-07-31T12:{i:02d}:00",
                "open": price + 0.15,
                "high": price + 0.75,
                "low": price - 0.75,
                "close": price,
                "tick_volume": 100,
            }
        )

    rows.append(
        {
            "time": "2026-07-31T13:01:00",
            "open": 4051.20,
            "high": 4052.90,
            "low": 4048.40,
            "close": 4052.30,
            "tick_volume": 190,
        }
    )

    rows.append(
        {
            "time": "2026-07-31T13:02:00",
            "open": 4052.30,
            "high": 4052.60,
            "low": 4052.00,
            "close": 4052.40,
            "tick_volume": 50,
        }
    )

    return pd.DataFrame(rows)


def main() -> None:
    sell = generate_signal(build_sell_case())

    print("[SELL CASE]")
    print(sell)

    assert sell is not None
    assert sell["strategy"] == "SESSION_EXHAUSTION_REVERSAL"
    assert sell["signal"] == "SELL"
    assert sell["entry_model"] == "SESSION_EXTENSION_EXHAUSTION_REVERSAL"
    assert sell["sl_reference"] > sell["entry_reference"]
    assert sell["tp_reference"] < sell["entry_reference"]
    assert sell["score"] >= 94
    assert sell["auto_trade_allowed"] is True
    assert sell["execution_mode"] == "GLOBAL_RUNTIME_CONTROLLED"

    buy = generate_signal(build_buy_case())

    print("")
    print("[BUY CASE]")
    print(buy)

    assert buy is not None
    assert buy["strategy"] == "SESSION_EXHAUSTION_REVERSAL"
    assert buy["signal"] == "BUY"
    assert buy["sl_reference"] < buy["entry_reference"]
    assert buy["tp_reference"] > buy["entry_reference"]
    assert buy["score"] >= 94

    live_bot = ROOT / "src" / "live_bot.py"
    settings = ROOT / "config" / "settings.py"

    live_text = live_bot.read_text(encoding="utf-8")
    settings_text = settings.read_text(encoding="utf-8")

    assert "ENABLE_SESSION_EXHAUSTION_REVERSAL" in settings_text
    assert "session_exhaustion_reversal_signal" in live_text
    assert '"SESSION_EXHAUSTION_REVERSAL"' in live_text
    assert "if not ENABLE_SESSION_EXHAUSTION_REVERSAL" in live_text

    print("")
    print("[PASS] Phase 6D session exhaustion reversal is integrated into live_bot.")


if __name__ == "__main__":
    main()
