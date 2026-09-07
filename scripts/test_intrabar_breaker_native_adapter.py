from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategies.strategy_breaker_block import generate_signal


def bullish_breaker_intrabar_df() -> pd.DataFrame:
    rows = []

    for i in range(41):
        base = 99.6 + ((i % 3) - 1) * 0.1
        rows.append(
            {
                "open": base,
                "high": base + 0.5,
                "low": base - 0.5,
                "close": base + 0.1,
                "atr_14": 4.0,
                "ema_20": 99.5,
            }
        )

    # Native zone / break / retest followed by the current forming candle.
    rows.extend(
        [
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "atr_14": 4.0,
                "ema_20": 99.5,
            },
            {
                "open": 100.4,
                "high": 102.5,
                "low": 100.3,
                "close": 102.0,
                "atr_14": 4.0,
                "ema_20": 99.5,
            },
            {
                "open": 102.0,
                "high": 102.2,
                "low": 100.8,
                "close": 101.5,
                "atr_14": 4.0,
                "ema_20": 99.5,
            },
            {
                "open": 101.2,
                "high": 102.5,
                "low": 100.9,
                "close": 102.2,
                "atr_14": 4.0,
                "ema_20": 99.5,
            },
        ]
    )

    return pd.DataFrame(rows)


def test_native_breaker_accepts_current_forming_candle_via_sentinel():
    df = bullish_breaker_intrabar_df()
    sentinel = df.iloc[[-1]].copy()
    native_view = pd.concat([df, sentinel], ignore_index=True)

    signal = generate_signal(native_view)

    assert signal is not None
    assert signal["strategy"] == "BREAKER_BLOCK"
    assert signal["signal"] == "BUY"
    assert signal["entry_model"] == "BULLISH_BREAKER_RETEST"
    assert signal["sl_reference"] < signal["entry_reference"]
    assert signal["tp_reference"] > signal["entry_reference"]
    assert signal["momentum"] == "bullish_breaker_retest_reclaim"


def test_live_adapter_delegates_to_native_breaker_logic():
    source = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8-sig")

    start = source.index("def build_native_breaker_intrabar_signal_data(")
    end = source.index("def build_intrabar_price_event_signal_data(", start)
    section = source[start:end]

    assert "generate_signal as _native_breaker_signal" in section
    assert "pd.concat([df, sentinel], ignore_index=True)" in section
    assert "native = _native_breaker_signal(breaker_df)" in section
    assert '"intrabar_trigger": "NATIVE_BREAKER_RETEST"' in section
    assert '"sl_reference": round(sl_reference, 2)' in section
    assert '"tp_reference": round(tp_reference, 2)' in section
    assert 'native_max_risk = float(native.get("max_allowed_risk"))' in section
    assert "stop_distance > native_max_risk" in section


if __name__ == "__main__":
    test_native_breaker_accepts_current_forming_candle_via_sentinel()
    test_live_adapter_delegates_to_native_breaker_logic()
    print("[PASS] Native BREAKER_BLOCK intrabar adapter regression passed.")
