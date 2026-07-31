from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.strategies.strategy_auto_structural_level_scalp import generate_signal  # noqa: E402


def build_bounce_buy_df() -> pd.DataFrame:
    rows = []
    price = 4076.0

    for i in range(80):
        if i % 12 == 0:
            low = 4067.9
            close = 4071.2
            open_price = 4069.1
            high = 4072.4
        else:
            close = price + ((i % 5) - 2) * 0.18
            open_price = close + 0.10
            high = close + 1.20
            low = max(4068.2, close - 1.30)

        rows.append(
            {
                "time": f"2026-07-31T16:{i % 60:02d}:00",
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "tick_volume": 120,
            }
        )

    rows.append(
        {
            "time": "2026-07-31T17:01:00",
            "open": 4067.70,
            "high": 4068.55,
            "low": 4067.20,
            "close": 4068.30,
            "tick_volume": 260,
        }
    )

    return pd.DataFrame(rows)


def build_break_sell_df() -> pd.DataFrame:
    rows = []

    for i in range(80):
        if i % 13 == 0:
            low = 4070.05
            close = 4072.20
            open_price = 4071.10
            high = 4073.40
        else:
            close = 4074.0 + ((i % 4) - 1.5) * 0.25
            open_price = close + 0.10
            high = close + 1.10
            low = max(4070.15, close - 1.20)

        rows.append(
            {
                "time": f"2026-07-31T16:{i % 60:02d}:00",
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "tick_volume": 120,
            }
        )

    rows.append(
        {
            "time": "2026-07-31T17:14:00",
            "open": 4071.20,
            "high": 4071.60,
            "low": 4069.30,
            "close": 4069.55,
            "tick_volume": 320,
        }
    )

    return pd.DataFrame(rows)


def main() -> None:
    bounce = generate_signal(build_bounce_buy_df())

    print("[BOUNCE BUY]")
    print(bounce)

    assert bounce is not None
    assert bounce["strategy"] == "AUTO_STRUCTURAL_LEVEL_SCALP"
    assert bounce["signal"] == "BUY"
    assert bounce["entry_model"] == "SUPPORT_BOUNCE_SCALP"
    assert bounce["structural_level_type"] == "SUPPORT"
    assert bounce["entry_reference"] == bounce["structural_level"]
    assert bounce["sl_reference"] < bounce["entry_reference"]
    assert bounce["tp_reference"] > bounce["entry_reference"]
    assert bounce["rr"] >= 1.0
    assert bounce["structural_level_confirmation"] in {
        "STRUCTURAL_SWING_CONFIRMED",
        "REPEATED_TOUCH_CONFIRMED",
    }

    brk = generate_signal(build_break_sell_df())

    print("")
    print("[BREAK SELL]")
    print(brk)

    assert brk is not None
    assert brk["strategy"] == "AUTO_STRUCTURAL_LEVEL_SCALP"
    assert brk["signal"] == "SELL"
    assert brk["entry_model"] == "SUPPORT_BREAK_HOLD_SCALP"
    assert brk["structural_level_type"] == "SUPPORT"
    assert round(brk["structural_level"] - brk["entry_reference"], 2) == 0.5
    assert brk["sl_reference"] > brk["entry_reference"]
    assert brk["tp_reference"] < brk["entry_reference"]
    assert brk["rr"] >= 1.0

    live_text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    risk_text = (ROOT / "src" / "risk.py").read_text(encoding="utf-8")

    assert "ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP" in settings_text
    assert "auto_structural_level_scalp_signal" in live_text
    assert '"AUTO_STRUCTURAL_LEVEL_SCALP"' in live_text
    assert '"AUTO_STRUCTURAL_LEVEL_SCALP"' in risk_text

    print("")
    print("[PASS] Phase 6G auto structural level scalp detects bounce and break-hold scalps.")


if __name__ == "__main__":
    main()
