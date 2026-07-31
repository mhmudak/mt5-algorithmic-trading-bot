from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.strategies.strategy_volatility_compression_breakout import (  # noqa: E402
    VolatilityCompressionBreakoutConfig,
    evaluate_volatility_compression_breakout,
)


def build_bullish_case() -> list[dict]:
    candles = []

    price = 4070.0

    for i in range(30):
        price += 0.10
        candles.append(
            {
                "time": f"2026-07-31T10:{i:02d}:00",
                "open": price - 0.35,
                "high": price + 1.10,
                "low": price - 1.10,
                "close": price + 0.35,
            }
        )

    for i in range(8):
        candles.append(
            {
                "time": f"2026-07-31T10:{30+i:02d}:00",
                "open": 4073.00,
                "high": 4073.35,
                "low": 4072.90,
                "close": 4073.10,
            }
        )

    candles.append(
        {
            "time": "2026-07-31T10:39:00",
            "open": 4073.10,
            "high": 4075.20,
            "low": 4073.00,
            "close": 4074.35,
        }
    )

    return candles


def build_bearish_case() -> list[dict]:
    candles = []

    price = 4085.0

    for i in range(30):
        price -= 0.10
        candles.append(
            {
                "time": f"2026-07-31T11:{i:02d}:00",
                "open": price + 0.35,
                "high": price + 1.10,
                "low": price - 1.10,
                "close": price - 0.35,
            }
        )

    for i in range(8):
        candles.append(
            {
                "time": f"2026-07-31T11:{30+i:02d}:00",
                "open": 4082.00,
                "high": 4082.10,
                "low": 4081.65,
                "close": 4081.90,
            }
        )

    candles.append(
        {
            "time": "2026-07-31T11:39:00",
            "open": 4081.90,
            "high": 4082.00,
            "low": 4079.70,
            "close": 4080.55,
        }
    )

    return candles


def main() -> None:
    cfg = VolatilityCompressionBreakoutConfig(
        max_sl_distance=7.0,
        min_rr=2.0,
        target_rr=2.2,
    )

    buy_signal = evaluate_volatility_compression_breakout(build_bullish_case(), config=cfg)

    print("[BUY CASE]")
    print(json.dumps(buy_signal, indent=2))

    assert buy_signal["valid"] is True
    assert buy_signal["signal"] == "BUY"
    assert buy_signal["family"] == "VOLATILITY_COMPRESSION_BREAKOUT"
    assert buy_signal["funded_suitable"] is True
    assert buy_signal["auto_trade_allowed"] is False
    assert buy_signal["decision_impact"] == "NONE"

    sell_signal = evaluate_volatility_compression_breakout(build_bearish_case(), config=cfg)

    print("")
    print("[SELL CASE]")
    print(json.dumps(sell_signal, indent=2))

    assert sell_signal["valid"] is True
    assert sell_signal["signal"] == "SELL"
    assert sell_signal["family"] == "VOLATILITY_COMPRESSION_BREAKOUT"
    assert sell_signal["funded_suitable"] is True

    no_signal_candles = build_bullish_case()
    no_signal_candles[-1]["close"] = 4073.20

    no_signal = evaluate_volatility_compression_breakout(no_signal_candles, config=cfg)

    print("")
    print("[NO SIGNAL CASE]")
    print(json.dumps(no_signal, indent=2))

    assert no_signal["valid"] is False
    assert no_signal["reason"] in {
        "breakout_body_too_small",
        "no_close_outside_compression",
    }

    print("")
    print("[PASS] Phase 6A volatility compression breakout strategy works.")


if __name__ == "__main__":
    main()
