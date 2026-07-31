from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.strategies.strategy_auto_structural_level_scalp import generate_signal  # noqa: E402


def build_intrabar_break_sell_df() -> pd.DataFrame:
    rows = []

    for i in range(80):
        rows.append(
            {
                "time": f"2026-07-31T16:{i % 60:02d}:00",
                "open": 4072.0,
                "high": 4073.0,
                "low": 4070.0 if i % 9 == 0 else 4070.2,
                "close": 4071.7,
                "tick_volume": 100,
            }
        )

    # Previous closed candle still above/supporting the line.
    rows.append(
        {
            "time": "2026-07-31T17:14:00",
            "open": 4071.2,
            "high": 4071.8,
            "low": 4070.1,
            "close": 4070.8,
            "tick_volume": 150,
        }
    )

    # Current forming candle: has just broken 0.50 below the line.
    # If the strategy waits for close, this would be ignored.
    rows.append(
        {
            "time": "2026-07-31T17:15:00",
            "open": 4070.8,
            "high": 4071.0,
            "low": 4069.4,
            "close": 4069.5,
            "tick_volume": 40,
        }
    )

    return pd.DataFrame(rows)


def main() -> None:
    signal = generate_signal(build_intrabar_break_sell_df())

    print("[INTRABAR BREAK SELL]")
    print(signal)

    assert signal is not None
    assert signal["strategy"] == "AUTO_STRUCTURAL_LEVEL_SCALP"
    assert signal["signal"] == "SELL"
    assert signal["entry_model"] == "SUPPORT_BREAK_HOLD_SCALP"
    assert round(signal["structural_level"] - signal["entry_reference"], 2) == 0.5
    assert signal["sl_reference"] > signal["entry_reference"]
    assert signal["tp_reference"] < signal["entry_reference"]

    settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    strategy_text = (ROOT / "src" / "strategies" / "strategy_auto_structural_level_scalp.py").read_text(encoding="utf-8")

    assert "ASLS_USE_INTRABAR_CANDLE = True" in settings_text
    assert "ASLS_USE_INTRABAR_CANDLE" in strategy_text
    assert "df.reset_index" in strategy_text

    print("")
    print("[PASS] Phase 6H structural level scalp uses intrabar/forming candle detection.")


if __name__ == "__main__":
    main()
